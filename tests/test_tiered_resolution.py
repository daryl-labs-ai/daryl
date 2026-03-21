"""Tests for Tiered Resolution on CollectiveEntry and CollectiveShard.

Validates:
- CollectiveEntry.at_tier(0..3) returns correct field subsets
- CollectiveEntry.tier_token_estimate() returns expected values
- CollectiveShard.recent_at_tier() with tier selection
- Auto-downgrade when max_tokens budget is exceeded
- Agent facade collective_at_tier()
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from dsm.collective import CollectiveEntry, CollectiveShard
from dsm.core.models import Entry
from dsm.core.storage import Storage


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def tmp_storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


def _make_collective_entry(agent_id="alice", summary="A short summary",
                            detail="Extended detail text here",
                            key_findings=("finding1", "finding2"),
                            action_type="observation"):
    return CollectiveEntry(
        hash="abc123",
        agent_id=agent_id,
        source_hash="src_h1",
        content_hash="cnt_h1",
        summary=summary,
        detail=detail,
        key_findings=key_findings,
        action_type=action_type,
        agent_prev_hash="prev_h1",
        contributed_at=datetime(2026, 3, 21, 12, 0, 0, tzinfo=timezone.utc),
    )


# ------------------------------------------------------------------
# CollectiveEntry.at_tier()
# ------------------------------------------------------------------


class TestAtTier:
    """Test CollectiveEntry.at_tier() returns correct field subsets."""

    def test_tier_0_minimal(self):
        e = _make_collective_entry()
        t0 = e.at_tier(0)
        assert set(t0.keys()) == {"hash", "agent_id", "contributed_at"}
        assert t0["hash"] == "abc123"
        assert t0["agent_id"] == "alice"
        assert "summary" not in t0
        assert "detail" not in t0

    def test_tier_1_with_summary(self):
        e = _make_collective_entry()
        t1 = e.at_tier(1)
        assert set(t1.keys()) == {"hash", "agent_id", "contributed_at", "summary", "action_type"}
        assert t1["summary"] == "A short summary"
        assert t1["action_type"] == "observation"
        assert "detail" not in t1

    def test_tier_2_with_detail(self):
        e = _make_collective_entry()
        t2 = e.at_tier(2)
        assert "detail" in t2
        assert "key_findings" in t2
        assert t2["detail"] == "Extended detail text here"
        assert t2["key_findings"] == ["finding1", "finding2"]
        assert "source_hash" not in t2

    def test_tier_3_full(self):
        e = _make_collective_entry()
        t3 = e.at_tier(3)
        assert "source_hash" in t3
        assert "content_hash" in t3
        assert "agent_prev_hash" in t3
        assert t3["source_hash"] == "src_h1"
        assert t3["content_hash"] == "cnt_h1"

    def test_tier_negative_is_tier_0(self):
        e = _make_collective_entry()
        t = e.at_tier(-1)
        assert set(t.keys()) == {"hash", "agent_id", "contributed_at"}

    def test_tier_above_3_is_tier_3(self):
        e = _make_collective_entry()
        t = e.at_tier(10)
        assert "source_hash" in t
        assert "content_hash" in t

    def test_contributed_at_is_isoformat(self):
        e = _make_collective_entry()
        for tier in range(4):
            t = e.at_tier(tier)
            assert "T" in t["contributed_at"]  # ISO format

    def test_key_findings_is_list_not_tuple(self):
        """at_tier converts tuple to list for JSON compatibility."""
        e = _make_collective_entry(key_findings=("a", "b", "c"))
        t2 = e.at_tier(2)
        assert isinstance(t2["key_findings"], list)
        t3 = e.at_tier(3)
        assert isinstance(t3["key_findings"], list)


# ------------------------------------------------------------------
# Token estimates
# ------------------------------------------------------------------


class TestTokenEstimates:
    def test_tier_0_estimate(self):
        assert CollectiveEntry.tier_token_estimate(0) == 30

    def test_tier_1_estimate(self):
        assert CollectiveEntry.tier_token_estimate(1) == 80

    def test_tier_2_estimate(self):
        assert CollectiveEntry.tier_token_estimate(2) == 300

    def test_tier_3_estimate(self):
        assert CollectiveEntry.tier_token_estimate(3) == 500

    def test_unknown_tier_defaults_to_500(self):
        assert CollectiveEntry.tier_token_estimate(99) == 500


# ------------------------------------------------------------------
# CollectiveShard.recent_at_tier()
# ------------------------------------------------------------------


def _mock_entries(n=5):
    """Create n mock CollectiveEntry objects."""
    return [
        CollectiveEntry(
            hash=f"hash_{i}",
            agent_id=f"agent_{i % 3}",
            source_hash=f"src_{i}",
            content_hash=f"cnt_{i}",
            summary=f"Summary {i}",
            detail=f"Detail text for entry {i}",
            key_findings=(f"finding_{i}",),
            action_type="observation",
            agent_prev_hash=f"prev_{i}",
            contributed_at=datetime(2026, 3, 21, 12, i, 0, tzinfo=timezone.utc),
        )
        for i in range(n)
    ]


class TestRecentAtTier:
    def test_returns_dicts(self, tmp_storage):
        cs = CollectiveShard(tmp_storage, "tier_test")
        entries = _mock_entries(3)
        cs._index = entries
        result = cs.recent_at_tier(tier=1)
        assert isinstance(result, list)
        assert all(isinstance(r, dict) for r in result)

    def test_tier_0_small_output(self, tmp_storage):
        cs = CollectiveShard(tmp_storage, "t0")
        cs._index = _mock_entries(5)
        result = cs.recent_at_tier(tier=0)
        for r in result:
            assert "summary" not in r
            assert "detail" not in r

    def test_tier_2_includes_detail(self, tmp_storage):
        cs = CollectiveShard(tmp_storage, "t2")
        cs._index = _mock_entries(3)
        result = cs.recent_at_tier(tier=2)
        for r in result:
            assert "detail" in r
            assert "key_findings" in r

    def test_respects_limit(self, tmp_storage):
        cs = CollectiveShard(tmp_storage, "lim")
        cs._index = _mock_entries(10)
        result = cs.recent_at_tier(tier=1, limit=3)
        assert len(result) == 3

    def test_empty_collective(self, tmp_storage):
        cs = CollectiveShard(tmp_storage, "empty")
        cs._index = []
        result = cs.recent_at_tier(tier=2)
        assert result == []

    def test_auto_downgrade_tier(self, tmp_storage):
        """When max_tokens is tight, tier auto-downgrades."""
        cs = CollectiveShard(tmp_storage, "auto")
        cs._index = _mock_entries(10)
        # 10 entries * 300 tokens/entry (Tier 2) = 3000 tokens
        # Budget = 1000 -> should downgrade to Tier 1 (10*80=800) or Tier 0 (10*30=300)
        result = cs.recent_at_tier(tier=2, max_tokens=1000)
        # Should have downgraded — no "detail" field
        assert len(result) == 10
        # At Tier 1 (10*80=800 <= 1000)
        assert "summary" in result[0]
        assert "detail" not in result[0]

    def test_auto_downgrade_to_tier_0(self, tmp_storage):
        """Very tight budget -> downgrade to Tier 0."""
        cs = CollectiveShard(tmp_storage, "tight")
        cs._index = _mock_entries(10)
        # Budget = 400 -> Tier 2: 3000, Tier 1: 800, Tier 0: 300
        result = cs.recent_at_tier(tier=2, max_tokens=400)
        assert len(result) == 10
        assert "summary" not in result[0]

    def test_auto_truncate_at_tier_0(self, tmp_storage):
        """Extremely tight budget -> truncate entries at Tier 0."""
        cs = CollectiveShard(tmp_storage, "trunc")
        cs._index = _mock_entries(10)
        # Budget = 60 -> Tier 0 at 30 tokens/entry -> 2 entries
        result = cs.recent_at_tier(tier=2, max_tokens=60)
        assert len(result) == 2

    def test_max_tokens_none_no_downgrade(self, tmp_storage):
        """No budget -> no downgrade, full tier."""
        cs = CollectiveShard(tmp_storage, "no_budget")
        cs._index = _mock_entries(5)
        result = cs.recent_at_tier(tier=2, max_tokens=None)
        assert len(result) == 5
        assert "detail" in result[0]

    def test_filter_by_agent(self, tmp_storage):
        cs = CollectiveShard(tmp_storage, "filt")
        cs._index = _mock_entries(6)
        # agent_0, agent_1, agent_2, agent_0, agent_1, agent_2
        result = cs.recent_at_tier(tier=1, agent_id="agent_0")
        assert len(result) == 2
        for r in result:
            assert r["agent_id"] == "agent_0"


# ------------------------------------------------------------------
# Agent facade — collective_at_tier
# ------------------------------------------------------------------


class TestAgentCollectiveAtTier:
    @pytest.fixture
    def agent(self, tmp_path):
        from dsm.agent import DarylAgent
        DarylAgent._reset_startup_cache()
        a = DarylAgent(
            agent_id="tier_agent",
            data_dir=str(tmp_path / "data"),
            signing_dir=False,
            artifact_dir=False,
            startup_verify=False,
        )
        yield a
        DarylAgent._reset_startup_cache()

    def test_collective_at_tier_empty(self, agent):
        result = agent.collective_at_tier(tier=1)
        assert result == []

    def test_collective_at_tier_with_data(self, agent):
        # Inject mock index
        agent.collective._index = _mock_entries(3)
        result = agent.collective_at_tier(tier=0)
        assert len(result) == 3
        assert "summary" not in result[0]

    def test_collective_at_tier_with_budget(self, agent):
        agent.collective._index = _mock_entries(10)
        result = agent.collective_at_tier(tier=2, max_tokens=500)
        # Should auto-downgrade
        assert len(result) > 0
        assert "detail" not in result[0]
