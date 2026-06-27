"""Passage (chunk) index — Retrieval v2 (ADR-PRL-0006), milestone R1.

The eval (experiments B→F) proved that **the passage is the recall unit**: a buried
decision that a single conversation vector misses is recalled when the transcript is
split into chunks and the conversation is scored by its *best* chunk. This module
ports that proven design into production.

Design (additive, kernel-frozen, P6 schema untouched):
- ``ChunkIndex`` composes the P8 ``SemanticIndex`` — one vector per chunk, ids of the
  form ``"<session_id>#c<n>"``. ``search`` collapses chunk hits back to the
  conversation by its best chunk, so it exposes the **same conversation-level
  ``search(query, k)`` interface as SemanticIndex** and RecallEngine is unchanged.
- Full transcript text comes from a ``FullTextSource`` collector (see
  ``collectors.base``), never from ``SessionNode`` — the P6 node stays preview-only.

ADR-PRL-0006 frozen default: ``chunk_chars = 500``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .semantic import Embedder, SemanticIndex

# Measured optimum (ADR-PRL-0006): smaller chunks recall buried decisions better.
DEFAULT_CHUNK_CHARS = 500


def chunk_text(text: str, chunk_chars: int) -> list[str]:
    """Split *text* into contiguous chunks of ~``chunk_chars`` (no overlap, v1)."""
    text = text or ""
    if not text or chunk_chars <= 0:
        return [text] if text else []
    return [text[i:i + chunk_chars] for i in range(0, len(text), chunk_chars)]


class ChunkIndex:
    """Passage-level index: each conversation is indexed as several chunks; a
    conversation's score is its best-matching chunk.

    Wraps :class:`SemanticIndex`, so the heavy ML dependency stays isolated (the
    embedder is injected) and persistence is inherited in a later milestone (R3).
    Presents a conversation-level :meth:`search`, identical in shape to
    ``SemanticIndex.search``, so downstream code (RecallEngine, FusionIndex) needs
    no special-casing.
    """

    def __init__(self, embedder: Embedder | None = None, chunk_chars: int = DEFAULT_CHUNK_CHARS):
        self._idx = SemanticIndex(embedder)
        self._chunk_chars = chunk_chars

    def __len__(self) -> int:
        return len(self._idx)

    def build(self, conv_items: list[tuple[str, str]]) -> None:
        """Index ``(session_id, full_text)`` pairs by chunking each full text."""
        units: list[tuple[str, str]] = []
        for session_id, text in conv_items:
            for i, ch in enumerate(chunk_text(text, self._chunk_chars)):
                if ch.strip():
                    units.append((f"{session_id}#c{i}", ch))
        self.build_units(units)

    def build_units(self, unit_items: list[tuple[str, str]]) -> None:
        """Index arbitrary units whose id is ``"<session_id>#<suffix>"``. Search
        collapses to the conversation by its best unit."""
        self._idx.build(unit_items)

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        """Return up to *k* ``(session_id, score)`` pairs, best chunk per
        conversation, highest score first."""
        raw = self._idx.search(query, k=max(k * 20, 200))  # over-fetch units, then collapse
        best: dict[str, float] = {}
        for unit_id, score in raw:
            session_id = unit_id.rsplit("#", 1)[0]  # strip the chunk suffix
            if session_id not in best or score > best[session_id]:
                best[session_id] = score
        return sorted(best.items(), key=lambda t: t[1], reverse=True)[:k]

    # -- persistence (JSON) — R3, mirrors SemanticIndex -----------------------

    def save(self, path: Any) -> None:
        """Persist the chunk vectors (expensive to recompute) + ``chunk_chars``."""
        Path(path).write_text(
            json.dumps({"chunk_chars": self._chunk_chars, "index": self._idx.to_dict()}),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Any, embedder: Embedder | None = None) -> "ChunkIndex":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        obj = cls(embedder=embedder, chunk_chars=int(data.get("chunk_chars", DEFAULT_CHUNK_CHARS)))
        obj._idx = SemanticIndex.from_dict(data.get("index", {}), embedder)
        return obj
