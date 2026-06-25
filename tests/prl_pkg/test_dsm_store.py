"""P3 tests — PRLStore commits a ProjectMap into DSM via Storage.append.

Requires the real DSM kernel (dsm.core.storage / dsm.core.models / dsm.verify)
and dsm_primitives. Validates: write path, per-project shard, timestamp bridge,
action_name hook, run_id propagation, and tamper-evident chain via verify_shard.
"""

from __future__ import annotations

from datetime import datetime

from dsm.core.storage import Storage
from dsm.verify import verify_shard

from prl.index import build_map, make_project_node
from prl.index.mapper import ProjectMap
from prl.store import CommitResult, PRLStore, new_run_id, prl_shard_name
from prl.types import (
    CommitNode,
    Edge,
    FileNode,
    ProjectNode,
    from_entry,
)

PID = "sha256:" + "a" * 64


def _sample_map() -> ProjectMap:
    project = ProjectNode(project_id=PID, root_path="/p/x", name="x")
    files = [
        FileNode(path="a.py", content_hash="sha256:" + "b" * 64, size=3,
                 mtime_ms=1_700_000_000_000, project_id=PID),
        FileNode(path="b.py", content_hash="sha256:" + "c" * 64, size=4,
                 mtime_ms=1_700_000_001_000, project_id=PID),
    ]
    commits = [
        CommitNode(sha="deadbeef", author="me", ts_ms=1_700_000_002_000,
                   message="feat", files=("a.py",), project_id=PID),
    ]
    edges = [
        Edge(edge_type="modified", src_id="deadbeef", dst_id="sha256:" + "b" * 64,
             evidence={"path": "a.py"}),
        Edge(edge_type="belongs_to", src_id="sha256:" + "b" * 64, dst_id=PID),
        Edge(edge_type="belongs_to", src_id="sha256:" + "c" * 64, dst_id=PID),
    ]
    return ProjectMap(project=project, files=files, commits=commits, edges=edges)


def _store(tmp_path) -> PRLStore:
    return PRLStore(Storage(data_dir=str(tmp_path)))


# --- shard name ------------------------------------------------------------


def test_shard_name_is_fs_safe():
    name = prl_shard_name(PID)
    assert name == "prl_" + "a" * 16
    assert ":" not in name and "/" not in name


# --- commit_map ------------------------------------------------------------


def test_commit_writes_all_nodes(tmp_path):
    pmap = _sample_map()
    res = _store(tmp_path).commit_map(pmap)
    assert isinstance(res, CommitResult)
    expected = 1 + len(pmap.files) + len(pmap.commits) + len(pmap.edges)
    assert res.n_entries == expected  # 1 + 2 + 1 + 3 = 7
    assert res.shard == prl_shard_name(PID)
    assert res.tip_hash  # non-empty chain tip


def test_committed_shard_verifies(tmp_path):
    store = _store(tmp_path)
    res = store.commit_map(_sample_map())
    report = verify_shard(store._storage, res.shard)
    assert str(report["status"]).endswith("OK")
    assert report["verified"] == report["total_entries"]
    assert report["total_entries"] == res.n_entries


def test_timestamp_bridged_to_datetime(tmp_path):
    store = _store(tmp_path)
    res = store.commit_map(_sample_map())
    entries = store._storage.read(res.shard, limit=100)
    assert entries
    assert all(isinstance(e.timestamp, datetime) for e in entries)


def test_action_name_on_every_entry(tmp_path):
    store = _store(tmp_path)
    res = store.commit_map(_sample_map())
    entries = store._storage.read(res.shard, limit=100)
    kinds = {e.metadata.get("action_name") for e in entries}
    assert kinds == {"prl.project", "prl.file", "prl.commit", "prl.edge"}


def test_run_id_is_session_id(tmp_path):
    store = _store(tmp_path)
    res = store.commit_map(_sample_map(), run_id="prl_run_fixed")
    entries = store._storage.read(res.shard, limit=100)
    assert {e.session_id for e in entries} == {"prl_run_fixed"}
    assert res.run_id == "prl_run_fixed"


def test_round_trip_from_entry(tmp_path):
    store = _store(tmp_path)
    pmap = _sample_map()
    res = store.commit_map(pmap)
    entries = store._storage.read(res.shard, limit=100)
    files = [from_entry(e) for e in entries if e.metadata.get("action_name") == "prl.file"]
    assert {f.content_hash for f in files} == {f.content_hash for f in pmap.files}


def test_recommit_appends_and_chain_holds(tmp_path):
    store = _store(tmp_path)
    pmap = _sample_map()
    r1 = store.commit_map(pmap, run_id="run-1")
    r2 = store.commit_map(pmap, run_id="run-2")
    report = verify_shard(store._storage, r2.shard)
    assert str(report["status"]).endswith("OK")
    assert report["total_entries"] == r1.n_entries + r2.n_entries
    entries = store._storage.read(r2.shard, limit=1000)
    assert {"run-1", "run-2"} <= {e.session_id for e in entries}


# --- integration with build_map (no git repo) ------------------------------


def test_commit_real_build_map(tmp_path):
    proj_dir = tmp_path / "proj"
    (proj_dir / "src").mkdir(parents=True)
    (proj_dir / "src" / "m.py").write_bytes(b"print(1)\n")
    (proj_dir / "README.md").write_bytes(b"# hi\n")

    project = make_project_node(proj_dir)
    from prl.config import PRLConfig

    pmap = build_map(project, PRLConfig(declared_projects=[proj_dir]))
    store = PRLStore(Storage(data_dir=str(tmp_path / "dsm")))
    res = store.commit_map(pmap)

    report = verify_shard(store._storage, res.shard)
    assert str(report["status"]).endswith("OK")
    assert res.n_entries == 1 + len(pmap.files) + len(pmap.commits) + len(pmap.edges)


def test_new_run_id_unique():
    assert new_run_id() != new_run_id()
