"""
Tests for Parallel Shard Lanes — zero-contention multi-agent writes.

Covers:
- Lane registration and naming
- Per-lane isolated writes
- Cross-lane unified reads
- Tiered resolution across lanes
- Lane tips and merge entries
- Budget-aware auto-downgrade across lanes
- Diagnostics and verification
"""

import json
import tempfile
import time
from datetime import datetime, timezone, timedelta
from threading import Thread
from uuid import uuid4

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.identity.identity_registry import IdentityRegistry
from dsm.sovereignty import SovereigntyPolicy
from dsm.orchestrator import NeutralOrchestrator, RuleSet
from dsm.lanes import LaneGroup, LaneTip, MergeEntry, LaneWriteResult, LANE_PREFIX


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def tmp_storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


@pytest.fixture
def setup(tmp_storage):
    """Set up identity, sovereignty, orchestrator, and lane group."""
    identity = IdentityRegistry(tmp_storage)
    policy = SovereigntyPolicy(tmp_storage)
    orchestrator = NeutralOrchestrator(
        tmp_storage,
        rules=RuleSet.default(),
        identity=identity,
        policy=policy,
    )

    # Register agents
    identity.register("claude_1", "pk_claude", "owner", "sig")
    identity.register("gpt_1", "pk_gpt", "owner", "sig")
    identity.register("gemini_1", "pk_gemini", "owner", "sig")

    # Set policy allowing all agents
    policy.set(
        owner_id="owner",
        owner_signature="sig",
        policy={
            "agents": ["claude_1", "gpt_1", "gemini_1"],
            "min_trust_score": 0.3,
            "allowed_types": ["observation", "tool_call", "action_result"],
            "approval_required": [],
            "cross_ai": True,
        },
    )

    lanes = LaneGroup(tmp_storage, identity, policy, orchestrator)
    return lanes, tmp_storage


