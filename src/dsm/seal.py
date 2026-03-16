"""
Shard Sealing — selective forgetting with cryptographic proof.

Seal = cryptographic tombstone: verify chain, compute seal_hash, write to registry.
Shard data can then be archived or deleted; the seal proves history existed.
"""

import hashlib
import json
import gzip
import logging
from pathlib import Path
from typing import List, Optional

from .verify import verify_shard

logger = logging.getLogger(__name__)


class SealRecord:
    def __init__(
        self,
        shard_id: str,
        entry_count: int,
        first_hash: str,
        last_hash: str,
        first_timestamp: str,
        last_timestamp: str,
        seal_hash: str,
        seal_timestamp: str,
        archived_path: Optional[str] = None,
    ):
        self.shard_id = shard_id
        self.entry_count = entry_count
        self.first_hash = first_hash
        self.last_hash = last_hash
        self.first_timestamp = first_timestamp
        self.last_timestamp = last_timestamp
        self.seal_hash = seal_hash
        self.seal_timestamp = seal_timestamp
        self.archived_path = archived_path

    def to_dict(self) -> dict:
        return {
            "shard_id": self.shard_id,
            "entry_count": self.entry_count,
            "first_hash": self.first_hash,
            "last_hash": self.last_hash,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "seal_hash": self.seal_hash,
            "seal_timestamp": self.seal_timestamp,
            "archived_path": self.archived_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SealRecord":
        return cls(
            shard_id=d["shard_id"],
            entry_count=d["entry_count"],
            first_hash=d["first_hash"],
            last_hash=d["last_hash"],
            first_timestamp=d["first_timestamp"],
            last_timestamp=d["last_timestamp"],
            seal_hash=d["seal_hash"],
            seal_timestamp=d["seal_timestamp"],
            archived_path=d.get("archived_path"),
        )


class SealRegistry:
    def __init__(self, seal_dir: str):
        self.seal_dir = Path(seal_dir)
        self.seal_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.seal_dir / "seal_registry.jsonl"

    def _append(self, record: dict) -> None:
        with open(self.registry_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            try:
                import os
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                pass

    def read_all(self) -> List[SealRecord]:
        if not self.registry_file.exists():
            return []
        records = []
        with open(self.registry_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(SealRecord.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, KeyError):
                        continue
        return records

    def find_seal(self, shard_id: str) -> Optional[SealRecord]:
        for r in self.read_all():
            if r.shard_id == shard_id:
                return r
        return None

    def is_sealed(self, shard_id: str) -> bool:
        return self.find_seal(shard_id) is not None


def _compute_seal_hash(shard_id: str, entry_count: int, first_hash: str, last_hash: str, seal_timestamp: str) -> str:
    payload = json.dumps(
        {
            "shard_id": shard_id,
            "entry_count": entry_count,
            "first_hash": first_hash,
            "last_hash": last_hash,
            "seal_timestamp": seal_timestamp,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def seal_shard(storage, shard_id: str, registry: SealRegistry, archive_path: Optional[str] = None) -> SealRecord:
    from datetime import datetime
    vr = verify_shard(storage, shard_id)
    if vr["status"] != "OK":
        raise ValueError("Cannot seal corrupted shard")
    entries = storage.read(shard_id, limit=10**6)
    if not entries:
        raise ValueError("Cannot seal empty shard")
    entries_chrono = list(reversed(entries))
    first, last = entries_chrono[0], entries_chrono[-1]
    first_ts = first.timestamp.isoformat() if hasattr(first.timestamp, "isoformat") else str(first.timestamp)
    last_ts = last.timestamp.isoformat() if hasattr(last.timestamp, "isoformat") else str(last.timestamp)
    seal_ts = datetime.utcnow().isoformat() + "Z"
    seal_hash = _compute_seal_hash(shard_id, len(entries_chrono), first.hash or "", last.hash or "", seal_ts)
    record = SealRecord(
        shard_id=shard_id,
        entry_count=len(entries_chrono),
        first_hash=first.hash or "",
        last_hash=last.hash or "",
        first_timestamp=first_ts,
        last_timestamp=last_ts,
        seal_hash=seal_hash,
        seal_timestamp=seal_ts,
        archived_path=None,
    )
    if archive_path:
        archive_dir = Path(archive_path)
        archive_dir.mkdir(parents=True, exist_ok=True)
        out_path = archive_dir / f"{shard_id}.sealed.jsonl.gz"
        segs = storage.segment_manager.get_segment_files_ordered(shard_id, reverse=False)
        with gzip.open(out_path, "wt", encoding="utf-8") as zf:
            if segs:
                for seg in segs:
                    with open(seg, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                zf.write(line)
            else:
                mono = storage.shards_dir / f"{shard_id}.jsonl"
                if mono.exists():
                    with open(mono, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                zf.write(line)
        record.archived_path = str(out_path)
    registry._append(record.to_dict())
    return record


def verify_seal(registry: SealRegistry, shard_id: str) -> dict:
    rec = registry.find_seal(shard_id)
    if not rec:
        return {"shard_id": shard_id, "status": "NOT_SEALED", "entry_count": 0, "sealed_at": ""}
    expected = _compute_seal_hash(rec.shard_id, rec.entry_count, rec.first_hash, rec.last_hash, rec.seal_timestamp)
    status = "VALID" if expected == rec.seal_hash else "HASH_MISMATCH"
    return {"shard_id": shard_id, "status": status, "entry_count": rec.entry_count, "sealed_at": rec.seal_timestamp}


def verify_seal_against_storage(storage, registry: SealRegistry, shard_id: str) -> dict:
    rec = registry.find_seal(shard_id)
    if not rec:
        return {"shard_id": shard_id, "status": "NOT_SEALED", "seal_entries": 0, "current_entries": 0}
    entries = storage.read(shard_id, limit=1)
    if not entries:
        return {"shard_id": shard_id, "status": "SHARD_GONE", "seal_entries": rec.entry_count, "current_entries": 0}
    current_tip = entries[0].hash if entries[0].hash else ""
    all_entries = storage.read(shard_id, limit=10**6)
    current_count = len(all_entries)
    if current_count == rec.entry_count and current_tip == rec.last_hash:
        status = "MATCHES"
    elif current_count > rec.entry_count or (current_count == rec.entry_count and current_tip != rec.last_hash):
        status = "DIVERGED"
    else:
        status = "SHARD_GONE"
    return {"shard_id": shard_id, "status": status, "seal_entries": rec.entry_count, "current_entries": current_count}


def list_sealed_shards(registry: SealRegistry) -> List[dict]:
    return [
        {"shard_id": r.shard_id, "entry_count": r.entry_count, "sealed_at": r.seal_timestamp, "archived": bool(r.archived_path)}
        for r in registry.read_all()
    ]
