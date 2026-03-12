#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Storage Operations
Append/Read/List with JSONL format (append-only) - Monolithic Mode
"""

import json
import hashlib
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from .models import Entry, ShardMeta

# Import du gestionnaire de segmentation
from .shard_segments import ShardSegmentManager


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
        # Calculer le hash si non fourni
        if not entry.hash:
            entry.hash = hashlib.sha256(entry.content.encode('utf-8')).hexdigest()

        # Déterminer le shard
        shard = entry.shard or "default"

        # Résoudre le chemin du segment actif via ShardSegmentManager
        active_segment_path = self.segment_manager.get_active_segment(shard)

        # Charger le hash précédent depuis la chaîne d'intégrité
        prev_hash = self._get_last_hash(shard)

        # Mettre à jour l'entrée avec la chaîne
        entry.prev_hash = prev_hash

        # Ouvrir le shard en mode append (segmenté)
        with open(active_segment_path, 'a', encoding='utf-8') as f:
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
            f.write(json.dumps(entry_dict, ensure_ascii=False) + '\n')

        # Mettre à jour le dernier hash
        self._set_last_hash(shard, entry.hash)

        # Mettre à jour les métadonnées du shard
        self._update_shard_metadata(shard)

        return entry

    def read(self, shard_id: str, limit: int = 100) -> List[Entry]:
        """
        Lit les entrées d'un shard (JSONL)
        Supporte les shards segmentés et monolithiques

        Args:
            shard_id: ID du shard
            limit: Nombre max d'entrées (les plus récentes)

        Returns:
            List[Entry]: Liste des entrées
        """
        # Vérifier si le shard est segmenté
        shard_family_dir = self.data_dir / "shards" / shard_id.replace("shard_", "")

        if shard_family_dir.exists() and shard_family_dir.is_dir():
            # Lecture multi-segments (ordre chronologique)
            entries = []
            for event_data in self.segment_manager.iter_shard_events(shard_id):
                entry = Entry(
                    id=event_data.get("id"),
                    timestamp=datetime.fromisoformat(event_data.get("timestamp")),
                    session_id=event_data.get("session_id"),
                    source=event_data.get("source"),
                    content=event_data.get("content"),
                    shard=event_data.get("shard"),
                    hash=event_data.get("hash"),
                    prev_hash=event_data.get("prev_hash"),
                    metadata=event_data.get("metadata", {}),
                    version=event_data.get("version", "v2.0")
                )
                entries.append(entry)

            # Limiter et inverser pour avoir les plus récents en premier
            return entries[-limit:][::-1]
        else:
            # Fallback pour shards monolithiques
            shard_file = self.shards_dir / f"{shard_id}.jsonl"

            if not shard_file.exists():
                return []

            entries = []
            with open(shard_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Lire les N dernières lignes
            for line in lines[-limit:]:
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
                        version=data.get("version", "v2.0")
                    )
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

            # Inverser pour avoir les plus récents en premier
            return entries[::-1]

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

        # Lister les familles de shards segmentés
        for shard_family_dir in self.shards_dir.glob("shard_*"):
            if shard_family_dir.is_dir():
                shard_id = f"shard_{shard_family_dir.name}"
                # Compter les entrées totales (lecture multi-segments)
                total_events = 0
                for event_data in self.segment_manager.iter_shard_events(shard_id):
                    total_events += 1

                # Récupérer la timestamp du dernier événement
                last_timestamp = None
                for event_data in self.segment_manager.iter_shard_events(shard_id):
                    if last_timestamp is None or event_data.get("timestamp", "") > last_timestamp:
                        last_timestamp = event_data.get("timestamp")
                if last_timestamp:
                    last_updated = datetime.fromisoformat(last_timestamp)
                else:
                    last_updated = datetime.utcnow()

                shards.append(ShardMeta(
                    shard_id=shard_id,
                    created_at=last_updated,
                    last_updated=last_updated,
                    entry_count=total_events,
                    size_bytes=0,  # À calculer
                    integrity_status="verified"
                ))

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
        """Récupère le dernier hash de la chaîne pour un shard"""
        last_hash_file = self.integrity_dir / f"{shard_id}_last_hash.json"

        if last_hash_file.exists():
            with open(last_hash_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("last_hash")

        return None

    def _set_last_hash(self, shard_id: str, hash_value: str):
        """Définit le dernier hash de la chaîne pour un shard"""
        last_hash_file = self.integrity_dir / f"{shard_id}_last_hash.json"

        data = {
            "shard_id": shard_id,
            "last_hash": hash_value,
            "updated_at": datetime.utcnow().isoformat()
        }

        with open(last_hash_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _get_shard_metadata(self, shard_id: str) -> ShardMeta:
        """Récupère les métadonnées d'un shard"""
        last_hash_file = self.integrity_dir / f"{shard_id}_last_hash.json"

        if last_hash_file.exists():
            created_at = datetime.fromtimestamp(last_hash_file.stat().st_mtime)
            return ShardMeta(
                shard_id=shard_id,
                created_at=created_at,
                last_updated=created_at,
                entry_count=0,  # À calculer
                size_bytes=last_hash_file.stat().st_size,
                integrity_status="verified"
            )
        else:
            return ShardMeta(
                shard_id=shard_id,
                created_at=datetime.utcnow(),
                last_updated=datetime.utcnow(),
                entry_count=0,
                size_bytes=0,
                integrity_status="unknown"
            )

    def _update_shard_metadata(self, shard_id: str):
        """Met à jour les métadonnées d'un shard après un append"""
        last_hash_file = self.integrity_dir / f"{shard_id}_last_hash.json"

        # Lire les métadonnées existantes si présentes pour préserver last_hash
        existing = {}
        if last_hash_file.exists():
            try:
                with open(last_hash_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        # Préserver last_hash et mettre à jour timestamp
        data = {
            "shard_id": shard_id,
            "updated_at": datetime.utcnow().isoformat(),
            "last_hash": existing.get("last_hash")
        }

        with open(last_hash_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
