"""Tests for P8 — Policy Adapter & Audit Reports."""

import json
import os
import tempfile
from datetime import datetime
from uuid import uuid4

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.audit import Policy
from dsm.policy_adapter import (
    InkogAdapter,
    OPAAdapter,
    PolicyAdapter,
    AuditReport,
    register_adapter,
    get_adapter,
    list_adapters,
    auto_detect_adapter,
    generate_audit_report,
    load_and_audit,
    verify_report,
)


# ── Fixtures ─────────────────────────────────────────────────────

def _make_entry(session_id, action_name=None, source="agent_1", shard="sessions"):
    meta = {}
    if action_name:
        meta["event_type"] = "action_intent"
        meta["action_name"] = action_name
    else:
        meta["event_type"] = "session_start"
        meta["source"] = source
    return Entry(
        id=str(uuid4()),
        timestamp=datetime.utcnow(),
        session_id=session_id,
        source=source,
        content=f"action: {action_name or 'start'}",
        shard=shard,
        hash="",
        prev_hash=None,
        metadata=meta,
        version="v2.0",
    )


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def storage_with_actions(tmp_dir):
    storage = Storage(data_dir=tmp_dir)
    storage.append(_make_entry("s1", source="agent_1"))
    storage.append(_make_entry("s1", "search"))
    storage.append(_make_entry("s1", "analyze"))
    storage.append(_make_entry("s1", "delete_all"))  # forbidden action
    return storage


