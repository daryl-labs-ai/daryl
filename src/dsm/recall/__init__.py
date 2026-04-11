"""DSM Consumption Layer — Recall (daryl port).

Phase 4 port of ``dsm_v0.recall``. Same public API, same output shape,
same enum string values. Backend swapped from raw JSONL session shards
to daryl's native :class:`Storage` + :class:`DSMReadRelay`.

Key backend differences vs dsm_v0 (documented here once, not inline)
--------------------------------------------------------------------
- Sessions are **logical** in daryl: multiple sessions co-exist within
  one physical shard (e.g. ``sessions``, ``collective_main``). Recall
  enumerates distinct ``session_id`` values across all shards returned
  by ``storage.list_shards()`` rather than listing shard files.
- Event type extraction: daryl entries carry ``event_type`` under
  ``entry.metadata["event_type"]``. When absent, we fall back to
  ``entry.source``.
- Content flattening: daryl ``Entry.content`` is a string by contract,
  not a dict — we skip the dict-extraction branch used by dsm_v0.
- Timestamps are ``datetime`` objects, normalized to unix seconds for
  scoring + provenance.

Everything else (tokenization, scoring, recency boost, type
classification, temporal status, superseded detection, promotion
delegation to :mod:`dsm.provenance`) is a faithful port of dsm_v0
semantics with identical string constants.
"""

from .search import (
    DEFAULT_DATA_DIR,
    STATUS_OUTDATED,
    STATUS_STILL_RELEVANT,
    STATUS_SUPERSEDED,
    STATUS_UNCERTAIN,
    TYPE_HISTORICAL_DECISION,
    TYPE_OUTDATED_POSSIBILITY,
    TYPE_VERIFIED_FACT,
    TYPE_WORKING_ASSUMPTION,
    current_session_id,
    list_sessions,
    search_memory,
)

__all__ = [
    "search_memory",
    "list_sessions",
    "current_session_id",
    "DEFAULT_DATA_DIR",
    "STATUS_STILL_RELEVANT",
    "STATUS_SUPERSEDED",
    "STATUS_OUTDATED",
    "STATUS_UNCERTAIN",
    "TYPE_VERIFIED_FACT",
    "TYPE_HISTORICAL_DECISION",
    "TYPE_WORKING_ASSUMPTION",
    "TYPE_OUTDATED_POSSIBILITY",
]
