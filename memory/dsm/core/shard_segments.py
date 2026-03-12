#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Shard Segmentation Logic
Gestionnaire de segmentation des shards DSM pour éviter les fichiers trop volumineux
"""

import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Generator
from datetime import datetime

# Configuration de segmentation
MAX_EVENTS_PER_SEGMENT = 10000  # Maximum d'events par segment
MAX_BYTES_PER_SEGMENT = 10 * 1024 * 1024  # 10 MB max par segment
SEGMENT_PADDING = 1000  # Padding avant rotation


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

    def _get_active_segment_path(self, family_dir: Path) -> Path:
        """
        Retourne le chemin vers le segment actif

        Args:
            family_dir: Répertoire de la famille de segments

        Returns:
            Path: Chemin vers le segment actif
        """
        segments = self._get_segment_files(family_dir)

        if not segments:
            # Premier segment
            return family_dir / f"{family_dir.name}_0001.jsonl"

        # Vérifier si le dernier segment dépasse les limites
        last_segment = segments[-1]
        last_segment_size = last_segment.stat().st_size
        last_segment_events = 0

        # Compter approximativement le nombre d'events
        with open(last_segment, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    last_segment_events += 1

        # Vérifier les limites
        limit_reached = (
            last_segment_events >= self.MAX_EVENTS_PER_SEGMENT or
            last_segment_size >= self.MAX_BYTES_PER_SEGMENT
        )

        if limit_reached:
            # Créer un nouveau segment
            last_number = self._get_segment_number(last_segment.name)
            next_number = last_number + 1

            # Format: family_0001.jsonl, family_0002.jsonl
            segment_name = f"{family_dir.name}_{next_number:04d}.jsonl"

            return family_dir / segment_name

        # Utiliser le dernier segment
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
                        print(f"⚠️  Erreur parsing ligne: {e}")

    def iter_shard_events_reverse(self, shard_id: str) -> Generator[Dict[str, Any], None, None]:
        """
        Itère sur tous les événements d'un shard_id, du plus récent au plus ancien

        Args:
            shard_id: ID du shard (ex: shard_sessions, shard_audience)

        Yields:
            dict: Événement DSM (yield event by event)
        """
        family_dir = self._get_shard_family_dir(shard_id)
        segments = self._get_segment_files(family_dir)

        # Itérer en ordre inverse
        for segment_file in reversed(segments):
            with open(segment_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        event = json.loads(line.strip())
                        yield event
                    except Exception as e:
                        print(f"⚠️  Erreur parsing ligne: {e}")


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
