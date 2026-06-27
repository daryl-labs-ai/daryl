"""R2 tests — Retrieval Policy v2.0 (chunk-primary, preview-gated fusion).

Two layers:
- the policy properties are tested with deterministic StubRetrievers (exact ranks),
  the cleanest way to prove the asymmetric combiner behaves as ADR-PRL-0006 §4 says;
- the integration is tested with a real preview SemanticIndex + ChunkIndex over a
  FakeEmbedder, asserting RecallEngine consumes FusionIndex unchanged.
"""

from __future__ import annotations

import hashlib

from prl.query.fusion_index import (
    DEFAULT_PREVIEW_GATE,
    DEFAULT_RRF_K,
    FusionIndex,
)
from prl.query.chunk_index import ChunkIndex
from prl.query.recall import RecallEngine
from prl.query.semantic import SemanticIndex
from prl.types import SessionNode


class StubRetriever:
    """Returns a fixed ranking; lets us drive exact preview/chunk ranks."""

    def __init__(self, order: list[str]):
        self._order = order

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        return [(cid, 1.0) for cid in self._order[:k]]


def _rank_of(results: list[tuple[str, float]], cid: str) -> int | None:
    ids = [c for c, _ in results]
    return ids.index(cid) + 1 if cid in ids else None


# --- policy properties (ADR-PRL-0006 §4) -----------------------------------

def test_defaults_are_frozen_optima():
    assert DEFAULT_PREVIEW_GATE == 10
    assert DEFAULT_RRF_K == 10


def test_gated_preview_lifts_title_evident_case():
    """Preview rank 1 (≤ gate) bonuses a gold that chunking diluted to rank 9."""
    preview = StubRetriever(["G"] + [f"a{i}" for i in range(8)])
    chunk = StubRetriever([f"b{i}" for i in range(8)] + ["G"])
    fx = FusionIndex(preview, chunk, preview_gate=5, rrf_k=10)
    assert _rank_of(fx.search("q", k=10), "G") == 1


def test_misleading_title_not_dragged_below_a_mediocre_competitor():
    """Gold strong in chunk but with a misleading (out-of-gate) title must stay
    above a competitor that is mediocre in both — what symmetric RRF-sum failed."""
    # chunk: G #3, Y #4 ; preview: both out of gate (Y #6, G #20)
    chunk = StubRetriever(["c1", "c2", "G", "Y", "c5"])
    preview = StubRetriever(["p1", "p2", "p3", "p4", "p5", "Y"] + [f"x{i}" for i in range(13)] + ["G"])
    fx = FusionIndex(preview, chunk, preview_gate=5, rrf_k=10)
    res = fx.search("q", k=10)
    assert _rank_of(res, "G") < _rank_of(res, "Y")


def test_out_of_gate_preview_adds_no_bonus():
    """A gold's preview rank *beyond the gate* contributes nothing — identical
    result to the gold being absent from preview (same candidate field). This is
    the precise invariant: the gated bonus is never subtractive."""
    chunk = StubRetriever(["A", "B", "G", "D"])
    # gate=1: only preview rank 1 qualifies. A (rank 1) is also a chunk member, so
    # the candidate set is unchanged; G at preview rank 2 is out of gate.
    g_out = FusionIndex(StubRetriever(["A", "G"]), chunk, preview_gate=1, rrf_k=10).search("q", 10)
    g_absent = FusionIndex(StubRetriever(["A"]), chunk, preview_gate=1, rrf_k=10).search("q", 10)
    assert g_out == g_absent  # G's out-of-gate preview rank changed nothing


def test_in_gate_preview_only_helps():
    """A within-gate preview rank can only raise (never lower) the bonused item,
    holding the competitor field fixed."""
    chunk = StubRetriever(["A", "B", "G", "D"])
    base = FusionIndex(StubRetriever([]), chunk).search("q", 10)        # G earns no bonus
    boosted = FusionIndex(StubRetriever(["G"]), chunk).search("q", 10)  # G preview rank 1 ≤ gate
    assert _rank_of(boosted, "G") <= _rank_of(base, "G")


def test_empty_inputs_return_empty():
    fx = FusionIndex(StubRetriever([]), StubRetriever([]), preview_gate=10, rrf_k=10)
    assert fx.search("q", k=5) == []


def test_returns_conversation_ids_not_unit_ids():
    fx = FusionIndex(StubRetriever(["conv-A"]), StubRetriever(["conv-B", "conv-A"]))
    ids = [c for c, _ in fx.search("q", k=5)]
    assert ids and all("#" not in c for c in ids)


# --- integration: RecallEngine consumes FusionIndex unchanged --------------

_DIM = 64


class FakeEmbedder:
    def embed(self, texts):
        return [self._vec(t) for t in texts]

    def _vec(self, text):
        v = [0.0] * _DIM
        for w in text.lower().split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % _DIM] += 1.0
        return v


def test_recall_engine_consumes_fusion_index():
    """Same .search() interface ⇒ RecallEngine (unchanged) ranks via FusionIndex.
    Also a buried-decision check: the needle lives only deep in s1's transcript."""
    sessions = [
        SessionNode(session_id="s1", tool="chatgpt", title="vague title",
                    started_ms=1, text_preview="small talk about nothing in particular"),
        SessionNode(session_id="s2", tool="chatgpt", title="lunch",
                    started_ms=1, text_preview="pizza salad menu"),
    ]
    noise = " ".join(["small talk about nothing"] * 30)
    full = {"s1": f"{noise} canonicalhashdecision rationale {noise}", "s2": "pizza salad menu"}

    emb = FakeEmbedder()
    preview = SemanticIndex(emb)
    preview.build([(s.session_id, f"{s.title or ''} {s.text_preview}") for s in sessions])
    chunk = ChunkIndex(emb, chunk_chars=30)
    chunk.build([(s.session_id, f"{s.title or ''} {full[s.session_id]}") for s in sessions])
    fusion = FusionIndex(preview, chunk, preview_gate=10, rrf_k=10)

    engine = RecallEngine(fusion, {s.session_id: s for s in sessions}, [])
    hits = engine.ask("canonicalhashdecision", k=2)
    assert hits and hits[0].session.session_id == "s1"  # buried decision recalled via chunk
