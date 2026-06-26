"""Natural-language recall (P9) — closes the PRL MVP loop.

    collector → binder → semantic search → structural enrichment → answer

``RecallEngine`` is a **pure orchestrator** (dependency-injected): it ranks
sessions for a natural-language question by combining the P8 semantic score with
the P7 binder edges (links to files/commits + their evidence). No generative LLM,
no multi-turn, no persisted recall state — just orchestration, ranking, and an
explainable output (``why`` = semantic score + binder evidence).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..types import CommitNode, Edge, FileNode, SessionNode
from .semantic import SemanticIndex

# How much a strong binder link nudges a hit above its raw semantic score.
# Semantic relevance dominates; links are a tiebreaker/booster.
_LINK_WEIGHT = 0.20


@dataclass(frozen=True)
class RecallHit:
    session: SessionNode
    score: float
    semantic_score: float
    linked_files: list[FileNode] = field(default_factory=list)
    linked_commits: list[CommitNode] = field(default_factory=list)
    why: list[str] = field(default_factory=list)


class RecallEngine:
    """Ranks sessions for a NL question: semantic search + binder enrichment.

    Args:
        semantic: a SemanticIndex built over sessions (id = session_id).
        sessions: session_id -> SessionNode.
        edges: binder ``references`` edges (src = session_id, dst = file
            content_hash | commit sha), each with confidence + evidence.
        files: content_hash -> FileNode (for enrichment).
        commits: sha -> CommitNode (for enrichment).
    """

    def __init__(
        self,
        semantic: SemanticIndex,
        sessions: dict[str, SessionNode],
        edges: list[Edge],
        *,
        files: dict[str, FileNode] | None = None,
        commits: dict[str, CommitNode] | None = None,
    ):
        self._semantic = semantic
        self._sessions = sessions
        self._files = files or {}
        self._commits = commits or {}
        self._edges_by_src: dict[str, list[Edge]] = {}
        for e in edges:
            self._edges_by_src.setdefault(e.src_id, []).append(e)

    def ask(self, question: str, k: int = 5) -> list[RecallHit]:
        """Return up to *k* explainable hits, best first."""
        hits: list[RecallHit] = []
        for session_id, sem_score in self._semantic.search(question, k=k):
            session = self._sessions.get(session_id)
            if session is None:
                continue  # indexed id with no session record — skip safely
            session_edges = self._edges_by_src.get(session_id, [])

            linked_files = [
                self._files[e.dst_id] for e in session_edges if e.dst_id in self._files
            ]
            linked_commits = [
                self._commits[e.dst_id] for e in session_edges if e.dst_id in self._commits
            ]

            link_boost = max((e.confidence for e in session_edges), default=0.0)
            score = sem_score + _LINK_WEIGHT * link_boost

            why = [f"semantic match (score {sem_score:.3f})"]
            for e in session_edges:
                method = e.evidence.get("method", "?")
                why.append(f"{method} → {e.dst_id[:16]} (conf {e.confidence:.2f})")

            hits.append(
                RecallHit(
                    session=session,
                    score=score,
                    semantic_score=sem_score,
                    linked_files=linked_files,
                    linked_commits=linked_commits,
                    why=why,
                )
            )

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]
