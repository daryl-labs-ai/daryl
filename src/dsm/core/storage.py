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

import fcntl
import json
import hashlib
import os
from collections import deque
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone

from .models import Entry, ShardMeta

# Import du gestionnaire de segmentation
from .shard_segments import ShardSegmentManager


def _compute_canonical_entry_hash(entry: Entry, prev_hash: Optional[str]) -> str:
    """Compute SHA-256 over full entry (session_id, source, timestamp, metadata, content, prev_hash).
    Used for chain integrity; deterministic serialization for replay/verification.
    """
    canonical_entry = {
        "session_id": entry.session_id,
        "source": entry.source,
        "timestamp": entry.timestamp.isoformat() if hasattr(entry.timestamp, "isoformat") else str(entry.timestamp),
        "metadata": entry.metadata or {},
        "content": entry.content,
        "prev_hash": prev_hash,
    }
    serialized = json.dumps(canonical_entry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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

    def append(self, entry: Entry) -> Entry:
        """
        Ajoute une entrée (append-only)
        Utilise la segmentation automatique si activée

        Args:
            entry: Entry à ajouter

        Returns:
            Entry: L'entrée ajoutée avec hash calculé
        """
        # Déterminer le shard
        shard = entry.shard or "default"

        # Résoudre le chemin du segment actif via ShardSegmentManager
        active_segment_path = self.segment_manager.get_active_segment(shard)

        # Lock segment file for entire append (read last_hash → compute hash → write entry → set last_hash)
        with open(active_segment_path, 'a', encoding='utf-8') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
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
                    "version": entry.version
                }
                line = json.dumps(entry_dict, ensure_ascii=False) + "\n"
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

                self._set_last_hash(shard, entry.hash)
                self.segment_manager.update_active_segment_metadata(shard, delta_events=1, delta_bytes=len(line.encode("utf-8")))
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        self._update_shard_metadata(shard, entry)

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

    def _set_last_hash(self, shard_id: str, hash_value: str):
        """Définit le dernier hash de la chaîne pour un shard (préserve entry_count, first/last_timestamp)."""
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
        """Met à jour les métadonnées du shard après un append (entry_count, first_timestamp, last_timestamp)."""
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
