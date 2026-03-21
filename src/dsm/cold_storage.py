"""
DSM Cold Storage — Archive sealed shards to external storage.

Provides a pluggable backend interface for archiving sealed shards.
Default backend: local filesystem (flat directory of JSON archives).
Future backends: S3, GCS, Azure Blob.

Usage:
    archive = ColdStorage(backend=LocalBackend("/path/to/archive"))
    result = archive.export(storage, shard_id="old_shard")
    # -> ArchiveResult(shard_id, path, entry_count, final_hash, size_bytes)

    # Verify archived shard integrity
    ok = archive.verify(shard_id="old_shard")

    # List archived shards
    shards = archive.list_archived()

    # Restore from archive
    archive.restore(storage, shard_id="old_shard")
"""

import hashlib
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core.models import Entry
from .core.storage import Storage

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Archive result
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ArchiveResult:
    """Result of archiving a shard to cold storage."""
    shard_id: str
    path: str                   # backend-specific location
    entry_count: int
    final_hash: str             # SHA-256 of the full archive
    size_bytes: int
    archived_at: datetime
    ok: bool
    error: Optional[str] = None


# ------------------------------------------------------------------
# Backend interface
# ------------------------------------------------------------------


class ColdStorageBackend(ABC):
    """Abstract backend for cold storage."""

    @abstractmethod
    def write(self, shard_id: str, data: bytes) -> str:
        """Write archive data. Returns path/key."""
        ...

    @abstractmethod
    def read(self, shard_id: str) -> Optional[bytes]:
        """Read archive data. Returns None if not found."""
        ...

    @abstractmethod
    def exists(self, shard_id: str) -> bool:
        """Check if archive exists."""
        ...

    @abstractmethod
    def list_shards(self) -> List[str]:
        """List all archived shard IDs."""
        ...

    @abstractmethod
    def delete(self, shard_id: str) -> bool:
        """Delete an archive. Returns True if deleted."""
        ...


# ------------------------------------------------------------------
# Local filesystem backend
# ------------------------------------------------------------------


class LocalBackend(ColdStorageBackend):
    """Stores archives as JSON files on local filesystem."""

    def __init__(self, archive_dir: str):
        self._dir = Path(archive_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, shard_id: str) -> Path:
        # Sanitize shard_id for filename (replace : with _)
        safe = shard_id.replace(":", "_").replace("/", "_")
        return self._dir / f"{safe}.json.gz"

    def write(self, shard_id: str, data: bytes) -> str:
        import gzip
        path = self._path(shard_id)
        with open(path, "wb") as f:
            f.write(gzip.compress(data))
        return str(path)

    def read(self, shard_id: str) -> Optional[bytes]:
        import gzip
        path = self._path(shard_id)
        if not path.exists():
            return None
        with open(path, "rb") as f:
            return gzip.decompress(f.read())

    def exists(self, shard_id: str) -> bool:
        return self._path(shard_id).exists()

    def list_shards(self) -> List[str]:
        result = []
        for p in self._dir.glob("*.json.gz"):
            # Reverse the sanitization (approximate)
            result.append(p.stem.replace(".json", ""))
        return result

    def delete(self, shard_id: str) -> bool:
        path = self._path(shard_id)
        if path.exists():
            path.unlink()
            return True
        return False


# ------------------------------------------------------------------
# ColdStorage — main interface
# ------------------------------------------------------------------


