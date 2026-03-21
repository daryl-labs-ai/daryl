"""Tests for DSM Sovereignty Policy (Module B)."""

import json

import pytest

from dsm.core.storage import Storage
from dsm.exceptions import InvalidPolicyStructure
from dsm.identity.identity_registry import IdentityRegistry
from dsm.sovereignty import (
    SOVEREIGNTY_SHARD,
    EnforcementResult,
    PolicySnapshot,
    SovereigntyPolicy,
)


@pytest.fixture
def tmp_storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


@pytest.fixture
def registry(tmp_storage):
    return IdentityRegistry(tmp_storage)


@pytest.fixture
def sovereignty(tmp_storage):
    return SovereigntyPolicy(tmp_storage)


def _make_policy(**overrides):
    """Helper to build a valid policy dict."""
    base = {
        "agents": ["agent_1", "agent_2"],
        "min_trust_score": 0.3,
        "allowed_types": ["observation", "analysis"],
        "trust_baseline": 0.5,
        "approval_required": [],
        "cross_ai": False,
    }
    base.update(overrides)
    return base


def _register_agent(registry, agent_id="agent_1", owner_id="owner_1", model="claude"):
    """Helper to register a test agent."""
    registry.register(agent_id, "k" * 64, owner_id, "sig", model=model)


# ------------------------------------------------------------------
# Set policy
# ------------------------------------------------------------------


class TestSetPolicy:
    def test_set_policy_success(self, sovereignty):
        entry = sovereignty.set("owner_1", "sig", _make_policy())
        assert entry is not None
        assert entry.shard == SOVEREIGNTY_SHARD
        data = json.loads(entry.content)
        assert data["event_type"] == "set_policy"
        assert data["owner_id"] == "owner_1"

    def test_set_policy_invalid_structure_raises(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="Missing"):
            sovereignty.set("owner_1", "sig", {"agents": ["a"]})

    def test_set_policy_supersedes_previous(self, sovereignty):
        sovereignty.set("owner_1", "sig", _make_policy(min_trust_score=0.3))
        sovereignty.set("owner_1", "sig", _make_policy(min_trust_score=0.8))
        snap = sovereignty.get("owner_1")
        assert snap.min_trust_score == 0.8

    def test_policy_is_projection_not_dump(self, sovereignty):
        policy = _make_policy()
        policy["extra_junk"] = "should_not_appear"
        entry = sovereignty.set("owner_1", "sig", policy)
        data = json.loads(entry.content)
        assert "extra_junk" not in data["policy"]


# ------------------------------------------------------------------
# Get policy
# ------------------------------------------------------------------


class TestGetPolicy:
    def test_get_policy_active(self, sovereignty):
        sovereignty.set("owner_1", "sig", _make_policy())
        snap = sovereignty.get("owner_1")
        assert isinstance(snap, PolicySnapshot)
        assert snap.owner_id == "owner_1"
        assert "agent_1" in snap.agents
        assert snap.min_trust_score == 0.3
        assert snap.trust_baseline == 0.5

    def test_get_policy_unknown_returns_none(self, sovereignty):
        assert sovereignty.get("nobody") is None

    def test_get_revoked_policy_returns_none(self, sovereignty):
        sovereignty.set("owner_1", "sig", _make_policy())
        sovereignty.revoke("owner_1", "sig", reason="obsolete")
        assert sovereignty.get("owner_1") is None


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------


class TestHistory:
    def test_history_shows_all_entries(self, sovereignty):
        sovereignty.set("owner_1", "sig", _make_policy())
        sovereignty.set("owner_1", "sig", _make_policy(min_trust_score=0.9))
        sovereignty.revoke("owner_1", "sig")
        history = sovereignty.history("owner_1")
        assert len(history) == 3

    def test_history_empty_for_unknown(self, sovereignty):
        assert sovereignty.history("ghost") == []


# ------------------------------------------------------------------
# Enforcement
# ------------------------------------------------------------------


