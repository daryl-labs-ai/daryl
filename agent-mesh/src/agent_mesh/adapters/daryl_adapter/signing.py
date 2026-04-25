"""Signing adapter — Ed25519 via PyNaCl. Reimplemented locally, no daryl imports."""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from nacl import signing as nacl_signing
from nacl.exceptions import BadSignatureError


# ---------- Primitives ----------

def canonicalize_payload(d: dict) -> bytes:
    """Canonical UTF-8 byte serialization of a dict.

    Per ADR-0002, delegates to dsm_primitives.canonical_json.
    Note: output now uses ensure_ascii=True (was False before V4-A.3).
    Breaking change vs pre-V4-A.3 mesh; intentional per ADR-0002.
    """
    from dsm_primitives import canonical_json
    return canonical_json(d)


def compute_content_hash(content: dict) -> str:
    """Compute the canonical content hash of a dict.

    Per ADR-0002, delegates to dsm_primitives.hash_canonical and returns
    'v1:<hex>'. Strict dict input only.
    """
    from dsm_primitives import hash_canonical
    if not isinstance(content, dict):
        raise TypeError(
            f"content must be a dict (per ADR-0002 strict schema); got {type(content)}"
        )
    return hash_canonical(content)


def generate_keypair() -> tuple[str, str]:
    sk = nacl_signing.SigningKey.generate()
    pk = sk.verify_key
    return (
        base64.b64encode(bytes(sk)).decode("ascii"),
        base64.b64encode(bytes(pk)).decode("ascii"),
    )


def sign_bytes(data: bytes, private_key_b64: str) -> str:
    sk = nacl_signing.SigningKey(base64.b64decode(private_key_b64))
    sig = sk.sign(data).signature
    return base64.b64encode(sig).decode("ascii")


def verify_bytes(data: bytes, signature_b64: str, public_key_b64: str) -> bool:
    try:
        vk = nacl_signing.VerifyKey(base64.b64decode(public_key_b64))
        vk.verify(data, base64.b64decode(signature_b64))
        return True
    except (BadSignatureError, ValueError, Exception):
        return False


# ---------- Dataclasses ----------

@dataclass
class SignedContribution:
    agent_id: str
    key_id: str
    mission_id: str
    task_id: str
    contribution_id: str
    contribution_type: str
    content_hash: str
    created_at: str
    signature: str


@dataclass
class VerificationResult:
    valid: bool
    reason: str | None


@dataclass
class KeyRegistration:
    agent_id: str
    key_id: str
    public_key_b64: str
    registered_at: str


@dataclass
class VerifyResult:
    valid: bool
    reason: str | None


@dataclass
class KeyRotation:
    agent_id: str
    old_key_id: str
    new_key_id: str
    rotated_at: str


# ---------- High-level helpers ----------

def _canonical_signing_payload(
    agent_id: str,
    key_id: str,
    mission_id: str,
    task_id: str,
    contribution_id: str,
    contribution_type: str,
    content_hash: str,
    created_at: str,
) -> dict:
    return {
        "schema_version": "signing.v1",
        "agent_id": agent_id,
        "key_id": key_id,
        "mission_id": mission_id,
        "task_id": task_id,
        "contribution_id": contribution_id,
        "contribution_type": contribution_type,
        "content_hash": content_hash,
        "created_at": created_at,
    }


def sign_contribution(
    private_key_b64: str,
    agent_id: str,
    key_id: str,
    mission_id: str,
    task_id: str,
    contribution_id: str,
    contribution_type: str,
    content_hash: str,
    created_at: str,
) -> SignedContribution:
    payload = _canonical_signing_payload(
        agent_id, key_id, mission_id, task_id, contribution_id, contribution_type, content_hash, created_at
    )
    signature = sign_bytes(canonicalize_payload(payload), private_key_b64)
    return SignedContribution(
        agent_id=agent_id,
        key_id=key_id,
        mission_id=mission_id,
        task_id=task_id,
        contribution_id=contribution_id,
        contribution_type=contribution_type,
        content_hash=content_hash,
        created_at=created_at,
        signature=signature,
    )


def verify_signed_contribution(signed: SignedContribution, public_key_b64: str) -> VerificationResult:
    payload = _canonical_signing_payload(
        signed.agent_id,
        signed.key_id,
        signed.mission_id,
        signed.task_id,
        signed.contribution_id,
        signed.contribution_type,
        signed.content_hash,
        signed.created_at,
    )
    ok = verify_bytes(canonicalize_payload(payload), signed.signature, public_key_b64)
    return VerificationResult(valid=ok, reason=None if ok else "signature_invalid")


# ---------- Adapter class ----------

def _derive_key_id(public_key_b64: str) -> str:
    return "key_" + hashlib.sha256(public_key_b64.encode("utf-8")).hexdigest()[:12]


class SigningAdapter:
    def __init__(self) -> None:
        self._keys: dict[str, str] = {}
        self._key_ids: dict[str, str] = {}

    def register_agent_key(self, agent_id: str, public_key_b64: str) -> KeyRegistration:
        if agent_id in self._keys:
            raise ValueError(f"agent already registered: {agent_id}")
        key_id = _derive_key_id(public_key_b64)
        self._keys[agent_id] = public_key_b64
        self._key_ids[agent_id] = key_id
        from datetime import datetime, timezone
        return KeyRegistration(
            agent_id=agent_id,
            key_id=key_id,
            public_key_b64=public_key_b64,
            registered_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    def verify_contribution(self, agent_id: str, payload: dict, signature_b64: str) -> VerifyResult:
        pk = self._keys.get(agent_id)
        if pk is None:
            return VerifyResult(valid=False, reason="agent_unknown")
        ok = verify_bytes(canonicalize_payload(payload), signature_b64, pk)
        return VerifyResult(valid=ok, reason=None if ok else "signature_invalid")

    def rotate_key(self, agent_id: str, new_public_key_b64: str) -> KeyRotation:
        if agent_id not in self._keys:
            raise ValueError(f"unknown agent: {agent_id}")
        old_key_id = self._key_ids[agent_id]
        new_key_id = _derive_key_id(new_public_key_b64)
        self._keys[agent_id] = new_public_key_b64
        self._key_ids[agent_id] = new_key_id
        from datetime import datetime, timezone
        return KeyRotation(
            agent_id=agent_id,
            old_key_id=old_key_id,
            new_key_id=new_key_id,
            rotated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
