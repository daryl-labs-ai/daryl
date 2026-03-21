"""Coverage boost tests — targets uncovered lines in A-E modules and agent facade.

Focuses on:
- agent.py error paths (OSError handlers, signing disabled branches)
- lifecycle.py edge cases (JSON decode errors, empty shards, auto-drain in seal)
- collective.py filter branches
- session_graph.py edge cases
- sovereignty.py uncovered lines
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.lifecycle import (
    LIFECYCLE_SHARD, ShardLifecycle, ShardState,
    LifecycleResult, VerifyResult, TriggerResult,
)
from dsm.collective import (
    CollectiveEntry, CollectiveShard, CollectiveMemoryDistiller,
    RollingDigester, ShardSyncEngine,
)
from dsm.identity.identity_registry import IdentityRegistry
from dsm.orchestrator import NeutralOrchestrator, RuleSet
from dsm.sovereignty import SovereigntyPolicy, _validate_policy


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def tmp_storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


@pytest.fixture
def lifecycle(tmp_storage):
    return ShardLifecycle(tmp_storage)


def _make_entry(shard="test_shard", content="test", **kw):
    return Entry(
        id=kw.get("id", "e1"),
        timestamp=kw.get("timestamp", datetime.now(timezone.utc)),
        session_id=kw.get("session_id", "s1"),
        source=kw.get("source", "agent1"),
        content=content,
        shard=shard,
        hash=kw.get("hash", "abc123"),
        prev_hash=kw.get("prev_hash", None),
        metadata=kw.get("metadata", {}),
        version="v2.0",
    )


# ------------------------------------------------------------------
# Lifecycle — edge cases
# ------------------------------------------------------------------


class TestLifecycleEdgeCases:
    """Cover uncovered branches in lifecycle.py."""

    def test_state_skips_malformed_json(self, tmp_storage, lifecycle):
        """Line 130: JSONDecodeError branch."""
        # Write a malformed entry to lifecycle registry
        entry = _make_entry(shard=LIFECYCLE_SHARD, content="NOT JSON")
        tmp_storage.append(entry)
        # Should return ACTIVE (default) since no valid transition found
        assert lifecycle.state("test_shard") == ShardState.ACTIVE

    def test_state_skips_wrong_shard(self, tmp_storage, lifecycle):
        """Line 132: shard_id != shard_id branch."""
        data = json.dumps({
            "event_type": "lifecycle_transition",
            "shard_id": "other_shard",
            "to_state": "draining",
        })
        entry = _make_entry(shard=LIFECYCLE_SHARD, content=data)
        tmp_storage.append(entry)
        # Should return ACTIVE for test_shard (transition is for other_shard)
        assert lifecycle.state("test_shard") == ShardState.ACTIVE

    def test_invalidate_clears_cache(self, lifecycle):
        """Line 109: _invalidate method."""
        lifecycle._state_cache["shard_x"] = ShardState.DRAINING
        lifecycle._invalidate("shard_x")
        assert "shard_x" not in lifecycle._state_cache

    def test_invalidate_nonexistent_key(self, lifecycle):
        """_invalidate on missing key does not raise."""
        lifecycle._invalidate("does_not_exist")  # no-op

    def test_seal_auto_drains_active(self, tmp_storage):
        """Lines 223-228: auto-drain when seal() called on active shard."""
        lc = ShardLifecycle(tmp_storage)
        # Write something to the shard so verify has data
        entry = _make_entry(shard="auto_drain_test", content="data", hash="h1")
        tmp_storage.append(entry)

        result = lc.seal("auto_drain_test", "owner", "sig")
        assert result.ok
        assert lc.state("auto_drain_test") == ShardState.SEALED

    def test_seal_fails_on_sealed(self, tmp_storage):
        """Line 230-233: seal on already sealed shard."""
        lc = ShardLifecycle(tmp_storage)
        entry = _make_entry(shard="s2", hash="h1")
        tmp_storage.append(entry)
        lc.drain("s2", "owner", "sig")
        lc.seal("s2", "owner", "sig")
        # Try to seal again
        result = lc.seal("s2", "owner", "sig")
        assert not result.ok
        assert "sealed" in result.error

    def test_archive_fails_on_active(self, tmp_storage):
        """Line 268-272: archive on non-sealed shard."""
        lc = ShardLifecycle(tmp_storage)
        result = lc.archive("active_shard", "owner", "sig")
        assert not result.ok
        assert "active" in result.error

    def test_archive_fails_on_draining(self, tmp_storage):
        """Archive on draining shard."""
        lc = ShardLifecycle(tmp_storage)
        entry = _make_entry(shard="d_shard", hash="h1")
        tmp_storage.append(entry)
        lc.drain("d_shard", "owner", "sig")
        result = lc.archive("d_shard", "owner", "sig")
        assert not result.ok
        assert "draining" in result.error

    def test_verify_deep_chain_break(self, tmp_storage):
        """Lines 321-327: chain break detection in deep verify."""
        lc = ShardLifecycle(tmp_storage)
        # Write two entries with broken chain
        e1 = _make_entry(shard="broken", hash="hash1", prev_hash=None, id="e1")
        tmp_storage.append(e1)
        e2 = _make_entry(shard="broken", hash="hash2", prev_hash="WRONG", id="e2")
        tmp_storage.append(e2)
        result = lc.verify("broken", deep=True)
        assert not result.passed
        assert "chain break" in result.reason

    def test_verify_empty_shard(self, tmp_storage):
        """Lines 302-304: verify on empty shard."""
        lc = ShardLifecycle(tmp_storage)
        result = lc.verify("empty_shard", deep=True)
        assert result.passed
        assert result.summary["entry_count"] == 0

    def test_verify_spot_check_missing_hash(self, tmp_storage):
        """Lines 310-311: spot check with missing hash on tip."""
        lc = ShardLifecycle(tmp_storage)
        entry = _make_entry(shard="no_hash", hash="", id="e1")
        tmp_storage.append(entry)
        result = lc.verify("no_hash", deep=False)
        assert not result.passed
        assert "missing hash" in result.reason

    def test_check_triggers_not_active(self, tmp_storage):
        """Lines 347-348: triggers on non-active shard."""
        lc = ShardLifecycle(tmp_storage)
        entry = _make_entry(shard="trig_shard", hash="h1")
        tmp_storage.append(entry)
        lc.drain("trig_shard", "owner", "sig")
        result = lc.check_triggers("trig_shard", "owner", "sig")
        assert not result.triggered
        assert "not active" in result.reason

    def test_history_skips_malformed(self, tmp_storage):
        """Lines 393-396: history skips malformed JSON."""
        lc = ShardLifecycle(tmp_storage)
        bad = _make_entry(shard=LIFECYCLE_SHARD, content="BAD JSON", id="bad")
        tmp_storage.append(bad)
        good_data = json.dumps({"shard_id": "target", "event_type": "lifecycle_transition"})
        good = _make_entry(shard=LIFECYCLE_SHARD, content=good_data, id="good")
        tmp_storage.append(good)
        hist = lc.history("target")
        assert len(hist) == 1


# ------------------------------------------------------------------
# Collective — filter branches
# ------------------------------------------------------------------


class TestCollectiveFilters:
    """Cover uncovered filter branches in collective.py."""

    def test_recent_filter_by_agent(self, tmp_storage):
        """Lines 161-162: agent_id filter."""
        cs = CollectiveShard(tmp_storage, "coll_test")
        # Write entries from different agents
        for i, agent in enumerate(["alice", "bob", "alice"]):
            data = json.dumps({
                "agent_id": agent,
                "source_hash": f"h{i}",
                "content_hash": f"ch{i}",
                "summary": f"sum{i}",
            })
            entry = _make_entry(shard="coll_test", content=data, id=f"e{i}", hash=f"hash{i}")
            tmp_storage.append(entry)

        result = cs.recent(agent_id="alice")
        assert len(result) == 2
        for e in result:
            assert e.agent_id == "alice"

    def test_recent_filter_by_type(self, tmp_storage):
        """Lines 163-164: entry_type filter."""
        cs = CollectiveShard(tmp_storage, "coll_type")
        for i, atype in enumerate(["observation", "decision", "observation"]):
            data = json.dumps({
                "agent_id": "agent1",
                "action_type": atype,
                "summary": f"sum{i}",
            })
            entry = _make_entry(shard="coll_type", content=data, id=f"e{i}", hash=f"hash{i}")
            tmp_storage.append(entry)

        result = cs.recent(entry_type="observation")
        assert len(result) == 2


# ------------------------------------------------------------------
# Sovereignty — validation edge cases
# ------------------------------------------------------------------


class TestSovereigntyValidationEdge:
    """Cover remaining uncovered lines in sovereignty.py."""

    def test_validate_empty_agents_list(self):
        """agents can't be empty list."""
        errors = _validate_policy({"agents": [], "min_trust_score": 0.5, "allowed_types": ["x"]})
        assert any("empty" in e.lower() or "agents" in e.lower() for e in errors)

    def test_validate_agents_with_empty_string(self):
        """agents can't contain empty strings."""
        errors = _validate_policy({"agents": [""], "min_trust_score": 0.5, "allowed_types": ["x"]})
        assert len(errors) > 0

    def test_validate_trust_negative(self):
        """min_trust_score can't be negative."""
        errors = _validate_policy({"agents": ["a"], "min_trust_score": -0.1, "allowed_types": ["x"]})
        assert len(errors) > 0

    def test_validate_trust_above_one(self):
        """min_trust_score can't be > 1.0."""
        errors = _validate_policy({"agents": ["a"], "min_trust_score": 1.5, "allowed_types": ["x"]})
        assert len(errors) > 0

    def test_validate_allowed_types_not_list(self):
        """allowed_types must be a list."""
        errors = _validate_policy({"agents": ["a"], "min_trust_score": 0.5, "allowed_types": "string"})
        assert len(errors) > 0

    def test_validate_trust_baseline_out_of_range(self):
        """trust_baseline must be in [0,1]."""
        errors = _validate_policy({
            "agents": ["a"], "min_trust_score": 0.5,
            "allowed_types": ["x"], "trust_baseline": 2.0,
        })
        assert len(errors) > 0

    def test_validate_cross_ai_not_bool(self):
        """cross_ai must be boolean."""
        errors = _validate_policy({
            "agents": ["a"], "min_trust_score": 0.5,
            "allowed_types": ["x"], "cross_ai": "yes",
        })
        assert len(errors) > 0

    def test_validate_valid_policy(self):
        """A fully valid policy returns no errors."""
        errors = _validate_policy({
            "agents": ["a", "b"], "min_trust_score": 0.5,
            "allowed_types": ["observation"], "trust_baseline": 0.3,
            "cross_ai": True, "approval_required": ["special"],
        })
        assert errors == []


