"""PRL query subpackage.

P4 ships the CLI (``python -m prl``) with the ``index`` and ``status`` commands
that close Phase 1. The structural/semantic query layers (RR bind, adjacency
index, NL recall) arrive in P5+.
"""

from __future__ import annotations

from .chunk_index import DEFAULT_CHUNK_CHARS, ChunkIndex, chunk_text
from .cli import build_parser, cmd_ask, cmd_index, cmd_status, main
from .recall import RecallEngine, RecallHit
from .semantic import Embedder, LocalEmbedder, SemanticError, SemanticIndex
from .structural import PRLAdjacencyIndex, StructuralQuery

__all__ = [
    "main",
    "build_parser",
    "cmd_index",
    "cmd_status",
    "cmd_ask",
    "StructuralQuery",
    "PRLAdjacencyIndex",
    "SemanticIndex",
    "Embedder",
    "LocalEmbedder",
    "SemanticError",
    "ChunkIndex",
    "chunk_text",
    "DEFAULT_CHUNK_CHARS",
    "RecallEngine",
    "RecallHit",
]
