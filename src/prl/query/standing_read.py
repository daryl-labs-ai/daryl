"""Standing — a derived projection (Resolution / Standing v1, ADR-PRL-0008).

The load-bearing rule: **standing is never a stored or mutated field.** A claim's
current standing is *computed by replaying its acts* — read the ``prl.resolution``
acts targeting the claim and derive the outcome. Read-only.

Reads go through a :class:`RegistryProjection` (the registry retrieval seam, abstracted
as a PRL-owned contract — Identity across projections v1). The default projection is RR
(``RRNavigator``); a second projection (e.g. SQLite) implements the same surface, so the
*same* query code runs on either — identity is projection-invariant by construction.

v1 derivation: a claim with no resolution is ``proposed``; otherwise its standing is
the decision of the **latest** resolution (authoritative record order). ``superseded`` and
``withdrawn`` are themselves new resolution acts — never edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from ..types import ResolutionNode, from_entry


class RegistryProjection(Protocol):
    """The registry retrieval seam (ADR-PRL-0004 Ch5: "the registry is one projection
    among many"). A projection enumerates certified acts by kind and resolves them to
    Entry-shaped objects. Identity (``claim_id``) lives in the resolved ``content`` and is
    filtered in PRL code, never an index axis.

    Contract:
    - ``navigate_action(action_name)`` returns records in **authoritative order**
      (ascending, stable). Each record exposes an ``entry_id`` (dict key or attribute).
    - ``resolve_entries(records)`` returns Entry-shaped objects (``.id`` / ``.hash`` /
      ``.content`` / ``.metadata['action_name']``); it does **not** guarantee order, so
      consumers replay in the records' order and join record→entry by id.
    - The receipt is the resolved entry's ``.hash`` — **projection-relative** (it certifies
      that projection's storage; a substrate swap would re-issue it, not carry it).
    """

    def navigate_action(self, action_name: str, limit: int | None = ...) -> list[Any]: ...
    def resolve_entries(self, records: list[Any], limit: int | None = ...) -> list[Any]: ...


@dataclass(frozen=True)
class StandingView:
    """The derived standing of a claim + the decisions behind it."""

    claim_id: str
    standing: str               # "proposed" | "accepted" | "rejected" | "superseded" | "withdrawn"
    decisions: tuple[str, ...]  # the resolution decisions in order (empty = proposed)
    last_receipt: str           # DSM receipt of the latest resolution ("" if none)


@dataclass(frozen=True)
class ResolutionFact:
    """One resolution act, reduced to the facts R-explain needs to answer
    'who decided, with which certified act' — each backed by a receipt."""

    decision: str    # accepted | rejected | superseded | withdrawn
    resolver: str    # the legacy producer display (MEF.producer)
    receipt: str     # the resolution Entry's hash (projection-relative)
    agent_id: str = ""  # the logical contributor (ADR-0009); "" = unknown (pre-0009)
    carrier: str = ""   # the execution carrier-of-record, e.g. "human" (ADR-0009)


def render_standing(view: StandingView) -> str:
    """Pure display."""
    if not view.decisions:
        return f"standing of {view.claim_id}: PROPOSED  (no resolution)"
    return (f"standing of {view.claim_id}: {view.standing.upper()}  "
            f"(decisions: {', '.join(view.decisions)} ; receipt {view.last_receipt})")


class StandingQuery:
    """Derives a claim's standing from its resolution acts via a registry projection
    (read-only). Runs unchanged on RR or any other :class:`RegistryProjection`."""

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RegistryProjection | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()
            _navigator = RRNavigator(builder, storage)
        self._nav: RegistryProjection = _navigator

    def _resolutions_for(self, claim_id: str) -> list[tuple[Any, ResolutionNode]]:
        # Authoritative order is the *records'* order: navigate_action is ascending;
        # resolve_entries does NOT preserve that order, so replay in records' order and
        # join record -> entry by id (never trust resolve_entries order). This holds for
        # any projection that honours the RegistryProjection contract.
        records = self._nav.navigate_action("prl.resolution")
        entries = self._nav.resolve_entries(records)
        by_id = {getattr(e, "id", None): e for e in entries}
        out: list[tuple[Any, ResolutionNode]] = []
        for rec in records:
            eid = rec.get("entry_id") if isinstance(rec, dict) else getattr(rec, "entry_id", None)
            entry = by_id.get(eid)
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
        last_entry, last_node = res[-1]  # latest by authoritative record order
        return StandingView(
            claim_id=claim_id,
            standing=last_node.decision,
            decisions=tuple(n.decision for _e, n in res),
            last_receipt=str(getattr(last_entry, "hash", "") or ""),
        )

    def resolutions_of(self, claim_id: str) -> list[ResolutionFact]:
        """The resolution acts targeting ``claim_id`` as facts (decision, resolver,
        receipt), in authoritative record order. Read-only; the *standing* is still
        derived by ``standing_of`` — this only exposes the acts behind it (R-explain)."""
        return [
            ResolutionFact(
                decision=node.decision,
                resolver=node.mef.producer,
                receipt=str(getattr(entry, "hash", "") or ""),
                agent_id=node.mef.agent_id or "",
                carrier=node.mef.carrier.short() if node.mef.carrier is not None else "",
            )
            for entry, node in self._resolutions_for(claim_id)
        ]