# ------------------------------------------------------------------
# Agent facade — error paths
# ------------------------------------------------------------------


class TestAgentErrorPaths:
    """Cover OSError handlers and signing-disabled paths in agent.py."""

    @pytest.fixture
    def agent(self, tmp_path):
        from dsm.agent import DarylAgent
        DarylAgent._reset_startup_cache()
        a = DarylAgent(
            agent_id="err_agent",
            data_dir=str(tmp_path / "data"),
            signing_dir=False,
            artifact_dir=False,
            startup_verify=False,
        )
        yield a
        DarylAgent._reset_startup_cache()

    def test_sign_returns_unsigned_when_no_signing(self, agent):
        """Line 685: _sign fallback."""
        assert agent._sign("some data") == "unsigned"

    def test_public_key_returns_none_when_no_signing(self, agent):
        """Line 691: _public_key fallback."""
        assert agent._public_key() is None

    def test_start_returns_session(self, agent):
        """Lines 238-239: normal start."""
        result = agent.start()
        assert result is not None

    def test_end_returns_result(self, agent):
        """Lines 251-254: normal end with sync=True."""
        agent.start()
        result = agent.end(sync=True)
        assert result is not None

    def test_end_without_sync(self, agent):
        """Lines 253-254: end with sync=False."""
        agent.start()
        result = agent.end(sync=False)
        assert result is not None

    def test_snapshot_works(self, agent):
        """Lines 261-262: normal snapshot."""
        agent.start()
        result = agent.snapshot({"key": "value"})
        assert result is not None

    def test_verify_all_shards(self, agent):
        """Line 355: verify without shard_id."""
        result = agent.verify()
        assert result is not None

    def test_verify_specific_shard(self, agent):
        """Line 354: verify with shard_id."""
        result = agent.verify(shard_id=agent.shard)
        assert result is not None

    def test_orphaned_intents_empty(self, agent):
        """Lines 345-350: orphaned intents on clean agent."""
        agent.start()
        result = agent.orphaned_intents()
        assert isinstance(result, list)

    def test_check_coverage_default(self, agent):
        """Lines 357-364: check_coverage."""
        result = agent.check_coverage()
        assert isinstance(result, dict)

    def test_lifecycle_state_via_facade(self, agent):
        """Lines 822-824: lifecycle_state facade."""
        state = agent.lifecycle_state("some_shard")
        assert state == "active"

    def test_collective_summary_via_facade(self, agent):
        """Line 810: collective_summary."""
        summary = agent.collective_summary()
        assert isinstance(summary, dict)

    def test_collective_recent_via_facade(self, agent):
        """Lines 812-814: collective_recent."""
        result = agent.collective_recent(limit=10)
        assert isinstance(result, list)

    def test_get_policy_returns_none_initially(self, agent):
        """Line 761: get_policy with no policy set."""
        result = agent.get_policy()
        assert result is None


