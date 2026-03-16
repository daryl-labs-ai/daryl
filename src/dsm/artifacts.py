"""
Artifact Store (P9) — Content-addressable store for raw I/O data.

Stores raw request/response data so third parties can verify that
the agent's claims match the actual evidence. Composes with P4
(capture_environment) and audit.
"""

import gzip
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


def _content_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _serialize(raw_data: Union[str, bytes, dict]) -> bytes:
    if isinstance(raw_data, bytes):
        return raw_data
    if isinstance(raw_data, str):
        return raw_data.encode("utf-8")
    if isinstance(raw_data, dict):
        return json.dumps(raw_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return str(raw_data).encode("utf-8")


class ArtifactStore:
    """Content-addressable store for raw I/O data.

    Layout:
        artifact_dir/
            ab/abc123def456...bin.gz
            ab/abc123def456...meta.json
    """

    def __init__(self, artifact_dir: str):
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, artifact_hash: str) -> tuple:
        prefix = artifact_hash[:2]
        sub = self.artifact_dir / prefix
        sub.mkdir(parents=True, exist_ok=True)
        base = sub / artifact_hash
        return base.with_suffix(".bin.gz"), base.with_suffix(".meta.json")

    def store(
        self,
        raw_data: Union[str, bytes, dict],
        source: str,
        artifact_type: str = "response",
        metadata: Optional[dict] = None,
    ) -> dict:
        """Store raw data as a content-addressable artifact."""
        raw_bytes = _serialize(raw_data)
        artifact_hash = _content_hash(raw_bytes)
        bin_path, meta_path = self._path_for(artifact_hash)

        if bin_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return {
                "artifact_hash": artifact_hash,
                "size_bytes": meta.get("size_bytes", len(raw_bytes)),
                "compressed_bytes": meta.get("compressed_bytes", 0),
                "source": meta.get("source", source),
                "artifact_type": meta.get("artifact_type", artifact_type),
                "stored_at": meta.get("stored_at", ""),
                "path": f"{artifact_hash[:2]}/{artifact_hash}.bin.gz",
            }

        compressed = gzip.compress(raw_bytes)
        bin_path.write_bytes(compressed)
        stored_at = datetime.now(timezone.utc).isoformat()
        meta = {
            "artifact_hash": artifact_hash,
            "size_bytes": len(raw_bytes),
            "compressed_bytes": len(compressed),
            "source": source,
            "artifact_type": artifact_type,
            "stored_at": stored_at,
            "linked_entries": [],
        }
        if metadata:
            meta["extra"] = metadata
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        try:
            with open(meta_path, "rb") as f:
                os.fsync(f.fileno())
        except (OSError, AttributeError) as e:
            logger.debug("artifact metadata read failed: %s", e)
        try:
            with open(bin_path, "rb") as f:
                os.fsync(f.fileno())
        except (OSError, AttributeError) as e:
            logger.debug("artifact data read failed: %s", e)

        return {
            "artifact_hash": artifact_hash,
            "size_bytes": len(raw_bytes),
            "compressed_bytes": len(compressed),
            "source": source,
            "artifact_type": artifact_type,
            "stored_at": stored_at,
            "path": f"{artifact_hash[:2]}/{artifact_hash}.bin.gz",
        }

    def retrieve(self, artifact_hash: str) -> Optional[bytes]:
        """Retrieve raw bytes for an artifact by hash."""
        bin_path, _ = self._path_for(artifact_hash)
        if not bin_path.exists():
            return None
        try:
            return gzip.decompress(bin_path.read_bytes())
        except Exception:
            return None

    def get_metadata(self, artifact_hash: str) -> Optional[dict]:
        """Get metadata for an artifact without reading content."""
        _, meta_path = self._path_for(artifact_hash)
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def exists(self, artifact_hash: str) -> bool:
        """Check if an artifact exists in the store."""
        bin_path, _ = self._path_for(artifact_hash)
        return bin_path.exists()

    def verify_artifact(self, artifact_hash: str) -> dict:
        """Verify artifact integrity: decompress, rehash, compare."""
        bin_path, meta_path = self._path_for(artifact_hash)
        if not bin_path.exists():
            return {"artifact_hash": artifact_hash, "status": "MISSING", "size_bytes": None}
        try:
            raw = gzip.decompress(bin_path.read_bytes())
            computed = _content_hash(raw)
            if computed != artifact_hash:
                return {"artifact_hash": artifact_hash, "status": "CORRUPTED", "size_bytes": None}
            return {"artifact_hash": artifact_hash, "status": "INTACT", "size_bytes": len(raw)}
        except Exception:
            return {"artifact_hash": artifact_hash, "status": "CORRUPTED", "size_bytes": None}

    def link_to_entry(self, artifact_hash: str, entry_id: str) -> dict:
        """Record that a DSM entry references this artifact."""
        _, meta_path = self._path_for(artifact_hash)
        if not meta_path.exists():
            return {"artifact_hash": artifact_hash, "entry_id": entry_id, "linked_entries_count": 0}
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        linked = meta.get("linked_entries", [])
        if entry_id not in linked:
            linked.append(entry_id)
            meta["linked_entries"] = linked
            meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return {"artifact_hash": artifact_hash, "entry_id": entry_id, "linked_entries_count": len(linked)}

    def list_artifacts(self, limit: int = 100) -> list:
        """List artifacts in the store (most recent first)."""
        result = []
        for sub in sorted(self.artifact_dir.iterdir()):
            if not sub.is_dir():
                continue
            for meta_path in sub.glob("*.meta.json"):
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    result.append({
                        "artifact_hash": meta.get("artifact_hash", ""),
                        "source": meta.get("source", ""),
                        "size_bytes": meta.get("size_bytes", 0),
                        "stored_at": meta.get("stored_at", ""),
                        "artifact_type": meta.get("artifact_type", ""),
                    })
                except Exception:
                    continue
        result.sort(key=lambda x: x.get("stored_at", ""), reverse=True)
        return result[:limit]

    def stats(self) -> dict:
        """Aggregate statistics for the artifact store."""
        total_artifacts = 0
        total_raw = 0
        total_compressed = 0
        for sub in self.artifact_dir.iterdir():
            if not sub.is_dir():
                continue
            for meta_path in sub.glob("*.meta.json"):
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    total_artifacts += 1
                    total_raw += meta.get("size_bytes", 0)
                    total_compressed += meta.get("compressed_bytes", 0)
                except Exception:
                    continue
        ratio = total_raw / total_compressed if total_compressed else 0.0
        return {
            "total_artifacts": total_artifacts,
            "total_bytes_raw": total_raw,
            "total_bytes_compressed": total_compressed,
            "compression_ratio": round(ratio, 4),
        }
