"""Phase 4.2 tests for ``dsm.recall.search_memory`` (daryl port).

Mirrors the 10 priority contracts from ``dsm_v0/test_recall.py`` but
uses daryl's native Storage + Entry + DSMReadRelay primitives. The
output shape and enum string values must match dsm_v0 bit-for-bit.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.recall import (
    STATUS_OUTDATED,
    STATUS_STILL_RELEVANT,
    STATUS_SUPERSEDED,
    STATUS_UNCERTAIN,
    TYPE_HISTORICAL_DECISION,
    TYPE_OUTDATED_POSSIBILITY,
    TYPE_WORKING_ASSUMPTION,
    current_session_id,
    list_sessions,
    search_memory,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


def _append(
    storage: Storage,
    shard: str,
    session_id: str,
    text: str,
    event_type: str = "user_prompt",
    ts: datetime | None = None,
) -> Entry:
    entry = Entry(
        id=str(uuid.uuid4()),
        timestamp=ts or datetime.now(timezone.utc),
        session_id=session_id,
        source="claude",
        content=text,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={"event_type": event_type},
        version="v2.0",
    )
    return storage.append(entry)


# ---------------------------------------------------------------------------
# Test 1 — shape stability on empty corpus
# ---------------------------------------------------------------------------


def test_shape_stability_empty_corpus(tmp_storage):
    out = search_memory("kernel freeze", storage=tmp_storage)
    required_top = {"query", "current_session", "past_session_recall",
                    "verified_claims", "provenance"}
    assert required_top.issubset(out.keys())
    assert out["query"] == "kernel freeze"
    assert out["current_session"]["session_id"] is None
    assert out["current_session"]["matches"] == []
    assert out["past_session_recall"] == []
    assert out["verified_claims"] == []
    prov = out["provenance"]
    assert prov["record_count"] == 0
    assert prov["trust_level"] == "partial"
    assert prov["integrity"] == "not_verified"
    assert prov["broken_chains"] == 0
    assert prov["oldest_entry_age_days"] is None
    assert prov["verification_hint"] is None  # no shards → no hint


# ---------------------------------------------------------------------------
# Test 2 — shape with results + field contract
# ---------------------------------------------------------------------------


def test_shape_stability_with_results(tmp_storage):
    _append(tmp_storage, "sessions", "sess-A", "kernel freeze must be respected")
    out = search_memory("kernel freeze", storage=tmp_storage)
    assert isinstance(out["past_session_recall"], list)
    assert len(out["past_session_recall"]) >= 1
    first = out["past_session_recall"][0]
    required = {"session_id", "entry_hash", "prev_hash", "event_type",
                "type", "content", "timestamp", "relevance_score",
                "time_status", "source_shard_id"}
    assert required.issubset(first.keys()), f"missing: {required - first.keys()}"
    assert first["session_id"] == "sess-A"
    assert first["source_shard_id"] == "sessions"
    assert first["type"] == TYPE_HISTORICAL_DECISION
    assert first["time_status"] in {
        STATUS_STILL_RELEVANT, STATUS_SUPERSEDED, STATUS_OUTDATED, STATUS_UNCERTAIN,
    }


# ---------------------------------------------------------------------------
# Test 3 — current session never in past_session_recall
# ---------------------------------------------------------------------------


def test_current_session_never_in_past(tmp_storage):
    # Two sessions living in the same shard — daryl's logical model.
    _append(tmp_storage, "sessions", "sess-old", "kernel freeze decision recorded")
    _append(tmp_storage, "sessions", "sess-current", "kernel freeze discussion today")

    out = search_memory(
        "kernel freeze",
        storage=tmp_storage,
        session_id="sess-current",
    )
    past_sessions = {m["session_id"] for m in out["past_session_recall"]}
    assert "sess-current" not in past_sessions
    assert out["current_session"]["session_id"] == "sess-current"
    assert out["current_session"]["matches"] == []  # default exclude

    out2 = search_memory(
        "kernel freeze",
        storage=tmp_storage,
        session_id="sess-current",
        include_current_session=True,
    )
    past2 = {m["session_id"] for m in out2["past_session_recall"]}
    curr2 = {m["session_id"] for m in out2["current_session"]["matches"]}
    assert "sess-current" not in past2
    assert curr2 == {"sess-current"}
    assert "sess-old" in past2


# ---------------------------------------------------------------------------
# Test 4 — superseded detection
# ---------------------------------------------------------------------------


def test_superseded_older_decision(tmp_storage):
    _append(
        tmp_storage, "sessions", "sess-old",
        "kernel freeze policy allow monkey patches",
    )
    _append(
        tmp_storage, "sessions", "sess-new",
        "kernel freeze policy updated forbid monkey patches entirely",
    )
    out = search_memory(
        "kernel freeze monkey patches", storage=tmp_storage, max_results=10,
    )
    by_sess = {m["session_id"]: m for m in out["past_session_recall"]}
    assert "sess-old" in by_sess
    assert "sess-new" in by_sess
    assert by_sess["sess-old"]["time_status"] == STATUS_SUPERSEDED
    assert by_sess["sess-new"]["time_status"] == STATUS_STILL_RELEVANT


# ---------------------------------------------------------------------------
# Test 5 — type classification mapping
# ---------------------------------------------------------------------------


def test_type_classification_mapping(tmp_storage):
    _append(tmp_storage, "sessions", "sess-T", "recall layer consumption",
            event_type="user_prompt")
    _append(tmp_storage, "sessions", "sess-T", "recall layer consumption scan",
            event_type="tool_exec:call")
    _append(tmp_storage, "sessions", "sess-T", "recall layer consumption failed",
            event_type="error")
    _append(tmp_storage, "sessions", "sess-T", "recall layer consumption",
            event_type="session_start")  # must be skipped

    out = search_memory(
        "recall layer consumption", storage=tmp_storage, max_results=20,
    )
    seen = {m["event_type"]: m["type"] for m in out["past_session_recall"]}
    assert "session_start" not in seen
    if "user_prompt" in seen:
        assert seen["user_prompt"] == TYPE_HISTORICAL_DECISION
    if "tool_exec:call" in seen:
        assert seen["tool_exec:call"] == TYPE_WORKING_ASSUMPTION
    if "error" in seen:
        assert seen["error"] == TYPE_OUTDATED_POSSIBILITY


# ---------------------------------------------------------------------------
# Test 6 — provenance block dedup + counts
# ---------------------------------------------------------------------------


def test_provenance_block_dedup_and_counts(tmp_storage):
    _append(tmp_storage, "sessions_p1", "sess-a", "provenance hash chain integrity")
    _append(tmp_storage, "sessions_p2", "sess-b", "provenance hash chain integrity")
    out = search_memory(
        "provenance hash chain integrity",
        storage=tmp_storage,
        max_results=10,
    )
    prov = out["provenance"]
    assert prov["record_count"] == len(out["past_session_recall"])
    assert sorted(prov["source_shards"]) == ["sessions_p1", "sessions_p2"]
    assert len(prov["entry_hashes"]) == len(set(prov["entry_hashes"]))
    assert prov["trust_level"] == "partial"
    # Phase 3/4 contract: non-null hint when not verified and shards exist
    assert prov["verification_hint"] is not None
    assert "dsm verify" in prov["verification_hint"]
    assert prov["broken_chains"] == 0
    assert prov["oldest_entry_age_days"] is not None


# ---------------------------------------------------------------------------
# Test 7 — no-write guarantee
# ---------------------------------------------------------------------------


def test_recall_never_writes(tmp_storage):
    _append(tmp_storage, "sessions", "sess-ro",
            "no write guarantee kernel frozen")
    data_dir = Path(tmp_storage.data_dir)

    before_files = sorted(p.relative_to(data_dir) for p in data_dir.rglob("*") if p.is_file())
    before_bytes = {str(p): (data_dir / p).read_bytes() for p in before_files}
    before_mtimes = {str(p): (data_dir / p).stat().st_mtime_ns for p in before_files}

    for _ in range(3):
        search_memory(
            "no write guarantee kernel frozen",
            storage=tmp_storage,
            max_results=5,
            include_current_session=True,
        )

    after_files = sorted(p.relative_to(data_dir) for p in data_dir.rglob("*") if p.is_file())
    assert after_files == before_files
    for p in after_files:
        assert (data_dir / p).read_bytes() == before_bytes[str(p)]
        assert (data_dir / p).stat().st_mtime_ns == before_mtimes[str(p)]


# ---------------------------------------------------------------------------
# Test 8 — list_sessions across daryl shards
# ---------------------------------------------------------------------------


def test_list_sessions_enumerates_across_shards(tmp_storage):
    _append(tmp_storage, "sessions", "sess-a", "alpha")
    _append(tmp_storage, "sessions", "sess-b", "beta")
    _append(tmp_storage, "collective_main", "sess-c", "gamma")
    sessions = list_sessions(storage=tmp_storage)
    assert set(sessions) == {"sess-a", "sess-b", "sess-c"}


# ---------------------------------------------------------------------------
# Test 9 — current_session_id resolves from sessions shard
# ---------------------------------------------------------------------------


def test_current_session_id_picks_latest(tmp_storage):
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    _append(tmp_storage, "sessions", "sess-old", "older", ts=now - timedelta(days=5))
    _append(tmp_storage, "sessions", "sess-new", "newer", ts=now)
    assert current_session_id(storage=tmp_storage) == "sess-new"


# ---------------------------------------------------------------------------
# Test 10 — verify=True integration promotes via dsm.provenance
# ---------------------------------------------------------------------------


def test_search_memory_verify_integration(tmp_storage):
    # Disjoint tokens to avoid spurious supersession (same lesson as Phase 3).
    _append(
        tmp_storage, "sessions", "sess-int",
        "integrationdecisionaaa promotes", event_type="user_prompt",
    )
    _append(
        tmp_storage, "sessions", "sess-int",
        "integrationtoolbbb invocation", event_type="tool_exec:call",
    )
    out = search_memory(
        "integrationdecisionaaa integrationtoolbbb",
        storage=tmp_storage,
        verify=True,
        max_results=10,
    )
    claims = out["verified_claims"]
    assert len(claims) == 1
    assert claims[0]["type"] == "verified_fact"
    assert claims[0]["promoted_from"] == TYPE_HISTORICAL_DECISION
    assert claims[0]["event_type"] == "user_prompt"

    prov = out["provenance"]
    assert prov["integrity"] == "OK"
    assert prov["trust_level"] == "verified"
    assert prov["verification_hint"] is None  # OK → no hint
