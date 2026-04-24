# -*- coding: utf-8 -*-
"""
RR Index Builder — scans DSM shards via Storage API and builds derived indexes.

Uses ONLY:
  - Storage.list_shards()
  - Storage.read(shard_id, offset=..., limit=...)
  - Storage.get_shard_size(shard_id)

Does NOT modify DSM shards. Indexes are stored under data/index/ (JSON).
Indexes are derived data and can be rebuilt at any time.
"""

import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.storage import Storage
from ...core.models import Entry
from .. import _profiler as _prof

logger = logging.getLogger(__name__)

INDEX_VERSION = 1


# Batch size for paginated reading (Storage.read(offset=..., limit=...))
DEFAULT_BATCH_SIZE = 5000


def _entry_to_index_record(entry: Entry, shard_id: str, offset: int) -> Optional[Dict[str, Any]]:
    """
    Extract index metadata from a DSM Entry. Serializable for JSON.
    Returns None only if timestamp is missing or invalid (entry skipped). Otherwise returns a record
    with safe defaults for missing session_id, agent, event_type.
    Timestamp is normalized to a numeric value (Unix timestamp) for reliable timeline sort.
    Includes optional action_name (promoted from metadata["action_name"], or "unknown" when
    event_type == "tool_call" without an explicit name — matches SessionIndex rule at
    src/dsm/session/session_index.py:84). action_name is None when the entry is not an action.
    """
    timestamp = getattr(entry, "timestamp", None)
    if timestamp is None:
        return None
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None
    elif hasattr(timestamp, "timestamp"):
        timestamp = timestamp.timestamp()

    session_id = getattr(entry, "session_id", None) or ""
    source = getattr(entry, "source", None) or ""
    metadata = getattr(entry, "metadata", None) or {}
    event_type = metadata.get("event_type", "") if isinstance(metadata, dict) else ""
    entry_id = getattr(entry, "id", None) or ""

    raw_action_name = metadata.get("action_name") if isinstance(metadata, dict) else None
    if raw_action_name:
        action_name = raw_action_name
    elif event_type == "tool_call":
        action_name = "unknown"
    else:
        action_name = None
    success = bool(metadata.get("success", True)) if isinstance(metadata, dict) else True

    return {
        "session_id": session_id,
        "timestamp": timestamp,
        "agent": source,
        "event_type": event_type,
        "shard_id": shard_id,
        "entry_id": entry_id,
        "offset": offset,
        "action_name": action_name,
        "success": success,
    }


def _read_batch(
    storage: Storage,
    shard_id: str,
    offset: int,
    limit: int,
) -> List[Entry]:
    """Read a batch of entries via Storage.read(shard_id, offset=offset, limit=limit)."""
    return storage.read(shard_id, offset=offset, limit=limit)


