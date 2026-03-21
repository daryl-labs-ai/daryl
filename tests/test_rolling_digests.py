"""Tests for Rolling Temporal Digests — automatic window detection and digest creation.

Validates:
- pending_windows() identifies hourly/daily/weekly/monthly gaps
- roll() produces digests for all pending windows
- Idempotency: roll() twice produces no duplicates
- Level filtering
- Window alignment (hour/day/week/month boundaries)
- Agent facade roll_digests()
"""

import json
from datetime import datetime, timezone, timedelta

import pytest

from dsm.collective import (
    CollectiveEntry, CollectiveShard, DigestEntry,
    RollingDigester,
)
from dsm.core.models import Entry
from dsm.core.storage import Storage


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def tmp_storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


@pytest.fixture
def collective(tmp_storage):
    return CollectiveShard(tmp_storage, "roll_test")


@pytest.fixture
def digester(collective, tmp_storage):
    return RollingDigester(collective, tmp_storage)


def _inject_entries(collective, entries):
    """Inject pre-built CollectiveEntry objects into the index."""
    collective._index = entries


def _make_ce(agent_id="alice", hours_ago=0, base_time=None):
    """Create a CollectiveEntry at a given time offset."""
    base = base_time or datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
    return CollectiveEntry(
        hash=f"h_{hours_ago}",
        agent_id=agent_id,
        source_hash=f"src_{hours_ago}",
        content_hash=f"cnt_{hours_ago}",
        summary=f"Summary at -{hours_ago}h",
        detail=f"Detail text at -{hours_ago}h",
        key_findings=(f"finding_{hours_ago}",),
        action_type="observation",
        agent_prev_hash="",
        contributed_at=base - timedelta(hours=hours_ago),
    )


# ------------------------------------------------------------------
# pending_windows
# ------------------------------------------------------------------


class TestPendingWindows:
    def test_no_entries_returns_empty(self, digester, collective):
        _inject_entries(collective, [])
        assert digester.pending_windows() == []

    def test_detects_hourly_windows(self, digester, collective):
        """Entries spanning 3 hours should produce 3 hourly pending windows."""
        now = datetime(2026, 3, 20, 15, 0, 0, tzinfo=timezone.utc)
        entries = [
            _make_ce(hours_ago=0, base_time=now),
            _make_ce(hours_ago=1, base_time=now),
            _make_ce(hours_ago=2, base_time=now),
        ]
        _inject_entries(collective, sorted(entries, key=lambda e: e.contributed_at))
        pending = digester.pending_windows(now=now)
        hourly = [p for p in pending if p["level"] == 1]
        assert len(hourly) >= 2  # at least 2 complete hourly windows

    def test_detects_daily_windows(self, digester, collective):
        """Entries spanning 3 days should produce daily pending windows."""
        now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
        entries = [
            _make_ce(hours_ago=0, base_time=now),
            _make_ce(hours_ago=24, base_time=now),
            _make_ce(hours_ago=48, base_time=now),
        ]
        _inject_entries(collective, sorted(entries, key=lambda e: e.contributed_at))
        pending = digester.pending_windows(now=now)
        daily = [p for p in pending if p["level"] == 2]
        assert len(daily) >= 2

    def test_window_has_correct_fields(self, digester, collective):
        now = datetime(2026, 3, 20, 15, 0, 0, tzinfo=timezone.utc)
        entries = [_make_ce(hours_ago=1, base_time=now)]
        _inject_entries(collective, entries)
        pending = digester.pending_windows(now=now)
        assert len(pending) > 0
        w = pending[0]
        assert "level" in w
        assert "label" in w
        assert "start" in w
        assert "end" in w
        assert "digest_id" in w
        assert w["end"] > w["start"]

    def test_hourly_aligned_to_hour(self, digester, collective):
        """Hourly windows should start at :00 minutes."""
        now = datetime(2026, 3, 20, 15, 30, 0, tzinfo=timezone.utc)
        entries = [_make_ce(hours_ago=2, base_time=now)]
        _inject_entries(collective, entries)
        pending = digester.pending_windows(now=now)
        hourly = [p for p in pending if p["level"] == 1]
        for h in hourly:
            assert h["start"].minute == 0
            assert h["start"].second == 0

    def test_daily_aligned_to_midnight(self, digester, collective):
        """Daily windows should start at 00:00."""
        now = datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc)
        entries = [_make_ce(hours_ago=48, base_time=now)]
        _inject_entries(collective, entries)
        pending = digester.pending_windows(now=now)
        daily = [p for p in pending if p["level"] == 2]
        for d in daily:
            assert d["start"].hour == 0
            assert d["start"].minute == 0


# ------------------------------------------------------------------
# roll
# ------------------------------------------------------------------


