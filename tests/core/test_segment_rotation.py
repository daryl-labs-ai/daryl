import uuid
from datetime import datetime

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.verify import verify_shard


def _make_entry(content: str, shard: str) -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        session_id="rotation_test",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


def test_segment_rotation(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    shard = "rotation_test"

    # Override rotation thresholds for test
    # Use low event count, high byte limit so rotation triggers on count only
    storage.segment_manager.MAX_EVENTS_PER_SEGMENT = 50
    storage.segment_manager.MAX_BYTES_PER_SEGMENT = 100 * 1024 * 1024  # 100MB = effectively disabled

    # Write 120 entries -> expect 3 segments (50 + 50 + 20)
    for i in range(120):
        entry = _make_entry(f"event_{i}", shard)
        storage.append(entry)

    # Verify segment files exist
    shard_dir = tmp_path / "shards" / shard
    assert shard_dir.is_dir()
    segments = sorted(shard_dir.glob("*.jsonl"))
    assert len(segments) == 3, f"Expected 3 segments, got {len(segments)}: {[s.name for s in segments]}"

    # Verify all entries are readable
    entries = storage.read(shard, limit=200)
    assert len(entries) == 120

    # Verify hash chain integrity across segments
    result = verify_shard(storage, shard)
    assert result["status"] == "OK"
    assert result["total_entries"] == 120
    assert result["verified"] == 120
    assert result["tampered"] == 0
    assert result["chain_breaks"] == 0
