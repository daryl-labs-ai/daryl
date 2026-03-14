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
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.storage import Storage
from ...core.models import Entry


INDEX_VERSION = 1


# Batch size for paginated reading (Storage.read(offset=..., limit=...))
DEFAULT_BATCH_SIZE = 5000


def _entry_to_index_record(entry: Entry, shard_id: str, offset: int) -> Optional[Dict[str, Any]]:
    """
    Extract index metadata from a DSM Entry. Serializable for JSON.
    Returns None only if timestamp is missing or invalid (entry skipped). Otherwise returns a record
    with safe defaults for missing session_id, agent, event_type.
    Timestamp is normalized to a numeric value (Unix timestamp) for reliable timeline sort.
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

    return {
        "session_id": session_id,
        "timestamp": timestamp,
        "agent": source,
        "event_type": event_type,
        "shard_id": shard_id,
        "entry_id": entry_id,
        "offset": offset,
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
    ):
        """
        Args:
            storage: DSM Storage instance. If None, creates one with data_dir from index_dir parent.
            index_dir: Directory for index files (e.g. data/index). Must be outside DSM shard storage.
            batch_size: Page size for Storage.read(offset=..., limit=batch_size).
        """
        self._storage = storage or Storage(data_dir=str(Path(index_dir).parent))
        self._index_dir = Path(index_dir)
        self._batch_size = batch_size

        # In-memory index structures (built by build())
        self.session_index: Dict[str, List[Dict[str, Any]]] = {}
        self.agent_index: Dict[str, List[Dict[str, Any]]] = {}
        self.timeline_index: List[Dict[str, Any]] = []
        self.shard_index: Dict[str, List[Dict[str, Any]]] = {}

    @property
    def storage(self) -> Storage:
        """DSM Storage (read-only)."""
        return self._storage

    def build(self) -> None:
        """
        Scan all DSM shards and build in-memory indexes, then persist to index_dir.

        1. Clear existing in-memory indexes.
        2. Call Storage.list_shards()
        3. For each shard, read in batches (paginated when offset is supported).
        4. Extract metadata from each entry; skip only if timestamp is missing.
        5. Build session_index, agent_index, timeline_index, shard_index.
        6. Sort timeline_index by timestamp.
        7. Write to data/index/*.idx (atomically).
        """
        self.session_index.clear()
        self.agent_index.clear()
        self.timeline_index.clear()
        self.shard_index.clear()

        shard_meta_list = self._storage.list_shards()
        for meta in shard_meta_list:
            shard_id = meta.shard_id
            offset = 0
            while True:
                entries = _read_batch(
                    self._storage,
                    shard_id,
                    offset=offset,
                    limit=self._batch_size,
                )
                if not entries:
                    break

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

                offset += len(entries)
                if len(entries) < self._batch_size:
                    break

        self.timeline_index.sort(key=lambda x: x["timestamp"])

        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._write_index_files()

    def _write_index_files(self) -> None:
        """Write in-memory indexes to JSON files under index_dir. Uses atomic rename."""
        self._index_dir.mkdir(parents=True, exist_ok=True)

        for name, data in [
            ("sessions.idx", self.session_index),
            ("agents.idx", self.agent_index),
            ("timeline.idx", self.timeline_index),
            ("shards.idx", self.shard_index),
        ]:
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
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

    def load(self) -> bool:
        """
        Load indexes from index_dir if files exist. Returns True if all files were loaded.

        If any file is missing, returns False and does not change in-memory state.
        Call build() to rebuild.
        """
        sessions_path = self._index_dir / "sessions.idx"
        agents_path = self._index_dir / "agents.idx"
        timeline_path = self._index_dir / "timeline.idx"
        shards_path = self._index_dir / "shards.idx"

        if not all(
            p.exists()
            for p in (sessions_path, agents_path, timeline_path, shards_path)
        ):
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

        return True

    def ensure_index(self) -> None:
        """
        Ensure indexes exist: load from disk if present, otherwise rebuild from shards.
        """
        if not self.load():
            self.build()
