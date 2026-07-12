"""ChatGPT corpus import (M1 · D2a) — normalized JSON → turn-level observation acts.

Ratified rules (MOHAMED, 2026-07-07 — a NEW canonical build, not a port of the C2-b
staging seeder):

- **subject = slug(title)** (fallback to the conversation id, then ``"untitled"``).
- **each turn → one Observation Knowledge Act** (``mode="observation"``); the object's
  standing then *derives* PROPOSED because nothing is resolved. "Every page PROPOSED" is
  emergent, not a stored flag.
- **attribution:** ``agent_id`` = the bare turn role (``user`` / ``assistant`` / ``tool``,
  or the role as given); the execution **carrier-of-record** names the chatgpt-export
  provenance. ``agent_id`` is never derived from the carrier (ADR-0009).
- **verbatim, with truncation reported:** the answer is stored verbatim up to
  :data:`MAX_ANSWER_CHARS` (8000); a longer turn gets an explicit truncation marker and is
  counted in the import report as evidence. The ceiling is revisable *only from user
  evidence* — it is a ratified parameter, not a re-explorable knob (so: no CLI flag).

Reuses proven primitives only: the normalized-export shapes the ``ChatGPTCollector``
tolerates, :meth:`ConsultationAdapter.to_act` (the observation-act producer), and
:meth:`PRLStore.commit_act` (the certified, hash-chained write). Raw ``.zip`` normalization
(PR-2b) and the boundary act / source map (PR-2c) are deliberately out of this slice.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .chatgpt_normalize import NormalizationReport, resolve_conversations
from .collectors import ConsultationAdapter
from .config import PRLConfig
from .exceptions import PRLError
from .store import new_run_id, open_store
from .types import Carrier, ConsultationNode, SessionNode

# Import-manifest marker: a reserved SessionNode.session_id prefix so the source-map read
# tells the per-run manifest apart from per-conversation boundary sessions (both prl.session).
_MANIFEST_PREFIX = "daryl-import-manifest"

# Ratified ceiling — revisable only from user evidence (not a knob, hence no CLI flag).
MAX_ANSWER_CHARS = 8000
_PREVIEW_MAX = 200  # boundary-act text_preview cap
_TRUNCATION_MARKER = "\n\n[…truncated by daryl-import: {omitted} chars omitted]"

# One uniform carrier-of-record: this act was recorded from a ChatGPT export via
# daryl-import. The role distinction lives in ``agent_id`` (ratified Q2), never here.
_IMPORT_CARRIER = Carrier(provider="chatgpt", model="export", adapter="daryl-import v1")
_PRODUCER = "chatgpt-export (daryl-import v1)"  # legacy display projection (ADR-0009)

_SUGGEST_MAX = 5
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase, collapse non-alphanumeric runs to a single hyphen, strip the ends.
    Empty in → empty out (the caller supplies the fallback)."""
    return _SLUG_RE.sub("-", str(text).strip().lower()).strip("-")


def _id6(conv_id: str) -> str:
    """First 6 hex chars of the conversation id (hyphens/noise stripped). This is the
    disambiguator that guarantees one subject per conversation."""
    hexchars = re.sub(r"[^0-9a-f]", "", str(conv_id).lower())
    return (hexchars or "000000")[:6]


def _subject_id(title: str, conv_id: str) -> str:
    """The canonical M1 import subject key (ratified 2026-07-08): ``slug(title).<id6>``.
    **Every conversation maps to exactly one subject** — the ``.<id6>`` suffix is *always*
    appended (uniform, never collision-only), so distinct conversations that share a title
    (e.g. "New chat", "Traduction en turc") are never conflated. Empty title → ``untitled``
    base, still suffixed."""
    base = slugify(title) or "untitled"
    return f"{base}.{_id6(conv_id)}"


def _ms(t: Any) -> int | None:
    """Unix-seconds timestamp → integer milliseconds; None on junk (mirrors the collector)."""
    try:
        return int(float(t) * 1000)
    except (TypeError, ValueError):
        return None


def _sorted_turns(conv: dict) -> list[tuple[str, str]]:
    """``(role, text)`` pairs, chronological, non-empty text only — the same ordering the
    collector uses for previews (timestamp-less messages kept last, original order)."""
    raw = conv.get("messages") or []
    pairs = [(_ms(m.get("t")), m) for m in raw if isinstance(m, dict)]
    pairs.sort(key=lambda p: (p[0] is None, p[0] if p[0] is not None else 0))
    turns: list[tuple[str, str]] = []
    for _, m in pairs:
        text = str(m.get("text", "")).strip()
        if not text:
            continue
        role = str(m.get("role", "")).strip() or "unknown"
        turns.append((role, text))
    return turns


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_ANSWER_CHARS:
        return text, False
    omitted = len(text) - MAX_ANSWER_CHARS
    return text[:MAX_ANSWER_CHARS] + _TRUNCATION_MARKER.format(omitted=omitted), True


