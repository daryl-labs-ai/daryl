"""Minimal Agent Memory API.

This module records agent reasoning items as regular DSM entries. It is an
agent-facing layer above the DSM kernel: no hash format, storage format, or
kernel behavior is changed here.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ..core.models import Entry
from ..core.storage import Storage
from ..rr.relay import DSMReadRelay

MEMORY_SCHEMA_VERSION = "dsm.agent_memory.v1"
DEFAULT_MEMORY_SHARD = "agent_memory"
_DEFAULT_SESSION_ID = "agent_memory"
_DEFAULT_SOURCE = "agent_memory"
_ALLOWED_KINDS = frozenset({"fact", "hypothesis", "inference", "decision"})


def record_fact(
    statement: str,
    *,
    source_refs: Optional[list[Any]] = None,
    depends_on: Optional[list[str]] = None,
    confidence: Optional[float] = None,
    session_id: Optional[str] = None,
    storage: Optional[Storage] = None,
    data_dir: str = "data",
    shard: str = DEFAULT_MEMORY_SHARD,
    source: str = _DEFAULT_SOURCE,
) -> Entry:
    """Record a factual claim used by an agent."""
    return _record_memory(
        "fact",
        statement,
        source_refs=source_refs,
        depends_on=depends_on,
        confidence=confidence,
        session_id=session_id,
        storage=storage,
        data_dir=data_dir,
        shard=shard,
        source=source,
    )


def record_hypothesis(
    statement: str,
    *,
    source_refs: Optional[list[Any]] = None,
    depends_on: Optional[list[str]] = None,
    confidence: Optional[float] = None,
    session_id: Optional[str] = None,
    storage: Optional[Storage] = None,
    data_dir: str = "data",
    shard: str = DEFAULT_MEMORY_SHARD,
    source: str = _DEFAULT_SOURCE,
) -> Entry:
    """Record an assumption that may later be confirmed or superseded."""
    return _record_memory(
        "hypothesis",
        statement,
        source_refs=source_refs,
        depends_on=depends_on,
        confidence=confidence,
        session_id=session_id,
        storage=storage,
        data_dir=data_dir,
        shard=shard,
        source=source,
    )


def record_inference(
    statement: str,
    *,
    depends_on: Optional[list[str]] = None,
    source_refs: Optional[list[Any]] = None,
    confidence: Optional[float] = None,
    session_id: Optional[str] = None,
    storage: Optional[Storage] = None,
    data_dir: str = "data",
    shard: str = DEFAULT_MEMORY_SHARD,
    source: str = _DEFAULT_SOURCE,
) -> Entry:
    """Record a conclusion derived from prior memory entries."""
    return _record_memory(
        "inference",
        statement,
        source_refs=source_refs,
        depends_on=depends_on,
        confidence=confidence,
        session_id=session_id,
        storage=storage,
        data_dir=data_dir,
        shard=shard,
        source=source,
    )


def record_decision(
    statement: str,
    *,
    depends_on: Optional[list[str]] = None,
    source_refs: Optional[list[Any]] = None,
    confidence: Optional[float] = None,
    session_id: Optional[str] = None,
    storage: Optional[Storage] = None,
    data_dir: str = "data",
    shard: str = DEFAULT_MEMORY_SHARD,
    source: str = _DEFAULT_SOURCE,
) -> Entry:
    """Record the final answer or decision an agent wants to justify."""
    return _record_memory(
        "decision",
        statement,
        source_refs=source_refs,
        depends_on=depends_on,
        confidence=confidence,
        session_id=session_id,
        storage=storage,
        data_dir=data_dir,
        shard=shard,
        source=source,
    )


def explain_decision(
    decision_id_or_hash: str,
    *,
    storage: Optional[Storage] = None,
    data_dir: str = "data",
    shard: str = DEFAULT_MEMORY_SHARD,
    max_depth: int = 2,
    limit: int = 100_000,
) -> dict[str, Any]:
    """Return a small justification chain for a recorded decision.

    The V1 traversal is intentionally shallow. Depth 1 returns direct
    dependencies. Depth 2 also returns dependencies of those dependencies,
    enough for a decision -> inference -> fact/hypothesis chain.
    """
    storage = storage or Storage(data_dir=data_dir)
    records = _load_memory_records(storage, shard=shard, limit=limit)
    by_id, by_hash = _index_records(records)

    decision = _find_record(decision_id_or_hash, by_id, by_hash)
    if decision is None:
        raise ValueError(f"decision not found: {decision_id_or_hash}")
    if decision["kind"] != "decision":
        raise ValueError(
            f"entry is {decision['kind']!r}, expected 'decision': {decision_id_or_hash}"
        )

    missing: list[str] = []
    direct = _resolve_refs(decision["depends_on"], by_id, by_hash, missing)
    dependency_map: dict[str, list[dict[str, Any]]] = {}
    supporting_entries: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def add_support(record: dict[str, Any]) -> None:
        key = record.get("entry_hash") or record.get("entry_id")
        if key and key not in seen_keys:
            seen_keys.add(key)
            supporting_entries.append(record)

    for record in direct:
        add_support(record)

    frontier = direct
    depth = 1
    while frontier and depth < max_depth:
        next_frontier: list[dict[str, Any]] = []
        for record in frontier:
            key = record["entry_hash"] or record["entry_id"]
            nested = _resolve_refs(record["depends_on"], by_id, by_hash, missing)
            dependency_map[key] = nested
            for nested_record in nested:
                add_support(nested_record)
            next_frontier.extend(nested)
        frontier = next_frontier
        depth += 1

    return {
        "decision": decision,
        "dependencies": direct,
        "dependency_map": dependency_map,
        "supporting_entries": supporting_entries,
        "missing_dependencies": missing,
        "verification": {
            "shard_id": shard,
            "hint": f"dsm verify --shard {shard}",
        },
    }


def _record_memory(
    kind: str,
    statement: str,
    *,
    source_refs: Optional[list[Any]],
    depends_on: Optional[list[str]],
    confidence: Optional[float],
    session_id: Optional[str],
    storage: Optional[Storage],
    data_dir: str,
    shard: str,
    source: str,
) -> Entry:
    if kind not in _ALLOWED_KINDS:
        raise ValueError(f"unsupported memory kind: {kind}")
    if not statement or not statement.strip():
        raise ValueError("statement must be a non-empty string")

    storage = storage or Storage(data_dir=data_dir)
    timestamp = datetime.now(timezone.utc)
    source_refs_list = list(source_refs or [])
    depends_on_list = list(depends_on or [])
    content = {
        "schema": MEMORY_SCHEMA_VERSION,
        "kind": kind,
        "statement": statement,
        "source_refs": source_refs_list,
        "depends_on": depends_on_list,
        "confidence": confidence,
        "created_at": timestamp.isoformat(),
    }
    entry = Entry(
        id=str(uuid.uuid4()),
        timestamp=timestamp,
        session_id=session_id or _DEFAULT_SESSION_ID,
        source=source,
        content=json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={
            "event_type": "agent_memory",
            "memory_schema": MEMORY_SCHEMA_VERSION,
            "memory_kind": kind,
            "depends_on": depends_on_list,
        },
        version="v2.0",
    )
    return storage.append(entry)


def _load_memory_records(
    storage: Storage,
    *,
    shard: str,
    limit: int,
) -> list[dict[str, Any]]:
    relay = DSMReadRelay(storage=storage)
    records: list[dict[str, Any]] = []
    for entry in relay.read_recent(shard, limit=limit):
        record = _record_from_entry(entry)
        if record is not None:
            records.append(record)
    return records


def _record_from_entry(entry: Entry) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(entry.content or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != MEMORY_SCHEMA_VERSION:
        return None
    kind = payload.get("kind")
    if kind not in _ALLOWED_KINDS:
        return None

    return {
        "entry_id": entry.id,
        "entry_hash": entry.hash,
        "prev_hash": entry.prev_hash,
        "shard": entry.shard,
        "session_id": entry.session_id,
        "source": entry.source,
        "timestamp": entry.timestamp.isoformat()
        if hasattr(entry.timestamp, "isoformat")
        else str(entry.timestamp),
        "schema": payload["schema"],
        "kind": kind,
        "statement": payload.get("statement", ""),
        "source_refs": list(payload.get("source_refs") or []),
        "depends_on": list(payload.get("depends_on") or []),
        "confidence": payload.get("confidence"),
        "created_at": payload.get("created_at"),
        "verification": {
            "shard_id": entry.shard,
            "entry_hash": entry.hash,
        },
    }


def _index_records(
    records: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id = {record["entry_id"]: record for record in records if record.get("entry_id")}
    by_hash = {
        record["entry_hash"]: record
        for record in records
        if record.get("entry_hash")
    }
    return by_id, by_hash


def _find_record(
    ref: str,
    by_id: dict[str, dict[str, Any]],
    by_hash: dict[str, dict[str, Any]],
) -> Optional[dict[str, Any]]:
    return by_hash.get(ref) or by_id.get(ref)


def _resolve_refs(
    refs: list[str],
    by_id: dict[str, dict[str, Any]],
    by_hash: dict[str, dict[str, Any]],
    missing: list[str],
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for ref in refs:
        record = _find_record(ref, by_id, by_hash)
        if record is None:
            missing.append(ref)
        else:
            resolved.append(record)
    return resolved
