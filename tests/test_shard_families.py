"""Tests for Shard Families — cross-cutting classification utility."""

import pytest

from dsm.shard_families import (
    FAMILY_RETENTION,
    ShardFamily,
    classify_shard,
)


class TestClassifyShard:
    """classify_shard() is a pure function, O(1)."""

    def test_sessions_is_agent(self):
        assert classify_shard("sessions") == ShardFamily.AGENT

    def test_identity_is_agent(self):
        assert classify_shard("identity") == ShardFamily.AGENT

    def test_identity_registry_is_registry(self):
        assert classify_shard("identity_registry") == ShardFamily.REGISTRY

    def test_sovereignty_policies_is_registry(self):
        assert classify_shard("sovereignty_policies") == ShardFamily.REGISTRY

    def test_lifecycle_registry_is_registry(self):
        assert classify_shard("lifecycle_registry") == ShardFamily.REGISTRY

    def test_orchestrator_audit_is_audit(self):
        assert classify_shard("orchestrator_audit") == ShardFamily.AUDIT

    def test_sync_log_is_infra(self):
        assert classify_shard("sync_log") == ShardFamily.INFRA

    def test_receipts_is_infra(self):
        assert classify_shard("receipts") == ShardFamily.INFRA

    def test_collective_prefix_is_collective(self):
        assert classify_shard("collective_main") == ShardFamily.COLLECTIVE

    def test_collective_distilled_is_collective(self):
        assert classify_shard("collective_distilled") == ShardFamily.COLLECTIVE

    def test_collective_digests_is_collective(self):
        assert classify_shard("collective_digests") == ShardFamily.COLLECTIVE

    def test_collective_team_b_is_collective(self):
        assert classify_shard("collective_team_b") == ShardFamily.COLLECTIVE

    def test_unknown_shard_defaults_to_agent(self):
        assert classify_shard("my_custom_shard") == ShardFamily.AGENT

    def test_empty_string_defaults_to_agent(self):
        assert classify_shard("") == ShardFamily.AGENT


class TestShardFamilyConstants:
    def test_all_families_present(self):
        assert ShardFamily.AGENT == "agent"
        assert ShardFamily.REGISTRY == "registry"
        assert ShardFamily.AUDIT == "audit"
        assert ShardFamily.COLLECTIVE == "collective"
        assert ShardFamily.INFRA == "infra"

    def test_all_set_has_five_members(self):
        assert len(ShardFamily.ALL) == 5

    def test_all_set_contains_all_families(self):
        for f in [ShardFamily.AGENT, ShardFamily.REGISTRY, ShardFamily.AUDIT,
                  ShardFamily.COLLECTIVE, ShardFamily.INFRA]:
            assert f in ShardFamily.ALL


class TestFamilyRetention:
    def test_registry_never_expires(self):
        r = FAMILY_RETENTION[ShardFamily.REGISTRY]
        assert r["max_age_days"] is None
        assert r["max_entries"] is None

    def test_audit_never_expires(self):
        r = FAMILY_RETENTION[ShardFamily.AUDIT]
        assert r["max_age_days"] is None

    def test_infra_short_retention(self):
        r = FAMILY_RETENTION[ShardFamily.INFRA]
        assert r["max_age_days"] == 30

    def test_all_families_have_retention(self):
        for f in ShardFamily.ALL:
            assert f in FAMILY_RETENTION
