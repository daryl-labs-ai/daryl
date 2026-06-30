"""Subject standings — read-only gather of a subject's claims and their standings
(#4a Object referent, the *read-gather* experiment).

The frontier #4 asks: many Acts (across producers, claims, subjects) → one coherent
**Knowledge Object**. Before a *compiler* can exist, the **referent** must be settled: can
``subject_id`` gather the governed state of all its claims, read-only, with **no new
identity**? This module answers only the *gather* half.

What it does — and deliberately does NOT do:
- It **GATHERS**: for one ``subject_id``, it lists that subject's consultation acts, takes
  their ``claim_id``s, and reads each claim's derived standing — returning them **side by
  side** (*N claims, N standings*).
- It does **NOT COMPILE**: it never merges those claims into one "object standing"; conflict /
  supersession / provenance *across* claims is the next frontier (#4b), out of scope here.
- It **walks the latent bridge** ``subject_id`` → (consultation) ``claim_id`` →
  ``standing_of(claim_id)``. It adds **no field** to any act (``subject_id`` is *not* put on
  resolutions), mints **no ``object_id``**, and **writes nothing**.
- Read-only and **derived**: composed from acts every call, droppable, the acts stay the source.
  ``#1`` (StandingIndex) / ``#2`` (conflict) derivations are reused unchanged.

Reads go through a shared :class:`RegistryProjection` (RR by default), so the same code runs
on any projection (Identity across projections v1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from .consultation_read import ConsultationQuery
from .standing_read import RegistryProjection, StandingQuery


@dataclass(frozen=True)
class ClaimStanding:
    """One claim a subject produced, with its derived standing — a single entry in the
    gather (never a merged object). ``conflict`` is the per-claim #2 signal, carried verbatim."""

    claim_id: str
    mode: str          # the consultation mode that minted the claim: "observation" | "proposal"
    standing: str      # derived (StandingQuery), single source — never recomputed here
    conflict: bool = False  # per-claim conflict signal (#2); never aggregated across claims
    agent_id: str = ""  # the contributor that produced the claim's consultation (ADR-0009)
    carrier: str = ""   # the execution carrier-of-record (ADR-0009)


@dataclass(frozen=True)
class SubjectStandingsView:
    """A subject's claims and their standings, **gathered side by side** (not compiled).
    The unit is a *list*, on purpose: #4a proves the referent reaches the governed layer; it
    does **not** yet produce one coherent Knowledge Object."""

    subject_id: str
    claims: tuple[ClaimStanding, ...]  # one per distinct claim_id under the subject (record order)


def render_subject_standings(view: SubjectStandingsView) -> str:
    """Pure display. The subject, then one line per claim — standings shown side by side,
    never merged into a single object standing."""
    if not view.claims:
        return f"subject {view.subject_id}: no claims"
    lines = [f"subject {view.subject_id}: {len(view.claims)} claim(s)  (standings, not compiled)"]
    for c in view.claims:
        flag = "  ⚠ CONFLICT" if c.conflict else ""
        lines.append(f"  claim {c.claim_id}  [{c.mode}]  agent={c.agent_id or '(unknown)'}  "
                     f"carrier={c.carrier or '(unknown)'}  : {c.standing.upper()}{flag}")
    return "\n".join(lines)


class SubjectStandingsQuery:
    """Gathers a subject's claims and their standings over a shared registry projection
    (read-only). Composes ``ConsultationQuery`` (subject → claims) and ``StandingQuery``
    (claim → standing); the standing is ``StandingQuery``'s single-source derivation, never
    recomputed here. Runs unchanged on RR or any other :class:`RegistryProjection`."""

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RegistryProjection | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()
            _navigator = RRNavigator(builder, storage)
        self._consult = ConsultationQuery(storage, index_dir, _navigator=_navigator)
        self._standing = StandingQuery(storage, index_dir, _navigator=_navigator)

    def standings_of_subject(self, subject_id: str) -> SubjectStandingsView:
        """Gather every claim under ``subject_id`` and read each claim's standing — side by
        side, **no cross-claim logic**. The bridge is ``subject → consultation.claim_id →
        standing_of(claim)``; nothing here merges, ranks, or reconciles the claims."""
        # subject → its consultation acts → their claim_ids (de-duplicated, record order).
        seen: set[str] = set()
        claims: list[ClaimStanding] = []
        for v in self._consult.list(subject_id=subject_id):
            if not v.claim_id or v.claim_id in seen:
                continue
            seen.add(v.claim_id)
            # each claim → its derived standing (single source; #1/#2 intact). No merge.
            sv = self._standing.standing_of(v.claim_id)
            claims.append(ClaimStanding(
                claim_id=v.claim_id,
                mode=v.mode,
                standing=sv.standing,
                conflict=sv.conflict,
                agent_id=v.agent_id,
                carrier=v.carrier,
            ))
        return SubjectStandingsView(subject_id=subject_id, claims=tuple(claims))
