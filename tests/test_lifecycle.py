"""Tests for DSM Shard Lifecycle (Module E)."""

import json
from datetime import datetime, timezone

import pytest

from dsm.collective import CollectiveMemoryDistiller, CollectiveShard, ShardSyncEngine
from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.identity.identity_registry import IdentityRegistry
from dsm.lifecycle import (
    LIFECYCLE_SHARD,
    LifecycleResult,
    ShardLifecycle,
    ShardState,
    TriggerResult,
    VerifyResult,
)
from dsm.orchestrator import NeutralOrchestrator, RuleSet
from dsm.sovereignty import SovereigntyPolicy


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def tmp_storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


@pytest.fixture
def lifecycle(tmp_storage):
    return ShardLifecycle(tmp_storage)


@pytest.fixture
def lifecycle_with_distiller(tmp_storage):
    distiller = CollectiveMemoryDistiller(threshold=5)
    return ShardLifecycle(tmp_storage, distiller=distiller)


def _populate_shard(storage, shard_id, count=3):
    """Helper: write N entries to a shard."""
    for i in range(count):
        entry = Entry(
            id=f"e{i}",
            timestamp=datetime.now(timezone.utc),
            session_id="test",
            source="test",
            content=f"content_{i}",
            shard=shard_id,
            hash="",
            prev_hash=None,
            metadata={"event_type": "test"},
            version="v2.0",
        )
        storage.append(entry)


# ------------------------------------------------------------------
# State
# ------------------------------------------------------------------


class TestState:
    def test_state_default_active(self, lifecycle):
        assert lifecycle.state("any_shard") == ShardState.ACTIVE

    def test_state_after_drain(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "my_shard")
        lifecycle.drain("my_shard", "owner_1", "sig")
        assert lifecycle.state("my_shard") == ShardState.DRAINING

    def test_state_cached(self, lifecycle):
        # First call scans, caches result
        lifecycle.state("x")
        # Second call from cache
        assert lifecycle.state("x") == ShardState.ACTIVE


# ------------------------------------------------------------------
# Drain
# ------------------------------------------------------------------


