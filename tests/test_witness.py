"""Tests for External Witness module."""

import json
from datetime import datetime
from uuid import uuid4

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.witness import ShardWitness


def _make_entry(shard, content="test"):
    return Entry(
        id=str(uuid4()),
        timestamp=datetime.utcnow(),
        session_id="witness_test",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


def test_capture_single_shard(tmp_path):
    """Capture witness for a shard with entries."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    for i in range(5):
        storage.append(_make_entry("test_shard", f"entry_{i}"))

    witness = ShardWitness(str(tmp_path / "witness"))
    record = witness.capture(storage, "test_shard")

    assert record is not None
    assert record["shard_id"] == "test_shard"
    assert record["entry_count"] == 5
    assert len(record["tip_hash"]) > 0
    assert len(record["witness_hash"]) == 64
    assert record["signed"] is False


def test_capture_with_key(tmp_path):
    """Capture with witness key marks record as signed."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("signed_shard"))

    witness = ShardWitness(str(tmp_path / "witness"), witness_key="secret123")
    record = witness.capture(storage, "signed_shard")

    assert record["signed"] is True


def test_capture_empty_shard_returns_none(tmp_path):
    """Empty shard produces no witness record."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    witness = ShardWitness(str(tmp_path / "witness"))
    record = witness.capture(storage, "nonexistent")
    assert record is None


def test_capture_all(tmp_path):
    """capture_all witnesses all shards."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("shard_a", "a"))
    storage.append(_make_entry("shard_b", "b"))

    witness = ShardWitness(str(tmp_path / "witness"))
    records = witness.capture_all(storage)

    shard_ids = {r["shard_id"] for r in records}
    assert "shard_a" in shard_ids
    assert "shard_b" in shard_ids


def test_read_log(tmp_path):
    """Witness log is readable after capture."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("log_test"))

    witness = ShardWitness(str(tmp_path / "witness"))
    witness.capture(storage, "log_test")

    log = witness.read_log()
    assert len(log) == 1
    assert log[0]["shard_id"] == "log_test"


def test_verify_record_valid(tmp_path):
    """Witness record hash validates correctly."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("verify_test"))

    witness = ShardWitness(str(tmp_path / "witness"), witness_key="mykey")
    record = witness.capture(storage, "verify_test")

    assert witness.verify_record(record) is True


def test_verify_record_tampered(tmp_path):
    """Tampered witness record fails verification."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("tamper_test"))

    witness = ShardWitness(str(tmp_path / "witness"), witness_key="mykey")
    record = witness.capture(storage, "tamper_test")

    record["entry_count"] = 999

    assert witness.verify_record(record) is False


def test_verify_shard_ok(tmp_path):
    """Shard matches witness -> status OK."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    for i in range(3):
        storage.append(_make_entry("ok_shard", f"e_{i}"))

    witness = ShardWitness(str(tmp_path / "witness"))
    witness.capture(storage, "ok_shard")

    result = witness.verify_shard_against_witness(storage, "ok_shard")
    assert result["status"] == "OK"
    assert result["witness_valid"] is True
    assert result["current_count"] == 3
    assert result["witnessed_count"] == 3


def test_verify_shard_after_append_ok(tmp_path):
    """Appending after witness -> still OK (append-only grows)."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    for i in range(3):
        storage.append(_make_entry("grow_shard", f"e_{i}"))

    witness = ShardWitness(str(tmp_path / "witness"))
    witness.capture(storage, "grow_shard")

    for i in range(2):
        storage.append(_make_entry("grow_shard", f"new_{i}"))

    result = witness.verify_shard_against_witness(storage, "grow_shard")
    assert result["status"] == "OK"
    assert result["current_count"] == 5
    assert result["witnessed_count"] == 3


def test_verify_shard_no_witness(tmp_path):
    """Shard with no witness record -> NO_WITNESS."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("unwatched"))

    witness = ShardWitness(str(tmp_path / "witness"))
    result = witness.verify_shard_against_witness(storage, "unwatched")
    assert result["status"] == "NO_WITNESS"


def test_verify_shard_diverged_after_tampering(tmp_path):
    """Tampering with shard after witness (entry count decreased) -> DIVERGED."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    for i in range(3):
        storage.append(_make_entry("tamper_shard", f"e_{i}"))

    witness = ShardWitness(str(tmp_path / "witness"))
    witness.capture(storage, "tamper_shard")

    # Tamper: remove one line from segment so entry count drops
    shard_dir = tmp_path / "data" / "shards" / "tamper_shard"
    segments = list(shard_dir.glob("*.jsonl"))
    assert segments, "expected at least one segment"
    content = segments[0].read_text()
    lines = [ln for ln in content.strip().split("\n") if ln.strip()]
    assert len(lines) >= 1
    lines.pop()
    segments[0].write_text("\n".join(lines) + "\n")

    result = witness.verify_shard_against_witness(storage, "tamper_shard")
    assert result["status"] == "DIVERGED"
