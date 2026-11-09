"""
Cross-Agent Trust Receipts (P6).

Portable proof of work: Agent B issues a TaskReceipt; Agent A stores it.
Third parties can verify the receipt against B's DSM.
P9: optional Ed25519 signature and public_key on receipt.

P1 fix: a receipt hash is unkeyed, so anyone can edit a receipt and
recompute it. A receipt is therefore only INTACT when its signature verifies
under a public key the VERIFIER trusts (imported out of band); the key
embedded in the receipt is never trusted on its own. Without a trusted key
the best possible verdict is UNAUTHENTICATED. dispatch_hash / routing_hash
are now covered by receipt_hash when present.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

try:
    import nacl.signing
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False

from .core.models import Entry
from .core.storage import Storage
from .status import ReceiptStatus, StorageReceiptStatus

logger = logging.getLogger(__name__)


def _receipt_payload(receipt: "TaskReceipt") -> dict:
    payload = {
        "receipt_id": receipt.receipt_id,
        "issuer_agent_id": receipt.issuer_agent_id,
        "task_description": receipt.task_description,
        "entry_id": receipt.entry_id,
        "entry_hash": receipt.entry_hash,
        "shard_id": receipt.shard_id,
        "shard_tip_hash": receipt.shard_tip_hash,
        "shard_entry_count": receipt.shard_entry_count,
        "timestamp": receipt.timestamp,
    }
    # Causal bindings are covered only when present, so receipts without them
    # keep the exact same hash as before.
    if getattr(receipt, "dispatch_hash", None) is not None:
        payload["dispatch_hash"] = receipt.dispatch_hash
    if getattr(receipt, "routing_hash", None) is not None:
        payload["routing_hash"] = receipt.routing_hash
    return payload


def _compute_receipt_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TaskReceipt:
    def __init__(
        self,
        receipt_id: str,
        issuer_agent_id: str,
        task_description: str,
        entry_id: str,
        entry_hash: str,
        shard_id: str,
        shard_tip_hash: str,
        shard_entry_count: int,
        timestamp: str,
        receipt_hash: str,
        signature: Optional[str] = None,
        public_key: Optional[str] = None,
        dispatch_hash: Optional[str] = None,
        routing_hash: Optional[str] = None,
    ):
        self.receipt_id = receipt_id
        self.issuer_agent_id = issuer_agent_id
        self.task_description = task_description
        self.entry_id = entry_id
        self.entry_hash = entry_hash
        self.shard_id = shard_id
        self.shard_tip_hash = shard_tip_hash
        self.shard_entry_count = shard_entry_count
        self.timestamp = timestamp
        self.receipt_hash = receipt_hash
        self.signature = signature
        self.public_key = public_key
        self.dispatch_hash = dispatch_hash
        self.routing_hash = routing_hash

    def to_dict(self) -> dict:
        out = {
            "receipt_id": self.receipt_id,
            "issuer_agent_id": self.issuer_agent_id,
            "task_description": self.task_description,
            "entry_id": self.entry_id,
            "entry_hash": self.entry_hash,
            "shard_id": self.shard_id,
            "shard_tip_hash": self.shard_tip_hash,
            "shard_entry_count": self.shard_entry_count,
            "timestamp": self.timestamp,
            "receipt_hash": self.receipt_hash,
        }
        if self.signature is not None:
            out["signature"] = self.signature
        if self.public_key is not None:
            out["public_key"] = self.public_key
        if self.dispatch_hash is not None:
            out["dispatch_hash"] = self.dispatch_hash
        if self.routing_hash is not None:
            out["routing_hash"] = self.routing_hash
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "TaskReceipt":
        return cls(
            receipt_id=d["receipt_id"],
            issuer_agent_id=d["issuer_agent_id"],
            task_description=d["task_description"],
            entry_id=d["entry_id"],
            entry_hash=d["entry_hash"],
            shard_id=d["shard_id"],
            shard_tip_hash=d["shard_tip_hash"],
            shard_entry_count=d["shard_entry_count"],
            timestamp=d["timestamp"],
            receipt_hash=d["receipt_hash"],
            signature=d.get("signature"),
            public_key=d.get("public_key"),
            dispatch_hash=d.get("dispatch_hash"),
            routing_hash=d.get("routing_hash"),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "TaskReceipt":
        return cls.from_dict(json.loads(s))


def issue_receipt(
    storage: Storage,
    agent_id: str,
    entry_id: str,
    shard_id: str,
    task_description: str,
    dispatch_hash: Optional[str] = None,
    routing_hash: Optional[str] = None,
    signing=None,
) -> TaskReceipt:
    """Issue a receipt for an entry. If `signing` (an AgentSigning with a
    keypair) is given, the receipt is signed; an unsigned receipt can never
    verify as INTACT."""
    entries = storage.read(shard_id, limit=10**6)
    entry = next((e for e in entries if e.id == entry_id), None)
    if not entry:
        raise ValueError(f"Entry {entry_id} not found in shard {shard_id}")
    tip_entries = storage.read(shard_id, limit=1)
    shard_tip_hash = tip_entries[0].hash if tip_entries else ""
    shard_entry_count = len(entries)
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    receipt = TaskReceipt(
        receipt_id=str(uuid4()),
        issuer_agent_id=agent_id,
        task_description=task_description,
        entry_id=entry_id,
        entry_hash=entry.hash or "",
        shard_id=shard_id,
        shard_tip_hash=shard_tip_hash,
        shard_entry_count=shard_entry_count,
        timestamp=timestamp,
        receipt_hash="",
        dispatch_hash=dispatch_hash,
        routing_hash=routing_hash,
    )
    receipt.receipt_hash = _compute_receipt_hash(_receipt_payload(receipt))
    if signing is not None:
        receipt.signature = signing.sign_receipt(receipt.receipt_hash)
        receipt.public_key = signing.get_public_key()
    return receipt


def _verify_receipt_signature(receipt: TaskReceipt, public_key: str) -> bool:
    """Verify the receipt's Ed25519 signature over receipt_hash with `public_key`."""
    from .checkpoint import ed25519_verify

    sig = getattr(receipt, "signature", None)
    if not sig or not NACL_AVAILABLE:
        return False
    return ed25519_verify(public_key, sig, receipt.receipt_hash)


