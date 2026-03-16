"""Tests for Cross-Agent Trust Receipts (P6) — dsm.exchange."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.exchange import (
    TaskReceipt,
    issue_receipt,
    list_received_receipts,
    store_external_receipt,
    verify_receipt,
    verify_receipt_against_storage,
)


def _make_entry(shard: str, content: str = "work"):
    return Entry(
        id=str(uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="test",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


def test_issue_receipt_creates_valid_receipt(tmp_path):
    """Receipt has all fields populated."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("tasks", "done something")
    storage.append(e)
    receipt = issue_receipt(storage, "agent_b", e.id, "tasks", "Task X")
    assert receipt.receipt_id
    assert receipt.issuer_agent_id == "agent_b"
    assert receipt.task_description == "Task X"
    assert receipt.entry_id == e.id
    assert receipt.entry_hash
    assert receipt.shard_id == "tasks"
    assert receipt.shard_tip_hash
    assert receipt.shard_entry_count == 1
    assert receipt.timestamp
    assert receipt.receipt_hash
    assert len(receipt.receipt_hash) == 64


def test_receipt_hash_deterministic(tmp_path):
    """Same entry = same entry_hash, shard_tip_hash, shard_entry_count (receipt_hash includes timestamp)."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("s1", "same")
    storage.append(e)
    r1 = issue_receipt(storage, "b", e.id, "s1", "T")
    r2 = issue_receipt(storage, "b", e.id, "s1", "T")
    assert r1.entry_hash == r2.entry_hash
    assert r1.shard_tip_hash == r2.shard_tip_hash
    assert r1.shard_entry_count == r2.shard_entry_count
    assert r1.issuer_agent_id == r2.issuer_agent_id
    assert r1.entry_id == r2.entry_id


def test_receipt_to_from_dict(tmp_path):
    """Round-trip serialization via dict."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("s1", "x")
    storage.append(e)
    receipt = issue_receipt(storage, "b", e.id, "s1", "desc")
    d = receipt.to_dict()
    back = TaskReceipt.from_dict(d)
    assert back.receipt_id == receipt.receipt_id
    assert back.issuer_agent_id == receipt.issuer_agent_id
    assert back.receipt_hash == receipt.receipt_hash


def test_receipt_to_from_json(tmp_path):
    """JSON round-trip (portable format)."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("s1", "y")
    storage.append(e)
    receipt = issue_receipt(storage, "b", e.id, "s1", "desc")
    js = receipt.to_json()
    back = TaskReceipt.from_json(js)
    assert back.receipt_id == receipt.receipt_id
    assert back.entry_hash == receipt.entry_hash


def test_verify_receipt_intact(tmp_path):
    """Unmodified receipt = INTACT."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("s1", "z")
    storage.append(e)
    receipt = issue_receipt(storage, "b", e.id, "s1", "task")
    result = verify_receipt(receipt)
    assert result["status"] == "INTACT"
    assert result["receipt_id"] == receipt.receipt_id
    assert result["issuer"] == "b"
    assert result["task"] == "task"


def test_verify_receipt_tampered(tmp_path):
    """Modified field = TAMPERED."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("s1", "z")
    storage.append(e)
    receipt = issue_receipt(storage, "b", e.id, "s1", "task")
    receipt.task_description = "tampered"
    result = verify_receipt(receipt)
    assert result["status"] == "TAMPERED"


def test_verify_against_storage_confirmed(tmp_path):
    """Entry exists and hash matches = CONFIRMED."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("s1", "work")
    storage.append(e)
    receipt = issue_receipt(storage, "b", e.id, "s1", "T")
    result = verify_receipt_against_storage(storage, receipt)
    assert result["status"] == "CONFIRMED"
    assert result["entry_found"] is True
    assert result["hash_matches"] is True


def test_verify_against_storage_entry_missing(tmp_path):
    """Entry not found in shard = ENTRY_MISSING (storage has shard but different entry)."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("s1", "x")
    storage.append(e)
    receipt = issue_receipt(storage, "b", e.id, "s1", "T")
    storage2 = Storage(data_dir=str(tmp_path / "other"))
    other = _make_entry("s1", "other entry")
    storage2.append(other)
    result = verify_receipt_against_storage(storage2, receipt)
    assert result["status"] == "ENTRY_MISSING"
    assert result["entry_found"] is False


def test_verify_against_storage_hash_mismatch(tmp_path):
    """Wrong hash = HASH_MISMATCH."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("s1", "x")
    storage.append(e)
    receipt = issue_receipt(storage, "b", e.id, "s1", "T")
    receipt.entry_hash = "a" * 64
    result = verify_receipt_against_storage(storage, receipt)
    assert result["status"] == "HASH_MISMATCH"
    assert result["entry_found"] is True
    assert result["hash_matches"] is False


