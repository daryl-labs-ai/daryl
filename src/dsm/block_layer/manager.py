# -*- coding: utf-8 -*-
"""
DSM v2 - Block layer: BlockManager.

Buffers entries into blocks of configurable size and appends each block
as one record via the DSM Storage API. Append-only semantics preserved.
"""

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Iterator

# Use DSM core API only (no core modifications)
from ..core.storage import Storage
from ..core.models import Entry


@dataclass
class BlockConfig:
    """Configuration for the block layer."""
    block_size: int = 32
    """Number of entries per block before flushing."""
    block_shard_suffix: str = "_block"
    """Suffix for block shard names (logical shard 'sessions' -> 'sessions_block')."""


def _entry_to_dict(entry: Entry) -> Dict[str, Any]:
    """Serialize Entry to a JSON-serializable dict."""
    return {
        "id": entry.id,
        "timestamp": entry.timestamp.isoformat(),
        "session_id": entry.session_id,
        "source": entry.source,
        "content": entry.content,
        "shard": entry.shard,
        "hash": entry.hash,
        "prev_hash": entry.prev_hash,
        "metadata": entry.metadata,
        "version": entry.version,
    }


def _dict_to_entry(data: Dict[str, Any]) -> Entry:
    """Deserialize dict to Entry."""
    return Entry(
        id=data.get("id", ""),
        timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(timezone.utc),
        session_id=data.get("session_id", ""),
        source=data.get("source", ""),
        content=data.get("content", ""),
        shard=data.get("shard", "default"),
        hash=data.get("hash", ""),
        prev_hash=data.get("prev_hash"),
        metadata=data.get("metadata", {}),
        version=data.get("version", "v2.0"),
    )


