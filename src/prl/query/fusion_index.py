"""Retrieval Policy v2.0 — chunk-primary, preview-gated fusion (ADR-PRL-0006, R2).

This is the **measured, ratified** production policy, not an exploration surface.
Experiments A→F (see ``PRL_RETRIEVAL_V2_FINDINGS.md``) eliminated every simpler
design; the winner is an *asymmetric* combiner:

- the **passage (chunk) retriever is the base ranker** — it owns buried decisions;
- the **conversation (preview) retriever adds a bonus only when its rank ≤ gate**
  (a title-evident match) — and a poor preview rank contributes **nothing**, so a
  misleading title can never penalize a strong chunk hit.

Invariant (ADR-PRL-0006 §4): fusion never *subtracts* from a result's chunk score.
The open title-mismatch frontier (Q14/Q15) is a recall problem reserved for a future
two-phase design (ADR §5) — it is deliberately **not** addressed here. R2 ships the
best demonstrated level, nothing more.

``FusionIndex`` exposes the same ``search(query, k)`` interface as ``SemanticIndex``
(it collapses to conversation ids), so ``RecallEngine`` consumes it unchanged.
"""

from __future__ import annotations

from .chunk_index import ChunkIndex
from .semantic import SemanticIndex

# Frozen optima (ADR-PRL-0006 §2). Configuration, not constants — overridable via
# PRLConfig — but these are the ratified defaults, not knobs for re-exploration.
DEFAULT_PREVIEW_GATE = 10
DEFAULT_RRF_K = 10


class FusionIndex:
    """Chunk-primary, preview-gated rank fusion of two independent retrievers.

    Args:
        preview: a conversation-level retriever (title + preview), e.g. SemanticIndex.
        chunk: a passage-level retriever (ChunkIndex).
        preview_gate: preview adds a reciprocal-rank bonus only when its rank ≤ this.
        rrf_k: the reciprocal-rank-fusion constant (score contribution = 1/(k+rank)).

    Both retrievers only need a ``search(query, k) -> list[(id, score)]`` method.
    """

    def __init__(
        self,
        preview: SemanticIndex,
        chunk: ChunkIndex,
        *,
        preview_gate: int = DEFAULT_PREVIEW_GATE,
        rrf_k: int = DEFAULT_RRF_K,
    ):
        self._preview = preview
        self._chunk = chunk
        self._gate = preview_gate
        self._k = rrf_k

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        depth = max(k * 10, 100)
        prev_rank = {cid: r for r, (cid, _s) in enumerate(self._preview.search(query, k=depth), start=1)}
        chunk_rank = {cid: r for r, (cid, _s) in enumerate(self._chunk.search(query, k=depth), start=1)}

        # Candidates: everything chunk found, PLUS title-evident preview hits (rank ≤ gate),
        # so a clean title match still surfaces when chunking dilutes it.
        candidates = set(chunk_rank) | {c for c, r in prev_rank.items() if r <= self._gate}

        scores: dict[str, float] = {}
        for cid in candidates:
            score = 1.0 / (self._k + chunk_rank[cid]) if cid in chunk_rank else 0.0
            pr = prev_rank.get(cid)
            if pr is not None and pr <= self._gate:  # gated, additive — never subtractive
                score += 1.0 / (self._k + pr)
            scores[cid] = score

        if not scores:
            return []
        top = max(scores.values()) or 1.0  # max-normalize so the binder boost stays a tiebreaker
        ranked = sorted(((cid, sc / top) for cid, sc in scores.items()),
                        key=lambda t: t[1], reverse=True)
        return ranked[:k]
