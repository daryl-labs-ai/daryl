#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - DSM Recycling Memory (DSM-RM)
Module prototype pour le recyclage de mémoire des sessions DSM
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# dsm.modules - uses dsm.core
import sys
_dsm_root = Path(__file__).resolve().parent.parent
_repo_root = _dsm_root.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
sys.path.insert(0, str(_dsm_root))

from dsm.core.shard_segments import ShardSegmentManager


class DSMRecyclingMemory:
    """Module de recyclage de mémoire pour les sessions DSM"""

    def __init__(self, memory_dir: str = None):
        """
        Initialise le module de recyclage de mémoire

        Args:
            memory_dir: Répertoire DSM (optionnel)
        """
        # Configuration du répertoire
        if memory_dir is None:
            memory_dir = str(Path.home() / "clawdbot_dsm_test" / "memory")

        self.memory_dir = Path(memory_dir)
        self.shards_dir = self.memory_dir / "shards"
        self.summaries_dir = self.memory_dir / "summaries"
        self.archive_dir = self.memory_dir / "archive"
        self.recycled_dir = self.memory_dir / "recycled"

        # Créer les sous-répertoires
        self.shards_dir.mkdir(parents=True, exist_ok=True)
        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.recycled_dir.mkdir(parents=True, exist_ok=True)

        # Gestionnaire de segmentation des shards
        self.segment_manager = ShardSegmentManager(base_dir=str(self.memory_dir))

    def _read_session_shard(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Lit tous les events d'une session depuis les shards segmentés

        Args:
            session_id: ID de la session

        Returns:
            List[dict]: Liste des events de la session
        """
        # Utiliser le segment manager pour lire les events
        events = []

        for entry in self.segment_manager.iter_shard_events("shard_sessions"):
            if entry.get("metadata", {}).get("session_id") == session_id:
                events.append(entry)

        return events

    def _aggregate_session_summary(self, session_id: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggrège plusieurs events d'une session en un résumé

        Args:
            session_id: ID de la session
            events: Liste des events de la session

        Returns:
            dict: Résumé de la session
        """
        # Compter les actions
        actions = []
        outcomes = []

        for event in events:
            event_type = event.get("metadata", {}).get("type", "")
            content = event.get("content", "")

            if event_type == "ACTION_SELECTED":
                actions.append(content.replace("ACTION_SELECTED ", ""))
            elif event_type == "ACTION_OUTCOME":
                outcomes.append(content.replace("ACTION_OUTCOME ", ""))

        # Calculer le karma
        karma_gain = 0
        for outcome in outcomes:
            if "karma_gain=" in outcome:
                try:
                    karma_gain += int(outcome.split("karma_gain=")[1].split()[0])
                except ValueError:
                    pass

        # Trouver le dernier event
        last_event = events[-1] if events else None
        last_timestamp = last_event.get("timestamp", "") if last_event else ""

        return {
            "type": "session_summary",
            "session_id": session_id,
            "actions": len(actions),
            "outcomes": len(outcomes),
            "karma_gain": karma_gain,
            "timestamp": last_timestamp
        }

    def _write_session_summary(self, session_summary: Dict[str, Any]) -> bool:
        """
        Écrit un résumé de session dans le shard des résumés

        Args:
            session_summary: Résumé de la session

        Returns:
            bool: True si succès, False sinon
        """
        shard_file = self.summaries_dir / "shard_session_summaries.jsonl"

        try:
            with open(shard_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(session_summary, ensure_ascii=False) + '\n')

            return True
        except Exception as e:
            print(f"❌ Erreur écriture résumé: {e}")
            return False

    def _detect_duplicate_snapshots(self, events: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Détecte les snapshots redondants (même hash)

        Args:
            events: Liste des events de la session

        Returns:
            dict: Snapshots redondants par hash
        """
        snapshot_hashes = defaultdict(list)

        for event in events:
            event_type = event.get("metadata", {}).get("type", "")
            content = event.get("content", "")

            if event_type == "HOME_SNAPSHOT" and content.startswith("HOME_SNAPSHOT "):
                snapshot_hash = content.replace("HOME_SNAPSHOT ", "")

                if snapshot_hash:
                    snapshot_hashes[snapshot_hash].append(event.get("id", ""))

        # Conserver uniquement les plus récents (garder un seul snapshot par état du monde)
        duplicate_snapshots = {}
        for snapshot_hash, event_ids in snapshot_hashes.items():
            if len(event_ids) > 1:
                # Garder le plus récent, marquer les autres comme dupliqués
                duplicate_snapshots[snapshot_hash] = event_ids[:-1]

        return duplicate_snapshots

    def _aggregate_snapshot(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggrège plusieurs snapshots en un seul snapshot agrégé

        Args:
            events: Liste des events de snapshot

        Returns:
            dict: Snapshot agrégé
        """
        if not events:
            return {}

        # Utiliser le hash du premier snapshot
        first_event = events[0]
        content = first_event.get("content", "")
        snapshot_hash = content.replace("HOME_SNAPSHOT ", "")

        # Compter les occurrences
        count = len(events)

        return {
            "type": "snapshot_aggregated",
            "hash": snapshot_hash,
            "count": count,
            "first_event_id": events[0].get("id", ""),
            "timestamp": events[0].get("timestamp", "")
        }

    def _write_snapshot_recycled(self, snapshot_recycled: Dict[str, Any]) -> bool:
        """
        Écrit un événement de snapshot recyclé

        Args:
            snapshot_recycled: Snapshot agrégé

        Returns:
            bool: True si succès, False sinon
        """
        shard_file = self.recycled_dir / "shard_snapshot_recycled.jsonl"

        try:
            with open(shard_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(snapshot_recycled, ensure_ascii=False) + '\n')

            return True
        except Exception as e:
            print(f"❌ Erreur écriture snapshot recyclé: {e}")
            return False

    def _archive_old_sessions(self, days_threshold: int = 30) -> int:
        """
        Archive les sessions anciennes (sans supprimer les données)

        Args:
            days_threshold: Nombre de jours avant l'archivage

        Returns:
            int: Nombre de sessions archivées
        """
        # Lister tous les events de sessions
        sessions_archived = 0

        for event in self.segment_manager.iter_shard_events("shard_sessions"):
            event_type = event.get("metadata", {}).get("type", "")

            if event_type == "SESSION_END":
                timestamp_str = event.get("timestamp", "")

                if timestamp_str:
                    try:
                        event_timestamp = datetime.fromisoformat(timestamp_str)
                        age_days = (datetime.now(timezone.utc) - event_timestamp).days

                        if age_days > days_threshold:
                            # Archiver la session complète
                            archived_event = {
                                "type": "session_archived",
                                "original_event_id": event.get("id", ""),
                                "timestamp": event.get("timestamp", ""),
                                "metadata": event.get("metadata", {})
                            }

                            shard_file = self.archive_dir / f"archived_sessions.jsonl"

                            with open(shard_file, 'a', encoding='utf-8') as f:
                                f.write(json.dumps(archived_event, ensure_ascii=False) + '\n')

                            sessions_archived += 1
                    except ValueError:
                        pass

        return sessions_archived

    def print_recycling_report(self):
        """Affiche un rapport de recyclage de mémoire"""
        print("\n" + "=" * 70)
        print("🔄 DSM RECYCLING MEMORY REPORT")
        print("=" * 70)

        # Compter les résumés de sessions
        summary_file = self.summaries_dir / "shard_session_summaries.jsonl"
        summaries_count = 0

        if summary_file.exists():
            with open(summary_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        summaries_count += 1

        print(f"\n📊 Session Summaries: {summaries_count}")

        # Compter les snapshots recyclés
        recycled_file = self.recycled_dir / "shard_snapshot_recycled.jsonl"
        recycled_count = 0

        if recycled_file.exists():
            with open(recycled_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        recycled_count += 1

        print(f"📊 Snapshots Recycled: {recycled_count}")

        # Compter les sessions archivées
        archive_file = self.archive_dir / "archived_sessions.jsonl"
        archived_count = 0

        if archive_file.exists():
            with open(archive_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        archived_count += 1

        print(f"📊 Sessions Archived: {archived_count}")

        # Total recyclage
        total_recycled = summaries_count + recycled_count + archived_count
        print(f"\n📊 Total Recycling Savings: {total_recycled} records")

        print("\n" + "=" * 70)


def main():
    """Fonction principale pour tester DSM-RM"""
    print("=" * 70)
    print("🔄 DSM v2 - Recycling Memory Test")
    print("=" * 70)

    # Créer le module de recyclage
    recycling = DSMRecyclingMemory()

    # Afficher le rapport de recyclage (initialement vide)
    recycling.print_recycling_report()

    print("\n✅ DSM-RM module implémenté")
    print("📂 Répertoires créés:")
    print(f"   📊 {recycling.summaries_dir}")
    print(f"   🔄 {recycling.recycled_dir}")
    print(f"   🗄️  {recycling.archive_dir}")

    print("\n" + "=" * 70)
    print("RESULTATS")
    print("=" * 70)

    print("\n✅ DSM-RM (Recycling Memory) : MODULE CRÉÉ")
    print("   - Session Summaries : Implémenté")
    print("   - Duplicate Snapshots Détecter : Implémenté")
    print("   - Snapshot Aggregation : Implémenté")
    print("   - Session Archiving : Implémenté (sans suppression)")
    print("   - Test Runner : Prêt (recycling_test.py)")

    print("\n📂 Structure de Répertoires:")
    print(f"   📊 {recycling.summaries_dir}")
    print(f"   🔄 {recycling.recycled_dir}")
    print(f"   🗄️  {recycling.archive_dir}")

    print("\n" + "=" * 70)
    print("DSM-RM READY")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
