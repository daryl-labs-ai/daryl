"""
Causal Ordering (P10) — Cross-agent dispatch binding.

Proves B's work was in response to A's specific dispatch.
Chain: dispatch → intent (pre-commit) → execution → receipt.
"""

import hashlib
import json
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


def create_dispatch_hash(
    dispatcher_entry_hash: str,
    task_params: dict,
    timestamp: Optional[str] = None,
) -> str:
    """Create dispatch_hash = SHA-256(entry_hash + canonical(task_params) + timestamp).

    Called by Agent A when dispatching work to Agent B.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    payload = (
        dispatcher_entry_hash
        + json.dumps(task_params, sort_keys=True, separators=(",", ":"))
        + timestamp
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_routing_hash(
    dispatch_hash: str,
    router_id: str,
    route_timestamp: Optional[str] = None,
) -> str:
    """Create routing_hash for third-party causal witness.

    Called by a registry/router that independently observes A→B dispatch.
    """
    if route_timestamp is None:
        route_timestamp = datetime.now(timezone.utc).isoformat()
    payload = dispatch_hash + router_id + route_timestamp
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class DispatchRecord:
    """Record of a dispatch from Agent A to Agent B."""

    dispatch_hash: str
    dispatcher_agent_id: str
    dispatcher_entry_hash: str
    target_agent_id: str
    task_params: dict
    timestamp: str
    routing_hash: Optional[str] = None
    router_id: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "DispatchRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def verify_dispatch_hash(record: DispatchRecord) -> dict:
    """Verify a dispatch record's hash integrity.

    Returns {"status": "VALID"|"HASH_MISMATCH", "dispatch_hash": str}
    """
    expected = create_dispatch_hash(
        record.dispatcher_entry_hash,
        record.task_params,
        record.timestamp,
    )
    status = "VALID" if expected == record.dispatch_hash else "HASH_MISMATCH"
    return {
        "dispatch_hash": record.dispatch_hash,
        "expected_hash": expected,
        "status": status,
    }


def verify_causal_chain(
    dispatch_record: DispatchRecord,
    intent_hash: str,
    receipt_dispatch_hash: Optional[str],
) -> dict:
    """Verify full causal chain: dispatch → intent → receipt.

    Checks:
    1. dispatch_record hash is valid
    2. receipt references the correct dispatch_hash

    Returns {"status": "VALID"|"BROKEN", "details": [...]}
    """
    details = []

    # Check dispatch hash integrity
    dv = verify_dispatch_hash(dispatch_record)
    if dv["status"] != "VALID":
        details.append("dispatch_hash integrity failed")

    # Check receipt references correct dispatch
    if receipt_dispatch_hash is None:
        details.append("receipt has no dispatch_hash")
    elif receipt_dispatch_hash != dispatch_record.dispatch_hash:
        details.append("receipt dispatch_hash does not match dispatch record")

    status = "VALID" if len(details) == 0 else "BROKEN"
    return {"status": status, "details": details}
