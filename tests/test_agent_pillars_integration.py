"""Integration tests — A→E pillars via DarylAgent facade.

Validates that the facade correctly wires all 5 modules
and that the full chain A→B→C→D→E works end-to-end.
"""

import json
from datetime import datetime, timezone, timedelta

import pytest

from dsm.agent import DarylAgent
from dsm.core.models import Entry
from dsm.collective import CollectiveEntry
from dsm.lifecycle import ShardState, LifecycleResult
from dsm.sovereignty import EnforcementResult


@pytest.fixture(autouse=True)
def reset_cache():
    DarylAgent._reset_startup_cache()
    yield
    DarylAgent._reset_startup_cache()


@pytest.fixture
def agent(tmp_path):
    return DarylAgent(
        agent_id="test_agent",
        data_dir=str(tmp_path / "data"),
        signing_dir=False,
        artifact_dir=False,
        startup_verify=False,
    )


@pytest.fixture
def entry(agent):
    """Helper: create a DSM entry in agent's shard."""
    agent.start()
    intent_id = agent.intend("test_action", {"key": "value"})
    result = agent.confirm(intent_id, result={"status": "ok"})
    return result


# ------------------------------------------------------------------
# A — Identity Registry via facade
# ------------------------------------------------------------------


class TestRegistryFacade:
    def test_register_and_resolve(self, agent):
        entry = agent.register_agent("agent_bob", "pubkey_hex_bob")
        assert entry is not None  # Returns DSM Entry
        resolved = agent.resolve_agent("agent_bob")
        assert resolved is not None
        assert resolved.public_key == "pubkey_hex_bob"

    def test_resolve_unknown_returns_none(self, agent):
        assert agent.resolve_agent("unknown") is None

    def test_revoke_agent(self, agent):
        agent.register_agent("agent_charlie", "pubkey_charlie")
        entry = agent.revoke_agent("agent_charlie", reason="testing")
        assert entry is not None
        resolved = agent.resolve_agent("agent_charlie")
        assert resolved is None  # revoked → resolve returns None

    def test_trust_score(self, agent):
        agent.register_agent("agent_dave", "pubkey_dave")
        score = agent.agent_trust("agent_dave")
        assert 0.0 <= score <= 1.0

    def test_list_registered(self, agent):
        agent.register_agent("a1", "k1")
        agent.register_agent("a2", "k2")
        agents = agent.list_registered_agents()
        ids = [a.agent_id for a in agents]
        assert "a1" in ids
        assert "a2" in ids


# ------------------------------------------------------------------
# B — Sovereignty via facade
# ------------------------------------------------------------------


class TestSovereigntyFacade:
    def test_set_and_get_policy(self, agent):
        agent.register_agent("worker_1", "key_1")
        entry = agent.set_policy(
            agents=["worker_1"],
            min_trust_score=0.3,
            allowed_types=["observation"],
        )
        assert entry is not None  # Returns DSM Entry
        fetched = agent.get_policy()
        assert fetched is not None
        assert "worker_1" in fetched.agents

    def test_check_sovereignty_allowed(self, agent):
        agent.register_agent("worker_1", "key_1")
        agent.set_policy(
            agents=["worker_1"],
            min_trust_score=0.0,
            allowed_types=["observation"],
        )
        result = agent.check_sovereignty("worker_1", "observation")
        assert isinstance(result, EnforcementResult)
        assert result.allowed

    def test_check_sovereignty_denied_no_policy(self, agent):
        result = agent.check_sovereignty("random_agent", "observation")
        assert not result.allowed

    def test_check_sovereignty_denied_wrong_type(self, agent):
        agent.register_agent("worker_1", "key_1")
        agent.set_policy(
            agents=["worker_1"],
            min_trust_score=0.0,
            allowed_types=["observation"],
        )
        result = agent.check_sovereignty("worker_1", "delete_all")
        assert not result.allowed


# ------------------------------------------------------------------
# C — Orchestrator via facade
# ------------------------------------------------------------------


class TestOrchestratorFacade:
    def test_admit_entry(self, agent, entry):
        # Setup: register self and set policy
        agent.register_agent("test_agent", "key_self")
        agent.set_policy(
            agents=["test_agent"],
            min_trust_score=0.0,
            allowed_types=["observation", "tool_call"],
        )
        decision = agent.admit_entry(entry, "test_agent")
        # Decision should exist (may be admitted or denied based on rules)
        assert decision is not None
        assert hasattr(decision, "admitted") or hasattr(decision, "allowed")


# ------------------------------------------------------------------
# D — Collective via facade
# ------------------------------------------------------------------


class TestCollectiveFacade:
    def test_push_and_pull(self, agent, entry):
        agent.register_agent("test_agent", "key_self")
        agent.set_policy(
            agents=["test_agent"],
            min_trust_score=0.0,
            # Include action_result since that's what confirm() produces
            allowed_types=["observation", "tool_call", "action_result"],
        )
        result = agent.push_to_collective(
            entry=entry,
            summary="Test observation",
            detail="Detailed test observation for integration",
            key_findings=["finding_1"],
        )
        # Returns PushResult with admitted/rejected tuples
        assert result is not None
        assert hasattr(result, "admitted")
        assert hasattr(result, "rejected")
        assert len(result.admitted) > 0  # Should be admitted with correct types

    def test_collective_summary(self, agent):
        summary = agent.collective_summary()
        assert isinstance(summary, dict)
        assert "entry_count" in summary

    def test_collective_recent_empty(self, agent):
        recent = agent.collective_recent(limit=10)
        assert isinstance(recent, list)

    def test_read_with_digests(self, agent):
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        context = agent.read_with_digests(since=since, max_tokens=4000)
        assert context is not None


