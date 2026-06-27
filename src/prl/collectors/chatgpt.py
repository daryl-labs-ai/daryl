"""ChatGPT collector (P6) — parse a ChatGPT backup export into SessionNodes.

Target format (documented in the user's ChatGPT-Business-Migration-Backup,
data-export/README.md). The export JSON is a map of conversations:

    conversations[<id>] = {
        "title": str,
        "gizmo_id": str | None,         # ChatGPT "project"/GPT id (kept for P7)
        "messages": [{"role": str, "text": str, "t": float}, ...],
    }

Tolerated shapes: a top-level ``{"conversations": {...}}`` wrapper, or a bare
``{<id>: conv}`` map. ``t`` is a unix timestamp in seconds (OpenAI create_time);
missing/None values are handled. This collector only *produces* SessionNodes —
no DSM/RR access. Binding a chat to local files/commits is the binder's job (P7);
``gizmo_id`` is intentionally not consumed in V1 (see ROADMAP P6 note).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..types import SessionNode
from .base import CollectorError, register

_PREVIEW_MAX = 200


def _ms(t: Any) -> int | None:
    """Convert a unix-seconds timestamp to integer milliseconds. None on junk."""
    try:
        return int(float(t) * 1000)
    except (TypeError, ValueError):
        return None


def _sorted_parts(conv: dict) -> tuple[list[int], list[str]]:
    """Return (timestamps_ms, ``"role: text"`` parts) sorted chronologically.

    Shared by the SessionNode preview and the full-text accessor so both see the
    same ordered transcript — the preview is just its first ``_PREVIEW_MAX`` chars.
    """
    raw = conv.get("messages") or []
    # (ms, message) pairs; sort chronologically (messages may arrive unordered),
    # with timestamp-less messages kept last in original order.
    pairs = [(_ms(m.get("t")), m) for m in raw if isinstance(m, dict)]
    pairs.sort(key=lambda p: (p[0] is None, p[0] if p[0] is not None else 0))

    times = [ms for ms, _ in pairs if ms is not None]
    parts: list[str] = []
    for _, m in pairs:
        text = str(m.get("text", "")).strip()
        if not text:
            continue
        role = str(m.get("role", "")).strip() or "?"
        parts.append(f"{role}: {text}")
    return times, parts


def _full_text(conv: dict) -> str:
    """Full transcript for the passage/chunk source (R1), in the **canonical
    retrieval format** (F2): raw message texts only — no ``role:`` prefixes, no
    ``" | "`` separators — joined by a single space, in original message order.

    This deliberately mirrors the eval harness's ``_full_texts`` *exactly* so the
    measured policy (``chunk_chars=500`` etc.) was tuned on the same text the
    production chunk index now embeds. The role lives in metadata, not in the
    embedded text. The P6 ``text_preview`` is independent and unchanged.
    """
    return " ".join(
        str(m.get("text", "")).strip()
        for m in (conv.get("messages") or [])
        if isinstance(m, dict) and str(m.get("text", "")).strip()
    )


def _to_session_node(conv_id: str, conv: dict) -> SessionNode:
    times, parts = _sorted_parts(conv)
    preview = " | ".join(parts)[:_PREVIEW_MAX]  # P6 schema: preview-only, unchanged

    return SessionNode(
        session_id=str(conv_id),
        tool="chatgpt",
        title=conv.get("title") or None,
        started_ms=times[0] if times else 0,   # first message timestamp (sorted)
        ended_ms=times[-1] if times else None,  # last message timestamp (sorted)
        text_preview=preview,
        project_id=None,  # bound in P7
    )


@register
class ChatGPTCollector:
    """Parses a ChatGPT export file into SessionNodes."""

    name = "chatgpt"

    def __init__(self, export_path: str | Path):
        self._path = Path(export_path)

    def _conversations(self) -> dict:
        """Load and return the ``{conv_id: conv}`` map, tolerating the real-export
        shapes: a ``{"conversations": {...}}`` wrapper, the checkpoint
        ``{"loose_conversations": {...}}`` wrapper, or a bare ``{<id>: conv}`` map.
        Shared by :meth:`collect` and :meth:`full_texts`."""
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CollectorError(f"cannot read ChatGPT export at {self._path}: {exc}") from exc
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise CollectorError(f"ChatGPT export is not valid JSON: {exc}") from exc

        if isinstance(data, dict) and isinstance(data.get("conversations"), dict):
            return data["conversations"]
        if isinstance(data, dict) and isinstance(data.get("loose_conversations"), dict):
            return data["loose_conversations"]
        if isinstance(data, dict):
            return data
        raise CollectorError("ChatGPT export must be a JSON object of conversations")

    def collect(self) -> list[SessionNode]:
        nodes: list[SessionNode] = []
        for conv_id, conv in self._conversations().items():
            if not isinstance(conv, dict):
                continue  # skip malformed entry defensively
            nodes.append(_to_session_node(conv_id, conv))
        return nodes

    def full_texts(self) -> dict[str, str]:
        """``session_id -> full transcript`` (Retrieval v2 / R1 ``FullTextSource``).

        The passage index consumes this; ``SessionNode`` stays preview-only. Only
        non-empty transcripts are returned."""
        out: dict[str, str] = {}
        for conv_id, conv in self._conversations().items():
            if not isinstance(conv, dict):
                continue
            text = _full_text(conv)
            if text:
                out[str(conv_id)] = text
        return out
