"""PRL index subpackage (Phase 1) — local, autonomous.

P1 scope: walk declared project folders and produce ``FileNode`` records keyed
by ``content_hash = sha256_uri(raw file bytes)``. This layer is the bottom of
the dependency rule (``index/`` never imports ``collectors/`` or ``query/``)
and has **no** external dependency: no DSM write, no RR access, no git
(git harvest is P2), no embeddings, no collectors.
"""

from __future__ import annotations

from .file_index import index_project, make_project_node
from .scanner import DEFAULT_IGNORES, walk_project

__all__ = [
    "walk_project",
    "DEFAULT_IGNORES",
    "index_project",
    "make_project_node",
]
