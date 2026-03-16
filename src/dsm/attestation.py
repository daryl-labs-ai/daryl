"""
Compute Attestation (P11) — Input-output binding for agent compute.

Proves the relationship between input and output:
- input_hash: SHA-256 of raw request/input
- output_hash: SHA-256 of raw response/output
- model_id: which model/version produced the output
- attestation_hash: SHA-256 of all fields combined
- Optionally signed with Ed25519 (P9)

Does NOT prove the computation was correct (requires TEEs).
DOES prove: the agent claims this output for this input, and the claim is signed.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional, Union

try:
    import nacl.signing
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False


def hash_content(raw: bytes) -> str:
    """SHA-256 hash of raw content."""
    return hashlib.sha256(raw).hexdigest()


def _serialize(data: Union[bytes, str, dict]) -> bytes:
    """Serialize to bytes for hashing."""
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    if isinstance(data, dict):
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return str(data).encode("utf-8")


@dataclass
class ComputeAttestation:
    """Attestation binding input to output for a specific computation."""

    attestation_id: str
    agent_id: str
    input_hash: str
    output_hash: str
    model_id: str
    timestamp: str
    attestation_hash: str
    entry_hash: Optional[str] = None  # pointer to DSM log entry
    signature: Optional[str] = None  # Ed25519 signature
    public_key: Optional[str] = None  # Ed25519 public key
    dispatch_hash: Optional[str] = None  # P10 causal binding

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "ComputeAttestation":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def create_attestation(
    agent_id: str,
    raw_input: Union[bytes, str, dict],
    raw_output: Union[bytes, str, dict],
    model_id: str,
    entry_hash: Optional[str] = None,
    dispatch_hash: Optional[str] = None,
) -> ComputeAttestation:
    """Create a compute attestation binding input to output.

    Args:
        agent_id: The agent creating the attestation
        raw_input: Raw input data (request, prompt, etc.)
        raw_output: Raw output data (response, result, etc.)
        model_id: Model/version identifier
        entry_hash: Optional DSM entry hash pointer
        dispatch_hash: Optional P10 dispatch hash for causal binding

    Returns:
        ComputeAttestation with computed hashes
    """
    input_hash = hash_content(_serialize(raw_input))
    output_hash = hash_content(_serialize(raw_output))
    timestamp = datetime.now(timezone.utc).isoformat()
    attestation_id = f"att_{uuid.uuid4().hex[:12]}"

    # attestation_hash = SHA-256(input_hash + output_hash + model_id + agent_id + timestamp)
    payload = input_hash + output_hash + model_id + agent_id + timestamp
    attestation_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    return ComputeAttestation(
        attestation_id=attestation_id,
        agent_id=agent_id,
        input_hash=input_hash,
        output_hash=output_hash,
        model_id=model_id,
        timestamp=timestamp,
        attestation_hash=attestation_hash,
        entry_hash=entry_hash,
        dispatch_hash=dispatch_hash,
    )


def sign_attestation(attestation: ComputeAttestation, signing) -> ComputeAttestation:
    """Sign an attestation with Ed25519 (P9 signing module).

    Args:
        attestation: The attestation to sign
        signing: AgentSigning instance

    Returns:
        New attestation with signature and public_key fields set
    """
    sig = signing.sign_receipt(attestation.attestation_hash)
    pub = signing.get_public_key()
    return ComputeAttestation(
        **{**asdict(attestation), "signature": sig, "public_key": pub}
    )


def verify_attestation(attestation: ComputeAttestation) -> dict:
    """Verify attestation hash integrity and optional signature.

    Returns:
        {"status": "VALID"|"HASH_MISMATCH"|"SIGNATURE_INVALID",
         "signature_verified": True|False|None}
    """
    # Recompute attestation hash
    payload = (
        attestation.input_hash
        + attestation.output_hash
        + attestation.model_id
        + attestation.agent_id
        + attestation.timestamp
    )
    expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    if expected != attestation.attestation_hash:
        return {"status": "HASH_MISMATCH", "signature_verified": None}

    # Check signature if present
    if attestation.signature and attestation.public_key:
        if not NACL_AVAILABLE:
            return {"status": "VALID", "signature_verified": None}
        try:
            verify_key = nacl.signing.VerifyKey(bytes.fromhex(attestation.public_key))
            msg = attestation.attestation_hash.encode("utf-8")
            signed = bytes.fromhex(attestation.signature) + msg
            verify_key.verify(signed)
            return {"status": "VALID", "signature_verified": True}
        except Exception:
            return {"status": "SIGNATURE_INVALID", "signature_verified": False}

    return {"status": "VALID", "signature_verified": None}


def verify_attestation_against_data(
    attestation: ComputeAttestation,
    raw_input: Union[bytes, str, dict],
    raw_output: Union[bytes, str, dict],
) -> dict:
    """Verify that attestation matches actual input/output data.

    Third party can re-hash the raw data and compare.

    Returns:
        {"status": "CONFIRMED"|"INPUT_MISMATCH"|"OUTPUT_MISMATCH"|"BOTH_MISMATCH"}
    """
    actual_input_hash = hash_content(_serialize(raw_input))
    actual_output_hash = hash_content(_serialize(raw_output))

    input_ok = actual_input_hash == attestation.input_hash
    output_ok = actual_output_hash == attestation.output_hash

    if input_ok and output_ok:
        return {"status": "CONFIRMED"}
    elif not input_ok and not output_ok:
        return {"status": "BOTH_MISMATCH"}
    elif not input_ok:
        return {"status": "INPUT_MISMATCH"}
    else:
        return {"status": "OUTPUT_MISMATCH"}
