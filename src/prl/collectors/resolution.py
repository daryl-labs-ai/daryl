"""Resolution act builder (Resolution / Standing v1, ADR-PRL-0008).

A Resolution is a **human/witnessed governance act** over a claim: it ratifies a
Proposal (accepted / rejected / superseded / withdrawn). This builder is pure (no DSM,
no Storage); the CLI commits the result via ``prl/store`` (the existing writer).

Invariants it carries:
- **The agent never ratifies.** This is the *only* place a Resolution is built, it is
  not reachable from ``ConsultationAdapter`` / ``AgentClient``, and ``producer`` is a
  human/witnessed identity (e.g. ``"human:<id>"``).
- **Accepted ≠ True.** The act records a *decision* (a standing-affecting governance
  outcome), never a truth value; ``ResolutionNode`` has no truth field.
- **An act, not a mutation.** Supersession/withdrawal are *new* resolutions; standing
  is derived by replay (see ``query.standing_read``), never stored.
"""

from __future__ import annotations

import uuid

from ..types import MEF, Carrier, ResolutionDecision, ResolutionNode

# v1 default regime for a governance act (free string; taxonomy is ADR-0003 / open).
_DEFAULT_RESOLUTION_REGIME = "governance.resolution"


def make_resolution(
    *,
    target_claim_id: str,
    decision: ResolutionDecision,
    agent_id: str,
    producer: str | None = None,
    regime: str = _DEFAULT_RESOLUTION_REGIME,
    confidence: float = 1.0,
    contested: bool = False,
    claim_id: str | None = None,
) -> ResolutionNode:
    """Build a human/witnessed :class:`ResolutionNode` over ``target_claim_id``.

    ``agent_id`` (ADR-0009) is the **logical human contributor** (e.g. ``mohamed.azizi``),
    **required** — the human-ness lives in the carrier (``provider = "human"``), never in
    the id (no ``human:`` prefix). ``producer`` is the legacy display projection (defaults
    to ``agent_id`` if not given). ``confidence`` is confidence in the *governance act*,
    not the truth of the claim. MEF is complete-or-refuse. Pure — writes nothing.
    """
    mef = MEF(
        claim_id=claim_id or f"claim_{uuid.uuid4().hex[:12]}",
        regime=regime,
        confidence=confidence,
        contested=contested,
        producer=producer if producer is not None else agent_id,  # legacy display projection
        agent_id=agent_id,                       # logical contributor (not "human:<id>")
        carrier=Carrier(provider="human"),       # human-ness lives in the carrier
    )
    return ResolutionNode(
        resolution_id=f"resolution_{uuid.uuid4().hex[:12]}",
        target_claim_id=target_claim_id,
        decision=decision,
        mef=mef,
    )
