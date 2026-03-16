"""
Test that entries written to disk use canonical JSON serialization
(sort_keys=True, separators=(',',':')) for consistency.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage


def _make_entry(content: str, shard: str = "canonical_test") -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="canonical",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={"z_key": "last", "a_key": "first"},
        version="v2.0",
    )


class TestCanonicalJson:
    def test_on_disk_format_is_canonical(self, tmp_path):
        """Entry written to disk should have sorted keys and compact separators."""
        storage = Storage(data_dir=str(tmp_path))
        storage.append(_make_entry("test_content"))

        seg = storage.segment_manager.get_active_segment("canonical_test")
        with open(seg, "r", encoding="utf-8") as f:
            raw_line = f.readline().strip()

        parsed = json.loads(raw_line)
        canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        assert raw_line == canonical, (
            f"On-disk format is not canonical.\n"
            f"Got:      {raw_line[:200]}\n"
            f"Expected: {canonical[:200]}"
        )

    def test_metadata_keys_sorted_on_disk(self, tmp_path):
        """Metadata dict keys should be sorted on disk."""
        storage = Storage(data_dir=str(tmp_path))
        storage.append(_make_entry("meta_test"))

        seg = storage.segment_manager.get_active_segment("canonical_test")
        with open(seg, "r", encoding="utf-8") as f:
            raw_line = f.readline().strip()

        a_pos = raw_line.index('"a_key"')
        z_pos = raw_line.index('"z_key"')
        assert a_pos < z_pos, "Metadata keys are not sorted on disk"
