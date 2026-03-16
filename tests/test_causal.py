"""Tests for P10 — cross-agent causal binding."""
import pytest
from dsm.causal import (
    create_dispatch_hash,
    create_routing_hash,
    DispatchRecord,
    verify_dispatch_hash,
    verify_causal_chain,
)


def test_create_dispatch_hash_deterministic():
    """Same inputs produce same hash."""
    h1 = create_dispatch_hash("abc123", {"task": "search"}, "2026-01-01T00:00:00Z")
    h2 = create_dispatch_hash("abc123", {"task": "search"}, "2026-01-01T00:00:00Z")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_create_dispatch_hash_differs_on_different_input():
    """Different inputs produce different hashes."""
    h1 = create_dispatch_hash("abc123", {"task": "search"}, "2026-01-01T00:00:00Z")
    h2 = create_dispatch_hash("xyz789", {"task": "search"}, "2026-01-01T00:00:00Z")
    assert h1 != h2


def test_create_routing_hash():
    """Routing hash should be deterministic."""
    rh1 = create_routing_hash("dispatch_abc", "router_1", "2026-01-01T00:00:00Z")
    rh2 = create_routing_hash("dispatch_abc", "router_1", "2026-01-01T00:00:00Z")
    assert rh1 == rh2
    assert len(rh1) == 64


def test_dispatch_record_round_trip():
    """DispatchRecord should survive to_dict/from_dict."""
    rec = DispatchRecord(
        dispatch_hash="d" * 64,
        dispatcher_agent_id="agent_a",
        dispatcher_entry_hash="e" * 64,
        target_agent_id="agent_b",
        task_params={"action": "compute"},
        timestamp="2026-01-01T00:00:00Z",
    )
    d = rec.to_dict()
    rec2 = DispatchRecord.from_dict(d)
    assert rec2.dispatch_hash == rec.dispatch_hash
    assert rec2.task_params == rec.task_params


def test_verify_dispatch_hash_valid():
    """Valid dispatch record should verify."""
    ts = "2026-01-01T00:00:00Z"
    params = {"task": "search"}
    dh = create_dispatch_hash("entry_hash_abc", params, ts)
    rec = DispatchRecord(
        dispatch_hash=dh,
        dispatcher_agent_id="agent_a",
        dispatcher_entry_hash="entry_hash_abc",
        target_agent_id="agent_b",
        task_params=params,
        timestamp=ts,
    )
    result = verify_dispatch_hash(rec)
    assert result["status"] == "VALID"


def test_verify_dispatch_hash_tampered():
    """Tampered dispatch hash should fail."""
    rec = DispatchRecord(
        dispatch_hash="tampered_hash",
        dispatcher_agent_id="agent_a",
        dispatcher_entry_hash="entry_hash_abc",
        target_agent_id="agent_b",
        task_params={"task": "search"},
        timestamp="2026-01-01T00:00:00Z",
    )
    result = verify_dispatch_hash(rec)
    assert result["status"] == "HASH_MISMATCH"


def test_verify_causal_chain_valid():
    """Full causal chain should verify when all parts match."""
    ts = "2026-01-01T00:00:00Z"
    params = {"task": "search"}
    dh = create_dispatch_hash("entry_abc", params, ts)
    rec = DispatchRecord(
        dispatch_hash=dh,
        dispatcher_agent_id="a",
        dispatcher_entry_hash="entry_abc",
        target_agent_id="b",
        task_params=params,
        timestamp=ts,
    )
    result = verify_causal_chain(rec, intent_hash="intent_xyz", receipt_dispatch_hash=dh)
    assert result["status"] == "VALID"


def test_verify_causal_chain_broken_no_dispatch_in_receipt():
    """Missing dispatch_hash in receipt should break the chain."""
    ts = "2026-01-01T00:00:00Z"
    dh = create_dispatch_hash("entry_abc", {"task": "x"}, ts)
    rec = DispatchRecord(
        dispatch_hash=dh,
        dispatcher_agent_id="a",
        dispatcher_entry_hash="entry_abc",
        target_agent_id="b",
        task_params={"task": "x"},
        timestamp=ts,
    )
    result = verify_causal_chain(rec, intent_hash="intent_xyz", receipt_dispatch_hash=None)
    assert result["status"] == "BROKEN"
    assert "no dispatch_hash" in result["details"][0]


def test_verify_causal_chain_broken_mismatch():
    """Mismatched dispatch_hash in receipt should break the chain."""
    ts = "2026-01-01T00:00:00Z"
    dh = create_dispatch_hash("entry_abc", {"task": "x"}, ts)
    rec = DispatchRecord(
        dispatch_hash=dh,
        dispatcher_agent_id="a",
        dispatcher_entry_hash="entry_abc",
        target_agent_id="b",
        task_params={"task": "x"},
        timestamp=ts,
    )
    result = verify_causal_chain(rec, intent_hash="intent_xyz", receipt_dispatch_hash="wrong_hash")
    assert result["status"] == "BROKEN"


def test_receipt_with_dispatch_hash():
    """TaskReceipt should accept and round-trip dispatch_hash."""
    from dsm.exchange import TaskReceipt

    receipt = TaskReceipt(
        receipt_id="r1",
        issuer_agent_id="agent_b",
        task_description="completed task",
        entry_id="e1",
        entry_hash="h1",
        shard_id="s1",
        shard_tip_hash="t1",
        shard_entry_count=1,
        timestamp="2026-01-01T00:00:00Z",
        receipt_hash="rh1",
        dispatch_hash="dh_abc",
        routing_hash="rh_xyz",
    )
    d = receipt.to_dict()
    assert d["dispatch_hash"] == "dh_abc"
    assert d["routing_hash"] == "rh_xyz"
    r2 = TaskReceipt.from_dict(d)
    assert r2.dispatch_hash == "dh_abc"
    assert r2.routing_hash == "rh_xyz"
