"""Filesystem scanner for declared project folders (P1).

Pure traversal: yields the files PRL should index, filtered by extension, size,
and an ignore set. No hashing, no model building, no I/O beyond ``os.walk`` and
``stat`` — :mod:`prl.index.file_index` consumes this.

Determinism: results are yielded in a stable, sorted order (directories and
files sorted by name) so an index build is reproducible run-to-run.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

# Directory and file names skipped anywhere in the tree.
DEFAULT_IGNORES: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".hypothesis",
        ".mypy_cache",
        ".ruff_cache",
        ".DS_Store",
    }
)


def walk_project(
    root: Path,
    extensions: tuple[str, ...],
    max_bytes: int,
    ignores: frozenset[str] | set[str] = DEFAULT_IGNORES,
) -> Iterator[Path]:
    """Yield files under *root* eligible for indexing.

    A file is yielded when:

    * its suffix (case-insensitive) is in *extensions*,
    * it is not inside (nor named as) an ignored entry,
    * its size is ``<= max_bytes``.

    Ignored directories are pruned from the walk (not descended into). Symlinks
    are not followed. Unreadable entries (vanished mid-walk, permission denied)
    are skipped silently rather than raising.
    """
    root = Path(root)
    ext_set = {e.lower() for e in extensions}

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune ignored directories in place + keep traversal order stable.
        dirnames[:] = sorted(d for d in dirnames if d not in ignores)
        for fname in sorted(filenames):
            if fname in ignores:
                continue
            p = Path(dirpath) / fname
            if p.suffix.lower() not in ext_set:
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size > max_bytes:
                continue
            yield p
