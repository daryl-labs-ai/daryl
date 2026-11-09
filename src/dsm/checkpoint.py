"""
Client-held shard checkpoints.

The integrity pin ({shard}_last_hash.json) lives in the same directory as the
data it protects: whoever can truncate a shard can also delete or rewrite the
pin. The kernel hash chain is unkeyed: whoever can rewrite the shard can also
recompute every hash. Neither can be fixed from inside the data directory.

A checkpoint is the out-of-band answer: a small record

    {"v": 1, "shard_id", "entry_count", "last_hash", "created_at",
     "signature"?, "public_key"?}

that the *client* (the verifier, an auditor, another agent) keeps outside the
agent's data directory. Because each entry hash covers its predecessor, the
pair (entry_count, last_hash) commits to the whole prefix of the shard.

* Unsigned checkpoint  -> detects truncation, deletion and prefix rewrite,
  as long as the client kept the checkpoint itself.
* Signed checkpoint + trusted public key -> additionally proves the agent
  (holder of the private key) vouched for that prefix; an attacker without
  the key cannot mint a replacement checkpoint for a rewritten chain.

Verification lives in dsm.verify.verify_shard(checkpoint=..., trusted_public_key=...).
This module is outside the frozen kernel (src/dsm/core/).
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

CHECKPOINT_VERSION = 1
_SIGNED_FIELDS = ("v", "shard_id", "entry_count", "last_hash", "created_at")


def checkpoint_digest(checkpoint: Dict[str, Any]) -> str:
    """SHA-256 over the canonical signed fields of a checkpoint (hex)."""
    body = {k: checkpoint.get(k) for k in _SIGNED_FIELDS}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _chrono_hashes(storage, shard_id: str) -> list:
    out = []
    for event_data in storage.segment_manager.iter_shard_events(shard_id):
        try:
            entry = storage._entry_from_event_data(event_data)
        except (KeyError, TypeError, ValueError):
            continue
        out.append(entry.hash)
    return out


def make_checkpoint(storage, shard_id: str, signing=None) -> Dict[str, Any]:
    """Build a checkpoint of the shard's current tip, signed if `signing`
    (a dsm.signing.AgentSigning with a keypair) is given.

    The tip is read from the segments themselves, not from the pin.
    """
    hashes = _chrono_hashes(storage, shard_id)
    cp: Dict[str, Any] = {
        "v": CHECKPOINT_VERSION,
        "shard_id": shard_id,
        "entry_count": len(hashes),
        "last_hash": hashes[-1] if hashes else None,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if signing is not None:
        cp["signature"] = signing.sign_entry(checkpoint_digest(cp))
        cp["public_key"] = signing.get_public_key()
    return cp


def verify_checkpoint_signature(
    checkpoint: Dict[str, Any], trusted_public_key: str
) -> Optional[str]:
    """Check the checkpoint signature against a key the verifier trusts.

    The public key embedded in the checkpoint is never used for verification.
    Returns None if valid, otherwise a status string:
    UNSIGNED | UNTRUSTED_KEY | SIGNATURE_INVALID.
    """
    sig = checkpoint.get("signature")
    if not sig:
        return "UNSIGNED"
    embedded = checkpoint.get("public_key")
    if embedded and embedded.lower() != trusted_public_key.lower():
        return "UNTRUSTED_KEY"
    if not ed25519_verify(trusted_public_key, sig, checkpoint_digest(checkpoint)):
        return "SIGNATURE_INVALID"
    return None


def ed25519_verify(public_key_hex: str, signature_hex: str, message: str) -> bool:
    """Verify an Ed25519 signature over a UTF-8 message. False on any error."""
    try:
        import nacl.signing
    except ImportError:
        return False
    try:
        pub = bytes.fromhex(public_key_hex)
        sig = bytes.fromhex(signature_hex)
    except (ValueError, TypeError, AttributeError):
        return False
    if len(pub) != 32 or len(sig) != 64:
        return False
    try:
        nacl.signing.VerifyKey(pub).verify(message.encode("utf-8"), sig)
        return True
    except Exception:
        return False
