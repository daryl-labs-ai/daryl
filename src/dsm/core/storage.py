#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM Kernel — Frozen Module

This file is part of the DSM storage kernel freeze (March 2026).

The kernel is considered stable and audited.

Modifications must follow the DSM kernel evolution process
and should not be changed casually.

See:
docs/architecture/DSM_KERNEL_FREEZE_2026_03.md
"""
"""
DSM v2 - Storage Operations
Append/Read/List with JSONL format (append-only) - Monolithic Mode
"""

import contextlib
import json
import os
from collections import deque
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone

from dsm_primitives import hash_canonical

from ._compat import portable_lock
from .models import Entry, ShardMeta

# Import du gestionnaire de segmentation
from .shard_segments import ShardSegmentManager


def _build_canonical_entry(entry: Entry, prev_hash: Optional[str]) -> dict:
    """Build the canonical dict representation of an entry for hashing.

    Single source of truth for the canonical entry shape, shared by the
    write path (_compute_canonical_entry_hash) and verify paths
    (verify.py, core/signing.py). Per ADR-0002 schema.

    Any change to this function is a breaking schema change requiring a
    new hash version (v2+).
    """
    return {
        "session_id": entry.session_id,
        "source": entry.source,
        "timestamp": entry.timestamp.isoformat() if hasattr(entry.timestamp, "isoformat") else str(entry.timestamp),
        "metadata": entry.metadata or {},
        "content": entry.content,
        "prev_hash": prev_hash,
    }


def _compute_canonical_entry_hash(entry: Entry, prev_hash: Optional[str]) -> str:
    """Compute the canonical hash of an entry.

    Returns the current canonical hash version (v1) per ADR-0002.
    Delegates to dsm_primitives.hash_canonical via _build_canonical_entry.

    Backward compatibility for entries created before V4-A.2 (v0 bare
    hex) is handled by callers via dsm_primitives.verify_hash, which
    routes by prefix detection.
    """
    return hash_canonical(_build_canonical_entry(entry, prev_hash))


class Storage:
    """Stockage DSM v2 avec JSONL (append-only) - Mode Segmenté"""

    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.shards_dir = self.data_dir / "shards"
        self.integrity_dir = self.data_dir / "integrity"
        self.shards_dir.mkdir(parents=True, exist_ok=True)
        self.integrity_dir.mkdir(parents=True, exist_ok=True)

        # Gestionnaire de segmentation
        self.segment_manager = ShardSegmentManager(base_dir=str(self.data_dir))

    @contextlib.contextmanager
    def _shard_lock(self, shard_id: str):
        """
        Acquire an exclusive portable lock for the entire shard operation.

        Uses a dedicated lockfile (integrity/{shard_id}.lock) to serialize
        all append operations on this shard — including metadata updates.
        This is the fix for K-2 (crash window) and K-3 (metadata race).
        Cross-platform: works on Windows and POSIX (W-7 fix).
        """
        lock_path = self.integrity_dir / f"{shard_id}.lock"
        with portable_lock(lock_path):
            yield

    def append(self, entry: Entry) -> Entry:
        """
        Ajoute une entrée (append-only).
        K-2/K-3 fix: toute l'opération (écriture segment + commit metadata)
        est protégée par un shard-level lock dédié.

        Args:
            entry: Entry à ajouter

        Returns:
            Entry: L'entrée ajoutée avec hash calculé
        """
        shard = entry.shard or "default"

        with self._shard_lock(shard):
            active_segment_path = self.segment_manager.get_active_segment(shard)
            with open(active_segment_path, "a", encoding="utf-8") as f:
                prev_hash = self._get_last_hash(shard)
                entry.prev_hash = prev_hash

                if not entry.hash:
                    entry.hash = _compute_canonical_entry_hash(entry, prev_hash)

                entry_dict = {
                    "id": entry.id,
                    "timestamp": entry.timestamp.isoformat(),
                    "session_id": entry.session_id,
                    "source": entry.source,
                    "content": entry.content,
                    "shard": shard,
                    "hash": entry.hash,
                    "prev_hash": entry.prev_hash,
                    "metadata": entry.metadata,
                    "version": entry.version,
                }
                line = json.dumps(entry_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

            self._commit_integrity_and_metadata(shard, entry)

            self.segment_manager.update_active_segment_metadata(
                shard, delta_events=1, delta_bytes=len(line.encode("utf-8"))
            )

        return entry

    def read(self, shard_id: str, offset: int = 0, limit: int = 100) -> List[Entry]:
        """
        Lit les entrées d'un shard (JSONL) avec pagination.
        Supporte les shards segmentés et monolithiques.
        Retourne les entrées les plus récentes en premier (offset=0, limit=N = N plus récentes).

        Args:
            shard_id: ID du shard
            offset: Nombre d'entrées à sauter (dans l'ordre "plus récent d'abord")
            limit: Nombre max d'entrées à retourner

        Returns:
            List[Entry]: Liste des entrées (nouveautés en premier)
        """
        shard_family_dir = self.data_dir / "shards" / shard_id.replace("shard_", "")

        if shard_family_dir.exists() and shard_family_dir.is_dir():
            return self._read_segmented(shard_id, offset, limit)
        return self._read_monolithic(shard_id, offset, limit)

    def _entry_from_event_data(self, event_data: dict) -> Entry:
        """Build an Entry from a raw event dict (segment or monolithic line)."""
        return Entry(
            id=event_data.get("id"),
            timestamp=datetime.fromisoformat(event_data.get("timestamp")),
            session_id=event_data.get("session_id"),
            source=event_data.get("source"),
            content=event_data.get("content"),
            shard=event_data.get("shard"),
            hash=event_data.get("hash"),
            prev_hash=event_data.get("prev_hash"),
            metadata=event_data.get("metadata", {}),
            version=event_data.get("version", "v2.0"),
        )

    def _read_segmented(self, shard_id: str, offset: int, limit: int) -> List[Entry]:
        """Read from segmented shard: stream newest-first, skip offset, take limit. O(limit) events read."""
        segments = self.segment_manager.get_segment_files_ordered(shard_id, reverse=True)
        skipped = 0
        collected = 0
        results: List[Entry] = []

        for segment_path in segments:
            with open(segment_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    event_data = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                if skipped < offset:
                    skipped += 1
                    continue
                try:
                    entry = self._entry_from_event_data(event_data)
                except (KeyError, TypeError, ValueError):
                    continue
                results.append(entry)
                collected += 1
                if collected >= limit:
                    return results
        return results

    def _read_monolithic(self, shard_id: str, offset: int, limit: int) -> List[Entry]:
        """Read from monolithic shard: stream line-by-line, keep last (offset+limit), return slice newest-first."""
        shard_file = self.shards_dir / f"{shard_id}.jsonl"
        if not shard_file.exists():
            return []
        window: deque = deque(maxlen=offset + limit)
        with open(shard_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line.strip())
                    entry = Entry(
                        id=data.get("id"),
                        timestamp=datetime.fromisoformat(data.get("timestamp")),
                        session_id=data.get("session_id"),
                        source=data.get("source"),
                        content=data.get("content"),
                        shard=data.get("shard"),
                        hash=data.get("hash"),
                        prev_hash=data.get("prev_hash"),
                        metadata=data.get("metadata", {}),
                        version=data.get("version", "v2.0"),
                    )
                    window.append(entry)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
        n = len(window)
        if n <= offset:
            return []
        start = max(0, n - offset - limit)
        end = n - offset
        return list(window)[start:end][::-1]

    def list_shards(self) -> List[ShardMeta]:
        """
        Liste tous les shards disponibles
        Supporte les shards segmentés et monolithiques

        Returns:
            List[ShardMeta]: Liste des shards avec métadonnées
        """
        shards = []

        # Lister les shards monolithiques (compatibilité)
        for shard_file in self.shards_dir.glob("*.jsonl"):
            shard_id = shard_file.stem
            metadata = self._get_shard_metadata(shard_id)
            shards.append(metadata)

        # Lister les familles de shards segmentés (sous-dossiers contenant des .jsonl)
        for path in self.shards_dir.iterdir():
            if path.is_dir() and not path.name.startswith("."):
                if list(path.glob("*.jsonl")):
                    # Shard ID may be path.name ("default") or "shard_" + path.name ("shard_sessions")
                    if (self.integrity_dir / f"{path.name}_last_hash.json").exists():
                        shard_id = path.name
                    else:
                        shard_id = f"shard_{path.name}"
                    metadata = self._get_shard_metadata(shard_id)
                    shards.append(metadata)

        return shards

    def get_shard_size(self, shard_id: str) -> int:
        """
        Récupère la taille d'un shard en bytes
        Supporte les shards segmentés et monolithiques

        Args:
            shard_id: ID du shard

        Returns:
            int: Taille en bytes
        """
        shard_family_dir = self.data_dir / "shards" / shard_id.replace("shard_", "")

        if shard_family_dir.exists() and shard_family_dir.is_dir():
            # Somme de la taille de tous les segments
            total_size = 0
            for segment_file in shard_family_dir.glob("*.jsonl"):
                total_size += segment_file.stat().st_size
            return total_size
        else:
            # Fallback pour shards monolithiques
            shard_file = self.shards_dir / f"{shard_id}.jsonl"

            if shard_file.exists():
                return shard_file.stat().st_size

            return 0

    # ========================================================================
    # INTERNAL HELPERS
    # ========================================================================

    def _get_last_hash(self, shard_id: str) -> Optional[str]:
        """Récupère le dernier hash de la chaîne pour un shard. Returns None if file missing or corrupted."""
        last_hash_file = self.integrity_dir / f"{shard_id}_last_hash.json"

        if last_hash_file.exists():
            try:
                with open(last_hash_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("last_hash")
            except Exception:
                return None

        return None

    def _commit_integrity_and_metadata(self, shard_id: str, entry: Entry):
        """
        Atomic commit of last_hash + shard metadata in a single file write.

        Must be called while holding the shard lock (_shard_lock).
        Replaces the separate _set_last_hash() + _update_shard_metadata() calls
        that were the root cause of K-2 and K-3.
        """
        last_hash_file = self.integrity_dir / f"{shard_id}_last_hash.json"

        existing = {}
        if last_hash_file.exists():
            try:
                with open(last_hash_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        entry_count = existing.get("entry_count", 0) + 1
        first_ts = existing.get("first_timestamp")
        if first_ts is None:
            first_ts = (
                entry.timestamp.isoformat()
                if hasattr(entry.timestamp, "isoformat")
                else str(entry.timestamp)
            )
        last_ts = (
            entry.timestamp.isoformat()
            if hasattr(entry.timestamp, "isoformat")
            else str(entry.timestamp)
        )

        data = {
            "shard_id": shard_id,
            "last_hash": entry.hash,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entry_count": entry_count,
            "first_timestamp": first_ts,
            "last_timestamp": last_ts,
        }

        tmp_path = last_hash_file.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, last_hash_file)

    def _set_last_hash(self, shard_id: str, hash_value: str):
        """Définit le dernier hash de la chaîne pour un shard. Deprecated for use in append(); use _commit_integrity_and_metadata() instead (K-2/K-3 fix)."""
        last_hash_file = self.integrity_dir / f"{shard_id}_last_hash.json"

        existing = {}
        if last_hash_file.exists():
            try:
                with open(last_hash_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        data = {
            "shard_id": shard_id,
            "last_hash": hash_value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entry_count": existing.get("entry_count"),
            "first_timestamp": existing.get("first_timestamp"),
            "last_timestamp": existing.get("last_timestamp"),
        }
        data = {k: v for k, v in data.items() if v is not None}

        tmp_path = last_hash_file.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, last_hash_file)

    def _get_shard_metadata(self, shard_id: str) -> ShardMeta:
        """Récupère les métadonnées d'un shard (entry_count, first/last_timestamp depuis le fichier d'intégrité)."""
        last_hash_file = self.integrity_dir / f"{shard_id}_last_hash.json"

        if last_hash_file.exists():
            try:
                with open(last_hash_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
            entry_count = data.get("entry_count", 0)
            first_ts = data.get("first_timestamp")
            last_ts = data.get("last_timestamp")
            created_at = datetime.fromisoformat(first_ts) if first_ts else datetime.fromtimestamp(last_hash_file.stat().st_mtime)
            last_updated = datetime.fromisoformat(last_ts) if last_ts else created_at
            size_bytes = self.get_shard_size(shard_id)
            return ShardMeta(
                shard_id=shard_id,
                created_at=created_at,
                last_updated=last_updated,
                entry_count=entry_count,
                size_bytes=size_bytes,
                integrity_status="verified",
            )
        return ShardMeta(
            shard_id=shard_id,
            created_at=datetime.now(timezone.utc),
            last_updated=datetime.now(timezone.utc),
            entry_count=0,
            size_bytes=0,
            integrity_status="unknown",
        )

    def _update_shard_metadata(self, shard_id: str, entry: Entry):
        """Met à jour les métadonnées du shard après un append. Deprecated for use in append(); use _commit_integrity_and_metadata() instead (K-2/K-3 fix)."""
        last_hash_file = self.integrity_dir / f"{shard_id}_last_hash.json"

        existing = {}
        if last_hash_file.exists():
            try:
                with open(last_hash_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        entry_count = existing.get("entry_count", 0) + 1
        first_ts = existing.get("first_timestamp")
        if first_ts is None:
            first_ts = entry.timestamp.isoformat() if hasattr(entry.timestamp, "isoformat") else str(entry.timestamp)
        last_ts = entry.timestamp.isoformat() if hasattr(entry.timestamp, "isoformat") else str(entry.timestamp)

        data = {
            "shard_id": shard_id,
            "last_hash": existing.get("last_hash"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entry_count": entry_count,
            "first_timestamp": first_ts,
            "last_timestamp": last_ts,
        }

        tmp_path = last_hash_file.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, last_hash_file)

    def _read_last_segment_tail(self, shard_id: str) -> Optional[dict]:
        """
        Read the last non-empty line from the last segment file.

        O(1) relative to total shard size — seeks from end of file.
        Returns parsed dict or None.
        """
        segments = self.segment_manager.get_segment_files_ordered(shard_id, reverse=True)
        for segment_path in segments:
            if not segment_path.exists():
                continue
            size = segment_path.stat().st_size
            if size == 0:
                continue
            read_size = min(size, 8192)
            with open(segment_path, "rb") as f:
                f.seek(-read_size, 2)
                tail = f.read().decode("utf-8", errors="replace")
            lines = tail.strip().split("\n")
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None

    def _count_shard_entries(self, shard_id: str) -> int:
        """Count total entries across all segments for a shard. Used only during reconciliation."""
        count = 0
        for segment_path in self.segment_manager.get_segment_files_ordered(shard_id):
            if not segment_path.exists():
                continue
            with open(segment_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        count += 1
        return count

    def reconcile_shard(self, shard_id: str) -> dict:
        """
        Reconcile segment content with integrity metadata after a crash.

        Reads ONLY the last entry from the last segment (O(1) seek-from-end),
        compares its hash with what last_hash.json reports.
        If they differ, recalculates entry_count and updates metadata.

        Returns:
            dict: reconciled (bool), old_hash, new_hash, entry_count (if reconciled)
        """
        stored_hash = self._get_last_hash(shard_id)
        last_event = self._read_last_segment_tail(shard_id)

        if last_event is None:
            return {"reconciled": False, "reason": "empty_shard"}

        last_hash_on_disk = last_event.get("hash")
        if last_hash_on_disk == stored_hash:
            return {
                "reconciled": False,
                "old_hash": stored_hash,
                "new_hash": stored_hash,
            }

        entry_count = self._count_shard_entries(shard_id)
        first_ts = None
        segments = self.segment_manager.get_segment_files_ordered(shard_id)
        for seg in segments:
            if not seg.exists():
                continue
            with open(seg, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        first_event = json.loads(line)
                        first_ts = first_event.get("timestamp")
                        break
                    except json.JSONDecodeError:
                        continue
            if first_ts:
                break

        last_ts = last_event.get("timestamp")
        last_hash_file = self.integrity_dir / f"{shard_id}_last_hash.json"
        data = {
            "shard_id": shard_id,
            "last_hash": last_hash_on_disk,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entry_count": entry_count,
            "first_timestamp": first_ts,
            "last_timestamp": last_ts,
        }
        data = {k: v for k, v in data.items() if v is not None}

        tmp_path = last_hash_file.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, last_hash_file)

        return {
            "reconciled": True,
            "old_hash": stored_hash,
            "new_hash": last_hash_on_disk,
            "entry_count": entry_count,
        }

    def reconcile_all(self) -> List[dict]:
        """Reconcile all known shards. Call at startup. O(1) detection per shard."""
        results = []
        for shard_meta in self.list_shards():
            result = self.reconcile_shard(shard_meta.shard_id)
            results.append({"shard_id": shard_meta.shard_id, **result})
        return results

    def startup_check(self, full_verify: bool = False) -> dict:
        """
        Run integrity checks at startup (S-5 fix).

        Always runs reconcile_all() — O(1) detection per shard, fixes K-2 metadata
        divergence (crash recovery). Does NOT detect tampering.
        Optionally runs full hash-chain verification if full_verify=True — re-hashes
        every entry from segments (detects tampering). Reconcile ≠ verify: only
        full verify detects modification of data.

        Args:
            full_verify: If True, verify every hash in every shard (O(n) per shard).
                         If False (default), only reconcile metadata.

        Returns:
            dict with keys: reconciled, verified, status, shards_reconciled, shards_with_errors.
        """
        import logging

        logger = logging.getLogger("dsm.core.storage")

        result = {
            "reconciled": [],
            "verified": [],
            "status": "OK",
            "shards_reconciled": 0,
            "shards_with_errors": 0,
        }

        try:
            reconcile_results = self.reconcile_all()
            result["reconciled"] = reconcile_results
            result["shards_reconciled"] = sum(
                1 for r in reconcile_results if r.get("reconciled")
            )
            if result["shards_reconciled"] > 0:
                result["status"] = "RECONCILED"
                logger.info(
                    "startup_check: reconciled %d shard(s)", result["shards_reconciled"]
                )
        except Exception as e:
            logger.error("startup_check: reconcile_all failed: %s", e)
            result["status"] = "INTEGRITY_ERROR"

        if full_verify:
            try:
                from ..verify import verify_all as _verify_all

                verify_results = _verify_all(self)
                result["verified"] = verify_results
                errors = sum(
                    1
                    for v in verify_results
                    if v.get("status") is not None
                    and getattr(v.get("status"), "value", str(v.get("status"))) != "OK"
                )
                result["shards_with_errors"] = errors
                if errors > 0:
                    result["status"] = "INTEGRITY_ERROR"
                    logger.warning(
                        "startup_check: %d shard(s) with integrity errors", errors
                    )
                elif result["status"] != "RECONCILED":
                    result["status"] = "OK"
            except Exception as e:
                logger.error("startup_check: verify_all failed: %s", e)
                result["status"] = "INTEGRITY_ERROR"

        return result