class TestEnforcement:
    def test_allows_authorized_agent(self, tmp_storage, sovereignty, registry):
        _register_agent(registry)
        sovereignty.set("owner_1", "sig", _make_policy())
        result = sovereignty.allows("owner_1", "agent_1", "observation", registry)
        assert result.allowed
        assert result.verdict == "allow"

    def test_denies_unknown_agent(self, sovereignty, registry):
        sovereignty.set("owner_1", "sig", _make_policy())
        result = sovereignty.allows("owner_1", "ghost", "observation", registry)
        assert not result.allowed
        assert result.reason == "not_whitelisted"

    def test_denies_low_trust_score(self, tmp_storage, sovereignty, registry):
        _register_agent(registry)
        # Set a very high trust threshold
        sovereignty.set("owner_1", "sig", _make_policy(min_trust_score=0.99))
        result = sovereignty.allows("owner_1", "agent_1", "observation", registry)
        assert not result.allowed
        assert result.reason == "low_trust"

    def test_denies_forbidden_type(self, tmp_storage, sovereignty, registry):
        _register_agent(registry)
        sovereignty.set("owner_1", "sig", _make_policy(allowed_types=["observation"]))
        result = sovereignty.allows("owner_1", "agent_1", "delete", registry)
        assert not result.allowed
        assert result.reason == "type_forbidden"

    def test_pending_on_approval_required(self, tmp_storage, sovereignty, registry):
        _register_agent(registry)
        sovereignty.set("owner_1", "sig", _make_policy(
            approval_required=["analysis"],
        ))
        result = sovereignty.allows("owner_1", "agent_1", "analysis", registry)
        assert result.verdict == "pending"
        assert not result.allowed

    def test_denies_no_policy(self, sovereignty, registry):
        result = sovereignty.allows("nobody", "agent_1", "observation", registry)
        assert not result.allowed
        assert result.reason == "no_policy"

    def test_enforcement_never_raises_only_result(self, sovereignty, registry):
        # Even with no setup, allows() returns a result, never raises
        result = sovereignty.allows("x", "y", "z", registry)
        assert isinstance(result, EnforcementResult)
        assert not result.allowed

    def test_cross_ai_flag_respected(self, tmp_storage, sovereignty, registry):
        _register_agent(registry, model="claude")
        sovereignty.set("owner_1", "sig", _make_policy(cross_ai=False))
        # Same model — should be allowed
        result = sovereignty.allows("owner_1", "agent_1", "observation", registry, agent_model="claude")
        assert result.allowed

    def test_cross_ai_denied_different_model(self, tmp_storage, sovereignty, registry):
        _register_agent(registry, model="claude")
        sovereignty.set("owner_1", "sig", _make_policy(cross_ai=False))
        result = sovereignty.allows("owner_1", "agent_1", "observation", registry, agent_model="gpt")
        assert not result.allowed
        assert result.reason == "cross_ai_denied"

    def test_cross_ai_allowed_when_enabled(self, tmp_storage, sovereignty, registry):
        _register_agent(registry, model="claude")
        sovereignty.set("owner_1", "sig", _make_policy(cross_ai=True))
        result = sovereignty.allows("owner_1", "agent_1", "observation", registry, agent_model="gpt")
        assert result.allowed


# ------------------------------------------------------------------
# Index
# ------------------------------------------------------------------


class TestIndex:
    def test_index_rebuilt_after_invalidation(self, sovereignty):
        sovereignty.set("owner_1", "sig", _make_policy())
        snap1 = sovereignty.get("owner_1")
        assert snap1 is not None

        sovereignty._invalidate_index()
        snap2 = sovereignty.get("owner_1")
        assert snap2 is not None
        assert snap2.owner_id == "owner_1"

    def test_index_o1_after_init(self, sovereignty):
        sovereignty.set("owner_1", "sig", _make_policy())
        # First call builds index
        sovereignty.get("owner_1")
        # Second call uses cached index
        snap = sovereignty.get("owner_1")
        assert snap is not None

    def test_trust_baseline_applied_to_new_agents(self, tmp_storage, sovereignty, registry):
        _register_agent(registry)
        sovereignty.set("owner_1", "sig", _make_policy(
            trust_baseline=0.7,
            min_trust_score=0.3,
        ))
        snap = sovereignty.get("owner_1")
        assert snap.trust_baseline == 0.7


