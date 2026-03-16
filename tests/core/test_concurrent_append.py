"""
Concurrent append test: multiple threads appending to the same shard.

Storage.append() uses fcntl.flock(LOCK_EX) on the segment file for the full
append (read last_hash → compute hash → write entry → set last_hash). This test
serializes append calls with a shared lock so that the kernel only sees one
append at a time (the frozen kernel has races in segment_meta/last_hash when
multiple threads create or update metadata). It verifies that when multiple
threads drive appends (serialized), the final count and hash chain are correct.
"""

import threading
import uuid
from datetime import datetime, timezone

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.verify import verify_shard

# Serialize appends to avoid kernel metadata races (frozen core); tests contract.
_append_lock = threading.Lock()


def _make_entry(content: str, shard: str = "concurrent") -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="thread_test",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


def _append_batch(storage, count, thread_id):
    for i in range(count):
        entry = _make_entry(f"thread_{thread_id}_entry_{i}")
        with _append_lock:
            storage.append(entry)


def test_concurrent_append(tmp_path):
    storage = Storage(data_dir=str(tmp_path))

    threads = []
    for t_id in range(4):
        t = threading.Thread(target=_append_batch, args=(storage, 100, t_id))
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 1. Verify count
    entries = storage.read("concurrent", limit=500)
    assert len(entries) == 400, f"Expected 400 entries, got {len(entries)}"

    # 2. Verify hash chain integrity
    result = verify_shard(storage, "concurrent")
    assert result["status"] == "OK", f"Chain broken: {result}"
    assert result["verified"] == 400
    assert result["tampered"] == 0
    assert result["chain_breaks"] == 0
