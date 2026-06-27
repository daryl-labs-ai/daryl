"""R-consult v1 (ADR-PRL-0008) — pure tests: adapter behavior, MEF enforcement,
ConsultationNode ↔ Entry round-trip. No DSM, no kernel (runnable anywhere)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from prl.collectors import ConsultationAdapter
from prl.types import MEF, ConsultationNode, from_entry, to_entry


def _adapter() -> ConsultationAdapter:
    return ConsultationAdapter()


# --- the load-bearing invariant: default = Observation ---------------------

def test_default_mode_is_observation():
    act = _adapter().to_act(subject_id="ko-1", answer="X", producer="claude via adapter v1",
                            confidence=0.6)
    assert act.mode == "observation"  # ADR-0008: answers are Observations by default


def test_proposal_only_on_explicit_flag():
    act = _adapter().to_act(subject_id="ko-1", answer="X", producer="gpt via adapter v1",
                            confidence=0.6, propose=True)
    assert act.mode == "proposal"
    assert act.mef.regime == "derived.proposed"  # v1 default for a proposal


# --- producer attribution mandatory & MEF complete-or-refuse ----------------

def test_producer_attribution_mandatory():
    with pytest.raises(ValidationError):
        _adapter().to_act(subject_id="ko-1", answer="X", producer="   ", confidence=0.6)


def test_mef_refuses_incomplete():
    # missing required fields → cannot construct (MEF complete or refuse)
    with pytest.raises(ValidationError):
        MEF(claim_id="c1", regime="observed.declared", confidence=0.5)  # no producer/contested
    # confidence out of range → refuse
    with pytest.raises(ValidationError):
        MEF(claim_id="c1", regime="observed.declared", confidence=1.5, contested=False,
            producer="p")


def test_consultation_node_requires_complete_mef():
    with pytest.raises(ValidationError):
        ConsultationNode(consultation_id="c", subject_id="ko-1", answer="X")  # no mef


# --- Entry mapping round-trip + action_name --------------------------------

def test_round_trip_through_entry():
    act = _adapter().to_act(subject_id="ko-1", answer="the answer", producer="claude via adapter v1",
                            confidence=0.7, contested=False)
    draft = to_entry(act, shard="prl_consultations", session_id="run-1")
    assert draft.metadata["action_name"] == "prl.consultation"
    back = from_entry(draft)
    assert isinstance(back, ConsultationNode)
    assert back == act  # full round-trip incl. nested MEF


def test_explicit_regime_override_kept():
    act = _adapter().to_act(subject_id="ko-1", answer="X", producer="local via adapter v1",
                            confidence=0.9, regime="observed.witnessed")
    assert act.mef.regime == "observed.witnessed"
    assert act.mef.producer == "local via adapter v1"
