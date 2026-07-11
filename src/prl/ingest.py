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

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .chatgpt_normalize import NormalizationReport, resolve_conversations
from .collectors import ConsultationAdapter
from .config import PRLConfig
from .exceptions import PRLError
from .store import open_store
from .types import Carrier, ConsultationNode

# Ratified ceiling — revisable only from user evidence (not a knob, hence no CLI flag).
MAX_ANSWER_CHARS = 8000
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

    conversations: int = 0
    subjects: int = 0
    acts: int = 0
    truncations: int = 0
    suggestions: list[str] = field(default_factory=list)
    # Official-tree normalization drops (P5); all zero on the already-normalized path.
    normalization: NormalizationReport = field(default_factory=NormalizationReport)


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


def import_chatgpt(
    config: PRLConfig,
    export_path: str | Path,
    *,
    org_id: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> ImportReport:
    """Seed every conversation turn as an Observation act into ``config``'s store, and
    return the :class:`ImportReport`. ``on_progress(done, total)`` is called per conversation
    for UX. Certified via ``commit_act`` (hash-chained); receipts mint fresh on each import."""
    # Resolve any accepted source to the normalized D2a shape: an official OpenAI export
    # (.zip or conversations.json tree) is normalized here (D2b); an already-normalized
    # JSON passes through. The seeding below is unchanged either way.
    conversations, normalization = resolve_conversations(export_path)
    store = open_store(config)
    adapter = ConsultationAdapter()

    subjects: set[str] = set()
    acts = 0
    truncations = 0
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
                    store.commit_act(node)
                    acts += 1
        if on_progress is not None:
            on_progress(i, total)

    return ImportReport(
        conversations=total,
        subjects=len(subjects),
        acts=acts,
        truncations=truncations,
        suggestions=_suggestions(recents),
        normalization=normalization,
    )
