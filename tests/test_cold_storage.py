"""Tests for DSM Cold Storage — archive and restore sealed shards."""

import json
from datetime import datetime, timezone

import pytest

from dsm.cold_storage import ColdStorage, LocalBackend, ArchiveResult
from dsm.core.models import Entry
from dsm.core.storage import Storage


@pytest.fixture
def tmp_storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


@pytest.fixture
def backend(tmp_path):
    return LocalBackend(str(tmp_path / "archive"))


@pytest.fixture
def cold(backend):
    return ColdStorage(backend)


def _write_entries(storage, shard_id, n=5):
    """Write n entries to a shard."""
    for i in range(n):
        entry = Entry(
            id=f"e{i}",
            timestamp=datetime.now(timezone.utc),
            session_id="s1",
            source="agent1",
            content=json.dumps({"value": i}),
            shard=shard_id,
            hash="",
            prev_hash=None,
            metadata={"event_type": "test"},
            version="v2.0",
        )
        storage.append(entry)


class TestLocalBackend:
    def test_write_and_read(self, backend):
        backend.write("shard_1", b"hello world")
        data = backend.read("shard_1")
        assert data == b"hello world"

    def test_read_nonexistent(self, backend):
        assert backend.read("nope") is None

    def test_exists(self, backend):
        assert not backend.exists("s1")
        backend.write("s1", b"data")
        assert backend.exists("s1")

    def test_list_shards(self, backend):
        backend.write("shard_a", b"a")
        backend.write("shard_b", b"b")
        shards = backend.list_shards()
        assert len(shards) == 2

    def test_delete(self, backend):
        backend.write("del_me", b"data")
        assert backend.exists("del_me")
        assert backend.delete("del_me")
        assert not backend.exists("del_me")

    def test_delete_nonexistent(self, backend):
        assert not backend.delete("nope")

    def test_colon_in_shard_name(self, backend):
        """Shard names with : should work (sanitized to _)."""
        backend.write("collective:main", b"data")
        assert backend.exists("collective:main")
        assert backend.read("collective:main") == b"data"


class TestColdStorageExport:
    def test_export_shard(self, tmp_storage, cold):
        _write_entries(tmp_storage, "test_shard", n=5)
        result = cold.export(tmp_storage, "test_shard")
        assert result.ok
        assert result.entry_count == 5
        assert result.size_bytes > 0
        assert result.final_hash != ""

    def test_export_empty_shard(self, tmp_storage, cold):
        result = cold.export(tmp_storage, "empty")
        assert not result.ok
        assert "empty" in result.error

    def test_export_with_verification(self, tmp_storage, cold):
        _write_entries(tmp_storage, "verified", n=3)
        result = cold.export(tmp_storage, "verified", verify_first=True)
        assert result.ok

    def test_export_without_verification(self, tmp_storage, cold):
        _write_entries(tmp_storage, "unverified", n=3)
        result = cold.export(tmp_storage, "unverified", verify_first=False)
        assert result.ok


class TestColdStorageVerify:
    def test_verify_valid_archive(self, tmp_storage, cold):
        _write_entries(tmp_storage, "vfy", n=3)
        cold.export(tmp_storage, "vfy")
        result = cold.verify("vfy")
        assert result["ok"]
        assert result["entry_count"] == 3

    def test_verify_nonexistent(self, cold):
        result = cold.verify("nope")
        assert not result["ok"]
        assert "not found" in result["error"]

    def test_verify_corrupt_archive(self, backend):
        """Tampered archive should fail verification."""
        cold = ColdStorage(backend)
        # Write valid data then tamper
        backend.write("tampered", b'{"archive_hash":"wrong","entries":[]}')
        result = cold.verify("tampered")
        assert not result["ok"]


class TestColdStorageRestore:
    def test_export_and_restore(self, tmp_path):
        """Full round-trip: export from storage A, restore to storage B."""
        storage_a = Storage(data_dir=str(tmp_path / "a"))
        storage_b = Storage(data_dir=str(tmp_path / "b"))
        backend = LocalBackend(str(tmp_path / "archive"))
        cold = ColdStorage(backend)

        _write_entries(storage_a, "roundtrip", n=5)
        export_result = cold.export(storage_a, "roundtrip")
        assert export_result.ok

        restore_result = cold.restore(storage_b, "roundtrip")
        assert restore_result["ok"]
        assert restore_result["restored"] == 5

        # Verify restored entries
        entries = storage_b.read("roundtrip", limit=100)
        assert len(entries) == 5

    def test_restore_nonexistent(self, cold, tmp_storage):
        result = cold.restore(tmp_storage, "nope")
        assert not result["ok"]

    def test_list_archived(self, tmp_storage, cold):
        _write_entries(tmp_storage, "list_a", n=2)
        _write_entries(tmp_storage, "list_b", n=2)
        cold.export(tmp_storage, "list_a")
        cold.export(tmp_storage, "list_b")
        archived = cold.list_archived()
        assert len(archived) == 2
