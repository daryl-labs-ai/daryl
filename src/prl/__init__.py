"""PRL — Project Recall Layer (foundation, P0).

PRL maps and recalls scattered project steps (files, commits, chat/coding
sessions) across a local machine. It composes the DSM kernel and the repository
canonical primitive (``dsm_primitives``) — it never modifies the frozen kernel,
the Read Relay, storage, or session_graph.

P0 surface only: config, node/edge models, the DSM-Entry mapping, and the
error taxonomy. No filesystem scan, no DSM write, no RR access, no collectors,
no embeddings — those arrive in later milestones (see
``deliverable/ROADMAP_PRL.md`` and ``deliverable/ADR_PRL_RR_BINDING.md``).
"""

from __future__ import annotations

from .config import PRLConfig
from .exceptions import (
    PRLConfigError,
    PRLEntryMappingError,
    PRLError,
    PRLValidationError,
)
from .types import (
    ACTION_TO_MODEL,
    PRL_ACTION,
    CommitNode,
    Edge,
    EdgeType,
    EntryDraft,
    FileNode,
    NodeType,
    ProjectNode,
    SessionNode,
    ToolName,
    from_entry,
    to_entry,
)

__all__ = [
    # config
    "PRLConfig",
    # exceptions
    "PRLError",
    "PRLConfigError",
    "PRLValidationError",
    "PRLEntryMappingError",
    # enums / literals
    "NodeType",
    "EdgeType",
    "ToolName",
    "PRL_ACTION",
    "ACTION_TO_MODEL",
    # nodes / edges
    "ProjectNode",
    "FileNode",
    "CommitNode",
    "SessionNode",
    "Edge",
    # entry mapping
    "EntryDraft",
    "to_entry",
    "from_entry",
]