def verify_receipt(receipt: TaskReceipt, trusted_public_key: Optional[str] = None) -> dict:
    """Verify a receipt.

    trusted_public_key: hex Ed25519 key of the issuer, obtained out of band
        (e.g. DarylAgent.import_agent_key). Required for an INTACT verdict.

    Status (ReceiptStatus):
        TAMPERED          receipt_hash does not match the content
        SIGNATURE_INVALID signature does not verify (under the trusted key, or
                          under the embedded key when no trusted key is given)
        UNTRUSTED_KEY     signed by a key other than the trusted one
        UNSIGNED          trusted key given, but the receipt is not signed
        UNAUTHENTICATED   content consistent, but no trusted key: proves nothing
        INTACT            content consistent AND signed by the trusted key

    Fields: signature_verified (True/False/None), signer_trusted, authenticated.
    """
    expected = _compute_receipt_hash(_receipt_payload(receipt))
    sig = getattr(receipt, "signature", None)
    embedded = getattr(receipt, "public_key", None)
    result = {
        "receipt_id": receipt.receipt_id,
        "status": ReceiptStatus.TAMPERED,
        "issuer": receipt.issuer_agent_id,
        "task": receipt.task_description,
        "signature_verified": None,
        "signer_trusted": False,
        "authenticated": False,
    }
    if expected != receipt.receipt_hash:
        return result

    if trusted_public_key is None:
        # Best effort only: an embedded key proves nothing about the issuer.
        if sig and embedded:
            ok = _verify_receipt_signature(receipt, embedded)
            result["signature_verified"] = ok
            if not ok:
                result["status"] = ReceiptStatus.SIGNATURE_INVALID
                return result
        result["status"] = ReceiptStatus.UNAUTHENTICATED
        return result

    if not sig:
        result["status"] = ReceiptStatus.UNSIGNED
        return result
    if embedded and embedded.lower() != trusted_public_key.lower():
        result["signature_verified"] = _verify_receipt_signature(receipt, embedded)
        result["status"] = ReceiptStatus.UNTRUSTED_KEY
        return result
    ok = _verify_receipt_signature(receipt, trusted_public_key)
    result["signature_verified"] = ok
    if not ok:
        result["status"] = ReceiptStatus.SIGNATURE_INVALID
        return result
    result["signer_trusted"] = True
    result["authenticated"] = True
    result["status"] = ReceiptStatus.INTACT
    return result


def verify_receipt_against_storage(storage: Storage, receipt: TaskReceipt) -> dict:
    entries = storage.read(receipt.shard_id, limit=10**6)
    if not entries:
        return {"receipt_id": receipt.receipt_id, "status": StorageReceiptStatus.SHARD_MISSING, "entry_found": False, "hash_matches": False}
    entry = next((e for e in entries if e.id == receipt.entry_id), None)
    if not entry:
        return {"receipt_id": receipt.receipt_id, "status": StorageReceiptStatus.ENTRY_MISSING, "entry_found": False, "hash_matches": False}
    hash_matches = (entry.hash or "") == receipt.entry_hash
    if not hash_matches:
        return {"receipt_id": receipt.receipt_id, "status": StorageReceiptStatus.HASH_MISMATCH, "entry_found": True, "hash_matches": False}
    return {"receipt_id": receipt.receipt_id, "status": StorageReceiptStatus.CONFIRMED, "entry_found": True, "hash_matches": True}


def store_external_receipt(
    storage: Storage,
    receipt: TaskReceipt,
    receiver_agent_id: str,
    shard_id: str = "receipts",
) -> Entry:
    entry = Entry(
        id=str(uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id=receiver_agent_id,
        source=receiver_agent_id,
        content=receipt.to_json(),
        shard=shard_id,
        hash="",
        prev_hash=None,
        metadata={
            "event_type": "external_receipt",
            "receipt_id": receipt.receipt_id,
            "issuer": receipt.issuer_agent_id,
            "task": receipt.task_description,
        },
        version="v2.0",
    )
    return storage.append(entry)


def list_received_receipts(storage: Storage, shard_id: str = "receipts") -> List[TaskReceipt]:
    entries = storage.read(shard_id, limit=10**6)
    result = []
    for e in entries:
        if (e.metadata or {}).get("event_type") != "external_receipt":
            continue
        try:
            result.append(TaskReceipt.from_json(e.content))
        except (json.JSONDecodeError, KeyError):
            continue
    return result
