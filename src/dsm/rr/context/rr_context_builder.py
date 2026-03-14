# -*- coding: utf-8 -*-
"""
RR Context Builder — turns RR query results into structured context for agents and LLMs.

Uses only RRQueryEngine. Does not modify DSM or call Storage.
Pipeline: Query Engine → records → structured context.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from ..query import RRQueryEngine

# Max characters for content_preview (avoids large payloads)
CONTENT_PREVIEW_MAX_LEN = 200

# Metadata keys to include in context events (structured, typically small)
METADATA_KEYS_WHITELIST = frozenset({"event_type", "action_name", "tool_name", "action", "error"})


def _normalize_ts(value: Any) -> Optional[float]:
    """Return numeric timestamp or None."""
    if value is None:
        return None
    if hasattr(value, "timestamp"):
        return value.timestamp()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class RRContextBuilder:
    """
    Builds structured context from RR query results. Sits above RRQueryEngine.
    """

    def __init__(self, query_engine: RRQueryEngine):
        """
        Args:
            query_engine: RRQueryEngine used for all queries. Context builder does not call navigator or storage.
        """
        self._query_engine = query_engine

    @property
    def query_engine(self) -> RRQueryEngine:
        return self._query_engine

    def build_context(
        self,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        start_time: Optional[Union[datetime, float, int]] = None,
        end_time: Optional[Union[datetime, float, int]] = None,
        limit: int = 20,
        resolve: bool = False,
    ) -> Dict[str, Any]:
        """
        Build structured context from a query.

        When resolve=False (default): uses index metadata only; content_preview is empty.
        When resolve=True: loads full entries so content_preview (first 200 chars) and metadata are filled.

        Returns a dict with:
          - recent_events: list of events (entry_id, agent, timestamp, event_type, summary, content_preview, metadata)
          - agents_involved: unique list of agents
          - sessions: unique list of session_ids
          - time_range: { start, end } from timestamps
          - context_summary: short text summary (or "No recent events found." if empty)
        """
        records = self._query_engine.query(
            session_id=session_id,
            agent=agent,
            start_time=start_time,
            end_time=end_time,
            resolve=resolve,
            limit=limit,
            sort="desc",
        )
        if not records:
            return {
                "recent_events": [],
                "agents_involved": [],
                "sessions": [],
                "time_range": {"start": None, "end": None},
                "context_summary": "No recent events found.",
            }
        return self._build_from_records(records)

    def _content_preview(self, record: Any) -> str:
        """First 200 characters of entry content; empty when content not available (e.g. resolve=False)."""
        content = ""
        if isinstance(record, dict):
            content = record.get("content") or ""
        else:
            content = getattr(record, "content", None) or ""
        if not isinstance(content, str):
            content = str(content)
        return content[:CONTENT_PREVIEW_MAX_LEN]

    def _event_metadata(self, record: Any) -> Dict[str, Any]:
        """Structured metadata for context (whitelist to avoid large payloads)."""
        meta = {}
        if isinstance(record, dict):
            meta = record.get("metadata") or {}
        else:
            meta = getattr(record, "metadata", None) or {}
        if not isinstance(meta, dict):
            return {}
        return {k: v for k, v in meta.items() if k in METADATA_KEYS_WHITELIST}

    def _timestamp_str(self, ts: Any) -> Any:
        """Return timestamp as ISO string when possible for consistent context output."""
        if ts is None:
            return None
        if hasattr(ts, "isoformat"):
            return ts.isoformat()
        return ts

    def _build_from_records(self, records: List[Any]) -> Dict[str, Any]:
        """Construct context dict from non-empty record list (dicts or Entry objects)."""
        recent_events: List[Dict[str, Any]] = []
        agents_set: set = set()
        sessions_set: set = set()
        timestamps: List[float] = []

        for r in records:
            if isinstance(r, dict):
                entry_id = r.get("entry_id") or ""
                agent_val = r.get("agent") or ""
                ts = r.get("timestamp")
                event_type = r.get("event_type") or ""
                meta = r.get("metadata") or {}
                session_id = r.get("session_id") or ""
            else:
                entry_id = getattr(r, "id", None) or ""
                agent_val = getattr(r, "source", None) or ""
                ts = getattr(r, "timestamp", None)
                meta = getattr(r, "metadata", None) or {}
                event_type = (meta.get("event_type", "") if isinstance(meta, dict) else "") or ""
                session_id = getattr(r, "session_id", None) or ""
            if isinstance(meta, dict):
                event_type = event_type or meta.get("event_type", "")

            if agent_val:
                agents_set.add(agent_val)
            if session_id and session_id != "none":
                sessions_set.add(session_id)
            ts_num = _normalize_ts(ts)
            if ts_num is not None:
                timestamps.append(ts_num)

            summary = f"{event_type or 'event'} by {agent_val or 'unknown'}" if (event_type or agent_val) else "event"
            recent_events.append({
                "entry_id": entry_id,
                "agent": agent_val,
                "timestamp": self._timestamp_str(ts),
                "event_type": event_type,
                "summary": summary,
                "content_preview": self._content_preview(r),
                "metadata": self._event_metadata(r),
            })

        time_start = min(timestamps) if timestamps else None
        time_end = max(timestamps) if timestamps else None
        context_summary = self._generate_summary(records)

        return {
            "recent_events": recent_events,
            "agents_involved": sorted(agents_set),
            "sessions": sorted(sessions_set),
            "time_range": {"start": time_start, "end": time_end},
            "context_summary": context_summary,
        }

    def _generate_summary(self, records: List[Any]) -> str:
        """Simple summarization: count of events, agents, sessions."""
        if not records:
            return "No recent events found."
        agents_set = set()
        sessions_set = set()
        for r in records:
            a = (r.get("agent") or "") if isinstance(r, dict) else (getattr(r, "source", None) or "")
            s = (r.get("session_id") or "") if isinstance(r, dict) else (getattr(r, "session_id", None) or "")
            if a:
                agents_set.add(a)
            if s and s != "none":
                sessions_set.add(s)
        n_events = len(records)
        n_agents = len(agents_set)
        n_sessions = len(sessions_set)
        agents_str = " and ".join(sorted(agents_set)) if agents_set else "no agents"
        if n_sessions <= 1 and n_agents <= 1:
            return f"Recent activity includes {n_events} event(s) from {agents_str}."
        return f"Recent activity includes {n_events} events involving {agents_str} across {n_sessions} session(s)."
