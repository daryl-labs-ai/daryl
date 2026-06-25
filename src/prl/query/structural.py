"""Structural queries over the PRL map (P5) — RR-backed, read-only.

Per ADR-0001 + ADR §8/§9, PRL reads ONLY through Read Relay, never through
``Storage.read``. This module imports only ``dsm.rr.*`` and *receives* a storage
instance as a parameter (the forbid-storage lint flags importing ``Storage``, not
using one passed in) — so it needs no ``LEGITIMATE_WRITERS`` entry.

RR is a flat index keyed on fixed axes; it has no graph. So PRL builds its own
**in-memory adjacency index** (decision: ADR §9 — no persisted ``.idx`` in P5)
from RR-resolved PRL entries:

    navigate_action("prl.*") -> resolve_entries() -> from_entry() -> maps.

Latest-run semantics: ``index`` appends a fresh full snapshot per run (no delete),
so a project's shard accumulates superseded runs. The adjacency keeps only the
**latest run per shard** (identified by the ``prl.project`` entry with the max
timestamp — each run writes exactly one, stamped at commit wall-clock).
"""

from __future__ import annotations

from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from ..types import CommitNode, Edge, FileNode, ProjectNode, from_entry

_PRL_KINDS = ("prl.project", "prl.file", "prl.commit", "prl.edge")


class PRLAdjacencyIndex:
    """In-memory graph adjacency over the current (latest-run) PRL nodes/edges."""

    def __init__(self) -> None:
        self.projects: dict[str, ProjectNode] = {}           # project_id -> ProjectNode
        self.files_by_hash: dict[str, FileNode] = {}         # content_hash -> FileNode
        self.files_by_project: dict[str, list[FileNode]] = {}  # project_id -> [FileNode]
        self.commits_by_sha: dict[str, CommitNode] = {}      # sha -> CommitNode
        self.commits_by_file: dict[str, list[str]] = {}      # content_hash -> [commit sha]
        self.project_by_file: dict[str, str] = {}            # content_hash -> project_id
        self.edges_by_src: dict[str, list[Edge]] = {}        # src_id -> [Edge]
        self.edges_by_dst: dict[str, list[Edge]] = {}        # dst_id -> [Edge]

    def add_node(self, node: ProjectNode | FileNode | CommitNode) -> None:
        if isinstance(node, ProjectNode):
            self.projects[node.project_id] = node
        elif isinstance(node, FileNode):
            self.files_by_hash[node.content_hash] = node
            self.files_by_project.setdefault(node.project_id, []).append(node)
        elif isinstance(node, CommitNode):
            self.commits_by_sha[node.sha] = node

    def add_edge(self, edge: Edge) -> None:
        self.edges_by_src.setdefault(edge.src_id, []).append(edge)
        self.edges_by_dst.setdefault(edge.dst_id, []).append(edge)
        if edge.edge_type == "modified":  # src = commit sha, dst = file content_hash
            self.commits_by_file.setdefault(edge.dst_id, []).append(edge.src_id)
        elif edge.edge_type == "belongs_to":  # src = file content_hash, dst = project_id
            self.project_by_file[edge.src_id] = edge.dst_id


def _latest_run_id(entries: list[Any]) -> str | None:
    """Latest run for a shard = session_id of the max-timestamp ``prl.project``
    entry (each run writes exactly one, stamped at commit wall-clock). Falls back
    to the max-timestamp entry overall if no project entry is present."""
    projects = [e for e in entries if (e.metadata or {}).get("action_name") == "prl.project"]
    pool = projects or entries
    if not pool:
        return None
    return max(pool, key=lambda e: e.timestamp).session_id


def _build_adjacency(navigator: RRNavigator) -> PRLAdjacencyIndex:
    records: list[dict] = []
    for kind in _PRL_KINDS:
        records.extend(navigator.navigate_action(kind))
    entries = navigator.resolve_entries(records)

    by_shard: dict[str, list[Any]] = {}
    for e in entries:
        by_shard.setdefault(getattr(e, "shard", ""), []).append(e)

    adj = PRLAdjacencyIndex()
    for ents in by_shard.values():
        latest = _latest_run_id(ents)
        for e in ents:
            if e.session_id != latest:
                continue  # superseded run — skip stale snapshot
            node = from_entry(e)
            if isinstance(node, Edge):
                adj.add_edge(node)
            else:
                adj.add_node(node)
    return adj


class StructuralQuery:
    """Answers structural questions over the PRL map from an in-memory adjacency
    index rebuilt from RR on construction.

    Args:
        storage: a DSM ``Storage`` instance (received, never imported here).
        index_dir: directory for RR's derived index files (outside shard storage).
    """

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RRNavigator | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()  # fresh build — always current (no cached .idx reliance)
            _navigator = RRNavigator(builder, storage)
        self._adj = _build_adjacency(_navigator)

    # -- queries -------------------------------------------------------------

    def files_of_project(self, project_id: str) -> list[FileNode]:
        return list(self._adj.files_by_project.get(project_id, []))

    def commits_touching(self, content_hash: str) -> list[CommitNode]:
        shas = self._adj.commits_by_file.get(content_hash, [])
        return [self._adj.commits_by_sha[s] for s in shas if s in self._adj.commits_by_sha]

    def project_of_file(self, content_hash: str) -> ProjectNode | None:
        pid = self._adj.project_by_file.get(content_hash)
        return self._adj.projects.get(pid) if pid else None

    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[Edge]:
        out = self._adj.edges_by_src.get(node_id, []) + self._adj.edges_by_dst.get(node_id, [])
        if edge_type is not None:
            out = [e for e in out if e.edge_type == edge_type]
        return out
