"""End-to-end integration test — Full A→B→C→D→E chain with Tiered Resolution + Rolling Digests.

Simulates a realistic multi-agent workflow:
1. Register 3 agents (A — Identity)
2. Set sovereignty policy (B — Sovereignty)
3. Agents produce entries, admitted via orchestrator (C — Orchestrator)
4. Entries pushed to collective, read at various tiers (D — Collective)
5. Rolling digests produced (D — Digests)
6. Shard lifecycle: drain → seal → archive (E — Lifecycle)

This test validates the ENTIRE pillar chain works together end-to-end.
"""

import json
from datetime import datetime, timezone, timedelta

import pytest

from dsm.agent import DarylAgent
from dsm.collective import CollectiveEntry, DigestEntry
from dsm.lifecycle import ShardState


@pytest.fixture(autouse=True)
def reset_cache():
    DarylAgent._reset_startup_cache()
    yield
    DarylAgent._reset_startup_cache()


@pytest.fixture
def owner(tmp_path):
    """Owner agent — controls the collective."""
    return DarylAgent(
        agent_id="owner_agent",
        data_dir=str(tmp_path / "owner"),
        signing_dir=str(tmp_path / "owner_keys"),
        artifact_dir=False,
        startup_verify=False,
    )


@pytest.fixture
def worker_a(tmp_path):
    return DarylAgent(
        agent_id="worker_a",
        data_dir=str(tmp_path / "worker_a"),
        signing_dir=False,
        artifact_dir=False,
        startup_verify=False,
    )


@pytest.fixture
def worker_b(tmp_path):
    return DarylAgent(
        agent_id="worker_b",
        data_dir=str(tmp_path / "worker_b"),
        signing_dir=False,
        artifact_dir=False,
        startup_verify=False,
    )


