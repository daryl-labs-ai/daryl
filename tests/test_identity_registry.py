"""Tests for DSM Identity Registry (Module A)."""

import json
import time

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.exceptions import UnauthorizedRevocation
from dsm.identity import AgentIdentity, IdentityRegistry
from dsm.identity.identity_registry import IDENTITY_REGISTRY_SHARD


@pytest.fixture
def tmp_storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


@pytest.fixture
def registry(tmp_storage):
    return IdentityRegistry(tmp_storage)


# ------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------


class TestRegistration:
    def test_register_agent_success(self, registry):
        entry = registry.register(
            agent_id="agent_1",
            public_key="aabbccdd" * 8,
            owner_id="owner_1",
            owner_signature="sig_placeholder",
            model="claude",
        )
        assert entry is not None
        assert entry.shard == IDENTITY_REGISTRY_SHARD
        data = json.loads(entry.content)
        assert data["event_type"] == "register"
        assert data["agent_id"] == "agent_1"
        assert data["model"] == "claude"

    def test_register_agent_duplicate_idempotent_latest_wins(self, registry):
        registry.register("agent_1", "key1" * 16, "owner_1", "sig1", model="claude")
        registry.register("agent_1", "key2" * 16, "owner_2", "sig2", model="gpt")

        identity = registry.resolve("agent_1")
        assert identity is not None
        # Latest registration wins
        assert identity.public_key == "key2" * 16
        assert identity.owner_id == "owner_2"
        assert identity.model == "gpt"

    def test_register_writes_to_correct_shard(self, registry):
        entry = registry.register("a1", "k" * 64, "o1", "s1")
        assert entry.shard == "identity_registry"


# ------------------------------------------------------------------
# Resolution
# ------------------------------------------------------------------


class TestResolution:
    def test_resolve_registered_agent(self, registry):
        registry.register("agent_1", "ab" * 32, "owner_1", "sig1", model="claude")
        identity = registry.resolve("agent_1")
        assert identity is not None
        assert isinstance(identity, AgentIdentity)
        assert identity.agent_id == "agent_1"
        assert identity.public_key == "ab" * 32
        assert identity.owner_id == "owner_1"
        assert identity.model == "claude"

    def test_resolve_unknown_agent_returns_none(self, registry):
        assert registry.resolve("nonexistent") is None

    def test_resolve_concurrent_register_latest_wins(self, registry):
        registry.register("a", "k1" * 32, "o1", "s1")
        registry.register("a", "k2" * 32, "o2", "s2")
        registry.register("a", "k3" * 32, "o3", "s3")
        identity = registry.resolve("a")
        assert identity.public_key == "k3" * 32
        assert identity.owner_id == "o3"


# ------------------------------------------------------------------
# Revocation
# ------------------------------------------------------------------


class TestRevocation:
    def test_revoke_agent_success(self, registry):
        registry.register("agent_1", "k" * 64, "owner_1", "sig1")
        entry = registry.revoke("agent_1", "owner_1", "sig_revoke", reason="compromised")
        assert entry is not None
        data = json.loads(entry.content)
        assert data["event_type"] == "revoke"
        assert data["reason"] == "compromised"

    def test_revoke_by_wrong_owner_raises(self, registry):
        registry.register("agent_1", "k" * 64, "owner_1", "sig1")
        with pytest.raises(UnauthorizedRevocation):
            registry.revoke("agent_1", "intruder", "bad_sig")

    def test_resolve_revoked_agent_returns_none(self, registry):
        registry.register("agent_1", "k" * 64, "owner_1", "sig1")
        registry.revoke("agent_1", "owner_1", "sig_r")
        assert registry.resolve("agent_1") is None

    def test_revocation_entry_still_in_log(self, registry):
        registry.register("agent_1", "k" * 64, "owner_1", "sig1")
        registry.revoke("agent_1", "owner_1", "sig_r")
        history = registry.history("agent_1")
        assert len(history) == 2
        types = [json.loads(e.content)["event_type"] for e in history]
        assert "register" in types
        assert "revoke" in types


# ------------------------------------------------------------------
# Trust scoring
# ------------------------------------------------------------------