# ------------------------------------------------------------------
# Agent facade — with signing enabled
# ------------------------------------------------------------------


class TestAgentWithSigning:
    """Test agent methods that use signing."""

    @pytest.fixture
    def signed_agent(self, tmp_path):
        from dsm.agent import DarylAgent
        DarylAgent._reset_startup_cache()
        a = DarylAgent(
            agent_id="signed_agent",
            data_dir=str(tmp_path / "data"),
            signing_dir=str(tmp_path / "keys"),
            artifact_dir=False,
            startup_verify=False,
        )
        a.generate_keys()
        yield a
        DarylAgent._reset_startup_cache()

    def test_sign_returns_real_signature(self, signed_agent):
        """Line 684: _sign with real keypair."""
        sig = signed_agent._sign("test data")
        assert sig != "unsigned"
        assert len(sig) > 10

    def test_public_key_returns_hex(self, signed_agent):
        """Lines 689-690: _public_key with keypair."""
        pk = signed_agent._public_key()
        assert pk is not None
        assert len(pk) > 10

    def test_register_with_real_signature(self, signed_agent):
        """Line 711: register_agent uses _sign()."""
        entry = signed_agent.register_agent("bob", "bob_pubkey")
        assert entry is not None
        data = json.loads(entry.content)
        assert data.get("owner_signature") != "unsigned"

    def test_set_policy_with_real_signature(self, signed_agent):
        """Lines 747-757: set_policy uses _sign()."""
        entry = signed_agent.set_policy(
            agents=["agent_a"],
            min_trust_score=0.5,
        )
        assert entry is not None

    def test_generate_keys_idempotent(self, signed_agent):
        """Line 518: generate_keys idempotent."""
        result = signed_agent.generate_keys()
        assert "public_key" in result

    def test_public_key_method(self, signed_agent):
        """Lines 520-524: public_key() method."""
        pk = signed_agent.public_key()
        assert pk is not None

    def test_key_history(self, signed_agent):
        """Lines 544-548: key_history."""
        hist = signed_agent.key_history()
        assert isinstance(hist, list)


