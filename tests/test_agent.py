"""Tests for DarylAgent SDK facade."""

import json

import pytest

from dsm.agent import DarylAgent


def test_start_end_session(tmp_path):
    """Basic lifecycle: start then end."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    agent.start()
    assert agent.graph.is_session_active()
    agent.end()
    assert not agent.graph.is_session_active()


def test_snapshot(tmp_path):
    """Snapshot is recorded."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    agent.start()
    out = agent.snapshot({"context": "current state"})
    agent.end()
    assert out is not None
    entries = agent.storage.read("sessions", limit=20)
    snapshots = [e for e in entries if e.metadata.get("event_type") == "snapshot"]
    assert len(snapshots) >= 1


def test_intend_confirm(tmp_path):
    """Full intent -> confirm cycle."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    agent.start()
    intent_id = agent.intend("call_api", {"url": "https://example.com"})
    assert intent_id is not None
    agent.confirm(intent_id, result={"status": 200}, success=True)
    agent.end()
    orphans = agent.orphaned_intents()
    assert len(orphans) == 0


def test_intend_confirm_with_raw_input(tmp_path):
    """Receipt is created from raw_input."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    agent.start()
    intent_id = agent.intend("call_api", {"url": "https://example.com"})
    assert intent_id is not None
    raw = '{"temperature": 25}'
    agent.confirm(intent_id, result={"parsed": "ok"}, success=True, raw_input=raw)
    agent.end()
    entries = agent.storage.read("sessions", limit=20)
    results = [e for e in entries if e.metadata.get("event_type") == "action_result"]
    assert len(results) == 1
    assert results[0].metadata.get("input_hash") is not None
    assert len(results[0].metadata["input_hash"]) == 64


def test_orphaned_intents_none(tmp_path):
    """No orphans after confirm."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    agent.start()
    intent_id = agent.intend("action_a", {})
    agent.confirm(intent_id, {"done": True})
    agent.end()
    assert len(agent.orphaned_intents()) == 0


def test_orphaned_intents_detected(tmp_path):
    """Intent without confirm = orphan."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    agent.start()
    agent.intend("risky_action", {})
    agent.end()
    orphans = agent.orphaned_intents()
    assert len(orphans) == 1
    assert orphans[0].metadata.get("action_name") == "risky_action"


def test_verify_integrity(tmp_path):
    """Hash chain passes after normal writes."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    agent.start()
    agent.snapshot({"x": 1})
    agent.end()
    result = agent.verify()
    results = result if isinstance(result, list) else [result]
    for r in results:
        if r.get("total_entries", 0) > 0:
            assert r.get("status") == "OK"


def test_check_coverage_full(tmp_path):
    """All entries indexed = FULLY_COVERED."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    agent.start()
    agent.snapshot({"a": 1})
    agent.end()
    entries = agent.storage.read("sessions", limit=1000)
    indexed_ids = {e.id for e in entries}
    out = agent.check_coverage(indexed_ids=indexed_ids)
    assert out["status"] == "FULLY_COVERED"
    assert out["missing_entries"] == 0


def test_check_coverage_gaps(tmp_path):
    """Missing entries = CRITICAL_GAPS or PARTIAL."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    agent.start()
    agent.snapshot({"a": 1})
    agent.end()
    entries = agent.storage.read("sessions", limit=1000)
    indexed_ids = {e.id for e in entries}
    if len(indexed_ids) >= 1:
        indexed_ids.pop()
    out = agent.check_coverage(indexed_ids=indexed_ids if indexed_ids else None)
    assert out["missing_entries"] >= 1
    assert out["status"] in ("CRITICAL_GAPS", "PARTIAL_COVERAGE", "NO_INDEX")


def test_witness_capture_and_verify(tmp_path):
    """Witness round-trip with witness_dir."""
    witness_dir = str(tmp_path / "witness_log")
    agent = DarylAgent(
        agent_id="test-agent",
        data_dir=str(tmp_path / "data"),
        witness_dir=witness_dir,
    )
    agent.start()
    agent.snapshot({"w": 1})
    agent.end()
    records = agent.witness_capture()
    assert isinstance(records, list)
    results = agent.witness_verify()
    assert isinstance(results, list)
    for r in results:
        assert "status" in r
        assert r["status"] in ("OK", "NO_WITNESS", "DIVERGED")


def test_witness_not_configured(tmp_path):
    """Raises ValueError if no witness_dir."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    with pytest.raises(ValueError, match="witness_dir"):
        agent.witness_capture()
    with pytest.raises(ValueError, match="witness_dir"):
        agent.witness_verify()


def test_audit_compliant(tmp_path):
    """Policy check passes."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    agent.start()
    intent_id = agent.intend("search", {"q": "x"})
    if intent_id:
        agent.confirm(intent_id, {"done": True})
    agent.end()
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps({"allowed_actions": ["search", "reply"]}))
    results = agent.audit(str(policy_file))
    for r in results:
        if r.get("shard_id") == "sessions" and r.get("actions_checked", 0) > 0:
            assert r["status"] == "COMPLIANT"


def test_audit_violation(tmp_path):
    """Forbidden action detected."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    agent.start()
    intent_id = agent.intend("delete_files", {"path": "/etc"})
    if intent_id:
        agent.confirm(intent_id, {"done": True})
    agent.end()
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps({"forbidden_actions": ["delete_files"]}))
    results = agent.audit(str(policy_file))
    violations = []
    for r in results:
        violations.extend(r.get("violations", []))
    forbidden = [v for v in violations if v.get("rule") == "forbidden_actions"]
    assert len(forbidden) >= 1


def test_no_crash_on_double_start(tmp_path):
    """Double start doesn't raise."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    agent.start()
    agent.start()
    agent.end()


def test_no_crash_on_end_without_start(tmp_path):
    """End without start doesn't raise."""
    agent = DarylAgent(agent_id="test-agent", data_dir=str(tmp_path))
    out = agent.end()
    assert out is None
