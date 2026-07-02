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
    cmd_governance,
    cmd_object,
    cmd_objects,
    cmd_subject_standings,
    main,
)
from .consultation_read import ConsultationQuery, ConsultationView, render_consultations
from .explain_read import ExplainQuery, Explanation, ProposalFact, render_explanation
from .fusion_index import DEFAULT_PREVIEW_GATE, DEFAULT_RRF_K, FusionIndex
from .governance_read import (
    ClaimGovernance,
    GovernanceQuery,
    SubjectGovernance,
    derive_governance_state,
    derive_subject_governance_state,
    render_claim_governance,
    render_subject_governance,
)
from .knowledge_object import (
    ClaimLine,
    KnowledgeObjectProjection,
    KnowledgeObjectQuery,
    KnowledgeObjectSummary,
    TimelineItem,
    object_reason,
    render_knowledge_object,
    render_objects,
)
from .recall import RecallEngine, RecallHit
from .semantic import Embedder, LocalEmbedder, SemanticError, SemanticIndex
from .standing_read import (
    RegistryProjection,
    ResolutionFact,
    StandingIndex,
    StandingQuery,
    StandingView,
    derive_governed_standing,
    derive_standing,
    detect_conflict,
    render_standing,
)
from .structural import PRLAdjacencyIndex, StructuralQuery
from .subject_read import (
    ClaimStanding,
    SubjectStandingsQuery,
    SubjectStandingsView,
    derive_object_standing,
    detect_coherence,
    render_subject_standings,
)

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
    "cmd_subject_standings",
    "cmd_governance",
    "cmd_objects",
    "cmd_object",
    "cmd_project_sqlite",
    "StandingQuery",
    "StandingIndex",
    "StandingView",
    "ResolutionFact",
    "RegistryProjection",
    "derive_standing",
    "derive_governed_standing",
    "detect_conflict",
    "render_standing",
    "ExplainQuery",
    "Explanation",
    "ProposalFact",
    "render_explanation",
    "SubjectStandingsQuery",
    "SubjectStandingsView",
    "ClaimStanding",
    "detect_coherence",
    "derive_object_standing",
    "render_subject_standings",
    "GovernanceQuery",
    "ClaimGovernance",
    "SubjectGovernance",
    "derive_governance_state",
    "derive_subject_governance_state",
    "render_claim_governance",
    "render_subject_governance",
    "KnowledgeObjectQuery",
    "KnowledgeObjectProjection",
    "KnowledgeObjectSummary",
    "ClaimLine",
    "TimelineItem",
    "object_reason",
    "render_objects",
    "render_knowledge_object",
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