class RRIndexBuilder:
    """
    Builds RR indexes from DSM shards using only the public Storage API.

    Indexes are stored under index_dir (default: data/index/) as JSON files:
      - sessions.idx  -> session_index
      - agents.idx    -> agent_index
      - timeline.idx   -> timeline_index
      - shards.idx     -> shard_index

    If index files are missing, call build() to rebuild from shards.
    """

    def __init__(
        self,
        storage: Optional[Storage] = None,
        index_dir: str = "data/index",
        batch_size: int = DEFAULT_BATCH_SIZE,
        enable_action_index: bool = True,
    ):
        """
        Args:
            storage: DSM Storage instance. If None, creates one with data_dir from index_dir parent.
            index_dir: Directory for index files (e.g. data/index). Must be outside DSM shard storage.
            batch_size: Page size for Storage.read(offset=..., limit=batch_size).
            enable_action_index: When True, build and persist action_index (5th index).
                                 Flag exists for Phase 7a benchmark (isolates the incremental cost
                                 of the action_name extension). Default True (production behaviour).
        """
        self._storage = storage or Storage(data_dir=str(Path(index_dir).parent))
        self._index_dir = Path(index_dir)
        self._batch_size = batch_size
        self._enable_action_index = enable_action_index

        # In-memory index structures (built by build())
        self.session_index: Dict[str, List[Dict[str, Any]]] = {}
        self.agent_index: Dict[str, List[Dict[str, Any]]] = {}
        self.timeline_index: List[Dict[str, Any]] = []
        self.shard_index: Dict[str, List[Dict[str, Any]]] = {}
        # action_index: action_name -> List[record], each list kept sorted by timestamp (ascending).
        # Populated only when enable_action_index=True.
        self.action_index: Dict[str, List[Dict[str, Any]]] = {}

    @property
    def storage(self) -> Storage:
        """DSM Storage (read-only)."""
        return self._storage

    def build(self) -> dict:
        """
        Scan all DSM shards and build in-memory indexes, then persist to index_dir.

        1. Clear existing in-memory indexes.
        2. Call Storage.list_shards()
        3. For each shard, read in batches (paginated when offset is supported).
        4. Extract metadata from each entry; skip only if timestamp is missing.
        5. Build session_index, agent_index, timeline_index, shard_index.
        6. Sort timeline_index by timestamp.
        7. Write to data/index/*.idx (atomically).

        When the DSM_RR_PROFILE env var is set to "1", section-level timings are
        accumulated via :mod:`dsm.rr._profiler` for Phase 7a.5 root-cause
        decomposition (ADR 0001). The profiler is a no-op when disabled, so this
        method's production-path behaviour is unchanged.

        Returns:
            A status dict with keys ``status``, ``entries_indexed``,
            ``sessions_found``, ``duration_seconds``. Byte-compatible with the
            former ``SessionIndex.build_from_storage`` contract so the CLI
            subcommand and ``DarylAgent.index_sessions`` can delegate here
            without changing their wire shape.
        """
        _t0 = time.monotonic()
        with _prof.Timed("build:total"):
            with _prof.Timed("build:clear"):
                self.session_index.clear()
                self.agent_index.clear()
                self.timeline_index.clear()
                self.shard_index.clear()
                self.action_index.clear()

            with _prof.Timed("build:list_shards"):
                shard_meta_list = self._storage.list_shards()

            with _prof.Timed("build:scan_and_populate"):
                for meta in shard_meta_list:
                    shard_id = meta.shard_id
                    offset = 0
                    while True:
                        with _prof.Timed("build:storage_read_batch"):
                            entries = _read_batch(
                                self._storage,
                                shard_id,
                                offset=offset,
                                limit=self._batch_size,
                            )
                        if not entries:
                            break

                        with _prof.Timed("build:populate_indexes"):
                            for i, entry in enumerate(entries):
                                record = _entry_to_index_record(entry, shard_id, offset + i)
                                if record is None:
                                    continue

                                sid = record["session_id"] or "none"
                                if sid not in self.session_index:
                                    self.session_index[sid] = []
                                self.session_index[sid].append(record)

                                agent = record["agent"] or "unknown"
                                if agent not in self.agent_index:
                                    self.agent_index[agent] = []
                                self.agent_index[agent].append(record)

                                self.timeline_index.append(record)

                                if shard_id not in self.shard_index:
                                    self.shard_index[shard_id] = []
                                self.shard_index[shard_id].append(record)

                                if self._enable_action_index:
                                    aname = record.get("action_name")
                                    if aname is not None:
                                        bucket = self.action_index.get(aname)
                                        if bucket is None:
                                            bucket = []
                                            self.action_index[aname] = bucket
                                        bucket.append(record)

                        offset += len(entries)
                        if len(entries) < self._batch_size:
                            break

            with _prof.Timed("build:timeline_sort"):
                self.timeline_index.sort(key=lambda x: x["timestamp"])
            if self._enable_action_index:
                with _prof.Timed("build:bucket_sort_actions"):
                    for bucket in self.action_index.values():
                        bucket.sort(key=lambda x: x["timestamp"])

            with _prof.Timed("build:write_files"):
                self._index_dir.mkdir(parents=True, exist_ok=True)
                self._write_index_files()

        return {
            "status": "OK",
            "entries_indexed": len(self.timeline_index),
            "sessions_found": len(self.session_index),
            "duration_seconds": round(time.monotonic() - _t0, 4),
        }

    def _write_index_files(self) -> None:
        """Write in-memory indexes to JSON files under index_dir. Uses atomic rename."""
        self._index_dir.mkdir(parents=True, exist_ok=True)

        file_specs = [
            ("sessions.idx", self.session_index),
            ("agents.idx", self.agent_index),
            ("timeline.idx", self.timeline_index),
            ("shards.idx", self.shard_index),
        ]
        if self._enable_action_index:
            file_specs.append(("actions.idx", self.action_index))

        for name, data in file_specs:
            with _prof.Timed(f"write:{name}:total"):
                path = self._index_dir / name
                payload = {"index_version": INDEX_VERSION, "entries": data}
                fd, tmp_path = tempfile.mkstemp(
                    prefix=f".{name}.",
                    suffix=".tmp",
                    dir=str(self._index_dir),
                    text=True,
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        with _prof.Timed(f"write:{name}:json_dump"):
                            json.dump(payload, f, ensure_ascii=False, indent=2)
                    with _prof.Timed(f"write:{name}:replace"):
                        os.replace(tmp_path, path)
                except Exception:
                    try:
                        os.unlink(tmp_path)
                    except OSError as e:
                        logger.debug("index file cleanup failed: %s", e)
                    raise

    def load(self) -> bool:
        """
        Load indexes from index_dir if files exist. Returns True if all files were loaded.

        If any file is missing, returns False and does not change in-memory state.
        Call build() to rebuild.
        When enable_action_index is True, actions.idx is required; when False, it is ignored.
        """
        sessions_path = self._index_dir / "sessions.idx"
        agents_path = self._index_dir / "agents.idx"
        timeline_path = self._index_dir / "timeline.idx"
        shards_path = self._index_dir / "shards.idx"
        actions_path = self._index_dir / "actions.idx"

        required = [sessions_path, agents_path, timeline_path, shards_path]
        if self._enable_action_index:
            required.append(actions_path)

        if not all(p.exists() for p in required):
            return False

        def _load_index(path: Path) -> Any:
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, dict) and "entries" in obj:
                return obj["entries"]
            return obj

        self.session_index = _load_index(sessions_path)
        self.agent_index = _load_index(agents_path)
        self.timeline_index = _load_index(timeline_path)
        self.shard_index = _load_index(shards_path)
        if self._enable_action_index and actions_path.exists():
            self.action_index = _load_index(actions_path)

        return True

    def ensure_index(self) -> None:
        """
        Ensure indexes exist: load from disk if present, otherwise rebuild from shards.
        """
        if not self.load():
            self.build()
