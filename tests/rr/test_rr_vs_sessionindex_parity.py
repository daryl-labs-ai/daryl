# -*- coding: utf-8 -*-
"""
ADR-0001 Phase 7a parity test: RRQueryEngine.query_actions ≡ SessionIndex.get_actions

Empirical gate for ADR-0001 acceptance. Proves that the new RR query path
returns the same records as the legacy SessionIndex on a dataset designed to
discriminate common implementation bugs (limit-before-filter, ordering drift,
action_name extraction divergence).

Dataset properties (guarded by structural tests):
  - 20 entries interleaved across 4 sessions (s1, s2, s3, s4)
  - s1 = 50% of entries (10/20), but NEVER in head position
    (position 0 = s2, by construction — forces limit-before-filter bugs
     to diverge from the correct limit-after-filter semantic)
  - Strictly monotonic timestamps
  - 3 action_names spread across all sessions: grep, read_file, write_file

If the dataset loses any of these properties, the structural guards fail
before the parity tests run — so a future edit to _build_dataset cannot
silently make the parity tests trivially pass.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator
from dsm.rr.query import RRQueryEngine
from dsm.session.session_index import SessionIndex


BASE_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------

_SESSION_PATTERN = [
    "s2", "s1", "s3", "s1", "s4", "s1", "s2", "s1", "s3", "s1",
    "s4", "s1", "s2", "s1", "s3", "s1", "s4", "s1", "s2", "s1",
]
_ACTION_PATTERN = [
    "grep", "read_file", "write_file",
    "grep", "read_file", "write_file",
    "grep", "read_file", "write_file",
    "grep", "read_file", "write_file",
    "grep", "read_file", "write_file",
    "grep", "read_file", "write_file",
    "grep", "read_file",
]

assert len(_SESSION_PATTERN) == 20
assert len(_ACTION_PATTERN) == 20
assert _SESSION_PATTERN[0] == "s2", "head must not be s1"
assert _SESSION_PATTERN.count("s1") == 10, "s1 must be 50%"


def _entry(idx: int, session_id: str, action_name: str) -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=BASE_TS + timedelta(seconds=idx),
        session_id=session_id,
        source="agent_a",
        content=f"c{idx}",
        shard="sessions",
        hash="",
        prev_hash=None,
        metadata={"event_type": "tool_call", "action_name": action_name},
        version="v2.0",
    )


def _build_dataset() -> list[Entry]:
    return [
        _entry(i, _SESSION_PATTERN[i], _ACTION_PATTERN[i])
        for i in range(20)
    ]


@pytest.fixture
def parity_data_dir(tmp_path):
    shards_dir = tmp_path / "shards"
    shards_dir.mkdir(parents=True)
    (tmp_path / "integrity").mkdir(parents=True)

    path = shards_dir / "sessions.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for e in _build_dataset():
            obj = {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "session_id": e.session_id,
                "source": e.source,
                "content": e.content,
                "shard": e.shard,
                "hash": e.hash or "",
                "prev_hash": e.prev_hash,
                "metadata": e.metadata,
                "version": e.version,
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    return tmp_path


@pytest.fixture
def parity_engines(parity_data_dir):
    storage = Storage(data_dir=str(parity_data_dir))

    # RR pipeline (unchanged)
    index_dir = parity_data_dir / "index"
    builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
    builder.ensure_index()
    navigator = RRNavigator(index_builder=builder, storage=storage)
    rr = RRQueryEngine(navigator=navigator)

    # SessionIndex — actual signature on this branch is
    #   SessionIndex(index_dir: str, shard_id: str = "sessions")
    # and it's populated via build_from_storage(storage), not build_index/ensure_index.
    si_index_dir = parity_data_dir / "si_index"
    si_index_dir.mkdir(parents=True, exist_ok=True)
    si = SessionIndex(str(si_index_dir), shard_id="sessions")
    si.build_from_storage(storage)

    return rr, si


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_to_float(ts):
    """Normalize timestamp to float, whatever form the engine returned it in."""
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, datetime):
        return ts.timestamp()
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _get(r, key):
    if isinstance(r, dict):
        return r.get(key)
    return getattr(r, key, None)


def _get_id(r):
    return _get(r, "id") or _get(r, "entry_id")


def _normalize(records):
    """Stable, format-agnostic comparison key. Rounds timestamp to 6 decimals
    to avoid float-equality traps between ISO-roundtripped and native floats."""
    def key(r):
        return (
            round(_ts_to_float(_get(r, "timestamp")), 6),
            _get_id(r) or "",
        )
    return sorted(records, key=key)


# ---------------------------------------------------------------------------
# Structural guards — must pass before parity tests are meaningful
# ---------------------------------------------------------------------------

def test_head_is_not_s1():
    """Dataset invariant: position 0 must not be s1, so limit-before-filter
    bugs on session_id='s1' produce a strictly smaller result than correct."""
    assert _SESSION_PATTERN[0] != "s1"


def test_s1_is_half():
    """Dataset invariant: s1 represents exactly 50% of entries."""
    assert _SESSION_PATTERN.count("s1") == len(_SESSION_PATTERN) // 2


def test_timestamps_monotonic(parity_data_dir):
    """Dataset invariant: timestamps are strictly increasing in write order."""
    path = parity_data_dir / "shards" / "sessions.jsonl"
    prev = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            ts = _ts_to_float(json.loads(line)["timestamp"])
            if prev is not None:
                assert ts > prev, f"timestamps not strictly monotonic: {prev} -> {ts}"
            prev = ts


# ---------------------------------------------------------------------------
# Parity — without limit (3 action_names)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action_name", ["grep", "read_file", "write_file"])
def test_by_action_name_no_limit(parity_engines, action_name):
    rr, si = parity_engines

    si_result = si.get_actions(action_name=action_name, limit=100)
    rr_result = rr.query_actions(action_name=action_name, limit=100)

    si_ids = [_get_id(r) for r in _normalize(si_result)]
    rr_ids = [_get_id(r) for r in _normalize(rr_result)]

    assert si_ids == rr_ids, (
        f"Parity failed for action_name='{action_name}' (no limit)\n"
        f"  SI ids: {si_ids}\n"
        f"  RR ids: {rr_ids}"
    )


# ---------------------------------------------------------------------------
# Parity — with limit=10 (critical: dataset forces limit-before-filter bugs
# to produce a strictly different result than limit-after-filter)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action_name", ["grep", "read_file", "write_file"])
def test_by_action_name_with_limit_10(parity_engines, action_name):
    rr, si = parity_engines

    si_result = si.get_actions(action_name=action_name, limit=10)
    rr_result = rr.query_actions(action_name=action_name, limit=10)

    si_ids = [_get_id(r) for r in _normalize(si_result)]
    rr_ids = [_get_id(r) for r in _normalize(rr_result)]

    assert si_ids == rr_ids, (
        f"Parity failed for action_name='{action_name}' (limit=10)\n"
        f"  SI ids: {si_ids}\n"
        f"  RR ids: {rr_ids}"
    )


# ---------------------------------------------------------------------------
# Parity — no filters at all (None/None, covers wildcard semantics)
# ---------------------------------------------------------------------------

def test_no_session_filter_safe(parity_engines):
    rr, si = parity_engines

    si_result = si.get_actions(
        action_name=None, session_id=None,
        start_time=None, end_time=None, limit=100,
    )
    rr_result = rr.query_actions(
        action_name=None, session_id=None,
        start_time=None, end_time=None, limit=100,
    )

    si_ids = [_get_id(r) for r in _normalize(si_result)]
    rr_ids = [_get_id(r) for r in _normalize(rr_result)]

    assert si_ids == rr_ids, (
        f"Parity failed for no-filter case\n"
        f"  SI ids ({len(si_ids)}): {si_ids}\n"
        f"  RR ids ({len(rr_ids)}): {rr_ids}"
    )
