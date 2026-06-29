"""Structured contributor attribution (ADR-PRL-0009) — pure tests.

The second identity pillar: `agent_id` ≠ `model_id`. A logical contributor keeps its
identity across a change of carrier (provider/model/adapter/run). Legacy acts (no
agent_id) read with `agent_id = None` — no inference, unknown means unknown.
"""

from __future__ import annotations

import pytest

from prl.collectors import ConsultationAdapter, make_resolution
from prl.types import MEF, Carrier, ConsultationNode, from_entry, to_entry


class _FakeClient:
    provider = "openai"

    def complete(self, prompt, *, model):
        return "native answer"


# --- agent_id is the logical contributor, distinct from the carrier ---------

def test_consult_sets_agent_id_distinct_from_carrier():
    node = ConsultationAdapter().consult(
        _FakeClient(), subject_id="KO-7", prompt="p", model="gpt-4o", agent_id="agent.architect")
    assert node.mef.agent_id == "agent.architect"
    assert node.mef.carrier.provider == "openai" and node.mef.carrier.model == "gpt-4o"
    assert node.mef.carrier.adapter == "consult-adapter v1"
    # agent_id is NOT the carrier
    assert node.mef.agent_id != node.mef.carrier.short()


def test_same_agent_id_across_two_carriers():
    a = ConsultationAdapter()
    n1 = a.consult(_FakeClient(), subject_id="KO", prompt="p", model="gpt-4o", agent_id="agent.architect")
    n2 = a.consult(_FakeClient(), subject_id="KO", prompt="p", model="gpt-5", agent_id="agent.architect")
    assert n1.mef.agent_id == n2.mef.agent_id == "agent.architect"   # one logical contributor
    assert n1.mef.carrier.short() == "openai:gpt-4o"
    assert n2.mef.carrier.short() == "openai:gpt-5"                  # carrier differs
    assert n1.mef.carrier != n2.mef.carrier


def test_resolution_human_agent_id_has_no_type_prefix():
    r = make_resolution(target_claim_id="c", decision="accepted", agent_id="mohamed.azizi")
    assert r.mef.agent_id == "mohamed.azizi"
    assert not r.mef.agent_id.startswith("human:")          # type is NOT in the id
    assert r.mef.carrier.provider == "human"                # human-ness lives in the carrier
    assert r.mef.carrier.model is None and r.mef.carrier.adapter is None


def test_agent_id_is_required_at_the_producer():
    with pytest.raises(TypeError):
        make_resolution(target_claim_id="c", decision="accepted")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        ConsultationAdapter().consult(_FakeClient(), subject_id="K", prompt="p", model="m")  # type: ignore[call-arg]


# --- backward compatibility: legacy acts read, no inference -----------------

def test_legacy_mef_has_no_agent_id_and_is_not_inferred():
    legacy = MEF(claim_id="c1", regime="observed.declared", confidence=0.5, contested=False,
                 producer="openai:gpt-4o (consult-adapter v1)")
    assert legacy.agent_id is None and legacy.carrier is None
    node = ConsultationNode(consultation_id="x", subject_id="KO", mode="observation",
                            answer="a", mef=legacy)
    draft = to_entry(node, shard="s", session_id="r")
    # byte-identity: an agent_id-less node serializes WITHOUT agent_id/carrier keys (exclude_none)
    assert "agent_id" not in draft.content and "carrier" not in draft.content
    back = from_entry(draft)
    assert back.mef.agent_id is None  # never fabricated / back-derived


def test_round_trip_preserves_agent_id_and_carrier():
    node = ConsultationAdapter().consult(
        _FakeClient(), subject_id="KO", prompt="p", model="gpt-4o", agent_id="agent.architect")
    back = from_entry(to_entry(node, shard="s", session_id="r"))
    assert back.mef.agent_id == "agent.architect"
    assert back.mef.carrier == Carrier(provider="openai", model="gpt-4o", adapter="consult-adapter v1")
