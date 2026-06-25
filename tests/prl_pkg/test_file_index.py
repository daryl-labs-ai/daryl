"""P1 tests — filesystem scanner + file index.

Scope guard: touches only ``prl`` + ``prl._canonical`` + a tmp filesystem. No
DSM, no RR, no git, no embeddings.
"""

from __future__ import annotations

from prl._canonical import sha256_uri
from prl.config import PRLConfig
from prl.index import index_project, make_project_node, walk_project
from prl.index.scanner import DEFAULT_IGNORES


def _config(tmp_path, **overrides):
    base = dict(declared_projects=[tmp_path])
    base.update(overrides)
    return PRLConfig(**base)


def _write(path, content: bytes = b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# --- walk_project ----------------------------------------------------------


def test_walk_yields_only_listed_extensions(tmp_path):
    _write(tmp_path / "a.py", b"print(1)")
    _write(tmp_path / "b.md", b"# hi")
    _write(tmp_path / "c.bin", b"\x00\x01")  # not in extensions
    cfg = _config(tmp_path)
    found = {p.name for p in walk_project(tmp_path, cfg.index_extensions, cfg.max_file_bytes)}
    assert found == {"a.py", "b.md"}


def test_walk_prunes_ignored_dirs(tmp_path):
    _write(tmp_path / "keep.py")
    _write(tmp_path / ".git" / "config.py")
    _write(tmp_path / "node_modules" / "dep.js")
    _write(tmp_path / "__pycache__" / "x.py")
    cfg = _config(tmp_path)
    found = {p.relative_to(tmp_path).as_posix()
             for p in walk_project(tmp_path, cfg.index_extensions, cfg.max_file_bytes)}
    assert found == {"keep.py"}


def test_walk_skips_oversize_files(tmp_path):
    _write(tmp_path / "small.txt", b"a" * 10)
    _write(tmp_path / "big.txt", b"a" * 5000)
    cfg = _config(tmp_path, max_file_bytes=100)
    found = {p.name for p in walk_project(tmp_path, cfg.index_extensions, cfg.max_file_bytes)}
    assert found == {"small.txt"}


def test_walk_is_deterministic(tmp_path):
    for n in ("c.py", "a.py", "b.py"):
        _write(tmp_path / n)
    cfg = _config(tmp_path)
    once = [p.name for p in walk_project(tmp_path, cfg.index_extensions, cfg.max_file_bytes)]
    twice = [p.name for p in walk_project(tmp_path, cfg.index_extensions, cfg.max_file_bytes)]
    assert once == twice == ["a.py", "b.py", "c.py"]


def test_default_ignores_cover_common_noise():
    for name in (".git", "node_modules", "__pycache__", ".pytest_cache", ".hypothesis", ".DS_Store"):
        assert name in DEFAULT_IGNORES


# --- index_project ---------------------------------------------------------


def test_index_project_one_node_per_file(tmp_path):
    _write(tmp_path / "src" / "a.py", b"print(1)")
    _write(tmp_path / "README.md", b"# hi")
    project = make_project_node(tmp_path)
    nodes = index_project(project, _config(tmp_path))
    assert len(nodes) == 2
    paths = {n.path for n in nodes}
    assert paths == {"src/a.py", "README.md"}
    assert all(n.project_id == project.project_id for n in nodes)


def test_content_hash_matches_raw_bytes(tmp_path):
    data = b"exact bytes here"
    _write(tmp_path / "f.txt", data)
    nodes = index_project(make_project_node(tmp_path), _config(tmp_path))
    assert nodes[0].content_hash == sha256_uri(data)
    assert nodes[0].size == len(data)


def test_identical_content_same_hash(tmp_path):
    _write(tmp_path / "one.py", b"same")
    _write(tmp_path / "dir" / "two.py", b"same")
    nodes = index_project(make_project_node(tmp_path), _config(tmp_path))
    hashes = {n.path: n.content_hash for n in nodes}
    assert hashes["one.py"] == hashes["dir/two.py"]


def test_modified_content_changes_hash(tmp_path):
    f = _write(tmp_path / "f.py", b"v1")
    project = make_project_node(tmp_path)
    cfg = _config(tmp_path)
    h1 = index_project(project, cfg)[0].content_hash
    f.write_bytes(b"v2-different")
    h2 = index_project(project, cfg)[0].content_hash
    assert h1 != h2


def test_index_populates_mtime(tmp_path):
    _write(tmp_path / "f.py", b"x")
    nodes = index_project(make_project_node(tmp_path), _config(tmp_path))
    assert nodes[0].mtime_ms > 0


def test_index_empty_project(tmp_path):
    nodes = index_project(make_project_node(tmp_path), _config(tmp_path))
    assert nodes == []


def test_index_ignores_unreadable(tmp_path):
    _write(tmp_path / "ok.py", b"x")
    # A path inside an ignored dir must not appear even if readable.
    _write(tmp_path / ".git" / "hook.py", b"x")
    nodes = index_project(make_project_node(tmp_path), _config(tmp_path))
    assert [n.path for n in nodes] == ["ok.py"]


# --- make_project_node -----------------------------------------------------


def test_make_project_node_deterministic(tmp_path):
    a = make_project_node(tmp_path)
    b = make_project_node(tmp_path)
    assert a.project_id == b.project_id
    assert a.project_id.startswith("sha256:")
    assert a.root_path == str(tmp_path)


def test_make_project_node_custom_name(tmp_path):
    node = make_project_node(tmp_path, name="my-proj")
    assert node.name == "my-proj"
