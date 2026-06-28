"""R-explain v1 — "why this decision?" (Step 6 of MVP_DEMO_SCENARIO).

Reconstructs *why a decision exists* from the certified chain: the **Proposal** act, the
**Resolution** act(s), and the **derived** standing — joined by ``MEF.claim_id``.

Cardinal rule: the explanation is a **reconstruction from certified acts, not a generated
narrative.** Every meaningful line is backed by a receipt. No LLM, no summarization, no
inference over the acts; if a fact has no receipt, it does not appear.

Read-only: assembles the two read paths (``ConsultationQuery`` for the Proposal facet,
``StandingQuery`` for the Resolution facts + derived standing) over a shared
:class:`RegistryProjection`. The same code runs on RR or any other projection (Identity
across projections v1) — so an explanation is projection-invariant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from .consultation_read import ConsultationQuery
from .standing_read import RegistryProjection, ResolutionFact, StandingQuery


@dataclass(frozen=True)
class ProposalFact:
    """The Proposal facet of an explanation — the certified contribution under decision."""

    producer: str
    confidence: float
    answer: str
    receipt: str       # the Proposal Entry's hash (projection-relative)
    subject_id: str


@dataclass(frozen=True)
class Explanation:
    """Why a claim holds its current standing, reconstructed from certified acts."""

    claim_id: str
    proposal: ProposalFact | None          # None when no Proposal act is on the chain
    resolutions: tuple[ResolutionFact, ...]  # all resolutions, in record order ( () = proposed )
    standing: str                          # derived (StandingQuery), never recomputed here


def render_explanation(explanation: Explanation) -> str:
    """Pure display. A receipt on every meaningful line; never narrates above the acts."""
    e = explanation
    lines = [f"why {e.claim_id} is {e.standing.upper()}"]
    if e.proposal is not None:
        p = e.proposal
        lines.append(f"  proposal   producer={p.producer}   receipt {p.receipt}")
    else:
        lines.append("  proposal   (none on chain)")
    for r in e.resolutions:
        lines.append(
            f"  resolution decision={r.decision}   resolver={r.resolver}   receipt {r.receipt}")
    if not e.resolutions:
        lines.append("  standing   PROPOSED (no resolution)")
    else:
        lines.append(f"  standing   {e.standing.upper()} (derived)")
    return "\n".join(lines)


class ExplainQuery:
    """Assembles the certified chain for a claim over a registry projection (read-only).
    Reuses ``ConsultationQuery`` + ``StandingQuery`` on a shared projection; the standing is
    ``StandingQuery``'s derivation, never recomputed here."""

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RegistryProjection | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()
            _navigator = RRNavigator(builder, storage)
        self._consult = ConsultationQuery(storage, index_dir, _navigator=_navigator)
        self._standing = StandingQuery(storage, index_dir, _navigator=_navigator)

    def explain(self, claim_id: str) -> Explanation:
        # Proposal facet: a 'proposal'-mode consultation whose claim_id matches (an
        # Observation is not a Proposal). First by record order if several; None if absent —
        # never fabricate a Proposal.
        proposal: ProposalFact | None = None
        for v in self._consult.list():
            if v.mode == "proposal" and v.claim_id == claim_id:
                proposal = ProposalFact(
                    producer=v.producer, confidence=v.confidence, answer=v.answer,
                    receipt=v.receipt, subject_id=v.subject_id)
                break
        resolutions = tuple(self._standing.resolutions_of(claim_id))
        standing = self._standing.standing_of(claim_id).standing  # derived, single source
        return Explanation(
            claim_id=claim_id, proposal=proposal, resolutions=resolutions, standing=standing)
