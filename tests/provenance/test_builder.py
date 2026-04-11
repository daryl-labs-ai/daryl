"""Phase 4.1 tests for ``dsm.provenance.build_provenance`` (daryl port).

Mirrors the 9 priority contracts from ``dsm_v0/test_provenance.py``,
but uses daryl's native ``Storage`` + ``Entry`` + ``verify.verify_shard``
primitives. The shapes and enums must match dsm_v0 bit-for-bit — this
is verified by ``test_enum_parity_with_dsm_v0``.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.provenance import (
    INTEGRITY_BROKEN,
    INTEGRITY_NOT_VERIFIED,
    INTEGRITY_OK,
    TRUST_PARTIAL,
    TRUST_UNVERIFIED,
    TRUST_VERIFIED,
    build_provenance,
    promote_to_verified_claims,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_storage(tmp_path):
    """Fresh daryl Storage under a tmp dir."""
    data_dir = tmp_path / "data"
    return Storage(data_dir=str(data_dir))


def _make_entry(
    storage: Storage,
    shard: str,
    session_id: str,
    source: str,
    content: str,
    event_type: str = "",
    ts: datetime | None = None,
) -> Entry:
    """Append an entry and return the persisted Entry."""
    entry = Entry(
        id=str(uuid.uuid4()),
        timestamp=ts or datetime.now(timezone.utc),
        session_id=session_id,
        source=source,
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={"event_type": event_type} if event_type else {},
        version="v2.0",
    )
    return storage.append(entry)


def _match_from_entry(
    entry: Entry,
    type_: str,
    time_status: str = "still_relevant",
) -> dict:
    """Build a recall-style match dict from a daryl Entry for testing."""
    return {
        "session_id": entry.session_id,
        "source_shard_id": entry.shard,
        "entry_hash": entry.hash,
        "prev_hash": entry.prev_hash,
        "event_type": (entry.metadata or {}).get("event_type", ""),
        "type": type_,
        "time_status": time_status,
        "timestamp": entry.timestamp.timestamp(),
        "content": entry.content,
        "relevance_score": 1.0,
    }


def _tamper_shard(storage: Storage, shard_id: str, line_index: int) -> None:
    """Mutate a line in the shard's JSONL file to break the hash chain.

    daryl stores classic shards as JSONL at
    ``data/shards/{shard_id}.jsonl``; we locate that file and rewrite it.
    Segmented shards use a subdirectory; we handle that too.
    """
    data_dir = Path(storage.data_dir)
    shards_dir = data_dir / "shards"
    classic = shards_dir / f"{shard_id}.jsonl"
    if classic.exists():
        target = classic
    else:
        # Segmented layout: daryl strips the "shard_" prefix when
        # computing the on-disk directory name
        # (``shard_segments.py:_get_shard_family_dir``).
        family_name = shard_id.replace("shard_", "")
        segdir = shards_dir / family_name
        candidates = sorted(segdir.glob(f"{family_name}_*.jsonl"))
        if not candidates:
            raise FileNotFoundError(
                f"shard {shard_id} (family={family_name}) not found on disk"
            )
        target = candidates[0]

    lines = target.read_text().splitlines()
    if line_index >= len(lines):
        raise IndexError(
            f"shard has {len(lines)} lines, can't mutate index {line_index}"
        )
    record = json.loads(lines[line_index])
    record["content"] = "TAMPERED_" + str(record.get("content", ""))
    lines[line_index] = json.dumps(record)
    target.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Test 1 — empty input
# ---------------------------------------------------------------------------


def test_empty_input_returns_well_shaped_block(tmp_storage):
    block = build_provenance(items=[], storage=tmp_storage)
    required = {
        "entry_hashes", "source_shards", "integrity", "verification_hint",
        "record_count", "trust_level", "broken_chains", "oldest_entry_age_days",
    }
    assert required.issubset(block.keys())
    assert block["entry_hashes"] == []
    assert block["source_shards"] == []
    assert block["integrity"] == INTEGRITY_NOT_VERIFIED
    assert block["verification_hint"] is None
    assert block["record_count"] == 0
    assert block["trust_level"] == TRUST_PARTIAL
    assert block["broken_chains"] == 0
    assert block["oldest_entry_age_days"] is None

    block_v = build_provenance(items=[], storage=tmp_storage, verify=True)
    assert block_v["verified_shards"] == []
    assert block_v["broken_shard_details"] == []
    assert block_v["promotable_hashes"] == []


# ---------------------------------------------------------------------------
# Test 2 — fast path shape (no verify)
# ---------------------------------------------------------------------------


def test_fast_path_matches_contract(tmp_storage):
    e = _make_entry(
        tmp_storage,
        shard="sessions",
        session_id="sess-A",
        source="claude",
        content="alpha beta gamma delta decision",
        event_type="user_prompt",
    )
    items = [_match_from_entry(e, type_="historical_decision")]
    block = build_provenance(items=items, storage=tmp_storage, verify=False)

    assert block["integrity"] == INTEGRITY_NOT_VERIFIED
    assert block["trust_level"] == TRUST_PARTIAL
    assert block["broken_chains"] == 0
    assert block["verification_hint"] is not None
    assert "dsm verify sessions" in block["verification_hint"]
    assert "verified_shards" not in block
    assert "broken_shard_details" not in block
    assert "promotable_hashes" not in block
    assert block["record_count"] == 1
    assert block["source_shards"] == ["sessions"]
    assert block["entry_hashes"] == [e.hash]


# ---------------------------------------------------------------------------
# Test 3 — verify on clean chain → OK + selective promotion
# ---------------------------------------------------------------------------


def test_verify_clean_chain_promotes_historical_decisions(tmp_storage):
    # Three entries in one shard. All still_relevant (disjoint matched
    # tokens in a real search; here we just set time_status manually).
    e_up = _make_entry(
        tmp_storage, "sessions", "sess-A", "claude",
        "decisiontokenxxx respected", event_type="user_prompt",
    )
    e_tool = _make_entry(
        tmp_storage, "sessions", "sess-A", "claude",
        "tooltokenyyy invocation", event_type="tool_exec:call",
    )
    e_err = _make_entry(
        tmp_storage, "sessions", "sess-A", "claude",
        "errortokenzzz failure", event_type="error",
    )
    items = [
        _match_from_entry(e_up, type_="historical_decision"),
        _match_from_entry(e_tool, type_="working_assumption"),
        _match_from_entry(e_err, type_="outdated_possibility"),
    ]

    block = build_provenance(items=items, storage=tmp_storage, verify=True)
    assert block["integrity"] == INTEGRITY_OK
    assert block["trust_level"] == TRUST_VERIFIED
    assert block["broken_chains"] == 0
    assert block["verification_hint"] is None
    assert block["verified_shards"] == ["sessions"]
    assert block["broken_shard_details"] == []

    # Only the historical_decision must be promotable.
    promotable = set(block["promotable_hashes"])
    assert e_up.hash in promotable
    assert e_tool.hash not in promotable
    assert e_err.hash not in promotable

    promoted = promote_to_verified_claims(items, block)
    assert len(promoted) == 1
    assert promoted[0]["type"] == "verified_fact"
    assert promoted[0]["promoted_from"] == "historical_decision"
    assert promoted[0]["entry_hash"] == e_up.hash


# ---------------------------------------------------------------------------
# Test 4 — verify on tampered shard (mixed) → broken + partial trust
# ---------------------------------------------------------------------------


def test_verify_tampered_shard_downgrades_trust(tmp_storage):
    # Two shards, tamper one.
    e_good = _make_entry(
        tmp_storage, "sessions_g", "sess-g", "claude",
        "alpha integrity policy good",
    )
    e_bad = _make_entry(
        tmp_storage, "sessions_b", "sess-b", "claude",
        "alpha integrity policy bad",
    )
    items = [
        _match_from_entry(e_good, type_="historical_decision"),
        _match_from_entry(e_bad, type_="historical_decision"),
    ]

    _tamper_shard(tmp_storage, "sessions_b", line_index=0)

    block = build_provenance(items=items, storage=tmp_storage, verify=True)
    assert block["integrity"] == INTEGRITY_BROKEN
    assert block["trust_level"] == TRUST_PARTIAL
    assert block["broken_chains"] == 1
    assert "sessions_g" in block["verified_shards"]
    broken_ids = [d["shard_id"] for d in block["broken_shard_details"]]
    assert "sessions_b" in broken_ids
    assert block["verification_hint"] is not None

    # Only the good shard's historical_decision should be promotable.
    promotable = set(block["promotable_hashes"])
    assert e_good.hash in promotable
    assert e_bad.hash not in promotable


# ---------------------------------------------------------------------------
# Test 5 — fully broken → unverified
# ---------------------------------------------------------------------------


def test_verify_fully_broken_becomes_unverified(tmp_storage):
    e = _make_entry(
        tmp_storage, "sessions_only_bad", "sess-x", "claude",
        "omega integrity fully broken",
    )
    items = [_match_from_entry(e, type_="historical_decision")]
    _tamper_shard(tmp_storage, "sessions_only_bad", line_index=0)

    block = build_provenance(items=items, storage=tmp_storage, verify=True)
    assert block["integrity"] == INTEGRITY_BROKEN
    assert block["trust_level"] == TRUST_UNVERIFIED
    assert block["broken_chains"] == 1
    assert block["verified_shards"] == []
    assert block["promotable_hashes"] == []


# ---------------------------------------------------------------------------
# Test 6 — hash-only resolver
# ---------------------------------------------------------------------------


def test_hash_only_resolver(tmp_storage):
    e = _make_entry(
        tmp_storage, "sessions", "sess-H", "claude",
        "hash resolver query target",
        event_type="user_prompt",
    )
    block = build_provenance(
        entry_hashes=[e.hash], storage=tmp_storage, verify=False,
    )
    assert block["record_count"] == 1
    assert e.hash in block["entry_hashes"]
    assert block["source_shards"] == ["sessions"]


# ---------------------------------------------------------------------------
# Test 7 — no-write guarantee
# ---------------------------------------------------------------------------


def test_provenance_never_writes(tmp_storage, tmp_path):
    e = _make_entry(
        tmp_storage, "sessions", "sess-RO", "claude",
        "readonly guarantee",
        event_type="user_prompt",
    )
    items = [_match_from_entry(e, type_="historical_decision")]

    # Snapshot all files under data_dir.
    data_dir = Path(tmp_storage.data_dir)
    before_files = sorted(p.relative_to(data_dir) for p in data_dir.rglob("*") if p.is_file())
    before_bytes = {
        str(p): (data_dir / p).read_bytes() for p in before_files
    }
    before_mtimes = {
        str(p): (data_dir / p).stat().st_mtime_ns for p in before_files
    }

    for _ in range(3):
        build_provenance(items=items, storage=tmp_storage, verify=False)
        build_provenance(items=items, storage=tmp_storage, verify=True)

    after_files = sorted(p.relative_to(data_dir) for p in data_dir.rglob("*") if p.is_file())
    assert after_files == before_files, f"new files: {set(after_files) - set(before_files)}"
    for p in after_files:
        assert (data_dir / p).read_bytes() == before_bytes[str(p)], \
            f"bytes mutated: {p}"
        assert (data_dir / p).stat().st_mtime_ns == before_mtimes[str(p)], \
            f"mtime mutated: {p}"


# ---------------------------------------------------------------------------
# Test 8 — enum parity with dsm_v0 (string equality — no drift)
# ---------------------------------------------------------------------------


def test_enum_parity_with_dsm_v0():
    """Daryl port must use the exact same string values as dsm_v0.

    This guards the contract promise in the consumption layer doc:
    "caller code written against dsm_v0.recall.search_memory can be
    re-imported as dsm.recall.search_memory with identical shape and
    enum values."
    """
    assert TRUST_VERIFIED == "verified"
    assert TRUST_PARTIAL == "partial"
    assert TRUST_UNVERIFIED == "unverified"
    assert INTEGRITY_OK == "OK"
    assert INTEGRITY_NOT_VERIFIED == "not_verified"
    assert INTEGRITY_BROKEN == "broken"


# ---------------------------------------------------------------------------
# Test 9 — oldest_entry_age_days is computed correctly
# ---------------------------------------------------------------------------


def test_oldest_entry_age_days(tmp_storage):
    now_dt = datetime.now(timezone.utc)
    old_dt = now_dt - timedelta(days=5)
    e_old = _make_entry(
        tmp_storage, "sessions", "sess-age", "claude",
        "old entry", event_type="user_prompt", ts=old_dt,
    )
    e_new = _make_entry(
        tmp_storage, "sessions", "sess-age", "claude",
        "new entry", event_type="user_prompt", ts=now_dt,
    )
    items = [
        _match_from_entry(e_old, type_="historical_decision"),
        _match_from_entry(e_new, type_="historical_decision"),
    ]
    block = build_provenance(
        items=items, storage=tmp_storage,
        now=now_dt.timestamp(),
    )
    age = block["oldest_entry_age_days"]
    assert age is not None
    assert 4.9 < age < 5.1, f"expected ~5.0, got {age}"
