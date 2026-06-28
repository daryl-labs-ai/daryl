"""PRL query subpackage.

P4 ships the CLI (``python -m prl``) with the ``index`` and ``status`` commands
that close Phase 1. The structural/semantic query layers (RR bind, adjacency
index, NL recall) arrive in P5+.
"""

from __future__ import annotations

from .chunk_index import DEFAULT_CHUNK_CHARS, ChunkIndex, chunk_text
from .cli import (
    build_parser,
    cmd_ask,
    cmd_consult,
    cmd_consultations,
    cmd_explain,
    cmd_index,
    cmd_project_sqlite,
    cmd_resolve,
    cmd_standing,
    cmd_status,
    main,
)
from .consultation_read import ConsultationQuery, ConsultationView, render_consultations
from .explain_read import ExplainQuery, Explanation, ProposalFact, render_explanation
from .fusion_index import DEFAULT_PREVIEW_GATE, DEFAULT_RRF_K, FusionIndex
from .recall import RecallEngine, RecallHit
from .semantic import Embedder, LocalEmbedder, SemanticError, SemanticIndex
from .standing_read import (
    RegistryProjection,
    ResolutionFact,
    StandingQuery,
    StandingView,
    render_standing,
)
from .structural import PRLAdjacencyIndex, StructuralQuery

__all__ = [
    "main",
    "build_parser",
    "cmd_index",
    "cmd_status",
    "cmd_ask",
    "cmd_consultations",
    "cmd_consult",
    "cmd_resolve",
    "cmd_standing",
    "cmd_explain",
    "cmd_project_sqlite",
    "StandingQuery",
    "StandingView",
    "ResolutionFact",
    "RegistryProjection",
    "render_standing",
    "ExplainQuery",
    "Explanation",
    "ProposalFact",
    "render_explanation",
    "ConsultationQuery",
    "ConsultationView",
    "render_consultations",
    "StructuralQuery",
    "PRLAdjacencyIndex",
    "SemanticIndex",
    "Embedder",
    "LocalEmbedder",
    "SemanticError",
    "ChunkIndex",
    "chunk_text",
    "DEFAULT_CHUNK_CHARS",
    "FusionIndex",
    "DEFAULT_PREVIEW_GATE",
    "DEFAULT_RRF_K",
    "RecallEngine",
    "RecallHit",
]
