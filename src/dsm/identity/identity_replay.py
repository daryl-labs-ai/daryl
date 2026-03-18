"""Replay identity events from shard `identity` into a derived IdentityState."""

import json
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.models import Entry
from ..core.storage import Storage


@dataclass
class IdentityState:
    agent_id: str
    identity_version: int
    purpose: str
    capabilities: List[str]
    constraints: List[str]
    model_id: Optional[str]
    config_hash: Optional[str]
    created_by: str
    genesis_timestamp: Optional[datetime]
    last_updated: Optional[datetime]
    event_count: int
    timeline: List[Dict[str, Any]]


def _summary_for_event(event_type: str, payload: Dict[str, Any]) -> str:
    if event_type == "genesis":
        return f"genesis: {payload.get('purpose', '')[:80]}"
    if event_type == "skill_added":
        return f"skill_added: {payload.get('skill', '')}"
    if event_type == "skill_removed":
        return f"skill_removed: {payload.get('skill', '')}"
    if event_type == "model_change":
        return f"model_change: {payload.get('to', '')}"
    return event_type


def replay_identity(
    storage: Storage,
    agent_id: str,
    up_to: Optional[datetime] = None,
) -> IdentityState:
    raw = storage.read("identity", offset=0, limit=100000)
    chronological = list(reversed(raw))

    agent_entries: List[Entry] = []
    for entry in chronological:
        try:
            data = json.loads(entry.content)
        except (json.JSONDecodeError, TypeError):
            continue
        if data.get("agent_id") != agent_id:
            continue
        ts = entry.timestamp
        if up_to is not None:
            if ts.tzinfo and up_to.tzinfo is None:
                from datetime import timezone as tz

                up_to = up_to.replace(tzinfo=tz.utc)
            elif ts.tzinfo is None and up_to.tzinfo:
                ts = ts.replace(tzinfo=up_to.tzinfo)
            if ts > up_to:
                continue
        agent_entries.append(entry)

    agent_entries.sort(key=lambda e: e.timestamp)

    if not agent_entries:
        raise ValueError(f"No genesis event found for agent {agent_id}")

    first = json.loads(agent_entries[0].content)
    if first.get("event_type") != "genesis":
        raise ValueError(f"No genesis event found for agent {agent_id}")

    purpose = ""
    capabilities: List[str] = []
    constraints: List[str] = []
    created_by = ""
    model_id: Optional[str] = None
    config_hash: Optional[str] = None
    genesis_timestamp: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    identity_version = 0
    timeline: List[Dict[str, Any]] = []

    for entry in agent_entries:
        data = json.loads(entry.content)
        et = data.get("event_type")
        payload = data.get("payload") or {}
        iv = data.get("identity_version", 0)
        identity_version = max(identity_version, int(iv) if iv else 0)

        if et == "genesis":
            purpose = str(payload.get("purpose", ""))
            capabilities = list(payload.get("initial_capabilities", []))
            constraints = list(payload.get("constraints", []))
            created_by = str(payload.get("created_by", ""))
            genesis_timestamp = entry.timestamp
            last_updated = entry.timestamp
        elif et == "skill_added":
            sk = payload.get("skill")
            if sk and sk not in capabilities:
                capabilities.append(sk)
            last_updated = entry.timestamp
        elif et == "skill_removed":
            sk = payload.get("skill")
            if sk in capabilities:
                capabilities.remove(sk)
            last_updated = entry.timestamp
        elif et == "model_change":
            if "to" in payload:
                model_id = str(payload["to"])
            last_updated = entry.timestamp
        elif et == "config_change":
            if payload.get("config_hash_after"):
                config_hash = str(payload["config_hash_after"])
            last_updated = entry.timestamp
        elif et == "behavior_change":
            last_updated = entry.timestamp
        elif et == "capability_declared":
            if payload.get("capabilities") is not None:
                capabilities = list(payload["capabilities"])
            last_updated = entry.timestamp

        timeline.append(
            {
                "event_type": et,
                "identity_version": data.get("identity_version"),
                "timestamp": entry.timestamp.isoformat(),
                "summary": _summary_for_event(et, payload),
            }
        )

    return IdentityState(
        agent_id=agent_id,
        identity_version=identity_version,
        purpose=purpose,
        capabilities=capabilities,
        constraints=constraints,
        model_id=model_id,
        config_hash=config_hash,
        created_by=created_by,
        genesis_timestamp=genesis_timestamp,
        last_updated=last_updated,
        event_count=len(agent_entries),
        timeline=timeline,
    )


def diff_identity(state_a: IdentityState, state_b: IdentityState) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for f in fields(IdentityState):
        name = f.name
        va = getattr(state_a, name)
        vb = getattr(state_b, name)
        if va != vb:
            out[name] = {"before": va, "after": vb}
    return out