def build_turn_act(
    adapter: ConsultationAdapter,
    *,
    subject_id: str,
    role: str,
    text: str,
    org_id: str | None = None,
) -> tuple[ConsultationNode, bool]:
    """Map one conversation turn to an Observation Knowledge Act under the ratified rules.
    Returns ``(node, was_truncated)``. Pure — builds the record, writes nothing."""
    answer, was_truncated = _truncate(text)
    node = adapter.to_act(
        subject_id=subject_id,
        answer=answer,
        producer=_PRODUCER,
        agent_id=role,          # bare role (ratified Q2); never derived from the carrier
        carrier=_IMPORT_CARRIER,
        confidence=1.0,         # confidence the turn WAS said, not its truth
        org_id=org_id,          # mode defaults to observation (ADR-0008)
    )
    return node, was_truncated


def _recency(conv: dict) -> int | None:
    """Best-effort recency key for the corpus-derived suggestions: update_time, else
    create_time, else the last message timestamp."""
    for key in ("update_time", "create_time"):
        ms = _ms(conv.get(key))
        if ms is not None:
            return ms
    times = [ms for ms in (_ms(m.get("t")) for m in (conv.get("messages") or [])
                           if isinstance(m, dict)) if ms is not None]
    return max(times) if times else None


def load_conversations(path: Path) -> dict:
    """Load the ``{conv_id: conv}`` map, tolerating the real-export wrappers the collector
    tolerates: ``{"conversations": {...}}``, ``{"loose_conversations": {...}}``, or a bare map."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PRLError(f"cannot read export at {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise PRLError(f"export is not valid JSON: {exc}") from exc
    if isinstance(data, dict) and isinstance(data.get("conversations"), dict):
        return data["conversations"]
    if isinstance(data, dict) and isinstance(data.get("loose_conversations"), dict):
        return data["loose_conversations"]
    if isinstance(data, dict):
        return data
    raise PRLError("export must be a JSON object of conversations")


@dataclass
class ImportReport:
    """The evidence surface of an import — the counts the contract requires plus the
    corpus-derived first-step suggestions."""

    conversations: int = 0          # received (every conversation in the source)
    subjects: int = 0               # imported (one subject per conversation with turns)
    acts: int = 0                   # turn-observation acts (ConsultationNodes)
    truncations: int = 0
    boundary_acts: int = 0          # one certified SessionNode envelope per imported conversation
    suggestions: list[str] = field(default_factory=list)
    # Official-tree normalization drops (P5); all zero on the already-normalized path.
    normalization: NormalizationReport = field(default_factory=NormalizationReport)
    # Import identity (PR-2c). The absolute storage_dir is deliberately NOT recorded.
    run_id: str = ""                # one shared run_id across every act in this import
    source_sha256: str = ""         # digest of the source bytes
    imported_at: str = ""           # ISO-8601 UTC import event time


def _suggestions(recents: list[tuple[int | None, str, str]]) -> list[str]:
    """Up to :data:`_SUGGEST_MAX` first-step pointers generated from the corpus itself —
    the most recent distinct subjects. These are ``daryl object`` commands that work *now*,
    post-import (they read the store); natural-language ``daryl ask`` over the store lands
    in D3, so we do not offer a step that does not yet work."""
    recents.sort(key=lambda r: (r[0] is None, -(r[0] or 0)))
    seen: set[str] = set()
    out: list[str] = []
    for _, title, subject in recents:
        if subject in seen:
            continue
        seen.add(subject)
        label = f"  # {title[:60]}" if title else ""
        out.append(f'daryl object --subject "{subject}"{label}')
        if len(out) >= _SUGGEST_MAX:
            break
    return out


def _conversation_span(conv: dict) -> tuple[int, int | None]:
    """The conversation's time envelope (started_ms, ended_ms) for the boundary SessionNode.
    Prefers the conversation-level create/update times; falls back to the turn timestamps.
    This is the ONLY time PR-2c persists — per-turn timestamps are deliberately not stored."""
    start = _ms(conv.get("create_time"))
    end = _ms(conv.get("update_time"))
    msg_ms = [ms for ms in (_ms(m.get("t")) for m in (conv.get("messages") or [])
                            if isinstance(m, dict)) if ms is not None]
    if start is None:
        start = min(msg_ms) if msg_ms else 0
    if end is None:
        end = max(msg_ms) if msg_ms else None
    return start, end


def build_boundary_act(conv_id: str, title: str, turns: list[tuple[str, str]],
                       span: tuple[int, int | None]) -> SessionNode:
    """The conversation envelope — one certified ``SessionNode`` per imported conversation,
    distinct from its turn ConsultationNodes. Carries the raw ``conv_id`` (session_id) and the
    conversation span. No new node type / writer (SessionNode is a frozen, committable act)."""
    preview = " | ".join(f"{role}: {text}" for role, text in turns)[:_PREVIEW_MAX]
    return SessionNode(
        session_id=str(conv_id), tool="chatgpt", title=title or None,
        started_ms=span[0], ended_ms=span[1], text_preview=preview,
    )


def build_manifest_act(run_id: str, source_sha256: str, imported_at: str,
                       imported_at_ms: int, counts: dict[str, Any]) -> SessionNode:
    """The per-import manifest — one certified ``SessionNode`` per run. Its ``text_preview``
    carries the deterministic accounting + import identity as canonical JSON (the manifest
    session's preview IS the manifest). Reserved ``session_id`` prefix so reads can tell it
    apart from boundary sessions. The absolute storage_dir is deliberately not recorded."""
    payload = {
        "kind": _MANIFEST_PREFIX,
        "run_id": run_id,
        "source_sha256": source_sha256,
        "imported_at": imported_at,
        "counts": counts,
    }
    return SessionNode(
        session_id=f"{_MANIFEST_PREFIX}.{run_id}", tool="chatgpt",
        title=_MANIFEST_PREFIX, started_ms=imported_at_ms, ended_ms=imported_at_ms,
        text_preview=json.dumps(payload, sort_keys=True),
    )


def import_chatgpt(
    config: PRLConfig,
    export_path: str | Path,
    *,
    org_id: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> ImportReport:
    """Seed every conversation turn as an Observation act, write one boundary ``SessionNode``
    per conversation and one manifest ``SessionNode`` per run, all under a shared ``run_id``.
    Certified via ``commit_act`` (hash-chained); receipts mint fresh on each import."""
    # Resolve any accepted source to the normalized D2a shape: an official OpenAI export
    # (.zip or conversations.json tree) is normalized here (D2b); an already-normalized
    # JSON passes through. The seeding below is unchanged either way.
    conversations, normalization = resolve_conversations(export_path)
    store = open_store(config)
    adapter = ConsultationAdapter()

    run_id = new_run_id()  # one import identity shared by every act in this run
    source_sha256 = hashlib.sha256(Path(export_path).read_bytes()).hexdigest()
    now = datetime.now(timezone.utc)
    imported_at = now.isoformat()

    subjects: set[str] = set()
    acts = 0
    truncations = 0
    boundary_acts = 0
    recents: list[tuple[int | None, str, str]] = []
    total = len(conversations)

    for i, (conv_id, conv) in enumerate(conversations.items(), start=1):
        if isinstance(conv, dict):
            title = str(conv.get("title") or "")
            subject = _subject_id(title, str(conv_id))
            turns = _sorted_turns(conv)
            if turns:
                subjects.add(subject)
                recents.append((_recency(conv), title, subject))
                for role, text in turns:
                    node, was_truncated = build_turn_act(
                        adapter, subject_id=subject, role=role, text=text, org_id=org_id
                    )
                    if was_truncated:
                        truncations += 1
                    store.commit_act(node, run_id=run_id)
                    acts += 1
                # the conversation envelope (boundary act)
                store.commit_act(
                    build_boundary_act(str(conv_id), title, turns, _conversation_span(conv)),
                    run_id=run_id,
                )
                boundary_acts += 1
        if on_progress is not None:
            on_progress(i, total)

    counts = {
        "conversations_received": total,
        "conversations_imported": len(subjects),
        "subjects": len(subjects),
        "turn_acts": acts,
        "boundary_acts": boundary_acts,
        "truncations": truncations,
        "dropped": {
            "branches": normalization.dropped_branches,
            "system": normalization.dropped_system,
            "hidden": normalization.dropped_hidden,
            "empty": normalization.dropped_empty,
        },
        "placeholder_nontext": normalization.placeholder_nontext,
    }
    store.commit_act(
        build_manifest_act(run_id, source_sha256, imported_at,
                           int(now.timestamp() * 1000), counts),
        run_id=run_id,
    )

    return ImportReport(
        conversations=total,
        subjects=len(subjects),
        acts=acts,
        truncations=truncations,
        boundary_acts=boundary_acts,
        suggestions=_suggestions(recents),
        normalization=normalization,
        run_id=run_id,
        source_sha256=source_sha256,
        imported_at=imported_at,
    )
