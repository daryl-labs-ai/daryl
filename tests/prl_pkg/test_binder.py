"""P7 tests — session binder (metadata signals, confidence + evidence).

Pure: touches only prl. No DSM/RR/Storage.
"""

from __future__ import annotations

from prl.collectors import bind_sessions
from prl.index.mapper import ProjectMap
from prl.types import CommitNode, FileNode, ProjectNode, SessionNode

PID = "sha256:" + "a" * 64
H_A = "sha256:" + "b" * 64
H_B = "sha256:" + "c" * 64

# session window: 1_700_000_000_000 .. 1_700_000_100_000 ms
S_START = 1_700_000_000_000
S_END = 1_700_000_100_000


def _map(files=None, commits=None) -> ProjectMap:
    project = ProjectNode(project_id=PID, root_path="/p/x", name="x")
    return ProjectMap(project=project, files=files or [], commits=commits or [], edges=[])


def _file(path, content_hash=H_A, mtime_ms=0):
    return FileNode(path=path, content_hash=content_hash, size=1, mtime_ms=mtime_ms, project_id=PID)


def _session(title="", preview="", started=0, ended=None, sid="s1"):
    return SessionNode(session_id=sid, tool="chatgpt", title=title or None,
                       started_ms=started, ended_ms=ended, text_preview=preview)


# --- citation signals ------------------------------------------------------


def test_path_citation():
    pmap = _map(files=[_file("src/a.py")])
    s = _session(preview="I edited src/a.py to fix the bug")
    edges = bind_sessions([s], pmap)
    assert len(edges) == 1
    e = edges[0]
    assert e.edge_type == "references" and e.src_id == "s1" and e.dst_id == H_A
    assert e.confidence == 0.75
    assert e.evidence["method"] == "path"


def test_filename_citation():
    pmap = _map(files=[_file("src/deep/a.py")])
    s = _session(title="question about a.py")
    edges = bind_sessions([s], pmap)
    assert len(edges) == 1
    assert edges[0].confidence == 0.60
    assert edges[0].evidence["method"] == "filename"


def test_short_basename_not_matched():
    # basename "x.y" (3 chars) is below the min length → no filename match
    pmap = _map(files=[_file("x.y", content_hash=H_B)])
    s = _session(preview="the value of x.y in math")
    assert bind_sessions([s], pmap) == []


# --- temporal signals ------------------------------------------------------


def test_commit_window():
    commit = CommitNode(sha="deadbeef", author="me", ts_ms=S_START + 5000,
                        message="fix", files=("src/a.py",), project_id=PID)
    pmap = _map(commits=[commit])
    s = _session(started=S_START, ended=S_END)
    edges = bind_sessions([s], pmap)
    assert len(edges) == 1
    assert edges[0].dst_id == "deadbeef"
    assert edges[0].confidence == 0.80
    assert edges[0].evidence["method"] == "commit_window"


def test_commit_outside_window_ignored():
    commit = CommitNode(sha="c", author="me", ts_ms=S_END + 10 * 3600 * 1000,
                        message="later", files=(), project_id=PID)
    pmap = _map(commits=[commit])
    s = _session(started=S_START, ended=S_END)
    assert bind_sessions([s], pmap) == []


def test_mtime_window_weak():
    pmap = _map(files=[_file("src/a.py", mtime_ms=S_START + 1000)])
    s = _session(started=S_START, ended=S_END)  # no citation → only mtime signal
    edges = bind_sessions([s], pmap)
    assert len(edges) == 1
    assert edges[0].confidence == 0.40
    assert edges[0].evidence["method"] == "mtime_window"


def test_no_timestamps_no_temporal():
    commit = CommitNode(sha="c", author="me", ts_ms=S_START, message="m", files=(), project_id=PID)
    pmap = _map(files=[_file("src/a.py", mtime_ms=S_START)], commits=[commit])
    s = _session(preview="no times here", started=0)  # started_ms=0 → no window
    edges = bind_sessions([s], pmap)
    # neither commit_window nor mtime_window fire; no citation either
    assert edges == []


# --- dedup + threshold -----------------------------------------------------


def test_dedup_keeps_strongest():
    # citation (0.75) AND mtime window (0.40) for the same file → one edge, 0.75
    pmap = _map(files=[_file("src/a.py", mtime_ms=S_START + 1000)])
    s = _session(preview="touched src/a.py", started=S_START, ended=S_END)
    edges = bind_sessions([s], pmap)
    assert len(edges) == 1
    assert edges[0].confidence == 0.75
    assert edges[0].evidence["method"] == "path"


def test_min_confidence_filters_weak():
    pmap = _map(files=[_file("src/a.py", mtime_ms=S_START + 1000)])
    s = _session(started=S_START, ended=S_END)  # mtime only → 0.40
    assert bind_sessions([s], pmap, min_confidence=0.7) == []


def test_every_edge_has_method_evidence():
    commit = CommitNode(sha="c", author="me", ts_ms=S_START, message="m", files=(), project_id=PID)
    pmap = _map(files=[_file("src/a.py")], commits=[commit])
    s = _session(preview="src/a.py", started=S_START, ended=S_END)
    edges = bind_sessions([s], pmap)
    assert edges
    assert all("method" in e.evidence and 0.0 <= e.confidence <= 1.0 for e in edges)


def test_empty_inputs():
    assert bind_sessions([], _map()) == []
    assert bind_sessions([_session(preview="x")], _map()) == []
