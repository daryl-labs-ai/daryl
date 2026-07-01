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
    agent_id: str = ""  # the logical contributor (ADR-0009); "" = unknown (pre-0009)
    carrier: str = ""   # the execution carrier-of-record, e.g. "openai:gpt-4o" (ADR-0009)
    org_id: str = ""    # the owning organization (ADR-0010); "" = unknown (no inference)


@dataclass(frozen=True)
class Explanation:
    """Why a claim holds its current standing, reconstructed from certified acts."""

    claim_id: str
    proposal: ProposalFact | None          # None when no Proposal act is on the chain
    resolutions: tuple[ResolutionFact, ...]  # all resolutions, in record order ( () = proposed )
    standing: str                          # RAW standing (latest-wins), derived (StandingQuery)
    conflict: bool = False                 # derived (#2): two distinct authorities disagree
    conflict_parties: tuple[str, ...] = ()  # the agent_ids in disagreement (empty unless conflict)
    governed_standing: str = "proposed"    # AUTHORITATIVE reading (ADR-0011); explain shows BOTH


def render_explanation(explanation: Explanation) -> str:
    """Pure display. A receipt on every meaningful line; never narrates above the acts."""
    e = explanation
    lines = [f"why {e.claim_id} is {e.governed_standing.upper()}"]
    if e.proposal is not None:
        p = e.proposal
        lines.append(f"  proposal   agent={p.agent_id or '(unknown)'}   "
                     f"carrier={p.carrier or '(unknown)'}   receipt {p.receipt}")
    else:
        lines.append("  proposal   (none on chain)")
    for r in e.resolutions:
        lines.append(f"  resolution decision={r.decision}   agent={r.agent_id or '(unknown)'}   "
                     f"carrier={r.carrier or '(unknown)'}   receipt {r.receipt}")
    if not e.resolutions:
        lines.append("  standing   PROPOSED (no resolution)")
    else:
        lines.append(f"  standing   governed={e.governed_standing.upper()}  "
                     f"raw={e.standing.upper()} (latest-wins) (derived, ADR-0011)")
    if e.conflict:
        parties = ", ".join(p or "?" for p in e.conflict_parties)
        lines.append(f"  ⚠ CONFLICT incompatible decisions by {parties} "
                     f"(standing unchanged — surfaced, not governed)")
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
                    receipt=v.receipt, subject_id=v.subject_id,
                    agent_id=v.agent_id, carrier=v.carrier, org_id=v.org_id)
                break
        resolutions = tuple(self._standing.resolutions_of(claim_id))
        view = self._standing.standing_of(claim_id)  # derived, single source (standing + conflict)
        return Explanation(
            claim_id=claim_id, proposal=proposal, resolutions=resolutions,
            standing=view.standing, conflict=view.conflict,
            conflict_parties=view.conflict_parties,
            governed_standing=view.governed_standing)