class TestTrustScore:
    def test_fast_trust_new_agent_uses_baseline(self, registry):
        registry.register("agent_1", "k" * 64, "owner_1", "sig1")
        score = registry.trust_score("agent_1")
        # Should be close to baseline (0.5) — just registered
        assert 0.49 <= score <= 0.51

    def test_fast_trust_o1_no_shard_scan(self, registry):
        registry.register("agent_1", "k" * 64, "owner_1", "sig1")
        # First call builds index
        registry.trust_score("agent_1")
        # Second call uses cached index — O(1)
        score = registry.trust_score("agent_1")
        assert score > 0

    def test_deep_trust_includes_chain_integrity(self, registry):
        registry.register("agent_1", "k" * 64, "owner_1", "sig1")
        deep = registry.deep_trust_score("agent_1")
        assert 0.0 < deep <= 1.0

    def test_deep_trust_cached_after_first_call(self, registry):
        registry.register("agent_1", "k" * 64, "owner_1", "sig1")
        score1 = registry.deep_trust_score("agent_1")
        score2 = registry.deep_trust_score("agent_1")
        assert score1 == score2

    def test_trust_score_revoked_drops_to_zero(self, registry):
        registry.register("agent_1", "k" * 64, "owner_1", "sig1")
        assert registry.trust_score("agent_1") > 0
        registry.revoke("agent_1", "owner_1", "sig_r")
        assert registry.trust_score("agent_1") == 0.0

    def test_trust_score_unknown_agent_zero(self, registry):
        assert registry.trust_score("ghost") == 0.0


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------


class TestUtilities:
    def test_list_agents_by_owner(self, registry):
        registry.register("a1", "k1" * 32, "owner_1", "s1")
        registry.register("a2", "k2" * 32, "owner_1", "s2")
        registry.register("a3", "k3" * 32, "owner_2", "s3")

        agents = registry.list_agents(owner_id="owner_1")
        ids = [a.agent_id for a in agents]
        assert "a1" in ids
        assert "a2" in ids
        assert "a3" not in ids

    def test_list_agents_excludes_revoked(self, registry):
        registry.register("a1", "k" * 64, "o1", "s1")
        registry.register("a2", "k2" * 32, "o1", "s2")
        registry.revoke("a1", "o1", "sr")
        agents = registry.list_agents()
        ids = [a.agent_id for a in agents]
        assert "a1" not in ids
        assert "a2" in ids

    def test_history_shows_all_entries(self, registry):
        registry.register("a1", "k" * 64, "o1", "s1")
        registry.register("a1", "k2" * 32, "o2", "s2")
        history = registry.history("a1")
        assert len(history) == 2

    def test_history_empty_for_unknown(self, registry):
        assert registry.history("ghost") == []


# ------------------------------------------------------------------
# Integrity & invariants
# ------------------------------------------------------------------


class TestIntegrity:
    def test_registry_is_append_only(self, tmp_storage, registry):
        registry.register("a1", "k" * 64, "o1", "s1")
        registry.register("a2", "k2" * 32, "o1", "s2")
        registry.revoke("a1", "o1", "sr")

        entries = tmp_storage.read(IDENTITY_REGISTRY_SHARD, limit=10**6)
        assert len(entries) == 3

    def test_hash_chain_integrity_on_identity_shard(self, tmp_storage, registry):
        registry.register("a1", "k" * 64, "o1", "s1")
        registry.register("a2", "k2" * 32, "o1", "s2")

        entries = tmp_storage.read(IDENTITY_REGISTRY_SHARD, limit=10**6)
        # Entries are newest-first; reverse for chain check
        chrono = list(reversed(entries))
        for i, e in enumerate(chrono):
            if i == 0:
                continue
            assert chrono[i].prev_hash == chrono[i - 1].hash

    def test_multi_agent_same_shard(self, registry):
        registry.register("a1", "k1" * 32, "o1", "s1", model="claude")
        registry.register("a2", "k2" * 32, "o2", "s2", model="gpt")
        assert registry.resolve("a1") is not None
        assert registry.resolve("a2") is not None
        assert registry.resolve("a1").model == "claude"
        assert registry.resolve("a2").model == "gpt"

    def test_cross_model_registration(self, registry):
        registry.register("claude_bot", "kc" * 32, "o1", "s1", model="claude")
        registry.register("gpt_bot", "kg" * 32, "o1", "s2", model="gpt")
        registry.register("gemini_bot", "km" * 32, "o1", "s3", model="gemini")

        for aid in ["claude_bot", "gpt_bot", "gemini_bot"]:
            assert registry.resolve(aid) is not None

    def test_index_rebuilt_after_invalidation(self, registry):
        registry.register("a1", "k" * 64, "o1", "s1")
        identity1 = registry.resolve("a1")
        assert identity1 is not None

        # Force invalidation
        registry._invalidate_index()

        # Should rebuild and still resolve
        identity2 = registry.resolve("a1")
        assert identity2 is not None
        assert identity2.agent_id == "a1"
