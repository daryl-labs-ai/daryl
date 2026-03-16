"""
Test K-3 fix: metadata updates are now inside the shard lock.
Concurrent appends (threads) should produce correct entry_count.
"""

import threading
import uuid
from datetime import datetime, timezone

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.verify import verify_shard


def _make_entry(content: str, shard: str = "k3_test") -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="k3_test",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


class TestK3MetadataRace:
    def test_concurrent_metadata_consistency(self, tmp_path):
        """After concurrent appends, entry_count in metadata matches actual count."""
        storage = Storage(data_dir=str(tmp_path))
        n_threads = 4
        n_per_thread = 50
        total_expected = n_threads * n_per_thread

        def append_batch(tid):
            for i in range(n_per_thread):
                storage.append(_make_entry(f"t{tid}_e{i}"))

        threads = [threading.Thread(target=append_batch, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        entries = storage.read("k3_test", limit=300)
        assert len(entries) == total_expected

        meta = storage._get_shard_metadata("k3_test")
        assert meta.entry_count == total_expected, (
            f"Metadata entry_count {meta.entry_count} != actual {total_expected}"
        )

        result = verify_shard(storage, "k3_test")
        assert result["status"] == "OK"
        assert result["verified"] == total_expected
        assert result["chain_breaks"] == 0

    def test_shard_lock_serializes_appends(self, tmp_path):
        """Verify that the shard lock properly serializes appends (no lost writes)."""
        storage = Storage(data_dir=str(tmp_path))
        n_appends = 100

        def do_append(idx):
            storage.append(_make_entry(f"serial_{idx}"))

        threads = [threading.Thread(target=do_append, args=(i,)) for i in range(n_appends)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        entries = storage.read("k3_test", limit=200)
        assert len(entries) == n_appends

        result = verify_shard(storage, "k3_test")
        assert result["status"] == "OK"
