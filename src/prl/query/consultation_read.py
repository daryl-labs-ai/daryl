"""Read & display consultation Knowledge Acts (R-consult v2, ADR-PRL-0008).

v1 proved the *write* (an attributed, certified consultation act). v2 proves the
*consumption*: read ``prl.consultation`` acts back through Read Relay and present the
governed contribution — producer, mode (Observation vs Proposal), confidence, subject,
and DSM receipt.

Per ADR-0001 / §8-9, reads go ONLY through RR. This module imports only ``dsm.rr.*``
and *receives* a ``storage`` instance (the forbid-storage lint flags importing
``Storage``, not using one passed in) — so it needs no ``LEGITIMATE_WRITERS`` entry.
It adds no new ``action_name`` and no writer; it is read-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from ..types import ConsultationNode, from_entry


@dataclass(frozen=True)
class ConsultationView:
    """A displayable view of one consultation act + its DSM receipt."""

    consultation_id: str
    subject_id: str
    mode: str          # "observation" | "proposal"
    producer: str
    confidence: float
    receipt: str       # the DSM Entry hash (certification: "v1:<sha256>")
    answer: str
    claim_id: str = ""  # the MEF claim_id (the identity a Resolution targets — Resolution v1)


def view_from_entry(entry: Any) -> ConsultationView:
    """Build a :class:`ConsultationView` from a resolved ``prl.consultation`` Entry.

    The node fields come from :func:`from_entry`; the **receipt** is the Entry's own
    ``hash`` (assigned at append, the certification of the act)."""
    node = from_entry(entry)
    if not isinstance(node, ConsultationNode):
        raise ValueError(f"not a consultation entry: {type(node).__name__}")
    return ConsultationView(
        consultation_id=node.consultation_id,
        subject_id=node.subject_id,
        mode=node.mode,
        producer=node.mef.producer,
        confidence=node.mef.confidence,
        receipt=str(getattr(entry, "hash", "") or ""),
        answer=node.answer,
        claim_id=node.mef.claim_id,
    )


def render_consultations(views: list[ConsultationView]) -> str:
    """Pure display. Distinguishes Observation vs Proposal; shows the governed frame."""
    if not views:
        return "no consultations found"
    lines: list[str] = []
    for v in views:
        lines.append(f"▸ {v.mode.upper()} on {v.subject_id}  [{v.consultation_id}]")
        lines.append(f"    producer: {v.producer}   confidence: {v.confidence:.2f}")
        lines.append(f"    claim: {v.claim_id}")
        lines.append(f"    DSM receipt: {v.receipt}")
    return "\n".join(lines)


class ConsultationQuery:
    """Reads ``prl.consultation`` acts via RR (read-only).

    Args:
        storage: a DSM ``Storage`` instance (received, never imported here).
        index_dir: directory for RR's derived index files.
    """

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RRNavigator | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()
            _navigator = RRNavigator(builder, storage)
        self._nav = _navigator

    def list(self, subject_id: str | None = None) -> list[ConsultationView]:
        """All consultation acts (optionally filtered by subject), newest-first by
        nothing in particular (RR order); display is the caller's concern."""
        records = self._nav.navigate_action("prl.consultation")
        entries = self._nav.resolve_entries(records)
        views = [view_from_entry(e) for e in entries]
        if subject_id is not None:
            views = [v for v in views if v.subject_id == subject_id]
        return views
