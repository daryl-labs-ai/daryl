"""
Cross-Agent Trust Receipts (P6).

Portable proof of work: Agent B issues a TaskReceipt; Agent A stores it.
Third parties can verify the receipt against B's DSM.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from .core.models import Entry
from .core.storage import Storage

logger = logging.getLogger(__name__)


def _receipt_payload(receipt: "TaskReceipt") -> dict:
    return {
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

    def to_dict(self) -> dict:
        return {
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
) -> TaskReceipt:
    entries = storage.read(shard_id, limit=10**6)
    entry = next((e for e in entries if e.id == entry_id), None)
    if not entry:
        raise ValueError(f"Entry {entry_id} not found in shard {shard_id}")
    tip_entries = storage.read(shard_id, limit=1)
    shard_tip_hash = tip_entries[0].hash if tip_entries else ""
    shard_entry_count = len(entries)
    timestamp = datetime.utcnow().isoformat() + "Z"
    receipt_id = str(uuid4())
    payload = {
        "receipt_id": receipt_id,
        "issuer_agent_id": agent_id,
        "task_description": task_description,
        "entry_id": entry_id,
        "entry_hash": entry.hash or "",
        "shard_id": shard_id,
        "shard_tip_hash": shard_tip_hash,
        "shard_entry_count": shard_entry_count,
        "timestamp": timestamp,
    }
    receipt_hash = _compute_receipt_hash(payload)
    return TaskReceipt(
        receipt_id=receipt_id,
        issuer_agent_id=agent_id,
        task_description=task_description,
        entry_id=entry_id,
        entry_hash=entry.hash or "",
        shard_id=shard_id,
        shard_tip_hash=shard_tip_hash,
        shard_entry_count=shard_entry_count,
        timestamp=timestamp,
        receipt_hash=receipt_hash,
    )


def verify_receipt(receipt: TaskReceipt) -> dict:
    payload = _receipt_payload(receipt)
    expected = _compute_receipt_hash(payload)
    status = "INTACT" if expected == receipt.receipt_hash else "TAMPERED"
    return {"receipt_id": receipt.receipt_id, "status": status, "issuer": receipt.issuer_agent_id, "task": receipt.task_description}


def verify_receipt_against_storage(storage: Storage, receipt: TaskReceipt) -> dict:
    entries = storage.read(receipt.shard_id, limit=10**6)
    if not entries:
        return {"receipt_id": receipt.receipt_id, "status": "SHARD_MISSING", "entry_found": False, "hash_matches": False}
    entry = next((e for e in entries if e.id == receipt.entry_id), None)
    if not entry:
        return {"receipt_id": receipt.receipt_id, "status": "ENTRY_MISSING", "entry_found": False, "hash_matches": False}
    hash_matches = (entry.hash or "") == receipt.entry_hash
    if not hash_matches:
        return {"receipt_id": receipt.receipt_id, "status": "HASH_MISMATCH", "entry_found": True, "hash_matches": False}
    return {"receipt_id": receipt.receipt_id, "status": "CONFIRMED", "entry_found": True, "hash_matches": True}


def store_external_receipt(
    storage: Storage,
    receipt: TaskReceipt,
    receiver_agent_id: str,
    shard_id: str = "receipts",
) -> Entry:
    entry = Entry(
        id=str(uuid4()),
        timestamp=datetime.utcnow(),
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
