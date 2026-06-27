"""R-consult v3 (ADR-PRL-0008) — pure tests: real-agent boundary mapping.

The one hypothesis v3 proves — *a real agent produces a certified Knowledge Act without
knowing PRL* — is exercised here with a FakeAgentClient (no network). The certified
write + CLI e2e (with the fake client) live in test_consultation_store.py (kernel). The
real OpenAI transcript is the manual acceptance gate (credentials required).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from prl.collectors import AgentClient, AgentClientError, ConsultationAdapter, OpenAIClient


class FakeAgentClient:
    """A real-agent stand-in: returns a canned native answer, no network."""

    provider = "openai"

    def __init__(self, answer: str = "use prev_hash"):
        self._answer = answer

    def complete(self, prompt: str, *, model: str) -> str:
        return self._answer


def test_fake_client_satisfies_protocol():
    assert isinstance(FakeAgentClient(), AgentClient)


def test_consult_maps_real_answer_to_observation():
    node = ConsultationAdapter().consult(
        FakeAgentClient("expose it via Dial record"),
        subject_id="ko-1", prompt="Should Storage.append expose prev_hash?", model="gpt-5",
    )
    assert node.mode == "observation"                       # default: not a claim
    assert node.answer == "expose it via Dial record"       # the model's native answer
    assert node.mef.producer == "openai:gpt-5 (consult-adapter v1)"  # provider+model+adapter version
    assert node.mef.confidence == 1.0                       # confidence in the Observation event
    assert node.subject_id == "ko-1"


def test_consult_proposal_only_on_explicit_flag():
    node = ConsultationAdapter().consult(
        FakeAgentClient(), subject_id="ko-1", prompt="?", model="gpt-5", propose=True)
    assert node.mode == "proposal"


def test_consult_confidence_override():
    node = ConsultationAdapter().consult(
        FakeAgentClient(), subject_id="ko-1", prompt="?", model="gpt-5", confidence=0.5)
    assert node.mef.confidence == 0.5


def test_consult_empty_producer_impossible():
    # provider is part of producer; an empty answer is fine, but the MEF still needs a producer.
    # (Sanity: the adapter always builds a non-empty producer from provider+model.)
    node = ConsultationAdapter().consult(FakeAgentClient(""), subject_id="ko-1", prompt="?",
                                         model="gpt-5")
    assert node.mef.producer.strip()
    assert node.answer == ""  # empty answer is recorded faithfully (Observation of the event)


def test_openai_client_missing_sdk_is_actionable():
    try:
        import openai  # noqa: F401
    except ImportError:
        with pytest.raises(AgentClientError):
            OpenAIClient()
    else:  # pragma: no cover
        pytest.skip("openai SDK installed")


def test_mef_still_complete_or_refuse_through_consult():
    # confidence out of range must still be refused even via the consult path
    with pytest.raises(ValidationError):
        ConsultationAdapter().consult(FakeAgentClient(), subject_id="ko-1", prompt="?",
                                      model="gpt-5", confidence=1.5)
