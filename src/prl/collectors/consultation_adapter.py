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
from typing import TYPE_CHECKING

from ..types import MEF, Carrier, ConsultationMode, ConsultationNode

if TYPE_CHECKING:  # avoid importing the client at runtime; consult receives one
    from .agent_client import AgentClient

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
        agent_id: str,
        confidence: float,
        carrier: Carrier | None = None,
        org_id: str | None = None,
        propose: bool = False,
        regime: str | None = None,
        contested: bool = False,
        claim_id: str | None = None,
    ) -> ConsultationNode:
        """Build a :class:`ConsultationNode` from an agent answer.

        ``propose`` must be set **explicitly** to produce a Proposal; otherwise the act
        is an Observation. ``agent_id`` (the logical contributor, ADR-0009), ``producer``
        and ``confidence`` are required; ``agent_id`` is **never** derived from the
        ``carrier``. Pure — builds the record, writes nothing.
        """
        mode: ConsultationMode = "proposal" if propose else "observation"
        if regime is None:
            regime = _DEFAULT_PROPOSAL_REGIME if propose else _DEFAULT_OBSERVATION_REGIME

        mef = MEF(
            claim_id=claim_id or f"claim_{uuid.uuid4().hex[:12]}",
            regime=regime,
            confidence=confidence,
            contested=contested,
            producer=producer,  # legacy display projection (ADR-0009)
            agent_id=agent_id,  # logical contributor; caller-supplied, not derived from carrier
            carrier=carrier,    # execution carrier-of-record
        )
        return ConsultationNode(
            consultation_id=f"consult_{uuid.uuid4().hex[:12]}",
            subject_id=subject_id,
            mode=mode,
            answer=answer,
            mef=mef,
            org_id=org_id,  # owning org (ADR-0010); optional, caller-supplied, not inferred
        )

    def consult(
        self,
        client: "AgentClient",
        *,
        subject_id: str,
        prompt: str,
        model: str,
        agent_id: str,
        confidence: float = 1.0,
        org_id: str | None = None,
        propose: bool = False,
    ) -> ConsultationNode:
        """R-consult v3: call a **real agent** and map its native answer to a Knowledge
        Act. The model is unaware of PRL; ``client`` is injected (so tests use a fake,
        no network).

        ``agent_id`` (ADR-0009) is the **logical contributor** (e.g. ``agent.architect``),
        **required and caller-supplied** — never inferred from provider/model. The
        execution **carrier-of-record** (provider/model/adapter) is recorded alongside; the
        legacy ``producer`` string stays a display projection. ``confidence`` is confidence
        in the *Observation* (the agent did answer this), not the truth of the answer.
        """
        answer = client.complete(prompt, model=model)
        provider = getattr(client, "provider", "agent")
        adapter = "consult-adapter v1"
        producer = f"{provider}:{model} ({adapter})"  # legacy display, unchanged
        carrier = Carrier(provider=provider, model=model, adapter=adapter)
        return self.to_act(
            subject_id=subject_id, answer=answer, producer=producer, agent_id=agent_id,
            carrier=carrier, org_id=org_id, confidence=confidence, propose=propose,
        )