# ------------------------------------------------------------------
# Agent facade — signing disabled raises
# ------------------------------------------------------------------


class TestAgentSigningDisabled:
    """Cover ValueError raises when signing is disabled."""

    @pytest.fixture
    def agent(self, tmp_path):
        from dsm.agent import DarylAgent
        DarylAgent._reset_startup_cache()
        a = DarylAgent(
            agent_id="nosign",
            data_dir=str(tmp_path / "data"),
            signing_dir=False,
            artifact_dir=False,
            startup_verify=False,
        )
        yield a
        DarylAgent._reset_startup_cache()

    def test_generate_keys_raises(self, agent):
        """Line 517: ValueError when signing disabled."""
        with pytest.raises(ValueError, match="Signing is disabled"):
            agent.generate_keys()

    def test_import_agent_key_raises(self, agent):
        """Lines 528-530: ValueError."""
        with pytest.raises(ValueError, match="Signing is disabled"):
            agent.import_agent_key("bob", "deadbeef")

    def test_rotate_key_raises(self, agent):
        """Lines 534-536: ValueError."""
        with pytest.raises(ValueError, match="Signing is disabled"):
            agent.rotate_key()

    def test_revoke_key_raises(self, agent):
        """Lines 540-542: ValueError."""
        with pytest.raises(ValueError, match="Signing is disabled"):
            agent.revoke_key("deadbeef")

    def test_public_key_returns_none(self, agent):
        """Lines 522-524: None when signing disabled."""
        assert agent.public_key() is None

    def test_key_history_returns_empty(self, agent):
        """Lines 546-548: empty list when signing disabled."""
        assert agent.key_history() == []


