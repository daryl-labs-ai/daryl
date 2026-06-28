"""Standing — a derived projection (Resolution / Standing v1, ADR-PRL-0008).

The load-bearing rule: **standing is never a stored or mutated field.** A claim's
current standing is *computed by replaying its acts* — read the ``prl.resolution``
acts targeting the claim and derive the outcome. Read-only, RR-only: this module
imports only ``dsm.rr.*`` and *receives* a storage instance (so no
``LEGITIMATE_WRITERS`` entry, like ``structural.py`` / ``consultation_read.py``).

v1 derivation: a claim with no resolution is ``proposed``; otherwise its standing is
the decision of the **latest** resolution (RR/append order). ``superseded`` and
``withdrawn`` are themselves new resolution acts — never edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from ..types import ResolutionNode, from_entry


def _record_entry_id(rec: Any) -> Any:
    """The entry id of an RR action record (dict from real RR, or attr on a stub)."""
    if isinstance(rec, dict):
        return rec.get("entry_id") or rec.get("id")
    return getattr(rec, "entry_id", None) or getattr(rec, "id", None)


@dataclass(frozen=True)
class StandingView:
    """The derived standing of a claim + the decisions behind it."""

    claim_id: str
    standing: str               # "proposed" | "accepted" | "rejected" | "superseded" | "withdrawn"
    decisions: tuple[str, ...]  # the resolution decisions in order (empty = proposed)
    last_receipt: str           # DSM receipt of the latest resolution ("" if none)


def render_standing(view: StandingView) -> str:
    """Pure display."""
    if not view.decisions:
        return f"standing of {view.claim_id}: PROPOSED  (no resolution)"
    return (f"standing of {view.claim_id}: {view.standing.upper()}  "
            f"(decisions: {', '.join(view.decisions)} ; receipt {view.last_receipt})")


class StandingQuery:
    """Derives a claim's standing from its resolution acts via RR (read-only)."""

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RRNavigator | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()
            _navigator = RRNavigator(builder, storage)
        self._nav = _navigator

    def _resolutions_for(self, claim_id: str) -> list[tuple[Any, ResolutionNode]]:
        # navigate_action returns records in RR build-time order — timestamp ascending
        # with a stable insertion tiebreaker (Phase 7a Amendement A), i.e. append order.
        # resolve_entries regroups by shard and does NOT preserve that order, so we
        # re-key the resolved entries by id and replay them in the records' order. That
        # is what makes "latest resolution wins" deterministic (see standing_of).
        records = list(self._nav.navigate_action("prl.resolution"))
        entries = self._nav.resolve_entries(records)
        by_id = {getattr(e, "id", None): e for e in entries}
        out: list[tuple[Any, ResolutionNode]] = []
        for rec in records:
            entry = by_id.get(_record_entry_id(rec))
            if entry is None:
                continue
            node = from_entry(entry)
            if isinstance(node, ResolutionNode) and node.target_claim_id == claim_id:
                out.append((entry, node))
        return out

    def standing_of(self, claim_id: str) -> StandingView:
        """Derive the current standing of ``claim_id`` by replaying its resolutions.
        Never reads a stored standing — it is computed here, every time."""
        res = self._resolutions_for(claim_id)
        if not res:
            return StandingView(claim_id=claim_id, standing="proposed", decisions=(), last_receipt="")
        last_entry, last_node = res[-1]  # v1: latest by RR/append order
        return StandingView(
            claim_id=claim_id,
            standing=last_node.decision,
            decisions=tuple(n.decision for _e, n in res),
            last_receipt=str(getattr(last_entry, "hash", "") or ""),
        )