# ------------------------------------------------------------------
# Schema validation (fix 3.2 — Manus audit)
# ------------------------------------------------------------------


class TestPolicyValidation:
    """Validate policy structure and types before accepting."""

    def test_missing_agents_raises(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="Missing"):
            sovereignty.set("o", "s", {"min_trust_score": 0.5, "allowed_types": ["x"]})

    def test_missing_min_trust_raises(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="Missing"):
            sovereignty.set("o", "s", {"agents": ["a"], "allowed_types": ["x"]})

    def test_missing_allowed_types_raises(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="Missing"):
            sovereignty.set("o", "s", {"agents": ["a"], "min_trust_score": 0.5})

    def test_agents_must_be_list(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="agents.*list"):
            sovereignty.set("o", "s", {
                "agents": "not_a_list",
                "min_trust_score": 0.5,
                "allowed_types": ["x"],
            })

    def test_agents_must_not_be_empty(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="agents.*empty"):
            sovereignty.set("o", "s", {
                "agents": [],
                "min_trust_score": 0.5,
                "allowed_types": ["x"],
            })

    def test_min_trust_must_be_number(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="min_trust_score.*number"):
            sovereignty.set("o", "s", {
                "agents": ["a"],
                "min_trust_score": "high",
                "allowed_types": ["x"],
            })

    def test_min_trust_must_be_in_range(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="min_trust_score.*\\[0.0, 1.0\\]"):
            sovereignty.set("o", "s", {
                "agents": ["a"],
                "min_trust_score": 1.5,
                "allowed_types": ["x"],
            })

    def test_min_trust_negative_rejected(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="min_trust_score.*\\[0.0, 1.0\\]"):
            sovereignty.set("o", "s", {
                "agents": ["a"],
                "min_trust_score": -0.1,
                "allowed_types": ["x"],
            })

    def test_allowed_types_must_be_list(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="allowed_types.*list"):
            sovereignty.set("o", "s", {
                "agents": ["a"],
                "min_trust_score": 0.5,
                "allowed_types": "not_a_list",
            })

    def test_allowed_types_must_not_be_empty(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="allowed_types.*empty"):
            sovereignty.set("o", "s", {
                "agents": ["a"],
                "min_trust_score": 0.5,
                "allowed_types": [],
            })

    def test_trust_baseline_must_be_in_range(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="trust_baseline.*\\[0.0, 1.0\\]"):
            sovereignty.set("o", "s", {
                "agents": ["a"],
                "min_trust_score": 0.5,
                "allowed_types": ["x"],
                "trust_baseline": 2.0,
            })

    def test_cross_ai_must_be_bool(self, sovereignty):
        with pytest.raises(InvalidPolicyStructure, match="cross_ai.*boolean"):
            sovereignty.set("o", "s", {
                "agents": ["a"],
                "min_trust_score": 0.5,
                "allowed_types": ["x"],
                "cross_ai": "yes",
            })

    def test_valid_policy_passes_all_checks(self, sovereignty):
        """A well-formed policy should pass validation."""
        entry = sovereignty.set("o", "s", {
            "agents": ["a", "b"],
            "min_trust_score": 0.5,
            "allowed_types": ["observation", "decision"],
            "trust_baseline": 0.4,
            "approval_required": ["decision"],
            "cross_ai": True,
        })
        assert entry is not None

    def test_boundary_values_accepted(self, sovereignty):
        """Edge values (0.0, 1.0) should be accepted."""
        entry = sovereignty.set("o", "s", {
            "agents": ["a"],
            "min_trust_score": 0.0,
            "allowed_types": ["x"],
            "trust_baseline": 1.0,
        })
        assert entry is not None