# ------------------------------------------------------------------
# Agent facade — artifact store disabled
# ------------------------------------------------------------------


class TestAgentArtifactDisabled:
    """Cover ValueError raises when artifact store is disabled."""

    @pytest.fixture
    def agent(self, tmp_path):
        from dsm.agent import DarylAgent
        DarylAgent._reset_startup_cache()
        a = DarylAgent(
            agent_id="noart",
            data_dir=str(tmp_path / "data"),
            signing_dir=False,
            artifact_dir=False,
            startup_verify=False,
        )
        yield a
        DarylAgent._reset_startup_cache()

    def test_store_artifact_raises(self, agent):
        """Lines 591-592: ValueError."""
        with pytest.raises(ValueError, match="Artifact store is disabled"):
            agent.store_artifact("data", "src")

    def test_retrieve_artifact_raises(self, agent):
        """Lines 597-598: ValueError."""
        with pytest.raises(ValueError, match="Artifact store is disabled"):
            agent.retrieve_artifact("deadbeef")

    def test_verify_artifact_raises(self, agent):
        """Lines 603-604: ValueError."""
        with pytest.raises(ValueError, match="Artifact store is disabled"):
            agent.verify_artifact("deadbeef")


# ------------------------------------------------------------------
# Agent facade — witness disabled
# ------------------------------------------------------------------


class TestAgentWitnessDisabled:
    """Cover ValueError raises when witness is disabled."""

    @pytest.fixture
    def agent(self, tmp_path):
        from dsm.agent import DarylAgent
        DarylAgent._reset_startup_cache()
        a = DarylAgent(
            agent_id="nowit",
            data_dir=str(tmp_path / "data"),
            signing_dir=False,
            artifact_dir=False,
            startup_verify=False,
        )
        yield a
        DarylAgent._reset_startup_cache()

    def test_witness_capture_raises(self, agent):
        """Line 368."""
        with pytest.raises(ValueError, match="witness_dir"):
            agent.witness_capture()

    def test_witness_verify_raises(self, agent):
        """Line 373."""
        with pytest.raises(ValueError, match="witness_dir"):
            agent.witness_verify()


# ------------------------------------------------------------------
# Agent — direct property access
# ------------------------------------------------------------------


class TestAgentDirectProperties:
    """Cover A-E property accessors in agent.py."""

    @pytest.fixture
    def agent(self, tmp_path):
        from dsm.agent import DarylAgent
        DarylAgent._reset_startup_cache()
        a = DarylAgent(
            agent_id="prop_test",
            data_dir=str(tmp_path / "data"),
            signing_dir=False,
            artifact_dir=False,
            startup_verify=False,
        )
        yield a
        DarylAgent._reset_startup_cache()

    def test_storage_property(self, agent):
        assert agent.storage is not None

    def test_graph_property(self, agent):
        assert agent.graph is not None

    def test_registry_type(self, agent):
        assert isinstance(agent.registry, IdentityRegistry)

    def test_sovereignty_type(self, agent):
        assert isinstance(agent.sovereignty, SovereigntyPolicy)

    def test_orchestrator_type(self, agent):
        assert isinstance(agent.orchestrator, NeutralOrchestrator)

    def test_collective_type(self, agent):
        assert isinstance(agent.collective, CollectiveShard)

    def test_sync_engine_type(self, agent):
        assert isinstance(agent.sync_engine, ShardSyncEngine)

    def test_digester_type(self, agent):
        assert isinstance(agent.digester, RollingDigester)

    def test_lifecycle_type(self, agent):
        assert isinstance(agent.lifecycle, ShardLifecycle)

    def test_startup_report_none_when_skipped(self, agent):
        """Lines 228-235: startup_report when verify=False."""
        assert agent.startup_report is None
