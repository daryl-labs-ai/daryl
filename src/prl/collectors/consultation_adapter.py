"""Agent consultation adapter (ADR-PRL-0008, R-consult v1).

The Daryl Adapter boundary (ADR-PRL-0007): the model stays normal and unaware; this
adapter maps an agent's *native answer* about a Knowledge Object into an attributed
``ConsultationNode`` — a Knowledge Act. It is a pure **Producer** (ADR-PRL-0002): no
DSM, no Storage, no RR; it only builds the record.

Invariants enforced here (ADR-PRL-0008):
- **Default = Observation.** ``mode`` is ``observation`` unless ``propose=True`` is
  passed explicitly. There is no implicit promotion to Proposal.
- **The agent never ratifies.** This adapter can only produce Observation / Proposal;
  it cannot emit a Resolution (no such path exists), and acceptance stays human/witnessed.
- **Producer attribution mandatory.** ``producer`` (e.g. "claude via adapter v1") is
  required; the MEF refuses to build without it.
- **MEF complete or refuse.** The record carries a complete :class:`MEF`; if any field
  is missing/invalid, construction raises (no record without a frame).
"""

from __future__ import annotations

import uuid

from ..types import MEF, ConsultationMode, ConsultationNode

# v1 default regimes — conservative; the exact taxonomy is ADR-0003 / open question 8.a
# (witnessed vs declared for the consultation event), deliberately NOT canonized here.
_DEFAULT_OBSERVATION_REGIME = "observed.declared"
_DEFAULT_PROPOSAL_REGIME = "derived.proposed"


class ConsultationAdapter:
    """Maps a live agent answer into a governed Knowledge Act (Observation by default)."""

    name = "consultation"

    def to_act(
        self,
        *,
        subject_id: str,
        answer: str,
        producer: str,
        confidence: float,
        propose: bool = False,
        regime: str | None = None,
        contested: bool = False,
        claim_id: str | None = None,
    ) -> ConsultationNode:
        """Build a :class:`ConsultationNode` from an agent answer.

        ``propose`` must be set **explicitly** to produce a Proposal; otherwise the act
        is an Observation. ``producer`` and ``confidence`` are required (the MEF refuses
        to build otherwise). Pure — builds the record, writes nothing.
        """
        mode: ConsultationMode = "proposal" if propose else "observation"
        if regime is None:
            regime = _DEFAULT_PROPOSAL_REGIME if propose else _DEFAULT_OBSERVATION_REGIME

        mef = MEF(
            claim_id=claim_id or f"claim_{uuid.uuid4().hex[:12]}",
            regime=regime,
            confidence=confidence,
            contested=contested,
            producer=producer,  # mandatory attribution; MEF._non_empty enforces it
        )
        return ConsultationNode(
            consultation_id=f"consult_{uuid.uuid4().hex[:12]}",
            subject_id=subject_id,
            mode=mode,
            answer=answer,
            mef=mef,
        )
