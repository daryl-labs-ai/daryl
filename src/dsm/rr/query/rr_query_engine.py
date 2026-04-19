# -*- coding: utf-8 -*-
"""
RR Query Engine — high-level query over RR Navigator.

Accepts optional filters: session_id, agent, shard_id, start_time, end_time.
When multiple filters are set, returns records matching all (intersection).
Optional limit, sort, and resolve (metadata vs full Entry).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from ...core.models import Entry
from ..navigator import RRNavigator


def _normalize_timestamp(value: Any) -> float:
    """Normalize timestamp for sorting: datetime → .timestamp(), int/float → float. None → 0.0."""
    if value is None:
        return 0.0
    if isinstance(value, datetime):
        return value.timestamp()
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _coerce_to_numeric(value: Any) -> Optional[float]:
    """
    Coerce a value to a numeric Unix timestamp or return None when no bound is requested.
    Accepts None, datetime, float/int, or ISO 8601 string (for SessionIndex.get_actions
    compatibility — see src/dsm/session/session_index.py:174).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


class RRQueryEngine:
    """
    Query engine on top of RRNavigator. Translates high-level criteria
    into navigator calls, applies intersection when multiple filters are set,
    then optional sort, limit, and resolution.
    """

    def __init__(self, navigator: RRNavigator):
        """
        Args:
            navigator: RRNavigator used for all lookups and resolution.
        """
        self._navigator = navigator

    @property
    def navigator(self) -> RRNavigator:
        return self._navigator

    def query(
        self,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        shard_id: Optional[str] = None,
        start_time: Optional[Union[datetime, float, int]] = None,
        end_time: Optional[Union[datetime, float, int]] = None,
        resolve: bool = False,
        limit: Optional[int] = None,
        sort: Optional[str] = None,
    ) -> List[Any]:
        """
        Run a query with optional filters. Returns metadata records or Entry objects.

        Filter selection (single or combined):
          - session_id  -> navigator.navigate_session(session_id)
          - agent       -> navigator.navigate_agent(agent)
          - shard_id    -> navigator.navigate_shard(shard_id)
          - start_time / end_time -> navigator.timeline(start_time, end_time)

        When multiple filters are set, only records matching ALL criteria are returned
        (intersection by entry_id). Optional sort by timestamp ("asc" or "desc").
        Limit is applied after filtering and sorting. If resolve=True,
        navigator.resolve_entries() is called and Entry objects are returned.

        If no filter is provided, returns [] (no full scan).

        Returns:
            List of metadata records (dicts), or List[Entry] if resolve=True.
        """
        has_time = start_time is not None or end_time is not None
        if not any([session_id, agent, shard_id, start_time, end_time]):
            return []

        candidates: List[List[Dict[str, Any]]] = []

        if session_id:
            candidates.append(self._navigator.navigate_session(session_id))
        if agent:
            candidates.append(self._navigator.navigate_agent(agent))
        if shard_id:
            candidates.append(self._navigator.navigate_shard(shard_id))
        if has_time:
            candidates.append(
                self._navigator.timeline(start_time=start_time, end_time=end_time)
            )

        if not candidates:
            return []

        if len(candidates) == 1:
            records = [r for r in candidates[0] if r.get("entry_id")]
        else:
            records = self._intersect_by_entry_id(candidates)

        if sort is not None:
            reverse = sort.lower() == "desc"
            records = sorted(
                records,
                key=lambda r: _normalize_timestamp(r.get("timestamp")),
                reverse=reverse,
            )

        if limit is not None:
            records = records[:limit]

        if resolve:
            return self._navigator.resolve_entries(records, limit=limit)
        return records

    def query_actions(
        self,
        action_name: Optional[str] = None,
        session_id: Optional[str] = None,
        start_time: Optional[Union[datetime, float, int, str]] = None,
        end_time: Optional[Union[datetime, float, int, str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query actions with optional filters, signature-compatible with SessionIndex.get_actions
        (src/dsm/session/session_index.py:156).

        When action_name is provided, uses action_index (O(k) dict lookup) to pull the bucket,
        which is already sorted by timestamp ascending. When action_name is None, iterates over
        every bucket. AND-filters by session_id, start_time, end_time. start_time / end_time may
        be ISO strings (for SessionIndex wire-compat) or datetime / numeric timestamps (normalized
        to float).
        Early-exit on limit. Does not call Storage.read().
        """
        start_ts = _coerce_to_numeric(start_time)
        end_ts = _coerce_to_numeric(end_time)

        if action_name is not None:
            buckets: List[List[Dict[str, Any]]] = [
                self._navigator.navigate_action(action_name)
            ]
        else:
            action_index = getattr(self._navigator.index_builder, "action_index", {}) or {}
            buckets = [list(bucket) for bucket in action_index.values()]

        results: List[Dict[str, Any]] = []
        for bucket in buckets:
            for act in bucket:
                if session_id and act.get("session_id") != session_id:
                    continue
                ts = act.get("timestamp")
                if start_ts is not None and (ts is None or ts < start_ts):
                    continue
                if end_ts is not None and (ts is None or ts > end_ts):
                    continue
                results.append(act)
                if len(results) >= limit:
                    return results
        return results

    def _intersect_by_entry_id(
        self,
        candidate_lists: List[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """Return records whose entry_id appears in every candidate list. O(n) via set intersection."""
        if not candidate_lists:
            return []
        record_lists = [
            [r for r in recs if r.get("entry_id")] for recs in candidate_lists
        ]
        record_lists = [lst for lst in record_lists if lst]
        if not record_lists:
            return []
        id_sets = [
            set(rec["entry_id"] for rec in records if rec.get("entry_id"))
            for records in record_lists
        ]
        if not id_sets:
            return []
        common_ids = set.intersection(*id_sets)
        base = record_lists[0]
        return [r for r in base if r.get("entry_id") in common_ids]
