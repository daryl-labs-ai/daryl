"""Tests for Policy Audit module."""

import json
from datetime import datetime
from uuid import uuid4

from dsm.audit import Policy, audit_all, audit_shard
from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.session.session_graph import SessionGraph
from dsm.session.session_limits_manager import SessionLimitsManager


def _make_session(tmp_path, actions, source="test"):
    """Helper: create a storage with a session containing given actions."""
    storage = Storage(data_dir=str(tmp_path))
    try:
        limits = SessionLimitsManager.agent_defaults(str(tmp_path))
        graph = SessionGraph(storage=storage, limits_manager=limits)
    except TypeError:
        graph = SessionGraph(storage=storage)

    graph.start_session(source=source)
    for action_name, payload in actions:
        intent = graph.execute_action(action_name, payload)
        if intent:
            intent_id = intent.metadata.get("intent_id") or intent.id
            graph.confirm_action(intent_id, {"done": True})
    graph.end_session()
    return storage


# --- Policy loading ---


def test_policy_from_file(tmp_path):
    """Load policy from JSON file."""
    policy_data = {
        "allowed_actions": ["search", "reply"],
        "forbidden_actions": ["delete_files"],
        "allowed_sources": ["test", "openclaw"],
        "max_actions_per_session": 10,
        "allowed_shards": ["sessions"],
    }
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps(policy_data))

    policy = Policy.from_file(str(policy_file))
    assert policy.allowed_actions == ["search", "reply"]
    assert policy.forbidden_actions == ["delete_files"]
    assert policy.max_actions_per_session == 10


# --- Compliant audit ---


def test_audit_compliant(tmp_path):
    """All actions allowed -> COMPLIANT."""
    storage = _make_session(
        tmp_path,
        [
            ("search", {"query": "weather"}),
            ("reply", {"text": "sunny"}),
        ],
    )

    policy = Policy(allowed_actions=["search", "reply"])
    result = audit_shard(storage, "sessions", policy)

    assert result["status"] == "COMPLIANT"
    assert result["violation_count"] == 0
    assert result["actions_checked"] >= 2


# --- Forbidden action ---


def test_audit_forbidden_action(tmp_path):
    """Forbidden action -> VIOLATIONS_FOUND."""
    storage = _make_session(
        tmp_path,
        [
            ("search", {}),
            ("delete_files", {"path": "/etc"}),
        ],
    )

    policy = Policy(forbidden_actions=["delete_files"])
    result = audit_shard(storage, "sessions", policy)

    assert result["status"] == "VIOLATIONS_FOUND"
    assert result["violation_count"] >= 1
    violations = result["violations"]
    forbidden = [v for v in violations if v["rule"] == "forbidden_actions"]
    assert len(forbidden) >= 1
    assert forbidden[0]["action_name"] == "delete_files"


# --- Action not in allowed list ---


def test_audit_action_not_allowed(tmp_path):
    """Action not in whitelist -> VIOLATIONS_FOUND."""
    storage = _make_session(
        tmp_path,
        [
            ("search", {}),
            ("hack_server", {}),
        ],
    )

    policy = Policy(allowed_actions=["search", "reply"])
    result = audit_shard(storage, "sessions", policy)

    assert result["status"] == "VIOLATIONS_FOUND"
    not_allowed = [v for v in result["violations"] if v["rule"] == "allowed_actions"]
    assert len(not_allowed) >= 1
    assert not_allowed[0]["action_name"] == "hack_server"


# --- Source not allowed ---


def test_audit_source_not_allowed(tmp_path):
    """Session source not in allowed list -> violation."""
    storage = _make_session(tmp_path, [("search", {})], source="unauthorized_bot")

    policy = Policy(allowed_sources=["test", "openclaw"])
    result = audit_shard(storage, "sessions", policy)

    assert result["status"] == "VIOLATIONS_FOUND"
    source_violations = [
        v for v in result["violations"] if v["rule"] == "allowed_sources"
    ]
    assert len(source_violations) >= 1


# --- Max actions per session ---


def test_audit_max_actions_exceeded(tmp_path):
    """Too many actions in one session -> violation."""
    actions = [(f"action_{i}", {}) for i in range(5)]
    storage = _make_session(tmp_path, actions)

    policy = Policy(max_actions_per_session=3)
    result = audit_shard(storage, "sessions", policy)

    assert result["status"] == "VIOLATIONS_FOUND"
    max_violations = [
        v for v in result["violations"] if v["rule"] == "max_actions_per_session"
    ]
    assert len(max_violations) >= 1


# --- Permissive policy ---


def test_audit_no_restrictions(tmp_path):
    """Empty policy (no restrictions) -> always COMPLIANT."""
    storage = _make_session(
        tmp_path,
        [
            ("anything", {}),
            ("whatever", {}),
        ],
    )

    policy = Policy()
    result = audit_shard(storage, "sessions", policy)

    assert result["status"] == "COMPLIANT"
    assert result["violation_count"] == 0


# --- Forbidden takes precedence over allowed ---


def test_forbidden_overrides_allowed(tmp_path):
    """Action in both allowed and forbidden -> forbidden wins."""
    storage = _make_session(tmp_path, [("search", {})])

    policy = Policy(
        allowed_actions=["search", "reply"],
        forbidden_actions=["search"],
    )
    result = audit_shard(storage, "sessions", policy)

    assert result["status"] == "VIOLATIONS_FOUND"
    assert any(v["rule"] == "forbidden_actions" for v in result["violations"])


# --- audit_all ---


def test_audit_all(tmp_path):
    """audit_all checks all shards."""
    storage = Storage(data_dir=str(tmp_path))

    for shard in ["sessions", "custom"]:
        entry = Entry(
            id=str(uuid4()),
            timestamp=datetime.utcnow(),
            session_id="test",
            source="test",
            content="{}",
            shard=shard,
            hash="",
            prev_hash=None,
            metadata={
                "event_type": "action_intent",
                "action_name": "search",
                "intent_id": str(uuid4()),
            },
            version="v2.0",
        )
        storage.append(entry)

    policy = Policy(allowed_shards=["sessions"])
    results = audit_all(storage, policy)

    assert len(results) >= 2
    statuses = {r["shard_id"]: r["status"] for r in results}
    assert statuses.get("sessions") == "COMPLIANT"
    assert statuses.get("custom") == "VIOLATIONS_FOUND"


# --- Empty shard ---


def test_audit_empty_shard(tmp_path):
    """Empty shard -> COMPLIANT with 0 entries."""
    storage = Storage(data_dir=str(tmp_path))
    policy = Policy(allowed_actions=["search"])
    result = audit_shard(storage, "nonexistent", policy)

    assert result["status"] == "COMPLIANT"
    assert result["total_entries"] == 0
    assert result["violation_count"] == 0
