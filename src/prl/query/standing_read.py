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

from collections.abc import Sequence
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
    conflict: bool = False      # derived signal (#2 conflict visibility): two distinct authorities
                                # disagree (accepted vs rejected). Orthogonal to standing — it never
                                # changes latest-wins; it only makes the disagreement impossible to miss.
    conflict_parties: tuple[str, ...] = ()  # the agent_ids in disagreement (empty unless conflict)


@dataclass(frozen=True)
class ResolutionFact:
    """One resolution act, reduced to the facts R-explain needs to answer
    'who decided, with which certified act' — each backed by a receipt."""

    decision: str    # accepted | rejected | superseded | withdrawn
    resolver: str    # the legacy producer display (MEF.producer)
    receipt: str     # the resolution Entry's hash (projection-relative)
    agent_id: str = ""  # the logical contributor (ADR-0009); "" = unknown (pre-0009)
    carrier: str = ""   # the execution carrier-of-record, e.g. "human" (ADR-0009)
    org_id: str = ""    # the owning organization (ADR-0010); "" = unknown (no inference)


def detect_conflict(resolutions: Sequence[ResolutionFact]) -> tuple[bool, tuple[str, ...]]:
    """Derive whether a claim is **in conflict** — two distinct authorities disagree (#2
    conflict visibility, angle b). Pure; computed from the acts every call, **never stored**
    (same discipline as standing). It does **not** govern the conflict and **never** changes the
    standing — it only makes an incompatible decision impossible to be invisible.

    Definition **D3** (conflict is *between* authorities, not *within* one):
    a conflict exists when two **distinct** ``agent_id`` issue **substantively opposite**
    decisions — one ``accepted`` and another ``rejected``. A single author changing their mind
    (same ``agent_id``, accepted then rejected) is a **supersession, not a conflict**.
    ``superseded`` / ``withdrawn`` are explicit transitions, never by themselves a conflict.

    **Legacy fallback (D2):** when an ``agent_id`` is unknown (pre-0009 acts, ``""``), we cannot
    attribute authorship, so opposite decisions are **surfaced** rather than silently ignored —
    never inferred as *no* conflict.

    Returns ``(conflict, parties)`` where ``parties`` are the disagreeing ``agent_id`` (empty
    unless a conflict; the unknown author is reported as ``""``)."""
    accepted = [r for r in resolutions if r.decision == "accepted"]
    rejected = [r for r in resolutions if r.decision == "rejected"]
    if not accepted or not rejected:
        return (False, ())  # need both substantive opposites at all

    a_authors = {r.agent_id for r in accepted if r.agent_id}
    r_authors = {r.agent_id for r in rejected if r.agent_id}
    # D3: a known author accepted and a *distinct* known author rejected.
    if any(a != b for a in a_authors for b in r_authors):
        return (True, tuple(sorted(a_authors | r_authors)))
    # Legacy fallback (D2): any unknown author on either side ⇒ cannot rule out a cross-author
    # conflict ⇒ surface (never silently False).
    if any(not r.agent_id for r in accepted) or any(not r.agent_id for r in rejected):
        parties = tuple(sorted(a_authors | r_authors | {""}))
        return (True, parties)
    # Otherwise: the only opposition is a single known author with itself (a supersession).
    return (False, ())


def derive_standing(claim_id: str, resolutions: Sequence[ResolutionFact]) -> StandingView:
    """The **single source of latest-wins** (Resolution v1). A claim with no resolution is
    ``proposed``; otherwise its standing is the **latest** resolution's decision (resolutions
    must already be in authoritative order). Pure: computes from facts, never reads a stored
    standing. Both ``StandingQuery`` (full scan) and ``StandingIndex`` (one-pass grouping)
    feed this same function — so an optimization cannot change the standing.

    The standing is computed by latest-wins **unchanged**; conflict is an **orthogonal derived
    signal** (#2) — :func:`detect_conflict` is read alongside, never to pick a winner."""
    if not resolutions:
        return StandingView(claim_id=claim_id, standing="proposed", decisions=(), last_receipt="")
    conflict, parties = detect_conflict(resolutions)
    return StandingView(
        claim_id=claim_id,
        standing=resolutions[-1].decision,
        decisions=tuple(r.decision for r in resolutions),
        last_receipt=resolutions[-1].receipt,
        conflict=conflict,
        conflict_parties=parties,
    )