class ColdStorage:
    """Archive sealed shards to cold storage.

    Exports all entries from a shard as a single JSON archive with
    integrity hash. Can restore from archive.
    """

    def __init__(self, backend: ColdStorageBackend):
        self._backend = backend

    def export(self, storage: Storage, shard_id: str,
               verify_first: bool = True) -> ArchiveResult:
        """Export a shard to cold storage.

        Args:
            storage: DSM storage instance.
            shard_id: Shard to archive.
            verify_first: If True, verify chain integrity before archiving.

        Returns:
            ArchiveResult with details of the archive.
        """
        now = datetime.now(timezone.utc)

        # Read all entries
        entries = storage.read(shard_id, limit=10**7)
        if not entries:
            return ArchiveResult(
                shard_id=shard_id, path="", entry_count=0,
                final_hash="", size_bytes=0, archived_at=now,
                ok=False, error="shard is empty",
            )

        # Optional chain verification
        if verify_first:
            chrono = list(reversed(entries))  # oldest first
            for i, e in enumerate(chrono):
                if i == 0:
                    continue
                if e.prev_hash and e.prev_hash != chrono[i - 1].hash:
                    return ArchiveResult(
                        shard_id=shard_id, path="", entry_count=len(entries),
                        final_hash="", size_bytes=0, archived_at=now,
                        ok=False, error=f"chain break at entry {i}",
                    )

        # Serialize entries
        archive_data = {
            "shard_id": shard_id,
            "archived_at": now.isoformat(),
            "entry_count": len(entries),
            "entries": [
                {
                    "id": e.id,
                    "timestamp": e.timestamp.isoformat(),
                    "session_id": e.session_id,
                    "source": e.source,
                    "content": e.content,
                    "shard": e.shard,
                    "hash": e.hash,
                    "prev_hash": e.prev_hash,
                    "metadata": e.metadata,
                    "version": e.version,
                }
                for e in reversed(entries)  # chronological order
            ],
        }

        data_bytes = json.dumps(
            archive_data, sort_keys=True, ensure_ascii=False
        ).encode("utf-8")

        # Compute archive hash
        archive_hash = hashlib.sha256(data_bytes).hexdigest()
        archive_data["archive_hash"] = archive_hash
        data_bytes = json.dumps(
            archive_data, sort_keys=True, ensure_ascii=False
        ).encode("utf-8")

        # Write to backend
        try:
            path = self._backend.write(shard_id, data_bytes)
        except Exception as e:
            return ArchiveResult(
                shard_id=shard_id, path="", entry_count=len(entries),
                final_hash=archive_hash, size_bytes=len(data_bytes),
                archived_at=now, ok=False, error=str(e),
            )

        logger.info(
            "Archived shard %s: %d entries, %d bytes, hash=%s",
            shard_id, len(entries), len(data_bytes), archive_hash[:16],
        )

        return ArchiveResult(
            shard_id=shard_id, path=path, entry_count=len(entries),
            final_hash=archive_hash, size_bytes=len(data_bytes),
            archived_at=now, ok=True,
        )

    def verify(self, shard_id: str) -> Dict[str, Any]:
        """Verify integrity of an archived shard.

        Re-computes SHA-256 and checks against stored hash.
        """
        data_bytes = self._backend.read(shard_id)
        if data_bytes is None:
            return {"ok": False, "error": "archive not found"}

        try:
            archive = json.loads(data_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return {"ok": False, "error": f"corrupt archive: {e}"}

        stored_hash = archive.get("archive_hash", "")

        # Recompute hash without the archive_hash field
        archive_copy = {k: v for k, v in archive.items() if k != "archive_hash"}
        recomputed = hashlib.sha256(
            json.dumps(archive_copy, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        if recomputed != stored_hash:
            return {
                "ok": False,
                "error": "hash mismatch",
                "stored": stored_hash,
                "computed": recomputed,
            }

        return {
            "ok": True,
            "shard_id": archive.get("shard_id"),
            "entry_count": archive.get("entry_count"),
            "archived_at": archive.get("archived_at"),
            "archive_hash": stored_hash,
        }

    def restore(self, storage: Storage, shard_id: str) -> Dict[str, Any]:
        """Restore entries from archive back into DSM storage.

        Entries are appended to the shard in chronological order.
        Idempotent: skips entries whose hash already exists.
        """
        data_bytes = self._backend.read(shard_id)
        if data_bytes is None:
            return {"ok": False, "error": "archive not found"}

        try:
            archive = json.loads(data_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return {"ok": False, "error": f"corrupt archive: {e}"}

        entries_data = archive.get("entries", [])
        restored = 0
        skipped = 0

        for ed in entries_data:
            entry = Entry(
                id=ed["id"],
                timestamp=datetime.fromisoformat(ed["timestamp"]),
                session_id=ed.get("session_id", ""),
                source=ed.get("source", ""),
                content=ed.get("content", ""),
                shard=ed.get("shard", shard_id),
                hash=ed.get("hash", ""),
                prev_hash=ed.get("prev_hash"),
                metadata=ed.get("metadata", {}),
                version=ed.get("version", "v2.0"),
            )
            try:
                storage.append(entry)
                restored += 1
            except Exception:
                skipped += 1

        return {
            "ok": True,
            "shard_id": shard_id,
            "restored": restored,
            "skipped": skipped,
        }

    def list_archived(self) -> List[str]:
        """List all archived shard IDs."""
        return self._backend.list_shards()
