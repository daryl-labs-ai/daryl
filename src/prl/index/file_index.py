"""File indexing (P1) — turn a project's files into ``FileNode`` records.

The join key of the whole system: ``content_hash = sha256_uri(raw file bytes)``
(NOT canonical JSON — raw bytes, so a chat-produced blob and an on-disk file
hash identically). Pure read + hash; no DSM write, no RR, no git, no embeddings.

Repo-adaptation note: ``sha256_uri`` is imported from :mod:`prl._canonical`
(which composes the repository primitive ``dsm_primitives``), not from
``dcp.canonical`` — the latter does not exist in this repo. Raw-bytes hashing
means the canonical-JSON scheme never touches ``content_hash``; the shim is used
for consistency, keeping the PRL join key on the ``sha256:`` scheme (distinct
from the kernel's ``v1:`` entry-hash).
"""

from __future__ import annotations

from pathlib import Path

from .._canonical import sha256_uri
from ..config import PRLConfig
from ..types import FileNode, ProjectNode
from .scanner import walk_project


def make_project_node(root_path: str | Path, name: str | None = None) -> ProjectNode:
    """Build a :class:`ProjectNode` with a deterministic ``project_id`` derived
    purely from the path string (no filesystem access)."""
    return ProjectNode.from_root(str(root_path), name=name)


def index_project(project: ProjectNode, config: PRLConfig) -> list[FileNode]:
    """Scan *project*'s root and return one :class:`FileNode` per eligible file.

    ``path`` is stored relative to the project root (POSIX form) for stable,
    cross-platform identity. Files that vanish or become unreadable between the
    walk and the read are skipped. Full re-scan (no incremental diff in V1).
    """
    root = Path(project.root_path)
    nodes: list[FileNode] = []
    for p in walk_project(root, config.index_extensions, config.max_file_bytes):
        try:
            data = p.read_bytes()
            mtime_ms = int(p.stat().st_mtime * 1000)
        except OSError:
            continue
        nodes.append(
            FileNode(
                path=p.relative_to(root).as_posix(),
                content_hash=sha256_uri(data),
                size=len(data),
                mtime_ms=mtime_ms,
                project_id=project.project_id,
            )
        )
    return nodes
