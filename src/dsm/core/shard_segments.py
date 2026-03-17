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
DSM v2 - Shard Segmentation Logic
Gestionnaire de segmentation des shards DSM pour éviter les fichiers trop volumineux.
Uses segment_meta.json per shard family for O(1) active segment resolution (no line counting).
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from ._compat import portable_lock_fd

logger = logging.getLogger(__name__)

# Configuration de segmentation
MAX_EVENTS_PER_SEGMENT = 10000  # Maximum d'events par segment
MAX_BYTES_PER_SEGMENT = 10 * 1024 * 1024  # 10 MB max par segment
SEGMENT_PADDING = 1000  # Padding avant rotation

SEGMENT_META_FILENAME = "segment_meta.json"


class ShardSegmentManager:
    """Gestionnaire de segmentation des shards DSM"""

    def __init__(self, base_dir: str = None):
        """
        Initialise le gestionnaire de segmentation

        Args:
            base_dir: Répertoire DSM (optionnel)
        """
        if base_dir is None:
            base_dir = str(Path.home() / "clawdbot_dsm_test" / "memory")

        self.base_dir = Path(base_dir)
        self.shards_dir = self.base_dir / "shards"
        self.shards_dir.mkdir(parents=True, exist_ok=True)

        # Logique de rotation
        self.MAX_EVENTS_PER_SEGMENT = MAX_EVENTS_PER_SEGMENT
        self.MAX_BYTES_PER_SEGMENT = MAX_BYTES_PER_SEGMENT

    def _get_shard_family_dir(self, shard_id: str) -> Path:
        """
        Retourne le répertoire de la famille de segments pour un shard_id

        Args:
            shard_id: ID du shard (ex: shard_sessions, shard_audience)

        Returns:
            Path: Répertoire de la famille de segments
        """
        # Extraire le nom de base (enlever le préfixe shard_)
        family_name = shard_id.replace("shard_", "")

        # Créer le répertoire de famille
        family_dir = self.shards_dir / family_name

        # Créer le répertoire s'il n'existe pas
        family_dir.mkdir(parents=True, exist_ok=True)

        return family_dir

    def _get_segment_files(self, family_dir: Path) -> List[Path]:
        """
        Retourne la liste des fichiers de segments dans l'ordre

        Args:
            family_dir: Répertoire de la famille de segments

        Returns:
            List[Path]: Liste des fichiers triés par numéro de segment
        """
        segments = list(family_dir.glob("*.jsonl"))

        # Trier par numéro de segment
        def segment_number(filename: Path) -> int:
            basename = filename.stem  # Enlever l'extension
            if basename.startswith(family_dir.name + "_"):
                # Format: family_0001.jsonl
                try:
                    return int(basename.split("_")[-1])
                except ValueError:
                    return 9999
            return 9999

        segments.sort(key=segment_number)

        return segments

    def _segment_meta_path(self, family_dir: Path) -> Path:
        """Path to segment_meta.json for this shard family."""
        return family_dir / SEGMENT_META_FILENAME

    def _read_segment_meta(self, family_dir: Path) -> Optional[Dict[str, Any]]:
        """Read segment_meta.json with portable lock (W-7 fix)."""
        meta_path = self._segment_meta_path(family_dir)
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                with portable_lock_fd(f):
                    return json.load(f)
        except Exception as e:
            logger.debug("segment meta read failed: %s", e)
            return None

    def _write_segment_meta_atomic(self, family_dir: Path, data: Dict[str, Any]) -> None:
        """Write segment_meta.json atomically with portable lock (W-7 fix)."""
        meta_path = self._segment_meta_path(family_dir)
        tmp_path = meta_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            with portable_lock_fd(f):
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
        os.replace(tmp_path, meta_path)

    def _get_active_segment_path(self, family_dir: Path) -> Path:
        """
        Return path to the active segment. Uses segment_meta.json for O(1) when present;
        otherwise falls back to scanning and creates metadata.
        """
        meta = self._read_segment_meta(family_dir)

        if meta is not None:
            active_name = meta.get("active_segment")
            event_count = meta.get("event_count", 0)
            size_bytes = meta.get("size_bytes", 0)
            if active_name and isinstance(active_name, str):
                active_path = family_dir / active_name
                limit_reached = (
                    event_count >= self.MAX_EVENTS_PER_SEGMENT
                    or size_bytes >= self.MAX_BYTES_PER_SEGMENT
                )
                if limit_reached:
                    # Hold exclusive lock during rotation to prevent race
                    next_number = self._get_segment_number(active_name) + 1
                    next_name = f"{family_dir.name}_{next_number:04d}.jsonl"
                    self._write_segment_meta_atomic(
                        family_dir,
                        {"active_segment": next_name, "event_count": 0, "size_bytes": 0},
                    )
                    return family_dir / next_name
                return active_path

        # Fallback: scan last segment and create metadata
        segments = self._get_segment_files(family_dir)
        if not segments:
            first_name = f"{family_dir.name}_0001.jsonl"
            self._write_segment_meta_atomic(
                family_dir,
                {"active_segment": first_name, "event_count": 0, "size_bytes": 0},
            )
            return family_dir / first_name

        last_segment = segments[-1]
        last_segment_size = last_segment.stat().st_size
        last_segment_events = 0
        with open(last_segment, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_segment_events += 1

        active_name = last_segment.name
        self._write_segment_meta_atomic(
            family_dir,
            {
                "active_segment": active_name,
                "event_count": last_segment_events,
                "size_bytes": last_segment_size,
            },
        )
        return last_segment

    def _get_segment_number(self, filename: str) -> int:
        """
        Extrait le numéro de segment depuis un nom de fichier

        Args:
            filename: Nom du fichier (ex: shard_sessions_0001.jsonl)

        Returns:
            int: Numéro de segment
        """
        # Extraire le nom de base (enlever l'extension)
        basename = filename.replace(".jsonl", "")

        # Extraire le numéro de segment (les 4 derniers caractères)
        if "_" in basename:
            try:
                return int(basename.split("_")[-1])
            except ValueError:
                return 9999

        return 9999

    def get_active_segment(self, shard_id: str) -> Path:
        """
        Retourne le chemin du segment actif pour un shard_id

        Args:
            shard_id: ID du shard (ex: shard_sessions, shard_audience)

        Returns:
            Path: Chemin vers le segment actif
        """
        family_dir = self._get_shard_family_dir(shard_id)
        return self._get_active_segment_path(family_dir)

    def get_segment_files_ordered(self, shard_id: str, reverse: bool = False) -> List[Path]:
        """
        Return segment file paths in chronological order (0001, 0002, ...).
        If reverse=True, return newest-first (for streaming read).
        """
        family_dir = self._get_shard_family_dir(shard_id)
        segments = self._get_segment_files(family_dir)
        if reverse:
            return list(reversed(segments))
        return segments

    def update_active_segment_metadata(
        self,
        shard_id: str,
        delta_events: int = 1,
        delta_bytes: int = 0,
    ) -> None:
        """
        Update segment_meta.json after an append (increment event_count and size_bytes).
        Call from Storage.append() while holding the segment lock.
        """
        family_dir = self._get_shard_family_dir(shard_id)
        meta = self._read_segment_meta(family_dir)
        if meta is None:
            return
        event_count = meta.get("event_count", 0) + delta_events
        size_bytes = meta.get("size_bytes", 0) + delta_bytes
        self._write_segment_meta_atomic(
            family_dir,
            {
                "active_segment": meta.get("active_segment", ""),
                "event_count": event_count,
                "size_bytes": size_bytes,
            },
        )

    def iter_shard_events(self, shard_id: str) -> Generator[Dict[str, Any], None, None]:
        """
        Itère sur tous les événements d'un shard_id, y compris les segments

        Args:
            shard_id: ID du shard (ex: shard_sessions, shard_audience)

        Yields:
            dict: Événement DSM (yield event by event)
        """
        family_dir = self._get_shard_family_dir(shard_id)
        segments = self._get_segment_files(family_dir)

        for segment_file in segments:
            with open(segment_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        event = json.loads(line.strip())
                        yield event
                    except Exception as e:
                        logger.warning(
                            "Malformed JSONL line in shard %s, segment %s: %s",
                            shard_id,
                            segment_file.name,
                            e,
                        )

    def iter_shard_events_reverse(self, shard_id: str) -> Generator[Dict[str, Any], None, None]:
        """
        Itère sur tous les événements d'un shard_id, du plus récent au plus ancien.
        Ordre vrai reverse chronologique : dernier segment en premier, lignes de chaque
        segment de la dernière à la première.
        """
        family_dir = self._get_shard_family_dir(shard_id)
        segments = self._get_segment_files(family_dir)

        for segment_file in reversed(segments):
            with open(segment_file, "r", encoding="utf-8") as f:
                # readlines() then reversed(): acceptable given segment rotation (~10k entries max)
                lines = f.readlines()
            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line.strip())
                    yield event
                except Exception as e:
                    logger.warning(
                        "Malformed JSONL line in shard %s, segment %s: %s",
                        shard_id,
                        segment_file.name,
                        e,
                    )


def main():
    """Fonction principale pour tester la segmentation"""
    manager = ShardSegmentManager()

    print("=" * 70)
    print("🔍 TEST DE SEGMENTATION SHARD")
    print("=" * 70)

    # Test 1: Obtenir le segment actif pour shard_sessions
    print("\n📋 Test 1: Segment actif pour shard_sessions")
    family_dir = manager._get_shard_family_dir("shard_sessions")
    active_segment = manager.get_active_segment("shard_sessions")

    print(f"   Répertoire famille: {family_dir}")
    print(f"   Segment actif: {active_segment.name}")
    print(f"   Chemin complet: {active_segment}")

    # Test 2: Lister les segments existants
    print("\n📋 Test 2: Segments existants")
    segments = manager._get_segment_files(family_dir)
    print(f"   Nombre de segments: {len(segments)}")
    for segment in segments:
        print(f"   - {segment.name}")

    # Test 3: Vérifier la rotation
    print("\n📋 Test 3: Vérification de rotation")
    print(f"   Limite events: {manager.MAX_EVENTS_PER_SEGMENT}")
    print(f"   Limite taille: {manager.MAX_BYTES_PER_SEGMENT / (1024 * 1024):.1f} MB")

    # Simuler des segments
    print("\n📋 Simulation de rotation")
    for i in range(1, 6):
        # Simuler des tailles de segments
        current_segment = f"{family_dir.name}_{i:04d}.jsonl"

        if i >= 3:
            print(f"   Segment {i}: {current_segment} -> Rotation requise")
        else:
            print(f"   Segment {i}: {current_segment}")

    print("\n✅ Test de segmentation terminé")
    print("=" * 70)

    # Afficher la structure de répertoires
    print("\n📂 Structure de répertoires DSM:")
    print(f"   📂 {manager.shards_dir}")
    print(f"      ├── 📂 {manager.shards_dir / 'shard_sessions'}")
    print(f"      └── 📂 {manager.shards_dir / 'shard_audience'}")


if __name__ == "__main__":
    main()