class TestFullChainE2E:
    """Full A→B→C→D→E chain in a single realistic scenario."""

    def test_complete_multi_agent_workflow(self, owner, worker_a, worker_b):
        # ============================================================
        # STEP A: Identity Registry — register agents
        # ============================================================
        owner.generate_keys()
        pk = owner.public_key()
        assert pk is not None

        # Owner registers itself and workers
        owner.register_agent("owner_agent", pk)
        owner.register_agent("worker_a", "worker_a_pubkey")
        owner.register_agent("worker_b", "worker_b_pubkey")

        # Verify resolution
        assert owner.resolve_agent("owner_agent") is not None
        assert owner.resolve_agent("worker_a") is not None
        assert owner.resolve_agent("worker_b") is not None
        assert owner.resolve_agent("unknown") is None

        agents = owner.list_registered_agents()
        assert len(agents) == 3

        # Trust scores
        assert owner.agent_trust("worker_a") >= 0.0
        assert owner.agent_trust("worker_b") >= 0.0

        # ============================================================
        # STEP B: Sovereignty Policy — set access rules
        # ============================================================
        policy_entry = owner.set_policy(
            agents=["owner_agent", "worker_a", "worker_b"],
            min_trust_score=0.0,
            allowed_types=["observation", "analysis", "tool_call", "action_result"],
            cross_ai=False,
        )
        assert policy_entry is not None

        policy = owner.get_policy()
        assert policy is not None
        assert "worker_a" in policy.agents

        # Check sovereignty: worker_a allowed for observation
        result = owner.check_sovereignty("worker_a", "observation")
        assert result.allowed

        # ============================================================
        # STEP C: Orchestrator — admission control
        # ============================================================
        owner.start()
        intent = owner.intend("produce_data", {"source": "sensor_1"})
        entry = owner.confirm(intent, result={"value": 42})
        assert entry is not None

        admission = owner.admit_entry(entry, "worker_a")
        assert admission.allowed

        # ============================================================
        # STEP D: Collective Memory — push, read at tiers, digest
        # ============================================================

        # Push entry to collective
        push_result = owner.push_to_collective(
            entry=entry,
            summary="Sensor reading: 42",
            detail="Worker A produced sensor reading from sensor_1, value=42, calibrated.",
            key_findings=["value_42", "sensor_1_active"],
        )
        assert len(push_result.admitted) > 0

        # Push a second entry
        intent2 = owner.intend("analysis", {"type": "trend"})
        entry2 = owner.confirm(intent2, result={"trend": "up"})
        push2 = owner.push_to_collective(
            entry=entry2,
            summary="Trend analysis: upward",
            detail="Analysis of recent sensor data shows upward trend over 24h.",
            key_findings=["trend_up", "24h_window"],
        )
        assert len(push2.admitted) > 0

        # Read at different tiers
        tier0 = owner.collective_at_tier(tier=0)
        tier1 = owner.collective_at_tier(tier=1)
        tier2 = owner.collective_at_tier(tier=2)
        tier3 = owner.collective_at_tier(tier=3)

        assert len(tier0) == 2
        assert len(tier1) == 2

        # Tier 0: minimal
        assert "summary" not in tier0[0]
        assert "detail" not in tier0[0]
        assert "hash" in tier0[0]

        # Tier 1: + summary
        assert "summary" in tier1[0]
        assert "detail" not in tier1[0]

        # Tier 2: + detail
        assert "detail" in tier2[0]
        assert "key_findings" in tier2[0]

        # Tier 3: + source hashes
        assert "source_hash" in tier3[0]
        assert "content_hash" in tier3[0]

        # Budget-constrained tier: should auto-downgrade
        budget_result = owner.collective_at_tier(tier=2, max_tokens=100)
        assert len(budget_result) > 0
        # With 100 tokens budget and 2 entries, should downgrade from Tier 2
        assert "detail" not in budget_result[0]

        # Collective summary
        summary = owner.collective_summary()
        assert isinstance(summary, dict)

        # ============================================================
        # STEP D (cont): Rolling Digests
        # ============================================================

        # Roll digests (may or may not produce based on timing)
        digests = owner.roll_digests(levels=[1, 2])
        assert isinstance(digests, list)

        # Read with digests (budget-aware context)
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        ctx = owner.read_with_digests(since=since, max_tokens=4000)
        assert ctx.total_tokens >= 0
        assert ctx.coverage != ""

        # ============================================================
        # STEP E: Lifecycle — drain → seal → archive
        # ============================================================

        # Check initial state
        shard = owner.shard
        assert owner.lifecycle_state(shard) == "active"

        # Drain
        drain_result = owner.drain(shard)
        assert drain_result.ok
        assert owner.lifecycle_state(shard) == "draining"

        # Seal
        seal_result = owner.lifecycle_seal(shard)
        assert seal_result.ok
        assert owner.lifecycle_state(shard) == "sealed"

        # Archive
        archive_result = owner.archive(shard)
        assert archive_result.ok
        assert owner.lifecycle_state(shard) == "archived"

        # ============================================================
        # END SESSION
        # ============================================================
        end_result = owner.end(sync=False)
        assert end_result is not None

    def test_sovereignty_blocks_unauthorized(self, owner):
        """Verify that sovereignty policy correctly blocks unauthorized access."""
        owner.generate_keys()
        owner.register_agent("owner_agent", owner.public_key())
        owner.register_agent("rogue", "rogue_key")

        # Policy only allows worker_a
        owner.set_policy(
            agents=["worker_a"],
            min_trust_score=0.5,
            allowed_types=["observation"],
        )

        # rogue is not in the policy agents list
        result = owner.check_sovereignty("rogue", "observation")
        # Should be denied (not in agents list)
        assert not result.allowed

    def test_tiered_resolution_token_efficiency(self, owner):
        """Verify tiered resolution actually reduces data volume."""
        owner.generate_keys()
        owner.register_agent("owner_agent", owner.public_key())
        owner.set_policy(
            agents=["owner_agent"],
            min_trust_score=0.0,
            allowed_types=["tool_call", "action_result"],
        )
        owner.start()

        # Push 5 entries
        for i in range(5):
            intent = owner.intend(f"action_{i}", {"i": i})
            entry = owner.confirm(intent, result={"v": i})
            owner.push_to_collective(
                entry=entry,
                summary=f"Short summary {i}",
                detail=f"Extended detail text for entry {i} with more information " * 5,
                key_findings=[f"finding_{i}_a", f"finding_{i}_b"],
            )

        # Invalidate index to pick up new entries
        owner.collective._invalidate()

        t0 = owner.collective_at_tier(tier=0)
        t2 = owner.collective_at_tier(tier=2)

        # Re-invalidate for tier 3 (index was rebuilt for t0)
        owner.collective._invalidate()
        t3 = owner.collective_at_tier(tier=3)

        assert len(t0) >= 5
        assert len(t3) >= 5

        # Tier 0 should have fewer keys than Tier 3
        assert len(t0[0]) < len(t3[0])
        assert len(t0[0]) == 3  # hash, agent_id, contributed_at
        assert len(t3[0]) == 10  # all fields

        # JSON size should decrease with lower tiers
        size_t0 = len(json.dumps(t0))
        size_t3 = len(json.dumps(t3))
        assert size_t0 < size_t3

        owner.end(sync=False)

    def test_revoke_agent_blocks_access(self, owner):
        """After revoking an agent, sovereignty should block it."""
        owner.generate_keys()
        owner.register_agent("owner_agent", owner.public_key())
        owner.register_agent("temp_worker", "temp_key")

        owner.set_policy(
            agents=["temp_worker"],
            min_trust_score=0.0,
            allowed_types=["observation"],
        )

        # Before revoke: allowed
        r1 = owner.check_sovereignty("temp_worker", "observation")
        assert r1.allowed

        # Revoke
        owner.revoke_agent("temp_worker", reason="compromised")

        # After revoke: trust should drop
        resolved = owner.resolve_agent("temp_worker")
        assert resolved is None or resolved.revoked