class BlockManager:
    """
    Experimental block layer on top of DSM Storage.

    - Buffers entries per shard; when buffer reaches block_size, flushes
      one block (one Storage.append) containing multiple entries.
    - Uses Storage API only; append-only semantics and hash chain preserved.
    - Block shards are distinct (e.g. shard_sessions_block) so classic and
      block mode can be compared.
    """

    BLOCK_MAGIC = "block"
    """Content key indicating a serialized block."""

    def __init__(
        self,
        storage: Optional[Storage] = None,
        block_size: int = 32,
        block_shard_suffix: str = "_block",
        data_dir: str = "data",
    ):
        """
        Args:
            storage: DSM Storage instance. If None, one is created with data_dir.
            block_size: Max entries per block before flush.
            block_shard_suffix: Suffix for block shard (logical shard + suffix).
            data_dir: Used only when storage is None.
        """
        self._storage = storage or Storage(data_dir=data_dir)
        self._config = BlockConfig(block_size=block_size, block_shard_suffix=block_shard_suffix)
        self._buffers: Dict[str, List[Entry]] = {}

    @property
    def block_size(self) -> int:
        return self._config.block_size

    @property
    def storage(self) -> Storage:
        """DSM Storage API (read-only access)."""
        return self._storage

    def _block_shard_id(self, logical_shard: str) -> str:
        """Return the shard id used for block storage (e.g. sessions -> sessions_block)."""
        base = logical_shard.replace("shard_", "") if logical_shard.startswith("shard_") else logical_shard
        return f"{base}{self._config.block_shard_suffix}"

    def append(self, entry: Entry) -> Entry:
        """
        Append an entry (append-only). May buffer; flushes when block is full.

        Args:
            entry: Entry to append (entry.shard = logical shard).

        Returns:
            The same entry (block flush returns the block record, not per-entry).
        """
        shard = entry.shard or "default"
        buf = self._buffers.setdefault(shard, [])

        # Ensure entry has hash
        if not entry.hash:
            entry.hash = hashlib.sha256(entry.content.encode("utf-8")).hexdigest()

        buf.append(entry)
        if len(buf) >= self._config.block_size:
            self._flush_shard(shard)
        return entry

    def _flush_shard(self, logical_shard: str) -> None:
        """Flush the buffer for the given logical shard as one block."""
        buf = self._buffers.get(logical_shard)
        if not buf:
            return
        block_shard = self._block_shard_id(logical_shard)
        block_payload = {
            self.BLOCK_MAGIC: True,
            "entries": [_entry_to_dict(e) for e in buf],
            "count": len(buf),
        }
        content_str = json.dumps(block_payload, ensure_ascii=False)
        block_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()
        block_entry = Entry(
            id=f"block-{buf[0].id}-{len(buf)}",
            timestamp=buf[-1].timestamp,
            session_id=buf[0].session_id,
            source="block_layer",
            content=content_str,
            shard=block_shard,
            hash=block_hash,
            prev_hash=None,
            metadata={"block": True, "logical_shard": logical_shard, "entry_count": len(buf)},
            version="v2.0",
        )
        self._storage.append(block_entry)
        self._buffers[logical_shard] = []

    def flush(self) -> None:
        """Flush all buffered entries (partial blocks) to storage."""
        for shard in list(self._buffers.keys()):
            if self._buffers[shard]:
                self._flush_shard(shard)

    def read(self, shard_id: str, limit: int = 100) -> List[Entry]:
        """
        Read entries from the block shard, expanding blocks into individual entries.

        Args:
            shard_id: Logical shard id (e.g. sessions); reads from shard_id_block.
            limit: Max number of entries to return (most recent first).

        Returns:
            List of Entry (blocks expanded).
        """
        block_shard = self._block_shard_id(shard_id)
        # Read more lines than limit because each line may be a block of many entries
        raw = self._storage.read(block_shard, limit=limit * max(1, self._config.block_size))
        expanded: List[Entry] = []
        for entry in raw:
            if not entry.content:
                continue
            try:
                data = json.loads(entry.content)
                if isinstance(data, dict) and data.get(self.BLOCK_MAGIC) and "entries" in data:
                    for d in data["entries"]:
                        expanded.append(_dict_to_entry(d))
                else:
                    expanded.append(entry)
            except (json.JSONDecodeError, KeyError, TypeError):
                expanded.append(entry)
        return expanded[:limit]

    def iter_entries(self, shard_id: str) -> Iterator[Entry]:
        """Iterate over all entries in the block shard (oldest first), expanding blocks."""
        block_shard = self._block_shard_id(shard_id)
        for event_data in self._storage.segment_manager.iter_shard_events(block_shard):
            content = event_data.get("content", "")
            if not content:
                continue
            try:
                data = json.loads(content)
                if isinstance(data, dict) and data.get(self.BLOCK_MAGIC) and "entries" in data:
                    for d in data["entries"]:
                        yield _dict_to_entry(d)
                else:
                    yield Entry(
                        id=event_data.get("id", ""),
                        timestamp=datetime.fromisoformat(event_data.get("timestamp", "")) if event_data.get("timestamp") else datetime.now(timezone.utc),
                        session_id=event_data.get("session_id", ""),
                        source=event_data.get("source", ""),
                        content=content,
                        shard=event_data.get("shard", "default"),
                        hash=event_data.get("hash", ""),
                        prev_hash=event_data.get("prev_hash"),
                        metadata=event_data.get("metadata", {}),
                        version=event_data.get("version", "v2.0"),
                    )
            except (json.JSONDecodeError, KeyError, TypeError):
                yield Entry(
                    id=event_data.get("id", ""),
                    timestamp=datetime.fromisoformat(event_data.get("timestamp", "")) if event_data.get("timestamp") else datetime.now(timezone.utc),
                    session_id=event_data.get("session_id", ""),
                    source=event_data.get("source", ""),
                    content=content,
                    shard=event_data.get("shard", "default"),
                    hash=event_data.get("hash", ""),
                    prev_hash=event_data.get("prev_hash"),
                    metadata=event_data.get("metadata", {}),
                    version=event_data.get("version", "v2.0"),
                )
