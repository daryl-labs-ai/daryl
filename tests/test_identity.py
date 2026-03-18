"""Tests for DSM Identity Layer v1 (P15)."""

import time
from datetime import datetime, timedelta, timezone

import pytest

from dsm.agent import DarylAgent
from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.identity import IdentityGuard, IdentityManager
from dsm.identity.identity_replay import IdentityState, diff_identity, replay_identity


@pytest.fixture
def tmp_storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


@pytest.fixture
def tmp_agent(tmp_path):
    return DarylAgent(
        agent_id="test_agent",
        data_dir=str(tmp_path / "data"),
        signing_dir=False,
    )


class TestIdentityManager:
    def test_create_genesis(self, tmp_storage):
        m = IdentityManager(tmp_storage, "agent1", session_id="identity")
        e = m.create_genesis(
            purpose="assist users",
            capabilities=["read"],
            constraints=["no harm"],
            created_by="admin",
        )
        assert e.shard == "identity"
        assert m.identity_version == 1
        import json

        data = json.loads(e.content)
        assert data["event_type"] == "genesis"
        assert data["payload"]["purpose"] == "assist users"
        assert data["payload"]["initial_capabilities"] == ["read"]

    def test_duplicate_genesis_raises(self, tmp_storage):
        m = IdentityManager(tmp_storage, "agent1")
        m.create_genesis("p", [], [], "x")
        with pytest.raises(ValueError, match="Genesis already exists"):
            m.create_genesis("p2", [], [], "y")

    def test_append_event(self, tmp_storage):
        m = IdentityManager(tmp_storage, "agent1")
        m.create_genesis("p", [], [], "x")
        m.append_event("skill_added", {"skill": "search"})
        assert m.identity_version == 2

    def test_append_event_without_genesis(self, tmp_storage):
        m = IdentityManager(tmp_storage, "agent1")
        m.append_event("skill_added", {"skill": "x"})
        # Writer allows; replay will fail without genesis

    def test_invalid_event_type_raises(self, tmp_storage):
        m = IdentityManager(tmp_storage, "agent1")
        with pytest.raises(ValueError, match="Invalid"):
            m.append_event("invalid_type", {})

    def test_genesis_as_append_raises(self, tmp_storage):
        m = IdentityManager(tmp_storage, "agent1")
        with pytest.raises(ValueError, match="create_genesis"):
            m.append_event("genesis", {})


class TestReplay:
    def test_replay_genesis_only(self, tmp_storage):
        m = IdentityManager(tmp_storage, "a1")
        m.create_genesis("my purpose", ["c1"], ["k1"], "creator")
        st = replay_identity(tmp_storage, "a1")
        assert st.purpose == "my purpose"
        assert st.capabilities == ["c1"]
        assert st.constraints == ["k1"]
        assert st.created_by == "creator"
        assert st.event_count == 1

    def test_replay_with_skill_added(self, tmp_storage):
        m = IdentityManager(tmp_storage, "a1")
        m.create_genesis("p", [], [], "x")
        m.append_event("skill_added", {"skill": "browse"})
        st = replay_identity(tmp_storage, "a1")
        assert "browse" in st.capabilities

    def test_replay_with_skill_removed(self, tmp_storage):
        m = IdentityManager(tmp_storage, "a1")
        m.create_genesis("p", ["a"], [], "x")
        m.append_event("skill_added", {"skill": "b"})
        m.append_event("skill_removed", {"skill": "a"})
        st = replay_identity(tmp_storage, "a1")
        assert "a" not in st.capabilities
        assert "b" in st.capabilities

    def test_replay_with_model_change(self, tmp_storage):
        m = IdentityManager(tmp_storage, "a1")
        m.create_genesis("p", [], [], "x")
        m.append_event("model_change", {"to": "gpt-4"})
        st = replay_identity(tmp_storage, "a1")
        assert st.model_id == "gpt-4"

    def test_replay_no_genesis_raises(self, tmp_storage):
        m = IdentityManager(tmp_storage, "solo")
        m.append_event("skill_added", {"skill": "x"})
        with pytest.raises(ValueError, match="No genesis"):
            replay_identity(tmp_storage, "solo")

    def test_replay_up_to(self, tmp_storage):
        m = IdentityManager(tmp_storage, "a1")
        m.create_genesis("p", [], [], "x")
        time.sleep(0.03)
        m.append_event("skill_added", {"skill": "e1"})
        time.sleep(0.03)
        m.append_event("skill_added", {"skill": "e2"})
        time.sleep(0.03)
        m.append_event("skill_added", {"skill": "e3"})
        raw = tmp_storage.read("identity", offset=0, limit=100)
        ours = [e for e in reversed(raw) if "a1" in e.content]
        assert len(ours) >= 4
        t2 = ours[2].timestamp
        t3 = ours[3].timestamp
        if t2 == t3:
            t3 = t3 + timedelta(milliseconds=10)
        up_to = t2 + (t3 - t2) / 2
        st = replay_identity(tmp_storage, "a1", up_to=up_to)
        assert "e1" in st.capabilities
        assert "e2" in st.capabilities
        assert "e3" not in st.capabilities

    def test_replay_timeline(self, tmp_storage):
        m = IdentityManager(tmp_storage, "a1")
        m.create_genesis("p", [], [], "x")
        m.append_event("skill_added", {"skill": "s1"})
        m.append_event("behavior_change", {"note": "n"})
        st = replay_identity(tmp_storage, "a1")
        assert len(st.timeline) == 3
        assert st.timeline[0]["event_type"] == "genesis"
        assert st.timeline[1]["event_type"] == "skill_added"
        assert st.timeline[2]["event_type"] == "behavior_change"


