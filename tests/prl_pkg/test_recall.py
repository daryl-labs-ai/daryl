"""P9 tests — NL recall (RecallEngine orchestrator + `prl ask` CLI wiring).

RecallEngine is tested with a deterministic FakeEmbedder + synthetic
sessions/edges; the CLI `ask` path is exercised end-to-end by monkeypatching the
embedder factory (no model download). The ≥7/10 acceptance gate is a manual
validation with the real model + real export — out of CI scope.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from prl.query import cli
from prl.query.recall import RecallEngine, RecallHit
from prl.query.semantic import SemanticIndex
from prl.types import CommitNode, Edge, FileNode, SessionNode

_DIM = 32


class FakeEmbedder:
    def embed(self, texts):
        return [self._vec(t) for t in texts]

    def _vec(self, text):
        v = [0.0] * _DIM
        for w in text.lower().split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % _DIM] += 1.0
        return v


PID = "sha256:" + "a" * 64
H_A = "sha256:" + "b" * 64
SHA = "deadbeef00"


def _session(sid, title, preview):
    return SessionNode(session_id=sid, tool="chatgpt", title=title, started_ms=1, text_preview=preview)


def _engine():
    sessions = [
        _session("s1", "Architecture decision", "we decided the storage kernel architecture"),
        _session("s2", "Lunch", "pizza salad menu"),
    ]
    index = SemanticIndex(FakeEmbedder())
    index.build([(s.session_id, f"{s.title} {s.text_preview}") for s in sessions])
    edges = [
        Edge(edge_type="references", src_id="s1", dst_id=H_A, confidence=0.75,
             evidence={"method": "path"}),
        Edge(edge_type="references", src_id="s1", dst_id=SHA, confidence=0.80,
             evidence={"method": "commit_window"}),
    ]
    files = {H_A: FileNode(path="src/kernel.py", content_hash=H_A, size=1, mtime_ms=1, project_id=PID)}
    commits = {SHA: CommitNode(sha=SHA, author="me", ts_ms=1, message="init", files=(), project_id=PID)}
    return RecallEngine(index, {s.session_id: s for s in sessions}, edges, files=files, commits=commits)


# --- RecallEngine ----------------------------------------------------------


def test_ask_ranks_relevant_session_first():
    hits = _engine().ask("storage kernel architecture decision", k=2)
    assert hits[0].session.session_id == "s1"
    assert isinstance(hits[0], RecallHit)


def test_hit_enriched_with_links_and_why():
    top = _engine().ask("architecture", k=1)[0]
    assert [f.path for f in top.linked_files] == ["src/kernel.py"]
    assert [c.sha for c in top.linked_commits] == [SHA]
    # why = semantic + binder evidence
    assert any("semantic match" in w for w in top.why)
    assert any("path" in w for w in top.why)
    assert any("commit_window" in w for w in top.why)


def test_link_boost_raises_score_above_semantic():
    top = _engine().ask("architecture", k=1)[0]
    assert top.score > top.semantic_score  # boosted by binder links


def test_k_respected_and_sorted():
    hits = _engine().ask("anything", k=2)
    assert len(hits) <= 2
    assert all(hits[i].score >= hits[i + 1].score for i in range(len(hits) - 1))


def test_session_missing_from_map_skipped():
    index = SemanticIndex(FakeEmbedder())
    index.build([("ghost", "orphan text")])
    engine = RecallEngine(index, {}, [])  # no session record for "ghost"
    assert engine.ask("orphan") == []


def test_no_edges_score_equals_semantic():
    s = _session("s1", "t", "alpha beta")
    index = SemanticIndex(FakeEmbedder())
    index.build([("s1", "alpha beta")])
    engine = RecallEngine(index, {"s1": s}, [])
    hit = engine.ask("alpha beta", k=1)[0]
    assert hit.score == hit.semantic_score
    assert hit.linked_files == [] and hit.linked_commits == []


# --- F3: candidate_k decoupled from output_k -------------------------------


class StubSemantic:
    """Returns a fixed (id, score) ranking — lets us drive exact semantic ranks."""

    def __init__(self, scored):
        self._scored = scored  # list[(id, score)] sorted desc

    def search(self, query, k=10):
        return self._scored[:k]


def _deep_engine():
    """6 sessions; gold s6 is semantic rank 6 but carries a strong binder edge."""
    sessions = [_session(f"s{i}", f"t{i}", "x") for i in range(1, 7)]
    scored = [("s1", 0.50), ("s2", 0.49), ("s3", 0.48), ("s4", 0.47), ("s5", 0.46), ("s6", 0.45)]
    edges = [Edge(edge_type="references", src_id="s6", dst_id=H_A, confidence=1.0,
                  evidence={"method": "path"})]
    files = {H_A: FileNode(path="src/k.py", content_hash=H_A, size=1, mtime_ms=1, project_id=PID)}
    return RecallEngine(StubSemantic(scored), {s.session_id: s for s in sessions}, edges, files=files)


def test_binder_rescues_deep_candidate_with_default_depth():
    """gold at semantic rank 6 rises to top-1 via the binder even with k=5,
    because candidate_k defaults to 50 (retrieves the whole pool before boosting)."""
    hits = _deep_engine().ask("q", k=5)  # no candidate_k → DEFAULT_CANDIDATE_K (50)
    assert hits[0].session.session_id == "s6"  # 0.45 + 0.20*1.0 = 0.65 > 0.50
    assert len(hits) == 5


def test_shallow_candidate_k_cannot_rescue():
    """With candidate_k == k (old coupled behavior), the rank-6 gold is never
    retrieved, so the binder cannot see it — proves the decoupling matters."""
    hits = _deep_engine().ask("q", k=5, candidate_k=5)
    assert "s6" not in [h.session.session_id for h in hits]


def test_candidate_k_below_k_is_clamped_to_k():
    """candidate_k < k must not retrieve fewer than k candidates."""
    hits = _deep_engine().ask("q", k=3, candidate_k=1)  # search_k = max(3, 1) = 3
    assert len(hits) == 3
    assert [h.session.session_id for h in hits] == ["s1", "s2", "s3"]


# --- CLI `ask` -------------------------------------------------------------


def _git_project(tmp_path):
    import os
    import subprocess

    d = tmp_path / "proj"
    (d / "src").mkdir(parents=True)
    (d / "src" / "kernel.py").write_bytes(b"print('kernel')\n")
    env = {**os.environ, "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True, env=env)
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(d), "commit", "-q", "-m", "init kernel"], check=True, env=env)
    return d


def _export(tmp_path):
    data = {"conversations": {
        "c1": {"title": "kernel architecture", "messages": [
            {"role": "user", "text": "we decided src/kernel.py architecture", "t": 1700000000},
        ]},
    }}
    p = tmp_path / "export.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_cli_ask_end_to_end(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_make_embedder", lambda name: FakeEmbedder())
    proj = _git_project(tmp_path)
    export = _export(tmp_path)
    rc = cli.main(["ask", "where did we decide the kernel architecture?",
                   "--project", str(proj), "--export", export, "--candidate-k", "50"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "kernel architecture" in out
    assert "src/kernel.py" in out  # binder linked the cited file
    assert "why:" in out


def test_cli_ask_index_dir_caches_and_reloads(tmp_path, capsys, monkeypatch):
    """--index-dir persists the fusion vectors on first run, then loads them on
    the second (cache hit) — both runs return the same answer (R3)."""
    from prl.query.fusion_index import FusionIndex

    monkeypatch.setattr(cli, "_make_embedder", lambda name: FakeEmbedder())
    proj = _git_project(tmp_path)
    export = _export(tmp_path)
    cache = tmp_path / "idx"

    rc1 = cli.main(["ask", "where did we decide the kernel architecture?",
                    "--project", str(proj), "--export", export, "--index-dir", str(cache)])
    out1 = capsys.readouterr().out
    assert rc1 == 0
    assert FusionIndex.is_persisted(cache)  # built + saved on first run

    rc2 = cli.main(["ask", "where did we decide the kernel architecture?",
                    "--project", str(proj), "--export", export, "--index-dir", str(cache)])
    out2 = capsys.readouterr().out
    assert rc2 == 0
    assert out1 == out2  # cache hit (load path) yields the identical result


def test_cli_ask_missing_semantic_extra_errors(tmp_path, capsys):
    # Without monkeypatching, _make_embedder uses LocalEmbedder; the 'semantic'
    # extra is absent in CI → clean error, exit 2 (not a crash).
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        proj = _git_project(tmp_path)
        export = _export(tmp_path)
        rc = cli.main(["ask", "q", "--project", str(proj), "--export", export])
        assert rc == 2
        assert "error:" in capsys.readouterr().err
    else:  # pragma: no cover
        pytest.skip("sentence-transformers installed")
