"""Tests for P11 — ComputeAttestation (input-output binding)."""
import pytest
from unittest.mock import patch
from dataclasses import asdict

from dsm.attestation import (
    ComputeAttestation,
    NACL_AVAILABLE,
    create_attestation,
    sign_attestation,
    verify_attestation,
    verify_attestation_against_data,
    hash_content,
    _serialize,
)


def test_create_attestation_produces_valid_hashes():
    """create_attestation() produces valid hashes (deterministic when timestamp is fixed)."""
    fixed_ts = "2026-01-15T12:00:00Z"
    with patch("dsm.attestation.datetime") as dt_mock:
        dt_mock.now.return_value.isoformat.return_value = fixed_ts
        att1 = create_attestation(
            agent_id="agent1",
            raw_input="hello",
            raw_output="world",
            model_id="model-v1",
        )
        att2 = create_attestation(
            agent_id="agent1",
            raw_input="hello",
            raw_output="world",
            model_id="model-v1",
        )
    assert att1.input_hash == att2.input_hash
    assert att1.output_hash == att2.output_hash
    assert len(att1.attestation_hash) == 64
    assert att1.attestation_hash == att2.attestation_hash
    assert att1.attestation_id != att2.attestation_id  # uuid differs


def test_create_attestation_deterministic_hashes():
    """Input/output hashes are deterministic; attestation_hash is consistent for same payload."""
    att = create_attestation(
        agent_id="a1",
        raw_input=b"input",
        raw_output={"result": 42},
        model_id="m1",
    )
    assert att.input_hash == hash_content(_serialize(b"input"))
    assert att.output_hash == hash_content(_serialize({"result": 42}))
    payload = att.input_hash + att.output_hash + att.model_id + att.agent_id + att.timestamp
    import hashlib
    expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert att.attestation_hash == expected


def test_verify_attestation_valid():
    """verify_attestation() returns VALID for untampered attestation."""
    att = create_attestation(
        agent_id="a1",
        raw_input="in",
        raw_output="out",
        model_id="m1",
    )
    result = verify_attestation(att)
    assert result["status"] == "VALID"
    assert result["signature_verified"] is None


def test_verify_attestation_hash_mismatch():
    """verify_attestation() returns HASH_MISMATCH when attestation_hash is tampered."""
    att = create_attestation(
        agent_id="a1",
        raw_input="in",
        raw_output="out",
        model_id="m1",
    )
    d = asdict(att)
    d["attestation_hash"] = "a" * 64
    att_tampered = ComputeAttestation(**d)
    result = verify_attestation(att_tampered)
    assert result["status"] == "HASH_MISMATCH"
    assert result["signature_verified"] is None


@pytest.mark.skipif(
    not NACL_AVAILABLE,
    reason="PyNaCl required for signature tests",
)
def test_verify_attestation_signature_invalid_when_tampered():
    """verify_attestation() returns SIGNATURE_INVALID when signature is tampered."""
    import tempfile
    from dsm.agent import DarylAgent

    tmp = tempfile.mkdtemp()
    agent = DarylAgent(agent_id="attest_agent", data_dir=tmp, signing_dir=tmp + "/keys")
    agent.generate_keys()
    att = create_attestation(
        agent_id="attest_agent",
        raw_input="in",
        raw_output="out",
        model_id="m1",
    )
    att = sign_attestation(att, agent._signing)
    att_tampered = ComputeAttestation(
        attestation_id=att.attestation_id,
        agent_id=att.agent_id,
        input_hash=att.input_hash,
        output_hash=att.output_hash,
        model_id=att.model_id,
        timestamp=att.timestamp,
        attestation_hash=att.attestation_hash,
        entry_hash=att.entry_hash,
        signature="f" * 64,
        public_key=att.public_key,
        dispatch_hash=att.dispatch_hash,
    )
    result = verify_attestation(att_tampered)
    assert result["status"] == "SIGNATURE_INVALID"
    assert result["signature_verified"] is False


@pytest.mark.skipif(
    not NACL_AVAILABLE,
    reason="PyNaCl required for signature tests",
)
def test_verify_attestation_signed_valid():
    """verify_attestation() returns VALID + signature_verified=True for correctly signed attestation."""
    import tempfile
    from dsm.agent import DarylAgent

    tmp = tempfile.mkdtemp()
    agent = DarylAgent(agent_id="sig_agent", data_dir=tmp, signing_dir=tmp + "/keys")
    agent.generate_keys()
    att = create_attestation(
        agent_id="sig_agent",
        raw_input="req",
        raw_output="resp",
        model_id="gpt-4",
    )
    att = sign_attestation(att, agent._signing)
    result = verify_attestation(att)
    assert result["status"] == "VALID"
    assert result["signature_verified"] is True


def test_verify_attestation_against_data_confirmed():
    """verify_attestation_against_data() returns CONFIRMED when data matches."""
    raw_in = {"prompt": "hello"}
    raw_out = "hi there"
    att = create_attestation(agent_id="a1", raw_input=raw_in, raw_output=raw_out, model_id="m1")
    result = verify_attestation_against_data(att, raw_in, raw_out)
    assert result["status"] == "CONFIRMED"


def test_verify_attestation_against_data_input_mismatch():
    """verify_attestation_against_data() returns INPUT_MISMATCH when input differs."""
    raw_in = "original input"
    raw_out = "output"
    att = create_attestation(agent_id="a1", raw_input=raw_in, raw_output=raw_out, model_id="m1")
    result = verify_attestation_against_data(att, "different input", raw_out)
    assert result["status"] == "INPUT_MISMATCH"


def test_verify_attestation_against_data_output_mismatch():
    """verify_attestation_against_data() returns OUTPUT_MISMATCH when output differs."""
    raw_in = "input"
    raw_out = "original output"
    att = create_attestation(agent_id="a1", raw_input=raw_in, raw_output=raw_out, model_id="m1")
    result = verify_attestation_against_data(att, raw_in, "different output")
    assert result["status"] == "OUTPUT_MISMATCH"


def test_compute_attestation_round_trip():
    """ComputeAttestation round-trips through to_dict/from_dict."""
    att = create_attestation(
        agent_id="a1",
        raw_input="x",
        raw_output="y",
        model_id="m1",
        entry_hash="eh123",
        dispatch_hash="dh456",
    )
    d = att.to_dict()
    att2 = ComputeAttestation.from_dict(d)
    assert att2.attestation_id == att.attestation_id
    assert att2.agent_id == att.agent_id
    assert att2.input_hash == att.input_hash
    assert att2.output_hash == att.output_hash
    assert att2.model_id == att.model_id
    assert att2.entry_hash == att.entry_hash
    assert att2.dispatch_hash == att.dispatch_hash


def test_attestation_with_dispatch_hash_preserves_p10():
    """Attestation with dispatch_hash preserves P10 causal binding."""
    att = create_attestation(
        agent_id="agent_b",
        raw_input="task",
        raw_output="done",
        model_id="m1",
        dispatch_hash="dispatch_abc123",
    )
    assert att.dispatch_hash == "dispatch_abc123"
    d = att.to_dict()
    assert d["dispatch_hash"] == "dispatch_abc123"
    att2 = ComputeAttestation.from_dict(d)
    assert att2.dispatch_hash == "dispatch_abc123"