def test_store_external_receipt(tmp_path):
    """Receipt stored in receiver's DSM."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("s1", "x")
    storage.append(e)
    receipt = issue_receipt(storage, "agent_b", e.id, "s1", "Task")
    entry = store_external_receipt(storage, receipt, "agent_a", shard_id="receipts")
    assert entry.id
    assert entry.shard == "receipts"
    assert entry.metadata.get("event_type") == "external_receipt"
    assert entry.metadata.get("receipt_id") == receipt.receipt_id
    assert TaskReceipt.from_json(entry.content).receipt_id == receipt.receipt_id


def test_list_received_receipts(tmp_path):
    """Lists stored receipts."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("s1", "x")
    storage.append(e)
    r1 = issue_receipt(storage, "b1", e.id, "s1", "T1")
    store_external_receipt(storage, r1, "agent_a", shard_id="receipts")
    entries = storage.read("receipts", limit=10)
    receipts = list_received_receipts(storage, shard_id="receipts")
    assert len(receipts) == 1
    assert receipts[0].receipt_id == r1.receipt_id
    assert receipts[0].issuer_agent_id == "b1"


def test_full_cross_agent_flow(tmp_path):
    """Agent A delegates to B, B issues receipt, A stores and verifies."""
    dir_b = tmp_path / "agent_b"
    dir_a = tmp_path / "agent_a"
    dir_b.mkdir()
    dir_a.mkdir()
    storage_b = Storage(data_dir=str(dir_b))
    storage_a = Storage(data_dir=str(dir_a))
    e = _make_entry("work", "B did the job")
    storage_b.append(e)
    receipt = issue_receipt(storage_b, "agent_b", e.id, "work", "Delegate task")
    assert verify_receipt(receipt)["status"] == "INTACT"
    stored = store_external_receipt(storage_a, receipt, "agent_a", shard_id="receipts")
    assert stored
    listed = list_received_receipts(storage_a, shard_id="receipts")
    assert len(listed) == 1
    assert listed[0].entry_id == e.id
    verify_a = verify_receipt_against_storage(storage_b, listed[0])
    assert verify_a["status"] == "CONFIRMED"


def test_receipt_works_with_different_storage(tmp_path):
    """Issue from storage1, verify against storage1 (simulating B's DSM)."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("shard1", "content")
    storage.append(e)
    receipt = issue_receipt(storage, "B", e.id, "shard1", "task")
    result = verify_receipt_against_storage(storage, receipt)
    assert result["status"] == "CONFIRMED"


def test_multiple_receipts(tmp_path):
    """Store 3 receipts, list returns all 3."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    receipts = []
    for i in range(3):
        e = _make_entry("s", f"work{i}")
        storage.append(e)
        r = issue_receipt(storage, f"agent_{i}", e.id, "s", f"Task {i}")
        store_external_receipt(storage, r, "agent_a", shard_id="receipts")
        receipts.append(r)
    listed = list_received_receipts(storage, shard_id="receipts")
    assert len(listed) == 3
    ids = {x.receipt_id for x in listed}
    assert ids == {r.receipt_id for r in receipts}


def test_receipt_with_empty_shard(tmp_path):
    """Issue from shard with single entry."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("single", "only one")
    storage.append(e)
    receipt = issue_receipt(storage, "b", e.id, "single", "Solo task")
    assert receipt.shard_entry_count == 1
    assert receipt.entry_hash == e.hash
    assert verify_receipt(receipt)["status"] == "INTACT"
    assert verify_receipt_against_storage(storage, receipt)["status"] == "CONFIRMED"


def test_verify_against_storage_shard_missing(tmp_path):
    """Shard missing in storage = SHARD_MISSING."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e = _make_entry("s1", "x")
    storage.append(e)
    receipt = issue_receipt(storage, "b", e.id, "s1", "T")
    storage_empty = Storage(data_dir=str(tmp_path / "empty"))
    storage_empty.append(_make_entry("other_shard", "y"))
    result = verify_receipt_against_storage(storage_empty, receipt)
    assert result["status"] == "SHARD_MISSING"
    assert result["entry_found"] is False


def test_issue_receipt_entry_not_found_raises(tmp_path):
    """issue_receipt raises ValueError when entry not in shard."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("s1", "x"))
    with pytest.raises(ValueError, match="not found"):
        issue_receipt(storage, "b", "nonexistent-id", "s1", "T")
