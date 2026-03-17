"""
Tests W-7: Portable file locking (Windows compatibility).

Validates that the _compat module provides correct locking semantics
and that all kernel modules no longer depend on fcntl.
"""

import ast
import json
import os
import threading
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. _compat module unit tests
# ---------------------------------------------------------------------------


class TestPortableLock:
    """Tests for portable_lock() context manager."""

    def test_lock_acquires_and_releases(self, tmp_path):
        """Basic acquire/release cycle completes without error."""
        from dsm.core._compat import portable_lock

        lock_path = tmp_path / "test.lock"
        with portable_lock(lock_path):
            assert lock_path.exists()

    def test_lock_creates_lockfile(self, tmp_path):
        """Lockfile is created if absent (assert while held — filelock may remove on release)."""
        from dsm.core._compat import portable_lock

        lock_path = tmp_path / "new.lock"
        assert not lock_path.exists()
        with portable_lock(lock_path):
            assert lock_path.exists()

    def test_lock_serializes_threads(self, tmp_path):
        """Two threads cannot hold the same lock simultaneously."""
        from dsm.core._compat import portable_lock

        lock_path = tmp_path / "serial.lock"
        results = []
        barrier = threading.Barrier(2, timeout=5)

        def worker(worker_id):
            barrier.wait()
            with portable_lock(lock_path):
                results.append(f"enter-{worker_id}")
                time.sleep(0.05)
                results.append(f"exit-{worker_id}")

        t1 = threading.Thread(target=worker, args=(1,))
        t2 = threading.Thread(target=worker, args=(2,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert len(results) == 4
        for i in range(0, len(results), 2):
            assert results[i].startswith("enter"), (
                f"Expected enter at index {i}, got {results[i]}"
            )
            assert results[i + 1].startswith("exit"), (
                f"Expected exit at index {i+1}, got {results[i + 1]}"
            )
            # Same worker ID for each enter/exit pair (no interleaving)
            assert results[i].split("-")[1] == results[i + 1].split("-")[1], (
                f"Interleaved workers: {results}"
            )

    def test_lock_not_reentrant_same_thread(self, tmp_path):
        """filelock is not reentrant — same thread re-acquiring times out."""
        import filelock

        from dsm.core._compat import portable_lock

        lock_path = tmp_path / "reentrant.lock"
        with portable_lock(lock_path):
            with pytest.raises(filelock.Timeout):
                with portable_lock(lock_path, timeout=0.1):
                    pass


class TestPortableLockFd:
    """Tests for portable_lock_fd() context manager."""

    def test_lock_fd_read(self, tmp_path):
        """Lock on an open file for reading."""
        from dsm.core._compat import portable_lock_fd

        data_path = tmp_path / "data.json"
        data_path.write_text('{"key": "value"}', encoding="utf-8")
        with open(data_path, "r", encoding="utf-8") as f:
            with portable_lock_fd(f):
                result = json.load(f)
        assert result == {"key": "value"}

    def test_lock_fd_write(self, tmp_path):
        """Lock on an open file for writing."""
        from dsm.core._compat import portable_lock_fd

        data_path = tmp_path / "out.json"
        with open(data_path, "w", encoding="utf-8") as f:
            with portable_lock_fd(f):
                json.dump({"a": 1}, f)
                f.flush()
                os.fsync(f.fileno())
        assert json.loads(data_path.read_text(encoding="utf-8")) == {"a": 1}

    def test_sidecar_lockfile_created(self, tmp_path):
        """Sidecar .lock file is created next to the data file (assert while held)."""
        from dsm.core._compat import portable_lock_fd

        data_path = tmp_path / "meta.json"
        data_path.write_text("{}", encoding="utf-8")
        sidecar = tmp_path / "meta.json.lock"
        with open(data_path, "r", encoding="utf-8") as f:
            with portable_lock_fd(f):
                assert sidecar.exists()

    def test_lock_fd_serializes_threads(self, tmp_path):
        """Two threads using portable_lock_fd on same file are serialized."""
        from dsm.core._compat import portable_lock_fd

        data_path = tmp_path / "shared.json"
        data_path.write_text("0", encoding="utf-8")
        barrier = threading.Barrier(2, timeout=5)

        def increment():
            barrier.wait()
            for _ in range(50):
                with open(data_path, "r+", encoding="utf-8") as f:
                    with portable_lock_fd(f):
                        val = int(f.read().strip())
                        f.seek(0)
                        f.write(str(val + 1))
                        f.truncate()
                        f.flush()

        t1 = threading.Thread(target=increment)
        t2 = threading.Thread(target=increment)
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        final = int(data_path.read_text(encoding="utf-8").strip())
        assert final == 100, f"Expected 100, got {final} — lock did not serialize"


# ---------------------------------------------------------------------------
# 2. No-fcntl-import audit
# ---------------------------------------------------------------------------


class TestNoFcntlImport:
    """Verify that kernel modules no longer import fcntl directly."""

    KERNEL_FILES = [
        "src/dsm/core/storage.py",
        "src/dsm/core/shard_segments.py",
        "src/dsm/core/session.py",
    ]

    @pytest.mark.parametrize("rel_path", KERNEL_FILES)
    def test_no_fcntl_import(self, rel_path):
        """AST-parse each kernel file and assert 'fcntl' is not imported."""
        here = Path(__file__).resolve()
        repo_root = here.parent.parent.parent
        filepath = repo_root / rel_path
        if not filepath.exists():
            pytest.skip(f"{rel_path} not found (running outside repo?)")
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "fcntl", (
                        f"{rel_path} still imports fcntl at line {node.lineno}"
                    )
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "fcntl", (
                    f"{rel_path} still imports from fcntl at line {node.lineno}"
                )


# ---------------------------------------------------------------------------
# 3. Integration: Storage._shard_lock still works
# ---------------------------------------------------------------------------


class TestStorageLockIntegration:
    """Verify Storage uses portable locking and concurrent appends still serialize."""

    def test_storage_append_creates_lockfile(self, tmp_path):
        """Append uses portable lock (integrity dir + entry present; lock file may be removed after release)."""
        from datetime import datetime, timezone

        from dsm.core.models import Entry
        from dsm.core.storage import Storage

        storage = Storage(data_dir=str(tmp_path))
        entry = Entry(
            id="w7-test-1",
            timestamp=datetime.now(timezone.utc),
            session_id="sess-w7",
            source="test",
            content="windows compat test",
            shard="default",
            hash="",
            prev_hash=None,
            metadata={},
            version="v2.0",
        )
        storage.append(entry)
        assert (tmp_path / "integrity").exists()
        entries = storage.read("default", limit=10)
        assert len(entries) == 1, "Append should have written one entry (lock was used)"

    def test_concurrent_appends_no_lost_writes(self, tmp_path):
        """Multiple threads appending to the same shard produce correct entry count."""
        from datetime import datetime, timezone

        from dsm.core.models import Entry
        from dsm.core.storage import Storage

        storage = Storage(data_dir=str(tmp_path))
        n_threads = 4
        n_per_thread = 25
        barrier = threading.Barrier(n_threads, timeout=10)
        errors = []

        def append_entries(thread_id):
            try:
                barrier.wait()
                for i in range(n_per_thread):
                    entry = Entry(
                        id=f"w7-t{thread_id}-{i}",
                        timestamp=datetime.now(timezone.utc),
                        session_id="sess-w7-conc",
                        source="test",
                        content=f"thread {thread_id} entry {i}",
                        shard="default",
                        hash="",
                        prev_hash=None,
                        metadata={},
                        version="v2.0",
                    )
                    storage.append(entry)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=append_entries, args=(t,))
            for t in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert not errors, f"Append errors: {errors}"
        all_entries = storage.read("default", limit=1000)
        expected = n_threads * n_per_thread
        assert len(all_entries) == expected, (
            f"Expected {expected} entries, got {len(all_entries)} — lock serialization failed"
        )


# ---------------------------------------------------------------------------
# 4. _compat importable on all platforms
# ---------------------------------------------------------------------------


class TestCompatImportable:
    """Verify _compat module imports cleanly (no fcntl dependency)."""

    def test_import_compat(self):
        """Importing _compat should not raise on any platform."""
        from dsm.core._compat import portable_lock, portable_lock_fd

        assert callable(portable_lock)
        assert callable(portable_lock_fd)

    def test_compat_no_fcntl_dependency(self):
        """_compat.py source must not reference fcntl."""
        here = Path(__file__).resolve()
        repo_root = here.parent.parent.parent
        compat_path = repo_root / "src" / "dsm" / "core" / "_compat.py"
        if not compat_path.exists():
            pytest.skip("_compat.py not found")
        source = compat_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename="_compat.py")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "fcntl", (
                        "_compat.py must not import fcntl"
                    )
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "fcntl", (
                    "_compat.py must not import from fcntl"
                )
