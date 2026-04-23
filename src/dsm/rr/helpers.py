# -*- coding: utf-8 -*-
"""
RR helpers — adapters that bridge RR index data structures to the
SessionIndex-compatible dict contracts used by consumers (DarylAgent
methods, CLI commands, MCP tools).

Per ADR-0001, RR is the only allowed read path. These helpers let
consumers keep their existing return-shape contracts (byte-for-byte
compatible with SessionIndex) while the underlying reads go through
RRQueryEngine / RRIndexBuilder.

Both helpers are small, pure, and have no dependencies beyond RR itself.
"""

from datetime import datetime, timezone

from .index import RRIndexBuilder


def get_populated_rr_builder(storage, index_dir):
    """Build or load a populated RRIndexBuilder for read access.

    Encapsulates the ensure_index + defensive-build pattern used by every
    RR-backed read path (DarylAgent.find_session, DarylAgent.query_actions,
    and the RR-backed CLI subcommands). Returns a builder whose
    session_index / action_index are guaranteed non-empty as long as the
    underlying shard has entries.

    Rationale for the defensive fallback: ensure_index() loads persisted
    index files if present but is a no-op otherwise. If the index has
    never been built (or was deleted), we trigger a full build to avoid
    silent empty-result bugs.
    """
    builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
    builder.ensure_index()
    if not builder.session_index:
        builder.build()
    return builder


def build_session_summary(records: list, session_id: str) -> dict:
    """Aggregate RR index records into a SessionIndex-compatible session summary.

    Contract parity (must match SessionIndex.find_session):
      session_id, source, start_time, end_time, entry_count, entry_ids, actions

    `actions` is a List[Dict[{"name", "count"}]] — list order follows first-
    appearance order in the records (matches dict-insertion order in Python 3.7+,
    which is what SessionIndex.find_session produced).
    """
    if not records:
        return {
            "session_id": session_id,
            "source": "",
            "start_time": "",
            "end_time": "",
            "entry_count": 0,
            "entry_ids": [],
            "actions": [],
        }

    def _ts_to_iso(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    timestamps = [r["timestamp"] for r in records if r.get("timestamp") is not None]
    action_counts: dict = {}
    for r in records:
        name = r.get("action_name")
        if name:  # None for non-action entries
            action_counts[name] = action_counts.get(name, 0) + 1

    return {
        "session_id": session_id,
        "source": records[0].get("agent", ""),  # RR renames entry.source → "agent"
        "start_time": _ts_to_iso(min(timestamps)) if timestamps else "",
        "end_time": _ts_to_iso(max(timestamps)) if timestamps else "",
        "entry_count": len(records),
        "entry_ids": [r.get("entry_id", "") for r in records],
        "actions": [{"name": k, "count": v} for k, v in action_counts.items()],
    }
