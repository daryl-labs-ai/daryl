"""P5 tests — StructuralQuery over the PRL map, RR-backed.

Requires the real DSM kernel + RR. Commits maps via the P3 store (write), then
queries via RR-backed StructuralQuery (read). Validates the four queries,
latest-run dedup, stale-snapshot dropping, and the no-Storage-import contract.
"""

from __future__ import annotations

import time
from pathlib import Path

from dsm.core.storage import Storage

from prl.config import PRLConfig
from prl.index import build_map, make_project_node
from prl.query.structural import StructuralQuery
from prl.store import PRLStore


def _project(tmp_path, name="proj"):
    d = tmp_path / name
    (d / "src").mkdir(parents=True)
    (d / "src" / "a.py").write_bytes(b"print(1)\n")
    (d / "README.md").write_bytes(b"# hi\n")
    d_git(d)
    return d


def d_git(d):
    import subprocess

    env = {
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t",
    }
    import os

    e = {**os.environ, **env}
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True, env=e)
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True, env=e)
    subprocess.run(["git", "-C", str(d), "commit", "-q", "-m", "init"], check=True, env=e)


def _commit_map(tmp_path, proj):
    storage = Storage(data_dir=str(tmp_path / "dsm"))
    config = PRLConfig(declared_projects=[proj])
    project = make_project_node(proj)
    pmap = build_map(project, config)
    PRLStore(storage).commit_map(pmap)
    return storage, project, pmap


def _sq(tmp_path, storage):
    return StructuralQuery(storage, tmp_path / "rr_index")


def test_files_of_project(tmp_path):
    proj = _project(tmp_path)
    storage, project, pmap = _commit_map(tmp_path, proj)
    sq = _sq(tmp_path, storage)
    got = {f.content_hash for f in sq.files_of_project(project.project_id)}
    assert got == {f.content_hash for f in pmap.files}


def test_commits_touching(tmp_path):
    proj = _project(tmp_path)
    storage, project, pmap = _commit_map(tmp_path, proj)
    sq = _sq(tmp_path, storage)
    # the README + a.py were both in the init commit
    a_hash = next(f.content_hash for f in pmap.files if f.path == "src/a.py")
    commits = sq.commits_touching(a_hash)
    assert len(commits) >= 1
    assert any(c.message == "init" for c in commits)


def test_project_of_file(tmp_path):
    proj = _project(tmp_path)
    storage, project, pmap = _commit_map(tmp_path, proj)
    sq = _sq(tmp_path, storage)
    a_hash = pmap.files[0].content_hash
    owner = sq.project_of_file(a_hash)
    assert owner is not None
    assert owner.project_id == project.project_id


def test_neighbors_modified(tmp_path):
    proj = _project(tmp_path)
    storage, project, pmap = _commit_map(tmp_path, proj)
    sq = _sq(tmp_path, storage)
    commit_sha = pmap.commits[0].sha
    mod = sq.neighbors(commit_sha, edge_type="modified")
    assert mod and all(e.edge_type == "modified" and e.src_id == commit_sha for e in mod)


def test_unknown_queries_empty(tmp_path):
    proj = _project(tmp_path)
    storage, _, _ = _commit_map(tmp_path, proj)
    sq = _sq(tmp_path, storage)
    assert sq.files_of_project("sha256:" + "0" * 64) == []
    assert sq.commits_touching("sha256:" + "0" * 64) == []
    assert sq.project_of_file("sha256:" + "0" * 64) is None
    assert sq.neighbors("nope") == []


def test_latest_run_dedup(tmp_path):
    proj = _project(tmp_path)
    storage, project, pmap = _commit_map(tmp_path, proj)
    # re-commit the SAME map a second time (new run, appended to the same shard)
    time.sleep(0.005)
    PRLStore(storage).commit_map(build_map(project, PRLConfig(declared_projects=[proj])))
    sq = _sq(tmp_path, storage)
    files = sq.files_of_project(project.project_id)
    # latest-run semantics: each file appears once, not doubled across runs
    assert len(files) == len(pmap.files)
    assert len({f.content_hash for f in files}) == len(files)


def test_changed_file_supersedes_old(tmp_path):
    proj = _project(tmp_path)
    storage, project, pmap = _commit_map(tmp_path, proj)
    old_hash = next(f.content_hash for f in pmap.files if f.path == "src/a.py")

    # modify a.py and re-index (new run with the new content hash)
    time.sleep(0.005)
    (proj / "src" / "a.py").write_bytes(b"print(2)\n# changed\n")
    pmap2 = build_map(project, PRLConfig(declared_projects=[proj]))
    PRLStore(storage).commit_map(pmap2)
    new_hash = next(f.content_hash for f in pmap2.files if f.path == "src/a.py")
    assert new_hash != old_hash

    sq = _sq(tmp_path, storage)
    current = {f.content_hash for f in sq.files_of_project(project.project_id)}
    assert new_hash in current
    assert old_hash not in current  # stale snapshot dropped
    assert sq.project_of_file(old_hash) is None
    assert sq.project_of_file(new_hash) is not None


def test_structural_does_not_import_storage():
    """Contract guard (ADR-0001): the read layer must not import Storage."""
    path = Path(__file__).resolve().parents[2] / "src" / "prl" / "query" / "structural.py"
    text = path.read_text(encoding="utf-8")
    assert "dsm.core.storage" not in text
    assert "import Storage" not in text
