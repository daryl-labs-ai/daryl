"""Project map assembly (P2).

Combines the P1 file index and the P2 git harvest into a single
:class:`ProjectMap` — nodes plus the edges that wire them together:

* ``modified`` : commit ``sha`` → file ``content_hash`` (a commit touched a file)
* ``belongs_to`` : file ``content_hash`` → project ``project_id``

Pure composition over ``index_project`` + ``harvest_commits``; no DSM write, no
RR, no embeddings. The session/edge encoding into DSM ``Entry`` objects is P3.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..config import PRLConfig
from ..types import CommitNode, Edge, FileNode, ProjectNode
from .file_index import index_project
from .git_harvest import harvest_commits, is_git_repo


class ProjectMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectNode
    files: list[FileNode]
    commits: list[CommitNode]
    edges: list[Edge]


def _link_commits_to_files(
    commits: list[CommitNode], files: list[FileNode]
) -> list[Edge]:
    """One ``modified`` edge per (commit, indexed file it touched).

    Commits referencing files that are not indexed (e.g. excluded extensions,
    deleted files) produce no edge — the join is on the P1 file set.
    """
    by_path: dict[str, FileNode] = {f.path: f for f in files}
    edges: list[Edge] = []
    for c in commits:
        for fp in c.files:
            f = by_path.get(fp)
            if f is not None:
                edges.append(
                    Edge(
                        edge_type="modified",
                        src_id=c.sha,
                        dst_id=f.content_hash,
                        evidence={"path": fp},
                    )
                )
    return edges


def build_map(project: ProjectNode, config: PRLConfig) -> ProjectMap:
    """Assemble the full :class:`ProjectMap` for *project*.

    Files come from the P1 scan; commits from git when the root is a repo
    (otherwise ``[]``). Edges = ``modified`` (commit→file) + ``belongs_to``
    (file→project).
    """
    files = index_project(project, config)
    commits = (
        harvest_commits(project)
        if is_git_repo(Path(project.root_path))
        else []
    )
    edges = _link_commits_to_files(commits, files)
    edges += [
        Edge(edge_type="belongs_to", src_id=f.content_hash, dst_id=project.project_id)
        for f in files
    ]
    return ProjectMap(project=project, files=files, commits=commits, edges=edges)