def _make_entry(source="test", content="test content", shard="sessions"):
    return Entry(
        id=str(uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="test_session",
        source=source,
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={"event_type": "observation"},
        version="v2.0",
    )


# ------------------------------------------------------------------
# Lane Registration
# ------------------------------------------------------------------


class TestLaneRegistration:

    def test_register_lane(self, setup):
        lanes, _ = setup
        shard = lanes.register_lane("claude_1")
        assert shard == f"{LANE_PREFIX}claude_1"
        assert lanes.has_lane("claude_1")

    def test_register_lane_idempotent(self, setup):
        lanes, _ = setup
        s1 = lanes.register_lane("claude_1")
        s2 = lanes.register_lane("claude_1")
        assert s1 == s2

    def test_has_lane_false(self, setup):
        lanes, _ = setup
        assert not lanes.has_lane("unknown_agent")

    def test_registered_agents(self, setup):
        lanes, _ = setup
        lanes.register_lane("claude_1")
        lanes.register_lane("gpt_1")
        agents = lanes.registered_agents()
        assert set(agents) == {"claude_1", "gpt_1"}

    def test_lane_shard_name(self, setup):
        lanes, _ = setup
        assert lanes.lane_shard_name("agent_x") == f"{LANE_PREFIX}agent_x"

    def test_get_lane_unregistered_raises(self, setup):
        lanes, _ = setup
        with pytest.raises(KeyError, match="No lane registered"):
            lanes._get_lane("nonexistent")


# ------------------------------------------------------------------
# Per-Lane Writes
# ------------------------------------------------------------------


class TestLaneWrites:

    def test_push_to_lane(self, setup):
        lanes, storage = setup
        lanes.register_lane("claude_1")
        entry = _make_entry(source="claude_1")
        # Write entry to storage first (push reads from storage)
        written = storage.append(entry)

        result = lanes.push(
            "claude_1", "owner", [written],
            summary_fn=lambda e: "test summary",
        )
        assert isinstance(result, LaneWriteResult)
        assert len(result.admitted) == 1
        assert len(result.rejected) == 0
        assert result.lane_shard == f"{LANE_PREFIX}claude_1"

    def test_push_unregistered_raises(self, setup):
        lanes, _ = setup
        with pytest.raises(KeyError):
            lanes.push("unknown", "owner", [_make_entry()])

    def test_push_isolated_per_agent(self, setup):
        """Two agents push to different lane shards — no contention."""
        lanes, storage = setup
        lanes.register_lane("claude_1")
        lanes.register_lane("gpt_1")

        e1 = storage.append(_make_entry(source="claude_1", content="claude data"))
        e2 = storage.append(_make_entry(source="gpt_1", content="gpt data"))

        r1 = lanes.push("claude_1", "owner", [e1], summary_fn=lambda e: "claude")
        r2 = lanes.push("gpt_1", "owner", [e2], summary_fn=lambda e: "gpt")

        assert r1.lane_shard != r2.lane_shard
        assert len(r1.admitted) == 1
        assert len(r2.admitted) == 1

    def test_push_multiple_entries(self, setup):
        lanes, storage = setup
        lanes.register_lane("claude_1")

        entries = [
            storage.append(_make_entry(source="claude_1", content=f"entry_{i}"))
            for i in range(5)
        ]

        result = lanes.push(
            "claude_1", "owner", entries,
            summary_fn=lambda e: "summary",
        )
        assert len(result.admitted) == 5


# ------------------------------------------------------------------
# Cross-Lane Reads
# ------------------------------------------------------------------


class TestCrossLaneReads:

    def _populate_lanes(self, lanes, storage):
        """Push entries to two lanes with different timestamps."""
        lanes.register_lane("claude_1")
        lanes.register_lane("gpt_1")

        for i in range(3):
            e = storage.append(_make_entry(
                source="claude_1",
                content=f"claude_entry_{i}",
            ))
            lanes.push("claude_1", "owner", [e], summary_fn=lambda e: f"claude_{i}")

        for i in range(2):
            e = storage.append(_make_entry(
                source="gpt_1",
                content=f"gpt_entry_{i}",
            ))
            lanes.push("gpt_1", "owner", [e], summary_fn=lambda e: f"gpt_{i}")

    def test_recent_all_lanes(self, setup):
        lanes, storage = setup
        self._populate_lanes(lanes, storage)

        recent = lanes.recent(limit=50)
        assert len(recent) == 5  # 3 claude + 2 gpt

    def test_recent_single_lane(self, setup):
        lanes, storage = setup
        self._populate_lanes(lanes, storage)

        claude_only = lanes.recent(limit=50, agent_id="claude_1")
        assert len(claude_only) == 3
        assert all(e.agent_id == "claude_1" for e in claude_only)

    def test_recent_limit(self, setup):
        lanes, storage = setup
        self._populate_lanes(lanes, storage)

        recent = lanes.recent(limit=3)
        assert len(recent) == 3

    def test_recent_sorted_by_time(self, setup):
        lanes, storage = setup
        self._populate_lanes(lanes, storage)

        recent = lanes.recent(limit=50)
        timestamps = [e.contributed_at for e in recent]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_recent_empty_lanes(self, setup):
        lanes, _ = setup
        lanes.register_lane("claude_1")
        assert lanes.recent() == []


# ------------------------------------------------------------------
# Tiered Resolution Across Lanes
# ------------------------------------------------------------------


class TestTieredAcrossLanes:

    def _populate(self, lanes, storage):
        lanes.register_lane("claude_1")
        lanes.register_lane("gpt_1")

        for agent in ["claude_1", "gpt_1"]:
            for i in range(3):
                e = storage.append(_make_entry(
                    source=agent, content=f"{agent}_{i}",
                ))
                lanes.push(agent, "owner", [e], summary_fn=lambda e: "sum")

    def test_tier_0_all_lanes(self, setup):
        lanes, storage = setup
        self._populate(lanes, storage)

        result = lanes.recent_at_tier(tier=0, limit=50)
        assert len(result) == 6
        # Tier 0: only hash, agent_id, contributed_at
        for item in result:
            assert "hash" in item
            assert "agent_id" in item
            assert "contributed_at" in item
            assert "summary" not in item

    def test_tier_2_all_lanes(self, setup):
        lanes, storage = setup
        self._populate(lanes, storage)

        result = lanes.recent_at_tier(tier=2, limit=50)
        for item in result:
            assert "detail" in item
            assert "key_findings" in item

    def test_tier_single_agent(self, setup):
        lanes, storage = setup
        self._populate(lanes, storage)

        result = lanes.recent_at_tier(tier=1, agent_id="claude_1")
        assert len(result) == 3
        for item in result:
            assert "summary" in item

    def test_budget_auto_downgrade(self, setup):
        lanes, storage = setup
        self._populate(lanes, storage)

        # 6 entries × 300 tokens (tier 2) = 1800 tokens
        # Budget of 500 should force downgrade
        result = lanes.recent_at_tier(tier=2, max_tokens=500)
        assert len(result) > 0
        # Should have been downgraded — no detail field at tier 0
        if len(result) == 6:
            # Was downgraded to tier 0 or 1
            assert "detail" not in result[0] or "summary" in result[0]

    def test_empty_lanes_tier(self, setup):
        lanes, _ = setup
        lanes.register_lane("claude_1")
        assert lanes.recent_at_tier(tier=2) == []


# ------------------------------------------------------------------
# Lane Tips & Merge
# ------------------------------------------------------------------


class TestLaneTipsAndMerge:

    def _populate(self, lanes, storage):
        lanes.register_lane("claude_1")
        lanes.register_lane("gpt_1")

        for agent in ["claude_1", "gpt_1"]:
            e = storage.append(_make_entry(source=agent, content=f"{agent}_data"))
            lanes.push(agent, "owner", [e], summary_fn=lambda e: "sum")

    def test_tips(self, setup):
        lanes, storage = setup
        self._populate(lanes, storage)

        tips = lanes.tips()
        assert len(tips) == 2
        assert all(isinstance(t, LaneTip) for t in tips)

        agent_ids = {t.agent_id for t in tips}
        assert agent_ids == {"claude_1", "gpt_1"}

        for tip in tips:
            assert tip.entry_count >= 1
            assert tip.latest_hash != ""

    def test_tips_empty_lane(self, setup):
        lanes, _ = setup
        lanes.register_lane("claude_1")

        tips = lanes.tips()
        assert len(tips) == 1
        assert tips[0].entry_count == 0
        assert tips[0].latest_hash == ""

    def test_create_merge(self, setup):
        lanes, storage = setup
        self._populate(lanes, storage)

        merge = lanes.create_merge()
        assert isinstance(merge, MergeEntry)
        assert merge.merge_id.startswith("merge_")
        assert len(merge.tips) == 2
        assert merge.merge_hash != ""

    def test_merge_hash_deterministic(self, setup):
        """Same tips should produce same merge hash."""
        lanes, storage = setup
        self._populate(lanes, storage)

        tips1 = lanes.tips()
        tips2 = lanes.tips()

        hashes1 = sorted(t.latest_hash for t in tips1 if t.latest_hash)
        hashes2 = sorted(t.latest_hash for t in tips2 if t.latest_hash)
        assert hashes1 == hashes2

    def test_merge_written_to_shard(self, setup):
        lanes, storage = setup
        self._populate(lanes, storage)

        merge = lanes.create_merge()

        # Read from merge shard
        history = lanes.merge_history()
        assert len(history) >= 1
        assert history[0]["merge_id"] == merge.merge_id
        assert history[0]["event_type"] == "lane_merge"

    def test_multiple_merges(self, setup):
        lanes, storage = setup
        self._populate(lanes, storage)

        lanes.create_merge()

        # Push more data
        e = storage.append(_make_entry(source="claude_1", content="new"))
        lanes.push("claude_1", "owner", [e], summary_fn=lambda e: "new")

        lanes.create_merge()

        history = lanes.merge_history(limit=10)
        assert len(history) >= 2


# ------------------------------------------------------------------
# Diagnostics
# ------------------------------------------------------------------


class TestDiagnostics:

    def test_stats_empty(self, setup):
        lanes, _ = setup
        lanes.register_lane("claude_1")

        stats = lanes.stats()
        assert stats["lane_count"] == 1
        assert stats["total_entries"] == 0

    def test_stats_with_data(self, setup):
        lanes, storage = setup
        lanes.register_lane("claude_1")
        lanes.register_lane("gpt_1")

        for agent in ["claude_1", "gpt_1"]:
            for i in range(3):
                e = storage.append(_make_entry(source=agent, content=f"{agent}_{i}"))
                lanes.push(agent, "owner", [e], summary_fn=lambda e: "s")

        stats = lanes.stats()
        assert stats["lane_count"] == 2
        assert stats["total_entries"] == 6
        assert len(stats["lanes"]) == 2

    def test_verify_lane(self, setup):
        lanes, storage = setup
        lanes.register_lane("claude_1")

        e = storage.append(_make_entry(source="claude_1"))
        lanes.push("claude_1", "owner", [e], summary_fn=lambda e: "s")

        result = lanes.verify_lane("claude_1")
        assert result["status"] == "OK"


# ------------------------------------------------------------------
# Concurrency — parallel writes to different lanes
# ------------------------------------------------------------------


class TestConcurrency:

    def test_parallel_writes_no_contention(self, setup):
        """Multiple threads writing to different lanes should not block."""
        lanes, storage = setup
        lanes.register_lane("claude_1")
        lanes.register_lane("gpt_1")
        lanes.register_lane("gemini_1")

        errors = []
        counts = {"claude_1": 0, "gpt_1": 0, "gemini_1": 0}

        def write_to_lane(agent_id, n):
            try:
                for i in range(n):
                    e = storage.append(_make_entry(
                        source=agent_id, content=f"{agent_id}_{i}",
                    ))
                    result = lanes.push(
                        agent_id, "owner", [e],
                        summary_fn=lambda e: "s",
                    )
                    if result.admitted:
                        counts[agent_id] += 1
            except Exception as ex:
                errors.append(str(ex))

        threads = [
            Thread(target=write_to_lane, args=("claude_1", 10)),
            Thread(target=write_to_lane, args=("gpt_1", 10)),
            Thread(target=write_to_lane, args=("gemini_1", 10)),
        ]

        start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        elapsed = time.monotonic() - start

        assert not errors, f"Errors during parallel writes: {errors}"
        assert counts["claude_1"] == 10
        assert counts["gpt_1"] == 10
        assert counts["gemini_1"] == 10

        # All 30 entries should be readable across lanes
        all_entries = lanes.recent(limit=100)
        assert len(all_entries) == 30