class TestDiff:
    def test_diff_identity(self):
        a = IdentityState(
            agent_id="1",
            identity_version=1,
            purpose="a",
            capabilities=[],
            constraints=[],
            model_id=None,
            config_hash=None,
            created_by="x",
            genesis_timestamp=None,
            last_updated=None,
            event_count=1,
            timeline=[],
        )
        b = IdentityState(
            agent_id="1",
            identity_version=2,
            purpose="b",
            capabilities=["x"],
            constraints=[],
            model_id=None,
            config_hash=None,
            created_by="x",
            genesis_timestamp=None,
            last_updated=None,
            event_count=2,
            timeline=[{}],
        )
        d = diff_identity(a, b)
        assert "purpose" in d
        assert d["purpose"]["before"] == "a"
        assert d["purpose"]["after"] == "b"


class TestGuard:
    def test_guard_no_genesis(self, tmp_storage):
        g = IdentityGuard(tmp_storage, "nobody")
        r = g.check_continuity()
        assert r["status"] == "no_genesis"

    def test_guard_with_genesis(self, tmp_storage):
        m = IdentityManager(tmp_storage, "hasg")
        m.create_genesis("p", [], [], "x")
        g = IdentityGuard(tmp_storage, "hasg")
        r = g.check_continuity()
        assert r["status"] == "consistent"
        assert r["identity_version"] >= 1


class TestDarylAgentIdentity:
    def test_agent_identity_genesis(self, tmp_agent):
        e = tmp_agent.identity_genesis(purpose="test")
        assert isinstance(e, Entry)
        assert e.shard == "identity"

    def test_agent_identity_event(self, tmp_agent):
        tmp_agent.identity_genesis(purpose="p")
        e = tmp_agent.identity_event("skill_added", {"skill": "x"})
        assert e.metadata["event_type"] == "skill_added"
        assert e.shard == "identity"

    def test_agent_identity_replay(self, tmp_agent):
        tmp_agent.identity_genesis(purpose="goal", capabilities=["a"], constraints=[])
        tmp_agent.identity_event("skill_added", {"skill": "b"})
        st = tmp_agent.identity_replay()
        assert st.purpose == "goal"
        assert "b" in st.capabilities

    def test_agent_identity_check(self, tmp_agent):
        tmp_agent.identity_genesis(purpose="p")
        r = tmp_agent.identity_check()
        assert r["status"] == "consistent"
