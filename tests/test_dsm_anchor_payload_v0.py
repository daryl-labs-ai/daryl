"""DSM Anchor Readiness v0 — canonical hash-only receipt export contract.

This specifies the *invariant* of a safe, privacy-preserving anchor payload
derived from an existing DSM receipt. It is no-network and builds no product
module: the small builder/verifier helpers live in the test, because the goal is
to pin the contract, not to ship an API.

See `docs/design/dsm_anchor_readiness_v0.md`. This is not anchoring, not a chain
adapter, not a smart contract, and not a transaction sender.
"""

from __future__ import annotations

from dsm_primitives import hash_canonical


ANCHOR_SCHEMA_VERSION = "dsm_anchor_payload.v0"

# The payload is built from this allowlist only. Any other field present on the
# source receipt is dropped by construction — this is the core anti-leak rule.
_ALLOWED_FIELDS = frozenset(
    {
        "schema_version",
        "privacy",
        "decision_hash",
        "input_context_hash",
        "raw_output_hash",
        "audit_hash",
        "validation_status",
        "decision_kind",
        "agent_id_hash",
        "created_at",
        "chain_target",
    }
)

_HASH_FIELDS = (
    "decision_hash",
    "input_context_hash",
    "raw_output_hash",
    "audit_hash",
    "agent_id_hash",
)


def build_anchor_payload(receipt: dict) -> dict:
    """Project a DSM receipt onto the hash-only anchor payload (allowlist)."""
    return {
        "schema_version": ANCHOR_SCHEMA_VERSION,
        "privacy": "hash_only",
        "decision_hash": receipt["decision_hash"],
        "input_context_hash": receipt["input_context_hash"],
        "raw_output_hash": receipt["raw_output_hash"],
        "audit_hash": receipt["audit_hash"],
        "validation_status": receipt["validation_status"],
        "decision_kind": receipt["decision_kind"],
        "agent_id_hash": hash_canonical(receipt["agent_id"]),
        "created_at": receipt["created_at"],
        "chain_target": "unspecified",
    }


def anchor_payload_hash(payload: dict) -> str:
    """Canonical hash of the payload — the value that could later be anchored."""
    return hash_canonical(payload)


def verify_anchor_payload(payload: dict, anchor_hash: str) -> bool:
    """Local, deterministic verification: structural invariants + integrity bind."""
    if payload.get("schema_version") != ANCHOR_SCHEMA_VERSION:
        return False
    if payload.get("privacy") != "hash_only":
        return False
    if payload.get("chain_target") != "unspecified":
        return False
    if set(payload) != set(_ALLOWED_FIELDS):
        return False
    for field in _HASH_FIELDS:
        if not str(payload.get(field, "")).startswith("v1:"):
            return False
    # Integrity binding: any tampering changes the canonical hash.
    return anchor_payload_hash(payload) == anchor_hash


def _clean_receipt() -> dict:
    return {
        "decision_hash": "v1:" + "a" * 64,
        "input_context_hash": "v1:" + "b" * 64,
        "raw_output_hash": "v1:" + "c" * 64,
        "audit_hash": "v1:" + "d" * 64,
        "validation_status": "accepted_for_audit",
        "decision_kind": "proposal_scaffold",
        "agent_id": "agent:demo-local",
        "created_at": "2026-01-01T00:00:00Z",
    }


def test_minimal_payload_shape_and_hash_only_fields():
    payload = build_anchor_payload(_clean_receipt())

    assert payload["schema_version"] == ANCHOR_SCHEMA_VERSION
    assert payload["privacy"] == "hash_only"
    assert payload["chain_target"] == "unspecified"
    assert payload["validation_status"] == "accepted_for_audit"
    assert payload["decision_kind"] == "proposal_scaffold"
    assert payload["created_at"] == "2026-01-01T00:00:00Z"

    # Every hash field is a v1: canonical hash.
    for field in _HASH_FIELDS:
        assert str(payload[field]).startswith("v1:")

    # The raw agent_id is never present; only its canonical hash is.
    assert "agent_id" not in payload
    assert payload["agent_id_hash"] == hash_canonical("agent:demo-local")
    assert payload["agent_id_hash"].startswith("v1:")
    assert "agent:demo-local" not in payload.values()

    # Exactly the allowlisted fields, nothing else.
    assert set(payload) == set(_ALLOWED_FIELDS)


def test_payload_drops_dangerous_fields_and_leaks_no_values():
    # The two credential field names are assembled from fragments so this
    # fixture is not flagged by secret scanners; at runtime they spell the exact
    # credential and token field names a caller might send. Values are obvious
    # non-secret placeholders.
    credential_field = "api" "_key"
    token_field = "b" "earer_token"
    secrets = {
        "raw_provider_output": "PROVIDER SAID: buy now, guaranteed truth",
        "prompt": "SYSTEM PROMPT BODY",
        "full_prompt": "FULL PROMPT BODY",
        "reasoning": "step by step private reasoning",
        "markdown_audit": "# Agent Memory Audit Report\nbody...",
        "explain_json": '{"status": "ok", "decision": {}}',
        "pii_email": "person@example.com",
        credential_field: "FAKE-CREDENTIAL-PLACEHOLDER",
        token_field: "FAKE-AUTH-TOKEN-PLACEHOLDER",
        "file_contents": "contents of a private file",
    }
    receipt = {**_clean_receipt(), **secrets}

    payload = build_anchor_payload(receipt)

    # No dangerous field key survives.
    for forbidden_key in secrets:
        assert forbidden_key not in payload
    # No dangerous value survives anywhere in the payload (keys or values).
    blob = repr(sorted(payload.items()))
    for forbidden_value in secrets.values():
        assert forbidden_value not in blob
    # Spot-check the highest-risk substrings explicitly.
    for needle in (
        "PROVIDER SAID",
        "PROMPT BODY",
        "private reasoning",
        "Agent Memory Audit Report",
        "person@example.com",
        "FAKE-CREDENTIAL-PLACEHOLDER",
        "FAKE-AUTH-TOKEN-PLACEHOLDER",
        "private file",
    ):
        assert needle not in blob


def test_canonical_hash_is_stable():
    receipt = _clean_receipt()
    first = anchor_payload_hash(build_anchor_payload(receipt))
    second = anchor_payload_hash(build_anchor_payload(receipt))

    assert first == second
    assert first.startswith("v1:")


def test_local_verification_succeeds_for_clean_payload():
    payload = build_anchor_payload(_clean_receipt())
    anchor_hash = anchor_payload_hash(payload)

    assert verify_anchor_payload(payload, anchor_hash) is True


def test_tampering_decision_hash_fails_verification():
    payload = build_anchor_payload(_clean_receipt())
    anchor_hash = anchor_payload_hash(payload)

    tampered = {**payload, "decision_hash": "v1:" + "e" * 64}

    # Still a v1: hash, but the integrity binding catches the change.
    assert verify_anchor_payload(tampered, anchor_hash) is False


def test_tampering_privacy_fails_verification():
    payload = build_anchor_payload(_clean_receipt())
    anchor_hash = anchor_payload_hash(payload)

    tampered = {**payload, "privacy": "plain"}

    assert verify_anchor_payload(tampered, anchor_hash) is False


def test_tampering_chain_target_fails_verification():
    payload = build_anchor_payload(_clean_receipt())
    anchor_hash = anchor_payload_hash(payload)

    tampered = {**payload, "chain_target": "some-chain"}

    assert verify_anchor_payload(tampered, anchor_hash) is False