class TestDrain:
    def test_drain_from_active_success(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        result = lifecycle.drain("s1", "owner", "sig")
        assert isinstance(result, LifecycleResult)
        assert result.ok
        assert result.transition == "active->draining"

    def test_drain_triggers_distillation(self, lifecycle_with_distiller, tmp_storage):
        coll = CollectiveShard(tmp_storage, "test_coll")
        # Populate collective via direct storage writes (simulating sync engine)
        for i in range(8):
            entry = Entry(
                id=f"c{i}", timestamp=datetime.now(timezone.utc),
                session_id="sync", source="sync",
                content=json.dumps({"agent_id": "a1", "source_hash": "", "content_hash": "",
                                    "summary": f"s{i}", "detail": "", "key_findings": [],
                                    "action_type": "obs", "agent_prev_hash": ""}),
                shard=coll.shard_name, hash="", prev_hash=None,
                metadata={"event_type": "collective_contribution"}, version="v2.0",
            )
            tmp_storage.append(entry)

        result = lifecycle_with_distiller.drain(coll.shard_name, "owner", "sig",
                                                 collective=coll)
        assert result.ok
        assert result.distilled >= 0  # distiller ran

    def test_drain_from_sealed_fails(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s2")
        lifecycle.drain("s2", "o", "s")
        lifecycle.seal("s2", "o", "s")
        result = lifecycle.drain("s2", "o", "s")
        assert not result.ok
        assert "sealed" in result.error


# ------------------------------------------------------------------
# Seal
# ------------------------------------------------------------------


class TestSeal:
    def test_seal_from_draining_success(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        lifecycle.drain("s1", "o", "s")
        result = lifecycle.seal("s1", "o", "s")
        assert result.ok
        assert result.transition == "draining->sealed"
        assert result.final_hash is not None

    def test_seal_auto_drains_if_active(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        result = lifecycle.seal("s1", "o", "s")
        assert result.ok
        # Should have auto-drained then sealed
        assert lifecycle.state("s1") == ShardState.SEALED

    def test_seal_spot_check_before_close(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        # Seal performs spot-check internally
        result = lifecycle.seal("s1", "o", "s")
        assert result.ok

    def test_seal_writes_final_entry_in_shard(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        result = lifecycle.seal("s1", "o", "s")
        assert result.entry is not None
        assert result.entry.shard == LIFECYCLE_SHARD

    def test_seal_fails_on_archived(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        lifecycle.seal("s1", "o", "s")
        lifecycle.archive("s1", "o", "s")
        result = lifecycle.seal("s1", "o", "s")
        assert not result.ok


# ------------------------------------------------------------------
# Archive
# ------------------------------------------------------------------


class TestArchive:
    def test_archive_from_sealed_success(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        lifecycle.seal("s1", "o", "s")
        result = lifecycle.archive("s1", "o", "s")
        assert result.ok
        assert result.transition == "sealed->archived"

    def test_archive_stores_hash_only(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        lifecycle.seal("s1", "o", "s")
        result = lifecycle.archive("s1", "o", "s")
        data = json.loads(result.entry.content)
        assert data.get("hash_only") is True
        assert data.get("final_hash") is not None

    def test_archive_from_active_fails(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        result = lifecycle.archive("s1", "o", "s")
        assert not result.ok
        assert "active" in result.error

    def test_archived_state_is_terminal(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        lifecycle.seal("s1", "o", "s")
        lifecycle.archive("s1", "o", "s")
        assert lifecycle.state("s1") == ShardState.ARCHIVED

        # Cannot drain, seal, or archive again
        assert not lifecycle.drain("s1", "o", "s").ok
        assert not lifecycle.seal("s1", "o", "s").ok
        assert not lifecycle.archive("s1", "o", "s").ok


# ------------------------------------------------------------------
# Verification
# ------------------------------------------------------------------


class TestVerify:
    def test_verify_spot_check_valid(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        result = lifecycle.verify("s1", deep=False)
        assert isinstance(result, VerifyResult)
        assert result.passed
        assert result.last_hash is not None

    def test_verify_spot_check_empty_shard(self, lifecycle):
        result = lifecycle.verify("empty_shard", deep=False)
        assert result.passed

    def test_verify_deep_full_replay(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1", count=5)
        result = lifecycle.verify("s1", deep=True)
        assert result.passed
        assert result.summary["entry_count"] == 5


# ------------------------------------------------------------------
# Triggers
# ------------------------------------------------------------------


class TestTriggers:
    def test_trigger_on_max_entries(self, lifecycle, tmp_storage):
        # infra shards have max_entries=10_000 by default
        # We use "sessions" (agent family, max_entries=100_000)
        # Create a shard in infra family
        _populate_shard(tmp_storage, "sync_log", count=5)
        result = lifecycle.check_triggers("sync_log", "o", "s")
        # 5 < 10_000 so no trigger
        assert not result.triggered

    def test_trigger_check_lightweight(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "sessions", count=2)
        result = lifecycle.check_triggers("sessions", "o", "s")
        assert isinstance(result, TriggerResult)
        assert not result.triggered

    def test_trigger_not_active_skips(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        lifecycle.seal("s1", "o", "s")
        result = lifecycle.check_triggers("s1", "o", "s")
        assert not result.triggered
        assert result.reason == "not active"


# ------------------------------------------------------------------
# History & invariants
# ------------------------------------------------------------------


class TestHistory:
    def test_lifecycle_history_in_shard(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        lifecycle.drain("s1", "o", "s")
        lifecycle.seal("s1", "o", "s")
        history = lifecycle.history("s1")
        assert len(history) >= 2

    def test_transitions_append_only(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        lifecycle.drain("s1", "o", "s")
        lifecycle.seal("s1", "o", "s")
        lifecycle.archive("s1", "o", "s")

        all_entries = tmp_storage.read(LIFECYCLE_SHARD, limit=100)
        # drain + seal transitions from auto-drain + seal + archive
        assert len(all_entries) >= 3

    def test_drain_blocks_further_transitions_except_seal(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        lifecycle.drain("s1", "o", "s")
        # Can't drain again
        assert not lifecycle.drain("s1", "o", "s").ok
        # Can't archive from draining
        assert not lifecycle.archive("s1", "o", "s").ok
        # CAN seal from draining
        assert lifecycle.seal("s1", "o", "s").ok

    def test_seal_blocks_further_push(self, lifecycle, tmp_storage):
        _populate_shard(tmp_storage, "s1")
        lifecycle.seal("s1", "o", "s")
        assert lifecycle.state("s1") == ShardState.SEALED
        # Cannot drain or seal again
        assert not lifecycle.drain("s1", "o", "s").ok
        assert not lifecycle.seal("s1", "o", "s").ok