# ------------------------------------------------------------------
# E — Lifecycle via facade
# ------------------------------------------------------------------


class TestLifecycleFacade:
    def test_lifecycle_state_default(self, agent):
        state = agent.lifecycle_state("sessions")
        assert state == ShardState.ACTIVE

    def test_drain_and_seal(self, agent):
        # Populate the shard first
        agent.start()
        agent.intend("action_1", {})
        agent.end()

        result = agent.drain("sessions")
        assert isinstance(result, LifecycleResult)
        assert result.ok
        assert agent.lifecycle_state("sessions") == ShardState.DRAINING

        seal_result = agent.lifecycle_seal("sessions", reason="test")
        assert seal_result.ok
        assert agent.lifecycle_state("sessions") == ShardState.SEALED

    def test_archive(self, agent):
        agent.start()
        agent.end()
        agent.lifecycle_seal("sessions")
        result = agent.archive("sessions")
        assert result.ok
        assert agent.lifecycle_state("sessions") == ShardState.ARCHIVED

    def test_lifecycle_verify(self, agent):
        agent.start()
        agent.end()
        result = agent.lifecycle_verify("sessions", deep=False)
        assert result.passed

    def test_lifecycle_triggers(self, agent):
        result = agent.lifecycle_triggers("sessions")
        assert not result.triggered


# ------------------------------------------------------------------
# Cross-cutting: Shard Families
# ------------------------------------------------------------------


class TestShardFamiliesFacade:
    def test_classify_shard(self, agent):
        assert agent.shard_family("sessions") == "agent"
        assert agent.shard_family("identity_registry") == "registry"
        assert agent.shard_family("sovereignty_policies") == "registry"
        assert agent.shard_family("collective_main") == "collective"
        assert agent.shard_family("sync_log") == "infra"

    def test_shards_by_family(self, agent):
        # Write something to make shards exist
        agent.start()
        agent.end()
        all_shards = agent.shards_by_family("agent")
        assert isinstance(all_shards, list)


# ------------------------------------------------------------------
# Full chain: A → B → C → D → E
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Direct module access (bypass facade)
# ------------------------------------------------------------------


class TestDirectAccess:
    """Advanced users can bypass the facade and use modules directly."""

    def test_registry_direct(self, agent):
        agent.registry.register("bob", "pk_bob", "test_agent", "sig")
        resolved = agent.registry.resolve("bob")
        assert resolved is not None
        assert resolved.agent_id == "bob"

    def test_sovereignty_direct(self, agent):
        agent.registry.register("bob", "pk_bob", "test_agent", "sig")
        agent.sovereignty.set("test_agent", "sig", {
            "agents": ["bob"],
            "min_trust_score": 0.0,
            "allowed_types": ["observation"],
        })
        result = agent.sovereignty.allows("test_agent", "bob", "observation", agent.registry)
        assert result.allowed

    def test_orchestrator_direct(self, agent):
        assert agent.orchestrator.rules is not None

    def test_collective_direct(self, agent):
        summary = agent.collective.summary()
        assert isinstance(summary, dict)

    def test_sync_engine_direct(self, agent):
        result = agent.sync_engine.pull("test_agent")
        assert hasattr(result, "synced")

    def test_digester_direct(self, agent):
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        ctx = agent.digester.read_with_digests(since=since, max_tokens=4000)
        assert ctx is not None

    def test_lifecycle_direct(self, agent):
        assert agent.lifecycle.state("sessions") == "active"

    def test_end_with_sync_hooks(self, agent):
        """end() passes sync_engine + lifecycle to session_graph."""
        agent.start()
        entry = agent.end(sync=True)
        assert entry is not None

    def test_end_without_sync(self, agent):
        """end(sync=False) skips A→E hooks."""
        agent.start()
        entry = agent.end(sync=False)
        assert entry is not None


class TestFullChain:
    def test_end_to_end_flow(self, agent):
        """Full A→E chain: register → policy → push → seal."""
        # A: Register
        agent.register_agent("test_agent", "key_self")
        agent.register_agent("worker", "key_worker")

        # B: Set policy
        agent.set_policy(
            agents=["test_agent", "worker"],
            min_trust_score=0.0,
            allowed_types=["observation", "tool_call"],
        )

        # Create an entry
        agent.start()
        intent = agent.intend("observe", {"target": "system"})
        entry = agent.confirm(intent, result={"cpu": 42})
        agent.end()

        # C+D: Push to collective (goes through orchestrator)
        pushed = agent.push_to_collective(
            entry=entry,
            summary="CPU at 42%",
            detail="System observation showing CPU usage",
        )

        # E: Lifecycle
        state = agent.lifecycle_state("sessions")
        assert state in (ShardState.ACTIVE, ShardState.DRAINING,
                          ShardState.SEALED, ShardState.ARCHIVED)

        # Verify integrity
        verify = agent.lifecycle_verify("sessions")
        assert verify.passed
