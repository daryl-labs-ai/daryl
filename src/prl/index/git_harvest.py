"""Git commit harvesting (P2).

Read-only extraction of a project's git history into :class:`CommitNode`
records, via ``git log`` over ``subprocess`` (``shell=False``, no shell
expansion). No network, no writes to the repo, no DSM/RR/embeddings.

Parsing strategy
----------------
``git log`` is asked for a machine-parseable format using ASCII control
separators that never appear in commit metadata:

* ``0x1e`` (record separator) prefixes each commit,
* ``0x1f`` (unit separator) separates the fixed fields,
* ``--name-only`` appends the touched paths on the following lines.

``-c core.quotePath=false`` keeps non-ASCII paths literal (no octal quoting),
so file paths match the POSIX paths produced by the P1 file index.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..types import CommitNode, ProjectNode

_RECORD_SEP = "\x1e"
_UNIT_SEP = "\x1f"
# %H sha, %an author name, %at author unix-time, %s subject
_PRETTY = f"format:{_RECORD_SEP}%H{_UNIT_SEP}%an{_UNIT_SEP}%at{_UNIT_SEP}%s"

_GIT_TIMEOUT_S = 30


def is_git_repo(root: Path) -> bool:
    """True if *root* is inside a git work tree. Pure read; never raises."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and out.stdout.strip() == "true"


def harvest_commits(project: ProjectNode, limit: int | None = None) -> list[CommitNode]:
    """Return the project's commits, newest first, as :class:`CommitNode`.

    Returns ``[]`` for a non-repo, an empty repo (no commits yet), or any git
    failure — never raises on the happy path. Paths in ``files`` are
    repo-root-relative POSIX strings (matching P1 ``FileNode.path``).
    """
    root = Path(project.root_path)
    cmd = [
        "git",
        "-c",
        "core.quotePath=false",
        "-C",
        str(root),
        "log",
        f"--pretty={_PRETTY}",
        "--name-only",
    ]
    if limit is not None:
        cmd += ["-n", str(limit)]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0 or not proc.stdout:
        return []

    return _parse_log(proc.stdout, project.project_id)


def _parse_log(stdout: str, project_id: str) -> list[CommitNode]:
    commits: list[CommitNode] = []
    for chunk in stdout.split(_RECORD_SEP):
        if not chunk.strip():
            continue
        lines = chunk.split("\n")
        header = lines[0]
        parts = header.split(_UNIT_SEP)
        if len(parts) != 4:
            continue  # malformed record — skip defensively
        sha, author, at, subject = parts
        try:
            ts_ms = int(at) * 1000
        except ValueError:
            continue
        files = tuple(ln for ln in lines[1:] if ln.strip())
        commits.append(
            CommitNode(
                sha=sha,
                author=author,
                ts_ms=ts_ms,
                message=subject,
                files=files,
                project_id=project_id,
            )
        )
    return commits
