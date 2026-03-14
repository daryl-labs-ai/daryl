# -*- coding: utf-8 -*-
"""
DSM-RR Minimal Implementation (Step 1).

See HEARTBEAT.md for the planned DSM-RR architecture. This module is a read-only
relay over DSM Storage: it does not write to shards or modify the core. It uses
only Storage.read() to inspect shard data.

Current capabilities (Step 1):
  - read_recent(shard_id, limit): return most recent entries from a shard.
  - summary(shard_id, limit): lightweight activity summary (entry count, unique
    sessions, errors, top actions).

Planned future features (not implemented here):
  - Session reconstruction (reconstruct_session(session_id)).
  - RR query engine for structured queries over shard data.
  - Context pack generation for agents (prepared context from DSM for LLM use).
  - Minimal indexing for faster lookups by session or time range.
"""

import json
from collections import Counter
from datetime import datetime
from typing import List, Dict, Any, Optional

from ..core.storage import Storage
from ..core.models import Entry


# Block format produced by block_layer (we expand these when reading)
_BLOCK_MAGIC = "block"


def _expand_entries(entries: List[Entry]) -> List[Entry]:
    """Expand block-format entries into individual entries. Uses only in-memory parsing."""
    out: List[Entry] = []
    for entry in entries:
        if not entry.content:
            out.append(entry)
            continue
        try:
            data = json.loads(entry.content)
            if isinstance(data, dict) and data.get(_BLOCK_MAGIC) and "entries" in data:
                for d in data["entries"]:
                    out.append(_dict_to_entry(d))
            else:
                out.append(entry)
        except (json.JSONDecodeError, KeyError, TypeError):
            out.append(entry)
    return out


def _dict_to_entry(data: Dict[str, Any]) -> Entry:
    """Build Entry from dict (e.g. from block payload)."""
    ts = data.get("timestamp")
    if isinstance(ts, str):
        try:
            timestamp = datetime.fromisoformat(ts)
        except ValueError:
            timestamp = datetime.utcnow()
    else:
        timestamp = datetime.utcnow()
    return Entry(
        id=data.get("id", ""),
        timestamp=timestamp,
        session_id=data.get("session_id", ""),
        source=data.get("source", ""),
        content=data.get("content", ""),
        shard=data.get("shard", "default"),
        hash=data.get("hash", ""),
        prev_hash=data.get("prev_hash"),
        metadata=data.get("metadata", {}),
        version=data.get("version", "v2.0"),
    )


class DSMReadRelay:
    """
    Read-only relay over DSM Storage. Uses only Storage.read().
    Compatible with classic shards and block shards (expands blocks in memory).
    """

    def __init__(self, data_dir: str = "data", storage: Optional[Storage] = None):
        """
        Args:
            data_dir: Used only when storage is None.
            storage: DSM Storage instance. If None, one is created with data_dir.
        """
        self._storage = storage or Storage(data_dir=data_dir)

    @property
    def storage(self) -> Storage:
        """DSM Storage (read-only)."""
        return self._storage

    def read_recent(self, shard_id: str, limit: int = 100) -> List[Entry]:
        """
        Return the most recent entries from the shard.
        Uses Storage.read() only. Expands block-format entries for block shards.
        """
        raw = self._storage.read(shard_id, limit=limit)
        expanded = _expand_entries(raw)
        return expanded[:limit]

    def summary(
        self,
        shard_id: str,
        limit: int = 500,
    ) -> Dict[str, Any]:
        """
        Lightweight summary of shard activity.
        Uses metadata["action_name"], metadata["error"], entry.session_id.
        """
        raw = self._storage.read(shard_id, limit=limit)
        entries = _expand_entries(raw)

        unique_sessions = set()
        errors = 0
        action_counter: Counter = Counter()

        for e in entries:
            if e.session_id:
                unique_sessions.add(e.session_id)
            meta = e.metadata or {}
            if meta.get("error"):
                errors += 1
            action_name = meta.get("action_name")
            if action_name:
                action_counter[action_name] += 1

        return {
            "shard_id": shard_id,
            "entry_count": len(entries),
            "unique_sessions": len(unique_sessions),
            "errors": errors,
            "top_actions": action_counter.most_common(10),
        }
