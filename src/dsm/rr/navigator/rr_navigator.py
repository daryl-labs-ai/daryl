# -*- coding: utf-8 -*-
"""
RR Navigator — navigation over DSM memory using the RR Index.

Uses only index lookups (session_index, agent_index, timeline_index, shard_index).
Does NOT scan shards directly. When full Entry content is needed, uses Storage.read().
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Union

from ...core.storage import Storage
from ...core.models import Entry
from ..index import RRIndexBuilder


logger = logging.getLogger(__name__)

# Batch size for paginated resolution (Storage.read(offset=..., limit=...))
_RESOLVE_BATCH_SIZE = 5000


def _to_timestamp(value: Union[datetime, float, int, None]) -> Optional[float]:
    """Normalize datetime or number to Unix timestamp (float). Accepts datetime, int, float."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.timestamp()
    return float(value)


def _read_batch(
    storage: Storage,
    shard_id: str,
    offset: int,
    limit: int,
) -> List[Entry]:
    """Read a batch of entries via Storage.read(shard_id, offset=offset, limit=limit)."""
    return storage.read(shard_id, offset=offset, limit=limit)


class RRNavigator:
    """
    Navigates DSM memory using the indexes built by RRIndexBuilder.

    All navigation methods return index metadata records (dicts with session_id,
    timestamp, agent, event_type, shard_id, entry_id, offset). Full Entry retrieval
    is done via resolve_entries() using Storage.read() when needed.
    """

    def __init__(self, index_builder: RRIndexBuilder, storage: Storage):
        """
        Args:
            index_builder: RRIndexBuilder whose indexes are used for lookups.
                           Call ensure_index() or build() before navigation if needed.
            storage: DSM Storage used only for resolving entries (Storage.read()).
        """
        self._index_builder = index_builder
        self._storage = storage

    @property
    def index_builder(self) -> RRIndexBuilder:
        return self._index_builder

    @property
    def storage(self) -> Storage:
        return self._storage

    def navigate_session(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Return metadata records belonging to the given session.

        Uses session_index. Does not call Storage.read().
        """
        index = self._index_builder.session_index
        records = index.get(session_id, [])
        return list(records)

    def navigate_agent(self, agent: str) -> List[Dict[str, Any]]:
        """
        Return metadata records produced by the given agent.

        Uses agent_index. Does not call Storage.read().
        """
        index = self._index_builder.agent_index
        records = index.get(agent, [])
        return list(records)

    def timeline(
        self,
        start_time: Optional[Union[datetime, float, int]] = None,
        end_time: Optional[Union[datetime, float, int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return timeline metadata records filtered by time range.

        Uses timeline_index (already sorted by timestamp). Optional start_time and
        end_time filter inclusively [start_time, end_time]. Accepts datetime or
        Unix timestamp (float/int). Normalized internally to numeric timestamp.
        """
        index = self._index_builder.timeline_index
        start_ts = _to_timestamp(start_time)
        end_ts = _to_timestamp(end_time)

        if start_ts is None and end_ts is None:
            return list(index)

        out: List[Dict[str, Any]] = []
        for rec in index:
            ts_num = _to_timestamp(rec.get("timestamp"))
            if ts_num is None:
                continue
            if start_ts is not None and ts_num < start_ts:
                continue
            if end_ts is not None and ts_num > end_ts:
                continue
            out.append(rec)
        return out

    def navigate_shard(self, shard_id: str) -> List[Dict[str, Any]]:
        """
        Return metadata records for the given shard.

        Uses shard_index. Does not call Storage.read().
        """
        index = self._index_builder.shard_index
        records = index.get(shard_id, [])
        return list(records)

    def navigate_action(self, action_name: str) -> List[Dict[str, Any]]:
        """
        Return metadata records for the given action_name.

        Uses action_index populated by RRIndexBuilder (Phase 7a extension). Each returned record
        exposes the same keys as other navigators plus action_name and success.
        Does not call Storage.read().
        """
        index = getattr(self._index_builder, "action_index", {}) or {}
        records = index.get(action_name, [])
        return list(records)

    def resolve_entries(
        self,
        records: List[Dict[str, Any]],
        limit: Optional[int] = None,
    ) -> List[Entry]:
        """
        Resolve index metadata records to full DSM entries using Storage.read().

        Groups records by shard_id, then for each shard reads in batches (paginated
        when Storage supports offset). Matches by entry_id using set lookup. Stops
        when all requested ids for a shard are resolved, or when limit is reached.
        Missing entries are skipped safely (debug log); no exception is raised.
        """
        if not records:
            return []

        records_by_shard: Dict[str, List[Dict[str, Any]]] = {}
        for rec in records:
            shard_id = rec.get("shard_id", "")
            if shard_id not in records_by_shard:
                records_by_shard[shard_id] = []
            records_by_shard[shard_id].append(rec)

        entries_out: List[Entry] = []
        seen_ids: Set[str] = set()

        for shard_id, recs in records_by_shard.items():
            if limit is not None and len(entries_out) >= limit:
                break

            requested_ids: Set[str] = set()
            for rec in recs:
                eid = rec.get("entry_id")
                if eid:
                    requested_ids.add(eid)

            if not requested_ids:
                continue

            still_needed = requested_ids - seen_ids
            if not still_needed:
                continue

            offset = 0
            while True:
                batch = _read_batch(
                    self._storage,
                    shard_id,
                    offset=offset,
                    limit=_RESOLVE_BATCH_SIZE,
                )
                if not batch:
                    break

                for entry in batch:
                    eid = getattr(entry, "id", None)
                    if not eid:
                        continue
                    if eid not in still_needed:
                        continue
                    if eid in seen_ids:
                        continue
                    entries_out.append(entry)
                    seen_ids.add(eid)
                    still_needed.discard(eid)

                    if limit is not None and len(entries_out) >= limit:
                        return entries_out[:limit]

                if not still_needed:
                    break

                offset += len(batch)
                if len(batch) < _RESOLVE_BATCH_SIZE:
                    break

            for eid in still_needed:
                logger.debug(
                    "RR Navigator: entry_id %s not found in shard %s",
                    eid,
                    shard_id,
                )

        return entries_out if limit is None else entries_out[:limit]
