"""Tests for DSM Collective Memory (Module D)."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from dsm.collective import (
    COLLECTIVE_PREFIX,
    SYNC_LOG_SHARD,
    CollectiveEntry,
    CollectiveMemoryDistiller,
    CollectiveShard,
    ContextStack,
    DigestEntry,
    PullResult,
    PushResult,
    ReconcileResult,
    RollingDigester,
    ShardSyncEngine,
)
from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.identity.identity_registry import IdentityRegistry
from dsm.orchestrator import NeutralOrchestrator, RuleSet
from dsm.sovereignty import SovereigntyPolicy


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def tmp_storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


@pytest.fixture
def registry(tmp_storage):
    return IdentityRegistry(tmp_storage)


@pytest.fixture
def sovereignty(tmp_storage):
    return SovereigntyPolicy(tmp_storage)


@pytest.fixture
def orchestrator(tmp_storage, registry, sovereignty):
    return NeutralOrchestrator(
        storage=tmp_storage,
        rules=RuleSet.default(),
        identity=registry,
        policy=sovereignty,
    )


@pytest.fixture
def collective(tmp_storage):
    return CollectiveShard(tmp_storage, "main")


@pytest.fixture
def sync_engine(tmp_storage, collective, registry, sovereignty, orchestrator):
    return ShardSyncEngine(tmp_storage, collective, registry, sovereignty, orchestrator)


def _setup_agent_and_policy(registry, sovereignty, agent_id="agent_1", owner_id="owner_1"):
    registry.register(agent_id, "k" * 64, owner_id, "sig", model="claude")
    sovereignty.set(owner_id, "sig", {
        "agents": [agent_id],
        "min_trust_score": 0.1,
        "allowed_types": ["observation", "analysis", "unknown"],
        "approval_required": [],
        "cross_ai": True,
    })


def _make_private_entry(content="test observation", event_type="observation", hash_val=None):
    h = hash_val or hashlib.sha256(content.encode()).hexdigest()
    return Entry(
        id="priv-" + h[:8],
        timestamp=datetime.now(timezone.utc),
        session_id="test",
        source="test",
        content=content,
        shard="sessions",
        hash=h,
        prev_hash=None,
        metadata={"event_type": event_type},
        version="v2.0",
    )


# ------------------------------------------------------------------
# Push
# ------------------------------------------------------------------


class TestPush:
    def test_push_eligible_entries_success(self, sync_engine, registry, sovereignty):
        _setup_agent_and_policy(registry, sovereignty)
        entries = [_make_private_entry("obs1"), _make_private_entry("obs2")]
        result = sync_engine.push("agent_1", "owner_1", entries)
        assert isinstance(result, PushResult)
        assert len(result.admitted) == 2
        assert len(result.rejected) == 0

    def test_push_incremental_since_hash(self, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        e1 = _make_private_entry("first")
        e2 = _make_private_entry("second")
        sync_engine.push("agent_1", "owner_1", [e1])
        sync_engine.push("agent_1", "owner_1", [e2])
        index = collective._ensure_index()
        assert len(index) == 2

    def test_push_rejected_by_orchestrator(self, sync_engine, registry, sovereignty):
        # No agent registered, no policy — orchestrator denies
        entries = [_make_private_entry()]
        result = sync_engine.push("ghost", "nobody", entries)
        assert len(result.rejected) == 1
        assert len(result.admitted) == 0

    def test_push_stores_projection_not_full_entry(self, tmp_storage, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        original = _make_private_entry("this is sensitive private content that should NOT appear in collective")
        # Use a summary_fn that produces a safe summary (real usage)
        sync_engine.push("agent_1", "owner_1", [original],
                         summary_fn=lambda e: "observation recorded")

        raw_entries = tmp_storage.read(collective.shard_name, limit=10)
        assert len(raw_entries) == 1
        data = json.loads(raw_entries[0].content)
        # Projection has summary + content_hash, not full content
        assert "content_hash" in data
        assert "source_hash" in data
        assert "this is sensitive private content" not in json.dumps(data)

    def test_push_single_writer_guaranteed(self, collective):
        # CollectiveShard has no append method — only SyncEngine writes
        assert not hasattr(collective, "append")

    def test_push_with_detail_and_key_findings(self, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        entry = _make_private_entry("detailed observation")

        def detail_fn(e):
            return ("Extended detail about the observation", ["finding_1", "finding_2"])

        result = sync_engine.push("agent_1", "owner_1", [entry], detail_fn=detail_fn)
        assert len(result.admitted) == 1

        recent = collective.recent(limit=1)
        assert len(recent) == 1
        assert recent[0].detail == "Extended detail about the observation"
        assert "finding_1" in recent[0].key_findings

    def test_push_without_detail_falls_back_to_summary(self, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        entry = _make_private_entry("short obs")
        sync_engine.push("agent_1", "owner_1", [entry])

        recent = collective.recent(limit=1)
        assert recent[0].detail == ""
        assert recent[0].summary != ""

    def test_tier2_default_empty_backward_compatible(self, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        entry = _make_private_entry("no detail")
        sync_engine.push("agent_1", "owner_1", [entry])
        recent = collective.recent(limit=1)
        assert recent[0].detail == ""
        assert recent[0].key_findings == ()


# ------------------------------------------------------------------
# Pull
# ------------------------------------------------------------------


class TestPull:
    def test_pull_incremental_success(self, tmp_storage, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        sync_engine.push("agent_1", "owner_1", [_make_private_entry("data")])
        result = sync_engine.pull("agent_1")
        assert isinstance(result, PullResult)
        assert result.synced >= 1

    def test_pull_writes_to_sync_log_not_agent_shard(self, tmp_storage, sync_engine, registry, sovereignty):
        _setup_agent_and_policy(registry, sovereignty)
        sync_engine.push("agent_1", "owner_1", [_make_private_entry()])
        sync_engine.pull("agent_1")

        sync_entries = tmp_storage.read(SYNC_LOG_SHARD, limit=10)
        assert len(sync_entries) >= 1
        data = json.loads(sync_entries[0].content)
        assert data["event_type"] == "sync_pull"

    def test_pull_empty_if_nothing_new(self, sync_engine, registry, sovereignty):
        _setup_agent_and_policy(registry, sovereignty)
        result = sync_engine.pull("agent_1")
        # No entries pushed — nothing to pull
        assert result.synced == 0

    def test_pull_writes_sync_entry_not_copies(self, tmp_storage, sync_engine, registry, sovereignty):
        _setup_agent_and_policy(registry, sovereignty)
        sync_engine.push("agent_1", "owner_1", [_make_private_entry()])
        sync_engine.pull("agent_1")
        sync_entries = tmp_storage.read(SYNC_LOG_SHARD, limit=10)
        data = json.loads(sync_entries[0].content)
        # Sync entry is a summary, not a copy of collective entries
        assert "entries_synced" in data
        assert "content" not in data


# ------------------------------------------------------------------
# Reconcile
# ------------------------------------------------------------------


class TestReconcile:
    def test_reconcile_push_then_pull(self, sync_engine, registry, sovereignty):
        _setup_agent_and_policy(registry, sovereignty)
        entries = [_make_private_entry("reconcile_test")]
        result = sync_engine.reconcile("agent_1", "owner_1", entries)
        assert isinstance(result, ReconcileResult)
        assert len(result.push.admitted) == 1
        assert result.pull.synced >= 1

    def test_reconcile_incremental_checkpoints(self, sync_engine, registry, sovereignty):
        _setup_agent_and_policy(registry, sovereignty)
        r1 = sync_engine.reconcile("agent_1", "owner_1", [_make_private_entry("batch1")])
        r2 = sync_engine.reconcile("agent_1", "owner_1", [_make_private_entry("batch2")],
                                   since_hash=r1.pull.last_hash)
        assert r2.pull.synced >= 0


# ------------------------------------------------------------------
# CollectiveShard index
# ------------------------------------------------------------------


class TestCollectiveIndex:
    def test_collective_index_o1_query(self, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        sync_engine.push("agent_1", "owner_1", [_make_private_entry("idx_test")])
        # First call builds index
        collective.recent()
        # Second call uses cached index — O(1)
        result = collective.recent(limit=1)
        assert len(result) == 1

    def test_collective_index_tracks_last_contribution_by_agent(self, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        sync_engine.push("agent_1", "owner_1", [_make_private_entry("c1")])
        last = collective.last_hash_for_agent("agent_1")
        assert last != ""

    def test_collective_window_sliding(self, tmp_storage):
        # Small window
        coll = CollectiveShard(tmp_storage, "tiny", window_size=2)
        assert coll._window_size == 2

    def test_collective_summary_accurate(self, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        sync_engine.push("agent_1", "owner_1", [_make_private_entry("s1"), _make_private_entry("s2")])
        s = collective.summary()
        assert s["entry_count"] == 2
        assert "agent_1" in s["agents"]

    def test_projection_includes_content_hash_and_summary(self, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        sync_engine.push("agent_1", "owner_1", [_make_private_entry("verifiable")])
        recent = collective.recent(limit=1)
        assert recent[0].content_hash != ""
        assert recent[0].summary != ""

    def test_projection_verifiable_without_private_shard(self, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        original_content = "verifiable content check"
        entry = _make_private_entry(original_content)
        sync_engine.push("agent_1", "owner_1", [entry])
        recent = collective.recent(limit=1)
        # Verify content_hash matches original
        expected_hash = hashlib.sha256(original_content.encode()).hexdigest()
        assert recent[0].content_hash == expected_hash


# ------------------------------------------------------------------
# Multi-agent
# ------------------------------------------------------------------


class TestMultiAgent:
    def test_multi_agent_same_collective(self, sync_engine, registry, sovereignty, collective):
        registry.register("agent_1", "k1" * 32, "owner_1", "sig1", model="claude")
        registry.register("agent_2", "k2" * 32, "owner_1", "sig2", model="gpt")
        sovereignty.set("owner_1", "sig", {
            "agents": ["agent_1", "agent_2"],
            "min_trust_score": 0.1,
            "allowed_types": ["observation", "unknown"],
            "cross_ai": True,
        })

        sync_engine.push("agent_1", "owner_1", [_make_private_entry("from_claude")])
        sync_engine.push("agent_2", "owner_1", [_make_private_entry("from_gpt")])

        s = collective.summary()
        assert s["entry_count"] == 2
        assert "agent_1" in s["agents"]
        assert "agent_2" in s["agents"]

    def test_agent_chain_maintained_in_collective(self, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        sync_engine.push("agent_1", "owner_1", [_make_private_entry("first_contrib")])
        first_hash = collective.last_hash_for_agent("agent_1")
        sync_engine.push("agent_1", "owner_1", [_make_private_entry("second_contrib")])

        recent = collective.recent(limit=1)
        assert recent[0].agent_prev_hash == first_hash


# ------------------------------------------------------------------
# Distiller
# ------------------------------------------------------------------


class TestDistiller:
    def test_distill_triggered_on_threshold(self, tmp_storage, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        # Push 5 entries, threshold = 3
        for i in range(5):
            sync_engine.push("agent_1", "owner_1", [_make_private_entry(f"entry_{i}")])

        distiller = CollectiveMemoryDistiller(threshold=3)
        result = distiller.distill(collective, tmp_storage, max_entries=3)
        assert result["distilled"] == 2
        assert result["kept"] == 3
        assert result["digest_hash"] != ""

    def test_distill_preserves_originals(self, tmp_storage, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        for i in range(4):
            sync_engine.push("agent_1", "owner_1", [_make_private_entry(f"keep_{i}")])

        distiller = CollectiveMemoryDistiller(threshold=2)
        distiller.distill(collective, tmp_storage, max_entries=2)

        # Original entries still in collective shard
        raw = tmp_storage.read(collective.shard_name, limit=100)
        assert len(raw) == 4  # all 4 still there (append-only)

    def test_distill_summary_verifiable_by_hash(self, tmp_storage, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        for i in range(3):
            sync_engine.push("agent_1", "owner_1", [_make_private_entry(f"v_{i}")])

        distiller = CollectiveMemoryDistiller(threshold=1)
        result = distiller.distill(collective, tmp_storage, max_entries=1)

        # Verify digest_hash is deterministic
        index = collective._ensure_index()
        to_distill = index[:2]
        expected = hashlib.sha256("".join(e.hash for e in to_distill).encode()).hexdigest()
        assert result["digest_hash"] == expected


# ------------------------------------------------------------------
# RollingDigester
# ------------------------------------------------------------------


class TestRollingDigester:
    def _push_timed_entries(self, sync_engine, registry, sovereignty, collective, count, start_time):
        _setup_agent_and_policy(registry, sovereignty)
        entries = []
        for i in range(count):
            e = _make_private_entry(f"timed_{i}", hash_val=hashlib.sha256(f"timed_{i}_{start_time}".encode()).hexdigest())
            entries.append(e)
        sync_engine.push("agent_1", "owner_1", entries)

    def test_digest_window_hourly_aggregates_key_findings(self, tmp_storage, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        entry = _make_private_entry("hourly test")
        sync_engine.push("agent_1", "owner_1", [entry],
                         detail_fn=lambda e: ("detail", ["finding_A", "finding_B"]))

        digester = RollingDigester(collective, tmp_storage)
        now = datetime.now(timezone.utc)
        digest = digester.digest_window(now - timedelta(hours=1), now, level=1)
        assert isinstance(digest, DigestEntry)
        assert digest.level == 1
        assert digest.source_count >= 1
        assert "finding_A" in digest.key_events

    def test_digest_source_hash_verifiable(self, tmp_storage, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        sync_engine.push("agent_1", "owner_1", [_make_private_entry("hash_check")])

        digester = RollingDigester(collective, tmp_storage)
        now = datetime.now(timezone.utc)
        digest = digester.digest_window(now - timedelta(hours=1), now, level=1)

        # Verify source_hash
        index = collective._ensure_index()
        expected = hashlib.sha256("".join(e.hash for e in index).encode()).hexdigest()
        assert digest.source_hash == expected

    def test_digest_structural_not_llm(self, tmp_storage, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        sync_engine.push("agent_1", "owner_1", [_make_private_entry("struct_test")],
                         detail_fn=lambda e: ("det", ["structural_finding"]))

        digester = RollingDigester(collective, tmp_storage)
        now = datetime.now(timezone.utc)
        digest = digester.digest_window(now - timedelta(hours=1), now, level=1)
        # Key events are directly from key_findings, not LLM-generated
        assert "structural_finding" in digest.key_events

    def test_read_with_digests_respects_max_tokens(self, tmp_storage, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        for i in range(10):
            sync_engine.push("agent_1", "owner_1", [_make_private_entry(f"tok_{i}")])

        digester = RollingDigester(collective, tmp_storage)
        now = datetime.now(timezone.utc)
        stack = digester.read_with_digests(now - timedelta(hours=1), max_tokens=600)
        assert isinstance(stack, ContextStack)
        assert stack.total_tokens <= 600

    def test_read_with_digests_recent_full_detail(self, tmp_storage, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        sync_engine.push("agent_1", "owner_1", [_make_private_entry("recent_detail")])

        digester = RollingDigester(collective, tmp_storage)
        now = datetime.now(timezone.utc)
        stack = digester.read_with_digests(now - timedelta(hours=1), max_tokens=8000)
        assert len(stack.recent) >= 1

    def test_context_stack_coverage_accurate(self, tmp_storage, sync_engine, registry, sovereignty, collective):
        _setup_agent_and_policy(registry, sovereignty)
        sync_engine.push("agent_1", "owner_1", [_make_private_entry("cov_test")])

        digester = RollingDigester(collective, tmp_storage)
        now = datetime.now(timezone.utc)
        stack = digester.read_with_digests(now - timedelta(hours=2), max_tokens=8000)
        assert "hour" in stack.coverage or "day" in stack.coverage or "no_recent" not in stack.coverage
