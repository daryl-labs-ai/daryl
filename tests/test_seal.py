"""Tests for Shard Sealing (P5)."""

import json
from datetime import datetime
from uuid import uuid4

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.seal import (
    SealRecord,
    SealRegistry,
    list_sealed_shards,
    seal_shard,
    verify_seal,
    verify_seal_against_storage,
)


def _make_entry(shard: str, content: str = "x"):
    return Entry(
        id=str(uuid4()),
        timestamp=datetime.utcnow(),
        session_id="seal_test",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


def test_seal_shard_creates_record(tmp_path):
    """Seal writes to registry."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    for i in range(3):
        storage.append(_make_entry("s1", f"e{i}"))
    registry = SealRegistry(str(tmp_path / "seals"))
    record = seal_shard(storage, "s1", registry)
    assert record.shard_id == "s1"
    assert record.entry_count == 3
    assert len(record.seal_hash) == 64
    assert registry.is_sealed("s1")


def test_seal_shard_captures_first_last_hash(tmp_path):
    """Correct boundary hashes."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("s2", "a"))
    storage.append(_make_entry("s2", "b"))
    registry = SealRegistry(str(tmp_path / "seals"))
    record = seal_shard(storage, "s2", registry)
    entries = list(reversed(storage.read("s2", limit=10)))
    assert record.first_hash == entries[0].hash
    assert record.last_hash == entries[-1].hash


def test_seal_shard_captures_timestamps(tmp_path):
    """First and last timestamps."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("s3", "x"))
    registry = SealRegistry(str(tmp_path / "seals"))
    record = seal_shard(storage, "s3", registry)
    assert record.first_timestamp
    assert record.last_timestamp
    assert record.seal_timestamp


def test_seal_hash_deterministic(tmp_path):
    """Recomputed seal hash matches stored hash (deterministic)."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("s4", "same"))
    registry = SealRegistry(str(tmp_path / "seals"))
    record = seal_shard(storage, "s4", registry)
    out = verify_seal(registry, "s4")
    assert out["status"] == "VALID"
    assert record.seal_hash


def test_seal_shard_refuses_corrupted(tmp_path):
    """Tampered shard (invalid hash) raises ValueError."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("corrupt", "e0"))
    shard_dir = tmp_path / "data" / "shards" / "corrupt"
    segs = list(shard_dir.glob("*.jsonl"))
    assert segs
    content = segs[0].read_text()
    lines = [ln for ln in content.strip().split("\n") if ln.strip()]
    obj = json.loads(lines[0])
    obj["hash"] = "tampered_hash"
    lines[0] = json.dumps(obj, ensure_ascii=False)
    segs[0].write_text("\n".join(lines) + "\n")
    registry = SealRegistry(str(tmp_path / "seals"))
    with pytest.raises(ValueError, match="corrupted"):
        seal_shard(storage, "corrupt", registry)


def test_seal_shard_empty_shard(tmp_path):
    """Empty shard raises ValueError."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    registry = SealRegistry(str(tmp_path / "seals"))
    with pytest.raises(ValueError, match="empty"):
        seal_shard(storage, "nonexistent", registry)


def test_seal_with_archive_path(tmp_path):
    """archived_path is set in record."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("arch", "x"))
    registry = SealRegistry(str(tmp_path / "seals"))
    archive_dir = tmp_path / "archive"
    record = seal_shard(storage, "arch", registry, archive_path=str(archive_dir))
    assert record.archived_path is not None
    assert "arch" in record.archived_path
    assert archive_dir.exists()
    assert any(archive_dir.glob("*.sealed.jsonl.gz"))


def test_verify_seal_valid(tmp_path):
    """Recomputed hash matches = VALID."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("v1", "x"))
    registry = SealRegistry(str(tmp_path / "seals"))
    seal_shard(storage, "v1", registry)
    out = verify_seal(registry, "v1")
    assert out["status"] == "VALID"
    assert out["entry_count"] == 1


def test_verify_seal_tampered(tmp_path):
    """Modified seal record = HASH_MISMATCH."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("v2", "x"))
    registry = SealRegistry(str(tmp_path / "seals"))
    seal_shard(storage, "v2", registry)
    with open(registry.registry_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    rec = json.loads(lines[-1])
    rec["entry_count"] = 999
    with open(registry.registry_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    out = verify_seal(registry, "v2")
    assert out["status"] == "HASH_MISMATCH"


def test_verify_seal_not_sealed(tmp_path):
    """Unknown shard = NOT_SEALED."""
    registry = SealRegistry(str(tmp_path / "seals"))
    out = verify_seal(registry, "unknown")
    assert out["status"] == "NOT_SEALED"


def test_verify_against_storage_matches(tmp_path):
    """Shard unchanged since seal = MATCHES."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("m1", "a"))
    registry = SealRegistry(str(tmp_path / "seals"))
    seal_shard(storage, "m1", registry)
    out = verify_seal_against_storage(storage, registry, "m1")
    assert out["status"] == "MATCHES"
    assert out["seal_entries"] == out["current_entries"] == 1


def test_verify_against_storage_diverged(tmp_path):
    """Entries added after seal = DIVERGED."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("d1", "a"))
    registry = SealRegistry(str(tmp_path / "seals"))
    seal_shard(storage, "d1", registry)
    storage.append(_make_entry("d1", "b"))
    out = verify_seal_against_storage(storage, registry, "d1")
    assert out["status"] == "DIVERGED"
    assert out["current_entries"] == 2
    assert out["seal_entries"] == 1


def test_verify_against_storage_gone(tmp_path):
    """Shard deleted after seal = SHARD_GONE."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("g1", "a"))
    registry = SealRegistry(str(tmp_path / "seals"))
    seal_shard(storage, "g1", registry)
    for f in (tmp_path / "data" / "shards" / "g1").glob("*.jsonl"):
        f.unlink()
    for f in (tmp_path / "data" / "integrity").glob("g1*"):
        f.unlink()
    out = verify_seal_against_storage(storage, registry, "g1")
    assert out["status"] == "SHARD_GONE"
    assert out["current_entries"] == 0


def test_list_sealed_shards(tmp_path):
    """Returns all sealed shards."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("l1", "a"))
    storage.append(_make_entry("l2", "b"))
    registry = SealRegistry(str(tmp_path / "seals"))
    seal_shard(storage, "l1", registry)
    seal_shard(storage, "l2", registry)
    items = list_sealed_shards(registry)
    assert len(items) == 2
    shard_ids = {s["shard_id"] for s in items}
    assert "l1" in shard_ids and "l2" in shard_ids


def test_seal_registry_empty(tmp_path):
    """Empty registry returns empty list."""
    registry = SealRegistry(str(tmp_path / "seals"))
    assert registry.read_all() == []
    assert list_sealed_shards(registry) == []


def test_seal_record_to_from_dict(tmp_path):
    """Serialization round-trip."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    storage.append(_make_entry("r1", "a"))
    registry = SealRegistry(str(tmp_path / "seals"))
    record = seal_shard(storage, "r1", registry)
    d = record.to_dict()
    r2 = SealRecord.from_dict(d)
    assert r2.shard_id == record.shard_id
    assert r2.entry_count == record.entry_count
    assert r2.seal_hash == record.seal_hash


def test_multiple_seals_different_shards(tmp_path):
    """Seal 3 shards, verify all."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    registry = SealRegistry(str(tmp_path / "seals"))
    for name in ["a", "b", "c"]:
        storage.append(_make_entry(name, name))
        seal_shard(storage, name, registry)
    assert len(registry.read_all()) == 3
    for name in ["a", "b", "c"]:
        out = verify_seal(registry, name)
        assert out["status"] == "VALID"
