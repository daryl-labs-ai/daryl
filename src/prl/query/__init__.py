"""PRL query subpackage.

P4 ships the CLI (``python -m prl``) with the ``index`` and ``status`` commands
that close Phase 1. The structural/semantic query layers (RR bind, adjacency
index, NL recall) arrive in P5+.
"""

from __future__ import annotations

from .cli import build_parser, cmd_index, cmd_status, main
from .semantic import Embedder, LocalEmbedder, SemanticError, SemanticIndex
from .structural import PRLAdjacencyIndex, StructuralQuery

__all__ = [
    "main",
    "build_parser",
    "cmd_index",
    "cmd_status",
    "StructuralQuery",
    "PRLAdjacencyIndex",
    "SemanticIndex",
    "Embedder",
    "LocalEmbedder",
    "SemanticError",
]
