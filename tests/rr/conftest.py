# -*- coding: utf-8 -*-
"""
Pytest fixtures for RR module tests. Uses temporary DSM storage only.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import uuid
import pytest

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator
from dsm.rr.query import RRQueryEngine


def _make_entry(
    session_id: str = "s1",
    source: str = "agent_a",
    content: str = "test",
    shard: str = "sessions",
    event_type: str = "tool_call",
) -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id=session_id,
        source=source,
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={"event_type": event_type},
        version="v2.0",
    )


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temp dir with a monolithic sessions.jsonl so list_shards and read work."""
    shards_dir = tmp_path / "shards"
    shards_dir.mkdir(parents=True)
    integrity_dir = tmp_path / "integrity"
    integrity_dir.mkdir(parents=True)

    entries = [
        _make_entry(session_id="s1", source="agent_a", content="c1", event_type="session_start"),
        _make_entry(session_id="s1", source="agent_a", content="c2", event_type="tool_call"),
        _make_entry(session_id="s2", source="agent_b", content="c3", event_type="snapshot"),
        _make_entry(session_id="s1", source="agent_a", content="c4", event_type="session_end"),
        _make_entry(session_id="s2", source="agent_b", content="c5", event_type="tool_call"),
    ]
    path = shards_dir / "sessions.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            obj = {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "session_id": e.session_id,
                "source": e.source,
                "content": e.content,
                "shard": e.shard,
                "hash": e.hash or "",
                "prev_hash": e.prev_hash,
                "metadata": e.metadata,
                "version": e.version,
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    return tmp_path


@pytest.fixture
def storage(temp_data_dir):
    """Storage instance using temp dir."""
    return Storage(data_dir=str(temp_data_dir))


@pytest.fixture
def index_builder(storage, temp_data_dir):
    """RRIndexBuilder with temp index dir. Call ensure_index() or build() in test."""
    index_dir = temp_data_dir / "index"
    return RRIndexBuilder(storage=storage, index_dir=str(index_dir))


@pytest.fixture
def navigator(index_builder, storage):
    """RRNavigator with index and storage. Index must be built before use."""
    index_builder.ensure_index()
    return RRNavigator(index_builder=index_builder, storage=storage)


@pytest.fixture
def query_engine(navigator):
    """RRQueryEngine with navigator (index already ensured)."""
    return RRQueryEngine(navigator=navigator)
