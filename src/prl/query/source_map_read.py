"""Source map (M1 · D2c) — `daryl source --subject <subject_id>`.

A **derived, read-only** RR projection. Given a ``subject_id`` (``slug(title).<id6>``), it
reconstructs the conversation's provenance: the boundary receipt + the **authoritative
ordered** turn acts, each with role, ordinal position, receipt, and truncation/placeholder
indicators when detectable from the stored answer. Keyed by ``subject_id`` (user-facing); the
raw ``conversation_id`` is shown as source provenance.

Per-turn timestamps are **not recorded in M1** (ratified): ordering is the authoritative
record order (RR) and the conversation span comes from the boundary ``SessionNode``. This
module adds no writer and no new ``action_name``; per ADR-0001 reads go only through RR (it
imports ``dsm.rr.*`` and receives a ``storage`` instance, never importing ``Storage``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from ..ingest import _MANIFEST_PREFIX, _subject_id
from ..types import SessionNode, from_entry
from .consultation_read import ConsultationQuery
from .standing_read import RegistryProjection

_TRUNC_MARK = "truncated by daryl-import"
_PLACEHOLDER_TOKENS = ("[image]", "[audio]", "[attachment]", "[file:")


def _has_placeholder(answer: str) -> bool:
    return any(tok in answer for tok in _PLACEHOLDER_TOKENS)


@dataclass(frozen=True)
class TurnRow:
    ordinal: int
    role: str
    receipt: str
    truncated: bool
    has_placeholder: bool


@dataclass(frozen=True)
class SourceMap:
    subject_id: str
    conversation_id: str | None
    title: str | None
    started_ms: int | None
    ended_ms: int | None
    boundary_receipt: str | None
    turns: list[TurnRow]

    def found(self) -> bool:
        return bool(self.turns or self.boundary_receipt)


class SourceMapQuery:
    """Reads a subject's provenance via RR (read-only). ``storage`` is received, never
    imported — so this module needs no ``LEGITIMATE_WRITERS`` entry."""

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RegistryProjection | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()
            _navigator = RRNavigator(builder, storage)
        self._nav = _navigator
        self._consult = ConsultationQuery(storage, index_dir, _navigator=_navigator)

    def project(self, subject_id: str) -> SourceMap:
        # ConsultationQuery yields RR recency order (newest-first); reverse to the
        # authoritative *append* order so ordinal #1 is the conversation's first turn.
        views = list(reversed(self._consult.list(subject_id=subject_id)))
        turns = [
            TurnRow(
                ordinal=i + 1,
                role=v.agent_id or "unknown",
                receipt=v.receipt,
                truncated=(_TRUNC_MARK in v.answer),
                has_placeholder=_has_placeholder(v.answer),
            )
            for i, v in enumerate(views)
        ]
        found = self._find_boundary(subject_id)
        if found is not None:
            node, receipt = found
            return SourceMap(subject_id, node.session_id, node.title,
                             node.started_ms, node.ended_ms, receipt, turns)
        return SourceMap(subject_id, None, None, None, None, None, turns)

    def _find_boundary(self, subject_id: str) -> tuple[SessionNode, str] | None:
        """Link subject → its boundary SessionNode by inverting the ratified key
        (``_subject_id(title, session_id) == subject_id``). The per-run manifest session is
        skipped by its reserved id prefix."""
        records = self._nav.navigate_action("prl.session")
        for entry in self._nav.resolve_entries(records):
            node = from_entry(entry)
            if not isinstance(node, SessionNode):
                continue
            if node.session_id.startswith(_MANIFEST_PREFIX):
                continue
            if _subject_id(node.title or "", node.session_id) == subject_id:
                return node, str(getattr(entry, "hash", "") or "")
        return None


def render_source_map(sm: SourceMap) -> str:
    """Pure display. Receipts link onward (`[go receipt …]`). Honest about M1's limits:
    the record order is authoritative; exact per-turn timestamps are not recorded."""
    from .links import LinkAnnotator

    ann = LinkAnnotator()
    if not sm.found():
        return (f"no source map for subject {sm.subject_id!r} in this projection\n"
                "  note: projection-relative — not found here ≠ does not exist elsewhere")

    lines = [f"Source Map — {sm.subject_id}"]
    lines.append(f"  conversation_id: {sm.conversation_id or '(unknown)'}   (raw source provenance)")
    lines.append(f"  span (ms):       {sm.started_ms}..{sm.ended_ms}   (conversation-level)")
    if sm.boundary_receipt:
        lines.append(f"  boundary receipt: {sm.boundary_receipt}{ann.tag('receipt', sm.boundary_receipt)}")
    lines.append(f"  turns: {len(sm.turns)}  "
                 "(authoritative record order; exact per-turn time not recorded in M1)")
    for t in sm.turns:
        flags = []
        if t.truncated:
            flags.append("truncated")
        if t.has_placeholder:
            flags.append("non-text")
        flag = f"  [{', '.join(flags)}]" if flags else ""
        lines.append(f"    #{t.ordinal:<3} {t.role:<10} {t.receipt}"
                     f"{ann.tag('receipt', t.receipt)}{flag}")
    return "\n".join(lines)
