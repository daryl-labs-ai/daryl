"""PRL index subpackage (Phase 1) — local, autonomous.

Scope: walk declared project folders into ``FileNode`` records keyed by
``content_hash = sha256_uri(raw file bytes)`` (P1), and harvest local git
history into ``CommitNode`` records assembled with their edges into a
``ProjectMap`` (P2). This layer is the bottom of the dependency rule
(``index/`` never imports ``collectors/`` or ``query/``) and stays local: git
is read read-only via ``subprocess``, with **no** DSM write, **no** RR access,
**no** embeddings, **no** collectors.
"""

from __future__ import annotations

from .file_index import index_project, make_project_node
from .git_harvest import harvest_commits, is_git_repo
from .mapper import ProjectMap, build_map
from .scanner import DEFAULT_IGNORES, walk_project

__all__ = [
    # P1 — scan + file index
    "walk_project",
    "DEFAULT_IGNORES",
    "index_project",
    "make_project_node",
    # P2 — git harvest + map
    "is_git_repo",
    "harvest_commits",
    "ProjectMap",
    "build_map",
]
