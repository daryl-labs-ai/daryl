"""Tests for P9 — Artifact Store."""

import tempfile
from pathlib import Path

import pytest

from dsm.artifacts import ArtifactStore


@pytest.fixture
def artifact_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_store_and_retrieve_bytes(artifact_dir):
    """Store raw bytes, retrieve identical bytes."""
    store = ArtifactStore(artifact_dir)
    raw = b"hello world \x00\x01"
    out = store.store(raw, source="test", artifact_type="response")
    assert out["artifact_hash"]
    assert out["size_bytes"] == len(raw)
    retrieved = store.retrieve(out["artifact_hash"])
    assert retrieved == raw


def test_store_and_retrieve_dict(artifact_dir):
    """Store dict, retrieve JSON bytes."""
    store = ArtifactStore(artifact_dir)
    data = {"a": 1, "b": 2}
    out = store.store(data, source="api", artifact_type="response")
    retrieved = store.retrieve(out["artifact_hash"])
    assert retrieved is not None
    import json
    back = json.loads(retrieved.decode("utf-8"))
    assert back == data


def test_store_deduplication(artifact_dir):
    """Same content stored twice → same hash, no duplicate files."""
    store = ArtifactStore(artifact_dir)
    raw = b"identical content"
    out1 = store.store(raw, source="s1")
    out2 = store.store(raw, source="s2")
    assert out1["artifact_hash"] == out2["artifact_hash"]
    sub = Path(artifact_dir) / out1["artifact_hash"][:2]
    bin_files = list(sub.glob("*.bin.gz"))
    assert len(bin_files) == 1


def test_verify_artifact_intact(artifact_dir):
    """Verify returns INTACT for valid artifact."""
    store = ArtifactStore(artifact_dir)
    out = store.store(b"data", source="test")
    result = store.verify_artifact(out["artifact_hash"])
    assert result["status"] == "INTACT"
    assert result["size_bytes"] == 4


def test_verify_artifact_corrupted(artifact_dir):
    """Corrupt .bin.gz, verify returns CORRUPTED."""
    store = ArtifactStore(artifact_dir)
    out = store.store(b"original", source="test")
    prefix = out["artifact_hash"][:2]
    bin_path = Path(artifact_dir) / prefix / (out["artifact_hash"] + ".bin.gz")
    bin_path.write_bytes(b"garbage")
    result = store.verify_artifact(out["artifact_hash"])
    assert result["status"] == "CORRUPTED"


def test_verify_artifact_missing(artifact_dir):
    """Verify non-existent hash returns MISSING."""
    store = ArtifactStore(artifact_dir)
    result = store.verify_artifact("a" * 64)
    assert result["status"] == "MISSING"
    assert result["size_bytes"] is None


def test_link_to_entry(artifact_dir):
    """Link artifact to entry_id, verify linked_entries in metadata."""
    store = ArtifactStore(artifact_dir)
    out = store.store(b"x", source="test")
    store.link_to_entry(out["artifact_hash"], "entry-1")
    store.link_to_entry(out["artifact_hash"], "entry-2")
    meta = store.get_metadata(out["artifact_hash"])
    assert "entry-1" in meta.get("linked_entries", [])
    assert "entry-2" in meta.get("linked_entries", [])
    link_result = store.link_to_entry(out["artifact_hash"], "entry-1")
    assert link_result["linked_entries_count"] == 2
