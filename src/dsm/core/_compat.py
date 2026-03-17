"""
DSM Kernel — Portable file-locking compatibility layer.

Replaces direct fcntl usage with filelock (cross-platform: Windows + POSIX).
See audit §9.2 #7: "Support Windows — remplacer fcntl par un locking portable".

Usage in kernel modules:
    from ._compat import portable_lock, portable_lock_fd

    # Context-manager on a lock file path (replaces _shard_lock pattern):
    with portable_lock(lock_path):
        ...

    # Context-manager on an already-open fd/file (replaces inline fcntl.flock):
    with open(path, "r") as f:
        with portable_lock_fd(f):
            data = json.load(f)
"""

import contextlib
import os
from pathlib import Path
from typing import Union

from filelock import FileLock


# Timeout 30s — prevent infinite deadlock; generous enough for any normal I/O.
_DEFAULT_TIMEOUT: float = 30.0


@contextlib.contextmanager
def portable_lock(lock_path: Union[str, Path], *, timeout: float = _DEFAULT_TIMEOUT):
    """
    Acquire an exclusive file lock using a dedicated lockfile.

    Drop-in replacement for the fcntl.flock(LOCK_EX) pattern in storage.py._shard_lock().

    Args:
        lock_path: Path to the lockfile (will be created if absent).
        timeout: Seconds to wait before raising Timeout. -1 = block forever.

    Yields:
        None — the lock is held for the duration of the with-block.
    """
    fl = FileLock(str(lock_path), timeout=timeout)
    fl.acquire()
    try:
        yield
    finally:
        fl.release()


@contextlib.contextmanager
def portable_lock_fd(
    file_obj,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
):
    """
    Acquire an exclusive lock scoped to an open file object.

    Replaces the inline fcntl.flock(f.fileno(), LOCK_SH/LOCK_EX) patterns
    in shard_segments.py and session.py.

    Uses a sidecar lockfile (<original_path>.lock) so the data file itself
    is never locked at the OS level — avoids Windows sharing-violation issues
    and keeps behaviour identical across platforms.

    Note: the original code distinguished LOCK_SH (shared) vs LOCK_EX
    (exclusive). filelock only provides exclusive locks, which is strictly
    more conservative and always correct. Performance impact is negligible
    because the locked sections read/write small JSON files (<1 KB).

    Args:
        file_obj: An open file object whose .name is a real filesystem path.
        timeout: Seconds to wait before raising Timeout.

    Yields:
        None — the lock is held for the duration of the with-block.
    """
    sidecar = str(file_obj.name) + ".lock"
    fl = FileLock(sidecar, timeout=timeout)
    fl.acquire()
    try:
        yield
    finally:
        fl.release()