def render_standing(view: StandingView) -> str:
    """Pure display. Standing is shown unchanged (latest-wins); a conflict, if any, is
    surfaced alongside it as ``⚠ CONFLICT`` — visible, not governing."""
    if not view.decisions:
        return f"standing of {view.claim_id}: PROPOSED  (no resolution)"
    flag = ""
    if view.conflict:
        parties = ", ".join(p or "?" for p in view.conflict_parties)
        flag = f"  ⚠ CONFLICT (incompatible decisions by {parties})"
    return (f"standing of {view.claim_id}: {view.standing.upper()}  "
            f"(decisions: {', '.join(view.decisions)} ; receipt {view.last_receipt}){flag}")


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
        Delegates to the pure :func:`derive_standing` (single source of latest-wins), fed
        by this query's facts. Never reads a stored standing — recomputed every call."""
        return derive_standing(claim_id, self.resolutions_of(claim_id))

    def resolutions_of(self, claim_id: str) -> list[ResolutionFact]:
        """The resolution acts targeting ``claim_id`` as facts (decision, resolver,
        receipt), in authoritative record order. Read-only; the *standing* is still
        derived by ``standing_of`` — this only exposes the acts behind it (R-explain)."""
        return [_fact(entry, node) for entry, node in self._resolutions_for(claim_id)]


def _fact(entry: Any, node: ResolutionNode) -> ResolutionFact:
    """Reduce a resolution (entry + node) to a :class:`ResolutionFact`."""
    return ResolutionFact(
        decision=node.decision,
        resolver=node.mef.producer,
        receipt=str(getattr(entry, "hash", "") or ""),
        agent_id=node.mef.agent_id or "",
        carrier=node.mef.carrier.short() if node.mef.carrier is not None else "",
        org_id=node.org_id or "",
    )


class StandingIndex:
    """A **non-authoritative, droppable** projection of resolution acts grouped by
    ``claim_id``, built in **one pass** over the ``prl.resolution`` bucket (#1, derived
    standing at scale).

    It memoizes the act **grouping**, **never the standing**: ``standing_of`` still derives
    via :func:`derive_standing` on every call. Drop the index and standing is recomputed from
    the acts — it is a *projection* (same discipline as the RR adjacency index / the SQLite
    read projection), never a source of truth. It has **no** authoritative write path.

    Cost: **O(N) once** to build; then **O(1)** lookup + **O(k)** derive per claim — vs
    ``StandingQuery``'s **O(N) per claim** full-bucket scan.
    """

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RegistryProjection | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()
            _navigator = RRNavigator(builder, storage)
        # ONE scan: resolve the whole bucket once, group resolutions by target_claim_id in
        # authoritative record order. This is the only place acts are read.
        records = _navigator.navigate_action("prl.resolution")
        entries = _navigator.resolve_entries(records)
        by_id = {getattr(e, "id", None): e for e in entries}
        self._by_claim: dict[str, list[ResolutionFact]] = {}
        for rec in records:
            eid = rec.get("entry_id") if isinstance(rec, dict) else getattr(rec, "entry_id", None)
            entry = by_id.get(eid)
            if entry is None:
                continue
            node = from_entry(entry)
            if isinstance(node, ResolutionNode):
                self._by_claim.setdefault(node.target_claim_id, []).append(_fact(entry, node))

    def resolutions_of(self, claim_id: str) -> list[ResolutionFact]:
        """O(1) lookup of a claim's resolution facts (authoritative order)."""
        return list(self._by_claim.get(claim_id, ()))

    def standing_of(self, claim_id: str) -> StandingView:
        """Standing is **derived** every call (never stored); only the act grouping is
        memoized. Same single-source :func:`derive_standing` as ``StandingQuery``."""
        return derive_standing(claim_id, self.resolutions_of(claim_id))
