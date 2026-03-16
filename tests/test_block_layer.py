"""Tests for block_layer module."""
import pytest
from pathlib import Path
from datetime import datetime, timezone

from dsm.core.models import Entry
from dsm.core.storage import Storage


def test_block_manager_import():
    """Block layer module should be importable."""
    from dsm.block_layer.manager import BlockManager
    assert BlockManager is not None


def test_block_manager_init(tmp_path):
    """BlockManager should initialize with a data directory."""
    from dsm.block_layer.manager import BlockManager
    bm = BlockManager(data_dir=str(tmp_path))
    assert bm is not None


def test_block_manager_add_event(tmp_path):
    """BlockManager should accept and store events."""
    from dsm.block_layer.manager import BlockManager
    bm = BlockManager(data_dir=str(tmp_path))
    entry = Entry(
        id="e1",
        timestamp=datetime.now(timezone.utc),
        session_id="s1",
        source="test",
        content='{"type": "test", "data": "hello"}',
        shard="default",
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )
    result = bm.append(entry)
    assert result is not None
    assert result.id == "e1"
