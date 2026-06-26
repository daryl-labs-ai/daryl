"""Session binder (P7) — link sessions to files/commits with confidence + evidence.

The product leap: chats and code have no native link, so PRL infers
``references`` edges between a ``SessionNode`` and the ``FileNode`` /
``CommitNode`` of a project — every edge carrying a ``confidence`` score and an
``evidence`` dict (never a silent link).

V1 signals (decision: ADR §10 — metadata only; ``content_hash`` matching is
deferred until collectors capture full transcripts / code blocks):

* **path citation** — a file's relative path appears in the session title/preview
  → confidence 0.75 (``method="path"``).
* **filename citation** — a file's basename appears → 0.60 (``method="filename"``).
* **commit window** — a commit's timestamp falls within the session's time window
  (± margin) → 0.80, edge session→commit (``method="commit_window"``).
* **mtime window** — a file's mtime falls within the session window → 0.40, weak
  fallback (``method="mtime_window"``).

Pure function: no DSM, no RR, no Storage. Edges are deduped per (session, target)
keeping the highest-confidence signal, then filtered by ``min_confidence``.
"""

from __future__ import annotations

from ..index.mapper import ProjectMap
from ..types import Edge, SessionNode

_CONF_PATH = 0.75
_CONF_FILENAME = 0.60
_CONF_COMMIT_WINDOW = 0.80
_CONF_MTIME_WINDOW = 0.40

# Sessions usually commit slightly after the last message; widen the window a bit.
_WINDOW_MARGIN_MS = 15 * 60 * 1000  # 15 minutes
_MIN_BASENAME_LEN = 4  # avoid noisy matches on very short names


def _session_window(session: SessionNode) -> tuple[int, int] | None:
    """Return (lo, hi) ms window for a session, or None if it has no usable time."""
    if not session.started_ms or session.started_ms <= 0:
        return None
    lo = session.started_ms
    hi = session.ended_ms if session.ended_ms else session.started_ms
    return (lo - _WINDOW_MARGIN_MS, hi + _WINDOW_MARGIN_MS)


def _haystack(session: SessionNode) -> str:
    return f"{session.title or ''} {session.text_preview or ''}".lower()


def _citation_signal(session: SessionNode, file_path: str) -> tuple[float, str, str] | None:
    """Return (confidence, method, matched) if the session cites the file, else None."""
    hay = _haystack(session)
    # A real relative path (contains "/") is a high-confidence citation. A bare
    # filename (no directory) is medium-confidence and must clear a min length to
    # avoid noisy matches on very short names.
    if "/" in file_path and file_path.lower() in hay:
        return (_CONF_PATH, "path", file_path)
    basename = file_path.rsplit("/", 1)[-1]
    if len(basename) >= _MIN_BASENAME_LEN and basename.lower() in hay:
        return (_CONF_FILENAME, "filename", basename)
    return None


def bind_sessions(
    sessions: list[SessionNode],
    pmap: ProjectMap,
    *,
    min_confidence: float = 0.40,
) -> list[Edge]:
    """Infer ``references`` edges from *sessions* to *pmap*'s files/commits.

    Each edge: src_id = session_id, dst_id = file.content_hash | commit.sha,
    edge_type = "references", with ``confidence`` and ``evidence={'method': ...}``.
    Deduped per (session_id, dst_id) keeping the strongest signal; filtered to
    ``confidence >= min_confidence``.
    """
    best: dict[tuple[str, str], Edge] = {}

    def _offer(session_id: str, dst_id: str, conf: float, evidence: dict[str, str]) -> None:
        key = (session_id, dst_id)
        existing = best.get(key)
        if existing is None or conf > existing.confidence:
            best[key] = Edge(
                edge_type="references",
                src_id=session_id,
                dst_id=dst_id,
                confidence=conf,
                evidence=evidence,
            )

    for session in sessions:
        sid = session.session_id
        window = _session_window(session)

        # file signals: citation (strong) and mtime window (weak fallback)
        for f in pmap.files:
            cite = _citation_signal(session, f.path)
            if cite is not None:
                conf, method, matched = cite
                _offer(sid, f.content_hash, conf, {"method": method, "matched": matched})
            if window is not None and window[0] <= f.mtime_ms <= window[1]:
                _offer(
                    sid,
                    f.content_hash,
                    _CONF_MTIME_WINDOW,
                    {"method": "mtime_window", "session_window": f"{window[0]}-{window[1]}"},
                )

        # commit signal: commit timestamp inside the session window
        if window is not None:
            for c in pmap.commits:
                if window[0] <= c.ts_ms <= window[1]:
                    _offer(
                        sid,
                        c.sha,
                        _CONF_COMMIT_WINDOW,
                        {"method": "commit_window", "commit_ts": str(c.ts_ms)},
                    )

    return [e for e in best.values() if e.confidence >= min_confidence]
