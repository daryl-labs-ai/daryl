#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Snapshot Dedup Validation Test
Valide l'implémentation complète de la déduplication Moltbook /api/v1/home
"""

import sys
import hashlib
import json
from pathlib import Path

# Ajouter le parent au PYTHONPATH
from dsm.core.storage import Storage
from dsm.session.session_graph import SessionGraph
from dsm.moltbook_home_normalizer import MoltbookHomeNormalizer


def run_validation_test():
    """Execute le test de validation de la déduplication"""

    print("=" * 70)
    print("DSM v2 Snapshot Dedup Validation Test")
    print("=" * 70)
    print("\nObjectif:")
    print("Valider que DSM + SessionGraph + MoltbookHomeNormalizer")
    print("collaborent correctement pour la déduplication de snapshots.")
    print("=" * 70)

    # Configuration DSM isolé
    test_dir = Path.home() / "clawdbot_dsm_test" / "memory"
    print(f"\n📂 DSM test directory: {test_dir}")

    # Créer le storage isolé
    print("\n🔧 Initialisation DSM Storage + SessionGraph...")
    storage = Storage(data_dir=str(test_dir))
    session_graph = SessionGraph(storage=storage)

    # Créer le normalizer
    home_normalizer = MoltbookHomeNormalizer(verbose=False)

    # ================================================================
    # CYCLE 1 : 5 cycles avec le MÊME home (normalisé)
    # ================================================================
    print("\n" + "=" * 70)
    print("📌 CYCLE 1 : 5 cycles avec le MÊME home")
    print("=" * 70)
    print("Attendu: 1 snapshot écrit, 4 snapshot SKIP")

    # Créer un home mock (stables)
    home_mock_1 = {
        "your_account": {
            "unread_notification_count": 100
        },
        "your_direct_messages": {
            "unread_message_count": "05"  # String pour tester la robustesse
        },
        "activity_on_your_posts": [
            {"post_id": "post-001", "new_notification_count": 50},
            {"post_id": "post-002", "new_notification_count": 25}
        ],
        "posts_from_accounts_you_follow": {
            "posts": [
                {"post_id": "post-003", "upvotes": 100},
                {"post_id": "post-004", "upvotes": 50}
            ]
        },
        "latest_moltbook_announcement": {
            "post_id": "ann-001"
        }
    }

    # Normaliser et calculer le hash
    normalized_1 = home_normalizer.normalize(home_mock_1)
    hash_1 = home_normalizer.compute_hash(normalized_1)

    print(f"\n📦 Home Mock #1:")
    print(f"   🔔 Notifications: {normalized_1['unread_notification_count']}")
    print(f"   💬 DMs non lus: {normalized_1['unread_message_count']}")
    print(f"   📊 Activité: {normalized_1['activity_posts_count']} posts")
    print(f"   📸 Hash: {hash_1[:16]}...")

    for i in range(5):
        print(f"\nCycle {i + 1}/5:")
        session_graph.start_session()

        entry = session_graph.record_snapshot(home=home_mock_1, force=(i == 0))
        if entry:
            print(f"   ✅ HOME_SNAPSHOT écrit (hash: {entry.metadata.get('raw_hash', 'N/A')[:16]}...)")
        else:
            print(f"   📦 Snapshot SKIP (déducliqué)")

        session_graph.select_action("mock_action")
        session_graph.record_action("mock_action")
        session_graph.record_outcome("mock_outcome")

    # ================================================================
    # CYCLE 2 : 5 cycles avec un home MODIFIÉ
    # ================================================================
    print("\n" + "=" * 70)
    print("📌 CYCLE 2 : 5 cycles avec un home MODIFIÉ")
    print("=" * 70)
    print("Attendu: 1 snapshot écrit, 4 snapshot SKIP")

    # Modifier légèrement le home (changment détectable)
    home_mock_2 = home_mock_1.copy()
    home_mock_2["your_account"]["unread_notification_count"] = 101  # Changement

    # Normaliser et calculer le hash
    normalized_2 = home_normalizer.normalize(home_mock_2)
    hash_2 = home_normalizer.compute_hash(normalized_2)

    print(f"\n📦 Home Mock #2:")
    print(f"   🔔 Notifications: {normalized_2['unread_notification_count']}")
    print(f"   📸 Hash: {hash_2[:16]}...")

    for i in range(5):
        print(f"\nCycle {i + 1}/5:")
        session_graph.start_session()

        entry = session_graph.record_snapshot(home=home_mock_2, force=(i == 0))
        if entry:
            print(f"   ✅ HOME_SNAPSHOT écrit (hash: {entry.metadata.get('raw_hash', 'N/A')[:16]}...)")
        else:
            print(f"   📦 Snapshot SKIP (déducliqué)")

        session_graph.select_action("mock_action")
        session_graph.record_action("mock_action")
        session_graph.record_outcome("mock_outcome")

    # ================================================================
    # VALIDATION FINALE
    # ================================================================
    print("\n" + "=" * 70)
    print("🔍 VALIDATION DES RÉSULTATS")
    print("=" * 70)

    # Vérifier le shard
    shard_file = test_dir / "shards" / "shard_sessions.jsonl"

    if not shard_file.exists():
        print(f"\n❌ ERREUR: Shard non créé: {shard_file}")
        return 1

    # Compter les snapshots écrits et les skip
    entries = storage.read("shard_sessions", limit=100)

    home_snapshots = [e for e in entries if "HOME_SNAPSHOT" in e.content]
    skipped_snapshots = [e for e in entries if "HOME_SNAPSHOT_SKIPPED" in e.content]

    print(f"\n📊 Statistiques:")
    print(f"   HOME_SNAPSHOT écrits: {len(home_snapshots)}")
    print(f"   HOME_SNAPSHOT_SKIPPED: {len(skipped_snapshots)}")
    print(f"   Entrées totales: {len(entries)}")

    # Vérifier le sidecar
    sidecar_path = session_graph._get_sidecar_path("last_home_snapshot_hash.txt")
    if sidecar_path.exists():
        with open(sidecar_path, 'r', encoding='utf-8') as f:
            last_hash = f.read().strip()
            print(f"\n📂 Sidecar (last_home_snapshot_hash.txt):")
            print(f"   {last_hash[:16]}...")
    else:
        print(f"\n❌ ERREUR: Sidecar non créé")
        return 1

    # Valider les hash
    print(f"\n🔍 Validation des hash:")
    print(f"   Attendu Hash #1: {hash_1[:16]}...")
    print(f"   Attendu Hash #2: {hash_2[:16]}...")

    # Vérifier que les hash sont différents
    if hash_1 != hash_2:
        print(f"   ✅ Hash différents (comportement attendu)")
    else:
        print(f"   ❌ Hash identiques (erreur de logique)")

    # Vérifier le nombre de snapshots écrits (doit être 2)
    if len(home_snapshots) == 2:
        print(f"   ✅ 2 snapshots écrits (correct)")
    else:
        print(f"   ❌ {len(home_snapshots)} snapshots écrits (attendu: 2)")

    # ================================================================
    # RÉSULTAT FINAL
    # ================================================================
    print("\n" + "=" * 70)

    if (
        shard_file.exists() and
        len(home_snapshots) == 2 and
        len(skipped_snapshots) == 8 and  # 5 cycles × 2 - 2 écrits = 8 skips
        hash_1 != hash_2 and
        sidecar_path.exists()
    ):
        print("✅ SNAPSHOT DEDUP VALIDATION TEST PASSED")
        print("=" * 70)
        print("\n🎉 DSM + SessionGraph + MoltbookHomeNormalizer sont opérationnels !")
        print("La déduplication de snapshots est fonctionnelle.")
        return 0
    else:
        print("❌ SNAPSHOT DEDUP VALIDATION TEST FAILED")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(run_validation_test())
