"""R1 tests — passage (chunk) index for Retrieval v2 (ADR-PRL-0006).

Deterministic FakeEmbedder (md5 bag-of-words) — NO model download. Verifies that
chunking recalls a buried passage that a single whole-conversation vector dilutes,
that search collapses chunk hits to the conversation by its best chunk, and that
the chunk splitter behaves at the edges.
"""

from __future__ import annotations

import hashlib

from prl.query.chunk_index import DEFAULT_CHUNK_CHARS, ChunkIndex, chunk_text

_DIM = 64


class FakeEmbedder:
    """Deterministic bag-of-words vector via md5 hashing (stable across runs)."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * _DIM
        for word in text.lower().split():
            h = int(hashlib.md5(word.encode()).hexdigest(), 16) % _DIM
            v[h] += 1.0
        return v


def _index(chunk_chars: int = 20) -> ChunkIndex:
    return ChunkIndex(embedder=FakeEmbedder(), chunk_chars=chunk_chars)


# --- chunk_text helper -----------------------------------------------------

def test_chunk_text_splits_by_size():
    assert chunk_text("abcdefghij", 4) == ["abcd", "efgh", "ij"]


def test_chunk_text_edges():
    assert chunk_text("", 100) == []
    assert chunk_text("abc", 0) == ["abc"]      # non-positive size: one chunk
    assert chunk_text("abc", 100) == ["abc"]    # smaller than one chunk


# --- build / search --------------------------------------------------------

def test_search_collapses_to_conversation_by_best_chunk():
    idx = _index(chunk_chars=20)
    idx.build([
        ("conv-A", "alpha alpha alpha alpha needle alpha alpha alpha alpha alpha"),
        ("conv-B", "beta beta beta beta beta beta beta beta beta beta beta beta"),
    ])
    hits = idx.search("needle", k=5)
    ids = [cid for cid, _ in hits]
    # every returned id is a conversation id, never a "#cN" unit id
    assert all("#" not in cid for cid in ids)
    assert ids[0] == "conv-A"  # the conversation holding the needle chunk wins


def test_buried_passage_recalled():
    """A needle diluted across a long transcript is still recalled because the
    conversation is scored by its best chunk, not a single averaged vector."""
    long_noise = " ".join(["lorem ipsum dolor sit amet"] * 40)
    idx = _index(chunk_chars=30)
    idx.build([
        ("buried", f"{long_noise} canonical-hash-decision {long_noise}"),
        ("other", " ".join(["unrelated words here"] * 40)),
    ])
    hits = idx.search("canonical-hash-decision", k=5)
    assert hits and hits[0][0] == "buried"


def test_empty_chunks_skipped_and_len():
    idx = _index(chunk_chars=10)
    idx.build([("c1", "   "), ("c2", "real content here")])  # c1 is whitespace-only
    ids = [cid for cid, _ in idx.search("real", k=5)]
    assert "c1" not in ids
    assert len(idx) >= 1  # only non-empty chunks indexed


def test_default_chunk_chars_is_500():
    assert DEFAULT_CHUNK_CHARS == 500
    assert ChunkIndex(embedder=FakeEmbedder())._chunk_chars == 500


# --- persistence (R3) ------------------------------------------------------

def test_save_load_round_trip(tmp_path):
    idx = ChunkIndex(embedder=FakeEmbedder(), chunk_chars=25)
    idx.build([("conv-A", "alpha needle alpha alpha"), ("conv-B", "beta beta beta")])
    before = idx.search("needle", k=5)

    path = tmp_path / "chunk.json"
    idx.save(path)
    loaded = ChunkIndex.load(path, embedder=FakeEmbedder())

    assert loaded._chunk_chars == 25  # chunk_chars preserved
    assert loaded.search("needle", k=5) == before  # identical results, no re-embedding
