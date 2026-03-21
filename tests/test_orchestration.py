"""Tests for DSM Neutral Orchestrator (Module C)."""

import json
from datetime import datetime, timezone

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.identity.identity_registry import IdentityRegistry
from dsm.orchestrator import (
    ORCHESTRATOR_SHARD,
    AdmissionResult,
    MinTrustScoreRule,
    NeutralOrchestrator,
    NoSelfReferenceRule,
    RateLimitRule,
    RuleSet,
    SovereigntyCheckRule,
)
from dsm.sovereignty import SovereigntyPolicy


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


def _register_and_policy(registry, sovereignty, agent_id="agent_1", owner_id="owner_1"):
    """Helper: register agent + set permissive policy."""
    registry.register(agent_id, "k" * 64, owner_id, "sig", model="claude")
    sovereignty.set(owner_id, "sig", {
        "agents": [agent_id],
        "min_trust_score": 0.1,
        "allowed_types": ["observation", "analysis", "unknown"],
        "approval_required": [],
        "cross_ai": True,
    })


def _make_entry(entry_hash="abc123", event_type="observation"):
    """Helper: create a test entry."""
    return Entry(
        id="test-id",
        timestamp=datetime.now(timezone.utc),
        session_id="test",
        source="test",
        content='{"data": "test"}',
        shard="test_shard",
        hash=entry_hash,
        prev_hash=None,
        metadata={"event_type": event_type},
        version="v2.0",
    )


# ------------------------------------------------------------------
# Admission
# ------------------------------------------------------------------


class TestAdmission:
    def test_admit_valid_entry_success(self, orchestrator, registry, sovereignty):
        _register_and_policy(registry, sovereignty)
        result = orchestrator.admit(_make_entry(), "agent_1", "owner_1")
        assert result.allowed
        assert result.verdict == "allow"

    def test_admit_unknown_identity_denied(self, orchestrator, registry, sovereignty):
        # No agent registered, but policy exists
        sovereignty.set("owner_1", "sig", {
            "agents": ["ghost"],
            "min_trust_score": 0.1,
            "allowed_types": ["observation"],
        })
        result = orchestrator.admit(_make_entry(), "ghost", "owner_1")
        # ghost has trust 0.0 — denied by min_trust or sovereignty
        assert not result.allowed

    def test_admit_low_trust_denied(self, tmp_storage, registry, sovereignty):
        registry.register("agent_1", "k" * 64, "owner_1", "sig")
        sovereignty.set("owner_1", "sig", {
            "agents": ["agent_1"],
            "min_trust_score": 0.1,
            "allowed_types": ["observation"],
        })
        # Use a high min trust rule
        orch = NeutralOrchestrator(
            tmp_storage,
            RuleSet([MinTrustScoreRule(0.99)]),
            registry,
            sovereignty,
        )
        result = orch.admit(_make_entry(), "agent_1", "owner_1")
        assert not result.allowed
        assert "trust" in result.reason

    def test_admit_sovereignty_denied(self, orchestrator, registry, sovereignty):
        registry.register("agent_1", "k" * 64, "owner_1", "sig")
        # No policy set — deny by default
        result = orchestrator.admit(_make_entry(), "agent_1", "owner_1")
        assert not result.allowed
        assert "sovereignty" in result.reason

    def test_admit_rate_limit_denied(self, tmp_storage, registry, sovereignty):
        _register_and_policy(registry, sovereignty)
        # Rate limit of 0 — always denied
        orch = NeutralOrchestrator(
            tmp_storage,
            RuleSet([SovereigntyCheckRule(), RateLimitRule(0)]),
            registry,
            sovereignty,
        )
        result = orch.admit(_make_entry(), "agent_1", "owner_1")
        assert not result.allowed
        assert "rate limit" in result.reason

    def test_admit_self_reference_denied(self, tmp_storage, registry, sovereignty):
        _register_and_policy(registry, sovereignty)
        orch = NeutralOrchestrator(
            tmp_storage,
            RuleSet([NoSelfReferenceRule()]),
            registry,
            sovereignty,
        )
        # Entry where hash == prev_hash (self-reference)
        entry = Entry(
            id="x", timestamp=datetime.now(timezone.utc),
            session_id="s", source="s", content="c", shard="t",
            hash="samehash", prev_hash="samehash",
            metadata={}, version="v2.0",
        )
        result = orch.admit(entry, "agent_1", "owner_1")
        assert not result.allowed
        assert "self" in result.reason

    def test_admit_cached_on_same_hash(self, orchestrator, registry, sovereignty):
        _register_and_policy(registry, sovereignty)
        entry = _make_entry(entry_hash="unique_hash_123")
        r1 = orchestrator.admit(entry, "agent_1", "owner_1")
        r2 = orchestrator.admit(entry, "agent_1", "owner_1")
        # Same object from cache
        assert r1 is r2
        assert r1.allowed


# ------------------------------------------------------------------
# Audit log
# ------------------------------------------------------------------


class TestAuditLog:
    def test_audit_log_is_delta_not_full_entry(self, tmp_storage, orchestrator, registry, sovereignty):
        _register_and_policy(registry, sovereignty)
        orchestrator.admit(_make_entry(), "agent_1", "owner_1")

        entries = tmp_storage.read(ORCHESTRATOR_SHARD, limit=10)
        assert len(entries) >= 1
        data = json.loads(entries[0].content)
        # Delta only: verdict + reason + entry_hash, not full content
        assert "verdict" in data
        assert "entry_hash" in data
        assert "data" not in data  # no full entry content

    def test_audit_log_append_only(self, tmp_storage, orchestrator, registry, sovereignty):
        _register_and_policy(registry, sovereignty)
        orchestrator.admit(_make_entry(entry_hash="h1"), "agent_1", "owner_1")
        orchestrator.admit(_make_entry(entry_hash="h2"), "agent_1", "owner_1")
        entries = tmp_storage.read(ORCHESTRATOR_SHARD, limit=100)
        assert len(entries) == 2


# ------------------------------------------------------------------
# RuleSet
# ------------------------------------------------------------------


class TestRuleSet:
    def test_ruleset_frozen_after_init(self):
        rs = RuleSet.default()
        assert len(rs) == 4
        # rules is a tuple — immutable
        assert isinstance(rs.rules, tuple)

    def test_with_rules_returns_new_instance(self, orchestrator):
        new_rules = RuleSet.permissive()
        new_orch = orchestrator.with_rules(new_rules)
        assert new_orch is not orchestrator
        assert len(new_orch.rules) == 1
        assert len(orchestrator.rules) == 4

    def test_ruleset_composable(self):
        rs = RuleSet([
            MinTrustScoreRule(0.5),
            RateLimitRule(50),
            NoSelfReferenceRule(),
        ])
        assert len(rs) == 3

    def test_ruleset_permissive(self):
        rs = RuleSet.permissive()
        assert len(rs) == 1

    def test_orchestrator_deterministic_same_inputs(self, orchestrator, registry, sovereignty):
        _register_and_policy(registry, sovereignty)
        entry = _make_entry(entry_hash="det_hash")
        r1 = orchestrator.admit(entry, "agent_1", "owner_1")
        # Clear cache to force re-evaluation
        orchestrator._cache.clear()
        r2 = orchestrator.admit(entry, "agent_1", "owner_1")
        assert r1.verdict == r2.verdict
        assert r1.reason == r2.reason
