"""Event envelope and factory tests."""
from __future__ import annotations

import pytest

from agent_mesh.dsm import factory as ev_factory
from agent_mesh.dsm.event import build_event
from agent_mesh.dsm.ulid import is_valid_ulid, new_event_id


def test_new_event_id_is_valid_ulid():
    eid = new_event_id()
    assert is_valid_ulid(eid)


def test_is_valid_ulid_rejects_garbage():
    assert is_valid_ulid("not-a-ulid") is False
    assert is_valid_ulid("") is False


def test_build_event_has_required_fields():
    ev = build_event(
        event_type="test",
        event_version="1.0",
        scope_type="system",
        scope_id="sys",
        source_type="server",
        source_id="s1",
        writer_type="server",
        writer_id="s1",
        payload={"x": 1},
    )
    for k in (
        "event_id",
        "schema_version",
        "event_type",
        "timestamp",
        "scope_type",
        "scope_id",
        "source_type",
        "source_id",
        "writer_type",
        "writer_id",
        "payload",
        "links",
        "auth",
    ):
        assert k in ev


def test_build_event_timestamp_z_suffix():
    ev = build_event("t", "1.0", "system", "s", "server", "s1", "server", "s1", {})
    assert ev["timestamp"].endswith("Z")


def test_build_event_default_auth():
    ev = build_event("t", "1.0", "system", "s", "server", "s1", "server", "s1", {})
    assert ev["auth"]["transport_authenticated"] is False
    assert ev["auth"]["signature_verified"] is False


def test_causal_refs_max_8():
    refs = [new_event_id() for _ in range(9)]
    with pytest.raises(ValueError):
        build_event(
            "t", "1.0", "system", "s", "server", "s1", "server", "s1", {}, causal_refs=refs
        )


def test_causal_refs_unique():
    eid = new_event_id()
    with pytest.raises(ValueError):
        build_event(
            "t", "1.0", "system", "s", "server", "s1", "server", "s1", {}, causal_refs=[eid, eid]
        )


def test_causal_refs_must_be_ulid():
    with pytest.raises(ValueError):
        build_event(
            "t", "1.0", "system", "s", "server", "s1", "server", "s1", {}, causal_refs=["garbage"]
        )


def test_causal_refs_accept_valid():
    refs = [new_event_id() for _ in range(3)]
    ev = build_event("t", "1.0", "system", "s", "server", "s1", "server", "s1", {}, causal_refs=refs)
    assert ev["links"]["causal_refs"] == refs


def test_factory_system_scope():
    ev = ev_factory.server_started("s1", {"server_id": "s1"})
    assert ev["scope_type"] == "system"
    assert ev["scope_id"] == "system.server.lifecycle"
    assert ev["source_type"] == "server"
    assert ev["source_id"] == "s1"
    assert ev["event_type"] == "server_started"


def test_factory_mission_scope():
    ev = ev_factory.mission_created("m1", "s1", {"mission_id": "m1"})
    assert ev["scope_type"] == "mission"
    assert ev["scope_id"] == "mission_m1"
    assert ev["source_type"] == "server"


def test_factory_agent_authored():
    ev = ev_factory.task_result_submitted("m1", "s1", "agent_a", {"foo": "bar"})
    assert ev["source_type"] == "agent"
    assert ev["source_id"] == "agent_a"
    assert ev["writer_type"] == "server"
    assert ev["writer_id"] == "s1"


def test_factory_agent_registered_is_system_agent_registry():
    ev = ev_factory.agent_registered("s1", {"agent_id": "a1"})
    assert ev["scope_id"] == "system.agent_registry"


def test_factory_reputation_updated_scope():
    ev = ev_factory.reputation_updated("s1", {"agent_id": "a1", "delta": 0.1})
    assert ev["scope_id"] == "system.reputation"


def test_factory_mission_closed():
    ev = ev_factory.mission_closed("m1", "s1", {"mission_id": "m1"})
    assert ev["event_type"] == "mission_closed"
    assert ev["scope_id"] == "mission_m1"


def test_factory_each_event_has_unique_id():
    e1 = ev_factory.server_started("s1", {})
    e2 = ev_factory.server_started("s1", {})
    assert e1["event_id"] != e2["event_id"]
