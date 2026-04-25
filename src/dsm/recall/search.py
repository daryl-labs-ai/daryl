"""Recall search engine — daryl port of ``dsm_v0.recall``.

Faithful port: identical public shape, identical string enums, identical
heuristics. Only the read path (``_scan_shard``) and session discovery
(``list_sessions``) are daryl-native.
"""

from __future__ import annotations

import math
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from ..core.models import Entry
from ..core.storage import Storage
from ..rr.helpers import get_populated_rr_builder
from ..rr.relay import DSMReadRelay

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

DEFAULT_DATA_DIR = "data"

# Status constants — same strings as dsm_v0.
STATUS_STILL_RELEVANT = "still_relevant"
STATUS_SUPERSEDED = "superseded"
STATUS_OUTDATED = "outdated"
STATUS_UNCERTAIN = "uncertain_time_status"

# Type constants — same strings as dsm_v0.
TYPE_VERIFIED_FACT = "verified_fact"
TYPE_HISTORICAL_DECISION = "historical_decision"
TYPE_WORKING_ASSUMPTION = "working_assumption"
TYPE_OUTDATED_POSSIBILITY = "outdated_possibility"

# ---------------------------------------------------------------------------
# Tuning constants (mirrors dsm_v0)
# ---------------------------------------------------------------------------

_CONTENT_PREVIEW_MAX = 400
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is",
    "are", "was", "were", "be", "been", "by", "it", "this", "that", "with",
    "as", "at", "from", "but", "not", "no", "if", "then", "so", "do", "did",
    "has", "have", "had", "can", "could", "will", "would", "should",
    # French
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "dans",
    "pour", "est", "sont", "\u00e9tait", "\u00eatre", "par", "ce", "cette",
    "avec", "au", "aux", "mais", "non", "si", "on", "plus", "tr\u00e8s",
})
_WORD_RE = re.compile(r"[A-Za-z\u00c0-\u024f][A-Za-z0-9_\u00c0-\u024f\-]*")

_RECENCY_HALF_LIFE_DAYS = 14.0
_OUTDATED_AGE_DAYS = 30.0

# Event type → memory type. Daryl uses metadata["event_type"] (same
# keys as dsm_v0). We also accept ``entry.source`` as a fallback when
# metadata lacks event_type.
_DEFAULT_TYPE_MAP: dict[str, Optional[str]] = {
    "session_start": None,
    "session_end": None,
    "user_prompt": TYPE_HISTORICAL_DECISION,
    "user_input": TYPE_HISTORICAL_DECISION,
    "final_output": TYPE_HISTORICAL_DECISION,
    "llm_response": TYPE_HISTORICAL_DECISION,
    "tool_exec:call": TYPE_WORKING_ASSUMPTION,
    "tool_exec:return": TYPE_WORKING_ASSUMPTION,
    "tool_call": TYPE_WORKING_ASSUMPTION,
    "snapshot": TYPE_WORKING_ASSUMPTION,
    "error": TYPE_OUTDATED_POSSIBILITY,
    "transcript_ingest": None,
    "transcript_ingest_error": None,
}