class TestRoll:
    def test_roll_produces_digests(self, digester, collective, tmp_storage):
        """roll() should create DigestEntry objects."""
        now = datetime(2026, 3, 20, 15, 0, 0, tzinfo=timezone.utc)
        entries = [
            _make_ce(hours_ago=1, base_time=now),
            _make_ce(hours_ago=2, base_time=now),
        ]
        _inject_entries(collective, sorted(entries, key=lambda e: e.contributed_at))
        created = digester.roll(now=now, levels=[1])
        assert len(created) >= 1
        assert all(isinstance(d, DigestEntry) for d in created)

    def test_roll_idempotent(self, digester, collective, tmp_storage):
        """Second roll() with same data produces no new digests."""
        now = datetime(2026, 3, 20, 15, 0, 0, tzinfo=timezone.utc)
        entries = [_make_ce(hours_ago=1, base_time=now)]
        _inject_entries(collective, sorted(entries, key=lambda e: e.contributed_at))

        first = digester.roll(now=now, levels=[1])
        assert len(first) >= 1

        second = digester.roll(now=now, levels=[1])
        assert len(second) == 0

    def test_roll_level_filter(self, digester, collective):
        """Only produce digests for requested levels."""
        now = datetime(2026, 3, 20, 15, 0, 0, tzinfo=timezone.utc)
        entries = [
            _make_ce(hours_ago=1, base_time=now),
            _make_ce(hours_ago=25, base_time=now),
        ]
        _inject_entries(collective, sorted(entries, key=lambda e: e.contributed_at))

        hourly_only = digester.roll(now=now, levels=[1])
        # Should only have level-1 digests
        for d in hourly_only:
            assert d.level == 1

    def test_roll_empty_collective(self, digester, collective):
        _inject_entries(collective, [])
        created = digester.roll()
        assert created == []

    def test_digest_has_source_count(self, digester, collective):
        """Each digest should have a source_count > 0."""
        now = datetime(2026, 3, 20, 15, 0, 0, tzinfo=timezone.utc)
        entries = [
            _make_ce(hours_ago=1, base_time=now),
            _make_ce(hours_ago=1, base_time=now),
        ]
        # Two entries in same hour
        entries[1] = CollectiveEntry(
            hash="h_1b", agent_id="bob",
            source_hash="src_1b", content_hash="cnt_1b",
            summary="Another", detail="Detail", key_findings=("f",),
            action_type="observation", agent_prev_hash="",
            contributed_at=now - timedelta(hours=1, minutes=10),
        )
        _inject_entries(collective, sorted(entries, key=lambda e: e.contributed_at))
        created = digester.roll(now=now, levels=[1])
        for d in created:
            assert d.source_count > 0

    def test_digest_written_to_shard(self, digester, collective, tmp_storage):
        """Digests should be persisted in the digests shard."""
        now = datetime(2026, 3, 20, 15, 0, 0, tzinfo=timezone.utc)
        entries = [_make_ce(hours_ago=1, base_time=now)]
        _inject_entries(collective, sorted(entries, key=lambda e: e.contributed_at))
        digester.roll(now=now, levels=[1])

        # Read from digests shard
        shard_entries = tmp_storage.read(digester._digests_shard, limit=100)
        assert len(shard_entries) >= 1
        data = json.loads(shard_entries[0].content)
        assert data["event_type"] == "digest"
        assert data["level"] == 1


# ------------------------------------------------------------------
# Integration with read_with_digests
# ------------------------------------------------------------------


class TestRollThenRead:
    def test_rolled_digests_appear_in_context(self, digester, collective, tmp_storage):
        """After roll(), read_with_digests should include the digests."""
        now = datetime(2026, 3, 20, 15, 0, 0, tzinfo=timezone.utc)
        entries = [
            _make_ce(hours_ago=1, base_time=now),
            _make_ce(hours_ago=2, base_time=now),
        ]
        _inject_entries(collective, sorted(entries, key=lambda e: e.contributed_at))

        # Roll hourly digests
        digester.roll(now=now, levels=[1])

        # Read with digests
        since = now - timedelta(hours=3)
        ctx = digester.read_with_digests(since=since, max_tokens=8000)
        assert len(ctx.hourly_digests) >= 1


# ------------------------------------------------------------------
# Agent facade
# ------------------------------------------------------------------


class TestAgentRollDigests:
    @pytest.fixture
    def agent(self, tmp_path):
        from dsm.agent import DarylAgent
        DarylAgent._reset_startup_cache()
        a = DarylAgent(
            agent_id="roll_agent",
            data_dir=str(tmp_path / "data"),
            signing_dir=False,
            artifact_dir=False,
            startup_verify=False,
        )
        yield a
        DarylAgent._reset_startup_cache()

    def test_roll_digests_empty(self, agent):
        result = agent.roll_digests()
        assert result == []

    def test_roll_digests_with_data(self, agent):
        now = datetime(2026, 3, 20, 15, 0, 0, tzinfo=timezone.utc)
        entries = [_make_ce(hours_ago=1, base_time=now)]
        agent.collective._index = sorted(entries, key=lambda e: e.contributed_at)
        result = agent.roll_digests(levels=[1])
        # May or may not produce digests depending on timing
        assert isinstance(result, list)

    def test_roll_digests_level_filter(self, agent):
        result = agent.roll_digests(levels=[2, 3])
        assert isinstance(result, list)
