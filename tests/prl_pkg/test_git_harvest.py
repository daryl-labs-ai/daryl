"""P2 tests — git harvest + project map.

Scope guard: touches only ``prl`` + a real git repo created in a tmp dir via
subprocess. No DSM, no RR, no embeddings. Requires ``git`` on PATH.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from prl.config import PRLConfig
from prl.index import (
    ProjectMap,
    build_map,
    harvest_commits,
    is_git_repo,
    make_project_node,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


def _git(root, *args, **env):
    base_env = {
        "GIT_AUTHOR_NAME": "Tester",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "Tester",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    base_env.update(env)
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**_os_environ(), **base_env},
    )


def _os_environ():
    import os

    return dict(os.environ)


def _write(path, content: bytes = b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _init_repo(root):
    _git(root, "init", "-q")
    return root


def _config(root, **overrides):
    base = dict(declared_projects=[root])
    base.update(overrides)
    return PRLConfig(**base)


# --- is_git_repo -----------------------------------------------------------


def test_is_git_repo_true_after_init(tmp_path):
    _init_repo(tmp_path)
    assert is_git_repo(tmp_path) is True


def test_is_git_repo_false_for_plain_dir(tmp_path):
    assert is_git_repo(tmp_path) is False


# --- harvest_commits -------------------------------------------------------


def test_harvest_parses_commit_fields(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path / "a.py", b"print(1)")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: add a")
    commits = harvest_commits(make_project_node(tmp_path))
    assert len(commits) == 1
    c = commits[0]
    assert c.message == "feat: add a"
    assert c.author == "Tester"
    assert c.ts_ms > 0
    assert c.files == ("a.py",)
    assert len(c.sha) == 40


def test_harvest_multi_file_commit(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path / "a.py")
    _write(tmp_path / "src" / "b.py")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "two files")
    commits = harvest_commits(make_project_node(tmp_path))
    assert set(commits[0].files) == {"a.py", "src/b.py"}


def test_harvest_newest_first_and_limit(tmp_path):
    _init_repo(tmp_path)
    for i in range(3):
        _write(tmp_path / f"f{i}.py", str(i).encode())
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", f"commit {i}")
    commits = harvest_commits(make_project_node(tmp_path))
    assert [c.message for c in commits] == ["commit 2", "commit 1", "commit 0"]
    limited = harvest_commits(make_project_node(tmp_path), limit=1)
    assert [c.message for c in limited] == ["commit 2"]


def test_harvest_non_repo_returns_empty(tmp_path):
    assert harvest_commits(make_project_node(tmp_path)) == []


def test_harvest_empty_repo_returns_empty(tmp_path):
    _init_repo(tmp_path)  # no commits yet
    assert harvest_commits(make_project_node(tmp_path)) == []


# --- build_map -------------------------------------------------------------


def test_build_map_modified_and_belongs_edges(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path / "a.py", b"print(1)")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "add a")
    project = make_project_node(tmp_path)
    pmap = build_map(project, _config(tmp_path))

    assert isinstance(pmap, ProjectMap)
    assert {f.path for f in pmap.files} == {"a.py"}
    assert len(pmap.commits) == 1

    modified = [e for e in pmap.edges if e.edge_type == "modified"]
    belongs = [e for e in pmap.edges if e.edge_type == "belongs_to"]
    file_hash = pmap.files[0].content_hash
    assert any(e.src_id == pmap.commits[0].sha and e.dst_id == file_hash for e in modified)
    assert any(e.src_id == file_hash and e.dst_id == project.project_id for e in belongs)


def test_build_map_no_modified_edge_for_unindexed_file(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path / "a.py", b"x")
    _write(tmp_path / "data.bin", b"\x00\x01")  # excluded extension → not indexed
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "mixed")
    pmap = build_map(make_project_node(tmp_path), _config(tmp_path))
    modified = [e for e in pmap.edges if e.edge_type == "modified"]
    # only a.py is indexed, so exactly one modified edge (none for data.bin)
    assert len(modified) == 1
    assert {f.path for f in pmap.files} == {"a.py"}


def test_build_map_non_repo_has_files_but_no_commits(tmp_path):
    _write(tmp_path / "a.py", b"x")
    pmap = build_map(make_project_node(tmp_path), _config(tmp_path))
    assert pmap.commits == []
    assert {f.path for f in pmap.files} == {"a.py"}
    assert [e for e in pmap.edges if e.edge_type == "modified"] == []
    assert len([e for e in pmap.edges if e.edge_type == "belongs_to"]) == 1
