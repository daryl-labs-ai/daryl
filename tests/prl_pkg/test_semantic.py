"""P8 tests — local semantic index (pure-Python cosine, JSON persistence).

Uses a deterministic FakeEmbedder (md5 bag-of-words) — NO model download, no
sentence-transformers. Also asserts LocalEmbedder degrades cleanly when the
'semantic' extra is absent.
"""

from __future__ import annotations

import hashlib

import pytest

from prl.query.semantic import LocalEmbedder, SemanticError, SemanticIndex

_DIM = 32


class FakeEmbedder:
    """Deterministic bag-of-words vector via md5 hashing (stable across runs,
    unlike Python's salted hash). Shared words → higher cosine."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * _DIM
        for word in text.lower().split():
            h = int(hashlib.md5(word.encode()).hexdigest(), 16) % _DIM
            v[h] += 1.0
        return v


def _index():
    return SemanticIndex(embedder=FakeEmbedder())


# --- search ----------------------------------------------------------------


def test_search_ranks_overlapping_text_first():
    idx = _index()
    idx.build([
        ("a", "decided the architecture of the storage kernel"),
        ("b", "lunch menu pizza and salad"),
        ("c", "weather forecast rain tomorrow"),
    ])
    hits = idx.search("architecture decision for the kernel", k=3)
    assert hits[0][0] == "a"
    # scores descending
    assert all(hits[i][1] >= hits[i + 1][1] for i in range(len(hits) - 1))


def test_search_respects_k():
    idx = _index()
    idx.build([(str(i), f"word{i} common") for i in range(5)])
    assert len(idx.search("common", k=2)) == 2


def test_empty_index_returns_empty():
    assert _index().search("anything") == []


def test_add_then_search():
    idx = _index()
    idx.add("x", "hash chain tamper evidence")
    idx.add("y", "completely unrelated cooking recipe")
    assert idx.search("tamper evidence hash", k=1)[0][0] == "x"


def test_len():
    idx = _index()
    idx.build([("a", "one"), ("b", "two")])
    assert len(idx) == 2


# --- persistence -----------------------------------------------------------


def test_save_load_round_trip(tmp_path):
    idx = _index()
    idx.build([("a", "alpha beta"), ("b", "gamma delta")])
    p = tmp_path / "sem.json"
    idx.save(p)

    loaded = SemanticIndex.load(p, embedder=FakeEmbedder())
    assert len(loaded) == 2
    assert idx.search("alpha beta", k=1) == loaded.search("alpha beta", k=1)


def test_loaded_index_needs_embedder_to_search(tmp_path):
    idx = _index()
    idx.build([("a", "alpha")])
    p = tmp_path / "sem.json"
    idx.save(p)
    loaded = SemanticIndex.load(p)  # no embedder
    with pytest.raises(SemanticError):
        loaded.search("alpha")


# --- guards ----------------------------------------------------------------


def test_no_embedder_raises_on_build():
    with pytest.raises(SemanticError):
        SemanticIndex().build([("a", "x")])


def test_local_embedder_missing_extra_raises():
    # The 'semantic' extra (sentence-transformers) is not installed in CI/test env;
    # LocalEmbedder must raise a clear SemanticError rather than a raw ImportError.
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        with pytest.raises(SemanticError):
            LocalEmbedder()
    else:  # pragma: no cover (only when the extra happens to be installed)
        pytest.skip("sentence-transformers installed; missing-extra path not exercised")