_SUPERSEDABLE_TYPES = frozenset({
    TYPE_HISTORICAL_DECISION, TYPE_WORKING_ASSUMPTION,
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [
        t.lower()
        for t in _WORD_RE.findall(text)
        if len(t) > 2 and t.lower() not in _STOPWORDS
    ]


def _flatten_content(content: Any) -> str:
    """Daryl ``Entry.content`` is always a string by contract; we accept
    the full dsm_v0 shape (dict/list/str) for forward-compat when a
    caller manually injects items."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (int, float, bool)):
        return str(content)
    if isinstance(content, dict):
        parts: list[str] = []
        for key in ("text", "prompt", "msg", "message", "output", "response", "result"):
            v = content.get(key)
            if isinstance(v, str):
                parts.append(v)
        if not parts:
            import json as _json
            parts.append(_json.dumps(content, ensure_ascii=False))
        return " ".join(parts)
    if isinstance(content, (list, tuple)):
        return " ".join(_flatten_content(x) for x in content)
    return str(content)


def _score_match(
    query_tokens: set[str], event_tokens: list[str]
) -> tuple[float, set[str]]:
    if not query_tokens or not event_tokens:
        return 0.0, set()
    event_set = set(event_tokens)
    matched = query_tokens & event_set
    if not matched:
        return 0.0, matched
    raw = float(len(matched)) / math.sqrt(len(event_tokens) + 1)
    return raw, matched


def _recency_boost(ts: float, now: float) -> float:
    if ts <= 0 or now <= 0 or ts > now:
        return 1.0
    age_days = max(0.0, (now - ts) / 86400.0)
    return 0.5 ** (age_days / _RECENCY_HALF_LIFE_DAYS)


def _ts_to_seconds(ts: Any) -> float:
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, datetime):
        try:
            return float(ts.timestamp())
        except (TypeError, ValueError):
            return 0.0
    if hasattr(ts, "timestamp"):
        try:
            return float(ts.timestamp())
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(ts)
    except (TypeError, ValueError):
        return 0.0


def _entry_event_type(entry: Entry) -> str:
    meta = entry.metadata or {}
    etype = meta.get("event_type") or meta.get("action_name") or ""
    if not etype:
        etype = entry.source or ""
    return str(etype)


# ---------------------------------------------------------------------------
# Session discovery (daryl-native)
# ---------------------------------------------------------------------------


def list_sessions(
    storage: Optional[Storage] = None,
    data_dir: str = DEFAULT_DATA_DIR,
    shard_ids: Optional[list[str]] = None,
) -> list[str]:
    """Enumerate all session_ids present across shards.

    Reads via RR (Phase 7c.1). Preserves the original contract:
    - shard_ids=None: returns all session_ids known to RR (sorted,
      distinct, non-empty)
    - shard_ids=[...]: returns session_ids that appear in at least
      one of the listed shards

    Empty session_ids and the placeholder "none" key are excluded.
    """
    if storage is None:
        storage = Storage(data_dir=data_dir)
    # Derive index_dir from storage.data_dir (not the parameter), so a
    # caller that passes a custom Storage instance gets indexes under
    # that storage's data_dir, not under DEFAULT_DATA_DIR.
    index_dir = str(Path(storage.data_dir) / "index")
    builder = get_populated_rr_builder(storage, index_dir)

    if shard_ids is None:
        # Whole-repo enumeration: session_index keys are exactly the
        # set of session_ids RR has seen.
        return sorted(
            sid for sid in builder.session_index.keys()
            if sid and sid != "none"
        )

    # Filtered enumeration: collect session_ids appearing in records
    # of the listed shards.
    sessions: set[str] = set()
    for shard_id in shard_ids:
        for record in builder.shard_index.get(shard_id, []):
            sid = record.get("session_id")
            if sid and sid != "none":
                sessions.add(sid)
    return sorted(sessions)


def current_session_id(
    storage: Optional[Storage] = None,
    data_dir: str = DEFAULT_DATA_DIR,
) -> Optional[str]:
    """Return the session_id of the most recent entry in the 'sessions'
    shard, or None if the shard is empty or missing.

    Reads via RR (Phase 7c.1). Preserves the original contract:
    'most recent' = max timestamp among entries in shard 'sessions'.
    """
    if storage is None:
        storage = Storage(data_dir=data_dir)
    # Derive index_dir from storage.data_dir (not the parameter), so a
    # caller that passes a custom Storage instance gets indexes under
    # that storage's data_dir, not under DEFAULT_DATA_DIR.
    index_dir = str(Path(storage.data_dir) / "index")
    builder = get_populated_rr_builder(storage, index_dir)

    sessions_records = builder.shard_index.get("sessions", [])
    if not sessions_records:
        return None

    latest = max(sessions_records, key=lambda r: r["timestamp"])
    sid = latest.get("session_id")
    return sid if sid else None


# ---------------------------------------------------------------------------
# Scan (daryl-native)
# ---------------------------------------------------------------------------


def _classify(
    event_type: str,
    type_overrides: Optional[dict[str, Optional[str]]],
) -> Optional[str]:
    mapping = _DEFAULT_TYPE_MAP
    if type_overrides:
        mapping = {**_DEFAULT_TYPE_MAP, **type_overrides}
    return mapping.get(event_type, TYPE_WORKING_ASSUMPTION)


def _iter_entries(
    storage: Storage,
    shard_ids: list[str],
    limit_per_shard: int = 100_000,
) -> Iterator[Entry]:
    relay = DSMReadRelay(storage=storage)
    for sid in shard_ids:
        try:
            entries = relay.read_recent(sid, limit=limit_per_shard)
        except Exception:
            continue
        for e in entries:
            yield e


def _build_match_from_entry(
    entry: Entry,
    type_overrides: Optional[dict[str, Optional[str]]],
    query_tokens: set[str],
    now: float,
) -> Optional[dict[str, Any]]:
    """Score an entry against the query; return a match dict or None."""
    event_type = _entry_event_type(entry)
    classified = _classify(event_type, type_overrides)
    if classified is None:
        return None
    text = _flatten_content(entry.content)
    tokens = _tokenize(text)
    raw, matched = _score_match(query_tokens, tokens)
    if raw <= 0:
        return None
    ts = _ts_to_seconds(entry.timestamp)
    score = raw * _recency_boost(ts, now)
    return {
        "session_id": entry.session_id,
        "source_shard_id": entry.shard,
        "entry_hash": entry.hash,
        "prev_hash": entry.prev_hash,
        "event_type": event_type,
        "type": classified,
        "content": text[:_CONTENT_PREVIEW_MAX],
        "timestamp": ts,
        "relevance_score": round(score, 4),
        "_raw_score": round(raw, 4),
        "_matched_tokens": sorted(matched),
        "time_status": STATUS_STILL_RELEVANT,
    }


def _apply_temporal_status(matches: list[dict[str, Any]], now: float) -> None:
    """Same rule as dsm_v0: coverage-based subsumption, restricted to
    revisable types. See dsm_v0/recall.py for the rationale."""
    for i, m in enumerate(matches):
        mi_type = m.get("type") or ""
        mi_tokens = set(m.get("_matched_tokens") or [])
        mi_ts = float(m.get("timestamp") or 0.0)
        superseded = False
        if mi_type in _SUPERSEDABLE_TYPES and mi_tokens:
            for j, other in enumerate(matches):
                if i == j:
                    continue
                oj_ts = float(other.get("timestamp") or 0.0)
                if oj_ts <= mi_ts:
                    continue
                oj_tokens = set(other.get("_matched_tokens") or [])
                if mi_tokens.issubset(oj_tokens):
                    superseded = True
                    break
        if superseded:
            m["time_status"] = STATUS_SUPERSEDED
            continue
        if mi_ts > 0 and (now - mi_ts) / 86400.0 > _OUTDATED_AGE_DAYS:
            m["time_status"] = STATUS_OUTDATED


def _strip_internals(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in m.items() if not k.startswith("_")} for m in matches]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def search_memory(
    query: str,
    storage: Optional[Storage] = None,
    data_dir: str = DEFAULT_DATA_DIR,
    session_id: Optional[str] = None,
    shard_ids: Optional[list[str]] = None,
    across_sessions: bool = True,
    max_results: int = 10,
    include_current_session: bool = False,
    include_provenance: bool = True,
    verify: bool = False,
    type_overrides: Optional[dict[str, Optional[str]]] = None,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """Search daryl memory and return a structured recall pack.

    Output shape is identical to ``dsm_v0.recall.search_memory``. Enum
    string values are identical. Only the read path and session
    discovery are daryl-native.

    Parameters specific to daryl:

    - ``storage`` / ``data_dir``: provide a daryl :class:`Storage`, or
      have one created from ``data_dir``.
    - ``shard_ids``: restrict the scan to specific shards. Defaults to
      every shard returned by ``storage.list_shards()``.
    """
    now_seconds = float(now) if now is not None else time.time()
    query_tokens = set(_tokenize(query))

    if storage is None:
        storage = Storage(data_dir=data_dir)

    # Faithful to dsm_v0: `session_id=None` does NOT auto-detect. The
    # caller is responsible for telling recall which session is current.
    # Use :func:`current_session_id` explicitly if you want a heuristic
    # pick ("latest entry in the sessions shard").
    resolved_current = session_id

    # Scan scope.
    if shard_ids is None:
        shard_ids = [s.shard_id for s in storage.list_shards()]

    current_matches: list[dict[str, Any]] = []
    past_matches: list[dict[str, Any]] = []

    if query_tokens and shard_ids:
        for entry in _iter_entries(storage, shard_ids):
            if not across_sessions and entry.session_id != resolved_current:
                continue
            match = _build_match_from_entry(
                entry, type_overrides, query_tokens, now_seconds,
            )
            if match is None:
                continue
            if resolved_current is not None and entry.session_id == resolved_current:
                current_matches.append(match)
            else:
                past_matches.append(match)

    # Rank + cap.
    past_matches.sort(key=lambda m: m["relevance_score"], reverse=True)
    past_matches = past_matches[: max(0, int(max_results))]

    if include_current_session:
        current_matches.sort(key=lambda m: m["relevance_score"], reverse=True)
        current_matches = current_matches[: max(0, int(max_results))]
    else:
        current_matches = []

    all_for_status = past_matches + current_matches
    _apply_temporal_status(all_for_status, now_seconds)

    clean_current = _strip_internals(current_matches)
    clean_past = _strip_internals(past_matches)
    all_clean = clean_past + clean_current

    out: dict[str, Any] = {
        "query": query,
        "current_session": {
            "session_id": resolved_current,
            "matches": clean_current,
        },
        "past_session_recall": clean_past,
        "verified_claims": [],
    }

    if include_provenance or verify:
        # Lazy import to avoid recall↔provenance top-level cycle.
        from ..provenance import build_provenance, promote_to_verified_claims
        prov = build_provenance(
            items=all_clean,
            storage=storage,
            verify=verify,
            now=now_seconds,
        )
        if include_provenance:
            out["provenance"] = prov
        if verify:
            out["verified_claims"] = promote_to_verified_claims(all_clean, prov)

    return out
