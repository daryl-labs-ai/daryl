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

MEMORY_SCHEMA_VERSION = "agent_memory.v1"
DEFAULT_MEMORY_SHARD = "agent_memory"
_DEFAULT_SESSION_ID = "agent_memory"
_DEFAULT_SOURCE = "agent_memory"
_ALLOWED_KINDS = frozenset({"fact", "hypothesis", "inference", "decision"})
SourceRef = dict[str, str]

# Source-ref existence states (source-ref integrity v0).
#
# These two states describe EXISTENCE ONLY: whether the referenced
# {shard, entry_hash} pair can be located in local DSM storage.
#
# RESOLVED means the referenced entry exists. It does NOT mean the source is
# relevant, supporting, semantically related, or true. A recorded fact that
# says "It's sunny in Paris" resolves exactly like a genuinely supporting one;
# DSM does not judge relevance and must not be read as doing so.
#
# MISSING means the referenced entry could not be located in the shard the ref
# names. That is the one source-ref defect DSM can establish from the registry
# alone.
SOURCE_REF_RESOLVED = "RESOLVED"
SOURCE_REF_MISSING = "MISSING"


def record_fact(
    statement: str,
    *,
    source_refs: Optional[list[SourceRef]] = None,
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
    source_refs: Optional[list[SourceRef]] = None,
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
    source_refs: Optional[list[SourceRef]] = None,
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
    source_refs: Optional[list[SourceRef]] = None,
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
        "source_ref_status": _resolve_source_refs(
            storage,
            [decision, *supporting_entries],
            limit=limit,
        ),
        "verification": {
            "shard_id": shard,
            "hint": f"dsm verify --shard {shard}",
        },
    }


def _resolve_source_refs(
    storage: Storage,
    records: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, str]]:
    """Report the EXISTENCE of every distinct ``source_ref`` in ``records``.

    Returns one entry per distinct ``{shard, entry_hash}`` pair, in first-seen
    order, each carrying ``status`` of :data:`SOURCE_REF_RESOLVED` or
    :data:`SOURCE_REF_MISSING`.

    This is an existence check and nothing more. ``RESOLVED`` says the
    referenced entry was located in local storage; it says nothing about
    whether that entry is relevant to, supports, or corroborates the statement
    that cites it. DSM has no mechanism for judging that and does not claim one.

    Known bound: resolution reads at most ``limit`` recent entries per
    referenced shard, the same window the traversal itself uses. A reference to
    an entry older than that window is reported ``MISSING`` — read that as
    "not found within the read window", not as proof of absence.
    """
    order: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        for ref in record.get("source_refs") or []:
            key = (ref.get("shard") or "", ref.get("entry_hash") or "")
            if key in seen:
                continue
            seen.add(key)
            order.append(key)

    if not order:
        return []

    relay = DSMReadRelay(storage=storage)
    present: dict[str, set[str]] = {}
    for shard, _ in order:
        if shard in present:
            continue
        try:
            entries = relay.read_recent(shard, limit=limit)
        except Exception:
            # An absent or unreadable shard resolves nothing: every ref into it
            # is reported MISSING rather than silently passing as fine.
            entries = []
        present[shard] = {entry.hash for entry in entries if entry.hash}

    return [
        {
            "shard": shard,
            "entry_hash": entry_hash,
            "status": (
                SOURCE_REF_RESOLVED
                if entry_hash in present.get(shard, frozenset())
                else SOURCE_REF_MISSING
            ),
        }
        for shard, entry_hash in order
    ]


def source_ref_status_map(
    source_ref_status: list[dict[str, str]],
) -> dict[tuple[str, str], str]:
    """Index a ``source_ref_status`` list by ``(shard, entry_hash)``."""
    return {
        (item.get("shard", ""), item.get("entry_hash", "")): item.get(
            "status", SOURCE_REF_MISSING
        )
        for item in source_ref_status
    }


def _record_memory(
    kind: str,
    statement: str,
    *,
    source_refs: Optional[list[SourceRef]],
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
    source_refs_list = _normalize_source_refs(source_refs)
    depends_on_list = list(depends_on or [])
    confidence_value = _normalize_confidence(confidence)
    content = {
        "schema": MEMORY_SCHEMA_VERSION,
        "schema_version": MEMORY_SCHEMA_VERSION,
        "kind": kind,
        "statement": statement,
        "source_refs": source_refs_list,
        "depends_on": depends_on_list,
        "confidence": confidence_value,
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
        "schema_version": payload.get("schema_version", payload["schema"]),
        "kind": kind,
        "statement": payload.get("statement", ""),
        "source_refs": _normalize_source_refs(payload.get("source_refs") or []),
        "depends_on": list(payload.get("depends_on") or []),
        "confidence": _normalize_confidence(payload.get("confidence")),
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


def _normalize_source_refs(source_refs: Optional[list[SourceRef]]) -> list[SourceRef]:
    refs: list[SourceRef] = []
    for ref in source_refs or []:
        if not isinstance(ref, dict):
            raise ValueError("source_refs entries must be dicts with shard and entry_hash")
        shard = ref.get("shard")
        entry_hash = ref.get("entry_hash")
        if not isinstance(shard, str) or not shard:
            raise ValueError("source_refs entries require non-empty shard")
        if not isinstance(entry_hash, str) or not entry_hash:
            raise ValueError("source_refs entries require non-empty entry_hash")
        refs.append({"shard": shard, "entry_hash": entry_hash})
    return refs


def _normalize_confidence(confidence: Optional[float]) -> Optional[float]:
    if confidence is None:
        return None
    if not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be a float between 0.0 and 1.0")
    value = float(confidence)
    if not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")
    return value