@pytest.fixture
def inkog_policy_file(tmp_dir):
    policy = {
        "policy_id": "inkog-test-001",
        "version": "1.0",
        "engine": "inkog",
        "rules": {
            "allow": ["search", "analyze", "reply"],
            "deny": ["delete_all", "drop_table"],
            "sources": ["agent_1", "agent_2"],
            "limits": {
                "max_actions_per_session": 50,
                "shards": ["sessions"]
            }
        },
        "metadata": {
            "author": "test",
            "created_at": "2026-03-16",
            "description": "Test Inkog policy"
        }
    }
    path = os.path.join(tmp_dir, "inkog_policy.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(policy, f)
    return path


@pytest.fixture
def opa_policy_file(tmp_dir):
    policy = {
        "engine": "opa",
        "package": "dsm.authz",
        "rules": {
            "allow_actions": ["search", "analyze"],
            "deny_actions": ["delete_all"],
            "allow_sources": ["agent_1"],
            "max_actions": 100,
            "allow_shards": ["sessions"]
        }
    }
    path = os.path.join(tmp_dir, "opa_policy.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(policy, f)
    return path


# ── Inkog Adapter ────────────────────────────────────────────────

def test_inkog_adapter_name():
    adapter = InkogAdapter()
    assert adapter.name() == "inkog"


def test_inkog_load_from_file(inkog_policy_file):
    adapter = InkogAdapter()
    policy = adapter.load(inkog_policy_file)
    assert policy.allowed_actions == ["search", "analyze", "reply"]
    assert policy.forbidden_actions == ["delete_all", "drop_table"]
    assert policy.allowed_sources == ["agent_1", "agent_2"]
    assert policy.max_actions_per_session == 50
    assert policy.allowed_shards == ["sessions"]


def test_inkog_load_from_json_string():
    adapter = InkogAdapter()
    source = json.dumps({
        "engine": "inkog",
        "rules": {"allow": ["search"], "deny": [], "limits": {}}
    })
    policy = adapter.load(source)
    assert policy.allowed_actions == ["search"]


def test_inkog_validate_source(inkog_policy_file):
    adapter = InkogAdapter()
    assert adapter.validate_source(inkog_policy_file) is True
    assert adapter.validate_source('{"engine": "opa"}') is False
    assert adapter.validate_source("not-a-file") is False


def test_inkog_rejects_wrong_engine():
    adapter = InkogAdapter()
    with pytest.raises(ValueError, match="Not an Inkog policy"):
        adapter.load(json.dumps({"engine": "opa", "rules": {}}))


# ── OPA Adapter ──────────────────────────────────────────────────

def test_opa_adapter_name():
    adapter = OPAAdapter()
    assert adapter.name() == "opa"


def test_opa_load_from_file(opa_policy_file):
    adapter = OPAAdapter()
    policy = adapter.load(opa_policy_file)
    assert policy.allowed_actions == ["search", "analyze"]
    assert policy.forbidden_actions == ["delete_all"]
    assert policy.max_actions_per_session == 100


def test_opa_validate_source(opa_policy_file, inkog_policy_file):
    adapter = OPAAdapter()
    assert adapter.validate_source(opa_policy_file) is True
    assert adapter.validate_source(inkog_policy_file) is False


# ── Adapter Registry ─────────────────────────────────────────────

def test_list_adapters():
    adapters = list_adapters()
    assert "inkog" in adapters
    assert "opa" in adapters


def test_get_adapter():
    adapter = get_adapter("inkog")
    assert adapter is not None
    assert adapter.name() == "inkog"


def test_get_adapter_unknown():
    assert get_adapter("nonexistent") is None


def test_auto_detect_inkog(inkog_policy_file):
    adapter = auto_detect_adapter(inkog_policy_file)
    assert adapter is not None
    assert adapter.name() == "inkog"


def test_auto_detect_opa(opa_policy_file):
    adapter = auto_detect_adapter(opa_policy_file)
    assert adapter is not None
    assert adapter.name() == "opa"


def test_auto_detect_fails_on_unknown():
    assert auto_detect_adapter("not-a-valid-policy") is None


# ── Audit Reports ────────────────────────────────────────────────

def test_generate_report_compliant(tmp_dir):
    storage = Storage(data_dir=tmp_dir)
    storage.append(_make_entry("s1", source="agent_1"))
    storage.append(_make_entry("s1", "search"))

    policy = Policy(allowed_actions=["search", "analyze"], forbidden_actions=[])
    report = generate_audit_report(storage, "agent_1", policy)

    assert report.summary["status"] == "COMPLIANT"
    assert report.summary["total_violations"] == 0
    assert report.report_hash


def test_generate_report_with_violations(storage_with_actions):
    policy = Policy(
        allowed_actions=["search", "analyze"],
        forbidden_actions=["delete_all"],
    )
    report = generate_audit_report(storage_with_actions, "agent_1", policy)

    assert report.summary["status"] == "VIOLATIONS_FOUND"
    assert report.summary["total_violations"] >= 1


def test_report_to_from_dict(storage_with_actions):
    policy = Policy(allowed_actions=["search", "analyze"])
    report = generate_audit_report(storage_with_actions, "agent_1", policy)

    d = report.to_dict()
    report2 = AuditReport.from_dict(d)
    assert report2.report_id == report.report_id
    assert report2.report_hash == report.report_hash


def test_report_to_from_json(storage_with_actions):
    policy = Policy()
    report = generate_audit_report(storage_with_actions, "agent_1", policy)

    j = report.to_json()
    report2 = AuditReport.from_json(j)
    assert report2.report_id == report.report_id


def test_verify_report_intact(storage_with_actions):
    policy = Policy()
    report = generate_audit_report(storage_with_actions, "agent_1", policy)
    result = verify_report(report)
    assert result["status"] == "INTACT"


def test_verify_report_tampered(storage_with_actions):
    policy = Policy()
    report = generate_audit_report(storage_with_actions, "agent_1", policy)
    report.agent_id = "tampered_agent"
    result = verify_report(report)
    assert result["status"] == "TAMPERED"


def test_report_specific_shards(tmp_dir):
    storage = Storage(data_dir=tmp_dir)
    storage.append(_make_entry("s1", "search", shard="sessions"))
    storage.append(_make_entry("s2", "analyze", shard="tasks"))

    policy = Policy()
    report = generate_audit_report(storage, "agent_1", policy, shard_ids=["sessions"])
    assert report.summary["shards_audited"] == 1


# ── Load and Audit (end-to-end) ──────────────────────────────────

def test_load_and_audit_inkog(storage_with_actions, inkog_policy_file):
    report = load_and_audit(
        storage_with_actions,
        agent_id="agent_1",
        policy_source=inkog_policy_file,
    )
    assert report.policy_engine == "inkog"
    assert report.summary["status"] == "VIOLATIONS_FOUND"  # delete_all is forbidden


def test_load_and_audit_opa(storage_with_actions, opa_policy_file):
    report = load_and_audit(
        storage_with_actions,
        agent_id="agent_1",
        policy_source=opa_policy_file,
        adapter_name="opa",
    )
    assert report.policy_engine == "opa"


def test_load_and_audit_unknown_adapter(storage_with_actions):
    with pytest.raises(ValueError, match="Unknown adapter"):
        load_and_audit(
            storage_with_actions,
            agent_id="agent_1",
            policy_source="{}",
            adapter_name="nonexistent",
        )


def test_load_and_audit_no_adapter_found(storage_with_actions):
    with pytest.raises(ValueError, match="No adapter"):
        load_and_audit(
            storage_with_actions,
            agent_id="agent_1",
            policy_source='{"engine": "unknown"}',
        )


# ── Custom Adapter Registration ──────────────────────────────────

def test_register_custom_adapter():
    class CustomAdapter(PolicyAdapter):
        def name(self):
            return "custom"

        def load(self, source):
            return Policy()

        def validate_source(self, source):
            return "custom" in source

    register_adapter(CustomAdapter())
    assert "custom" in list_adapters()
    assert get_adapter("custom") is not None
