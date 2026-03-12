#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Snapshot Dedup Test
Valide que les snapshots identiques ne sont pas écrits plusieurs fois
"""

import sys
import hashlib
from pathlib import Path

# Ajouter le parent au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from core.storage import Storage
from session_graph import SessionGraph


def run_dedup_test():
    """Execute le test de déduplication de snapshots"""

    print("=" * 70)
    print("DSM v2 Snapshot Dedup Test")
    print("=" * 70)
    print("\nObjectif:")
    print("- 5 sessions avec le MÊME snapshot")
    print("- Seul le 1er HOME_SNAPSHOT doit être écrit")
    print("- Les 4 suivants doivent être SKIP (déducliqués)")
    print("=" * 70)

    # Configuration DSM isolé
    test_dir = Path.home() / "clawdbot_dsm_test" / "memory"
    print(f"\n📂 DSM test directory: {test_dir}")

    # Créer le storage isolé
    print("\n🔧 Initialisation DSM Storage...")
    storage = Storage(data_dir=str(test_dir))

    # Snapshot fixe (même pour toutes les sessions)
    snapshot = {
        "notifications": 3,
        "dms": 1,
        "posts": 5
    }
    snapshot_hash = hashlib.sha256(str(snapshot).encode()).hexdigest()

    print(f"\n📦 Snapshot fixe:")
    print(f"   Notifications: {snapshot['notifications']}")
    print(f"   DMs: {snapshot['dms']}")
    print(f"   Hash: {snapshot_hash[:16]}...")

    # 5 sessions avec le même snapshot
    SESSIONS = 5

    print(f"\n🚀 Lancement de {SESSIONS} sessions avec snapshot identique...")
    print("-" * 70)

    snapshots_written = 0
    snapshots_skipped = 0

    for i in range(SESSIONS):
        print(f"\nSession {i + 1}/{SESSIONS}:")

        # Créer une nouvelle session
        session = SessionGraph(storage)
        print(f"   🆔 Session ID: {session.session_id[:16]}...")

        # Essayer d'enregistrer le snapshot
        entry = session.record_snapshot(
            raw_snapshot_hash=snapshot_hash,
            snapshot_data=snapshot
        )

        if entry:
            snapshots_written += 1
            print(f"   ✅ HOME_SNAPSHOT écrit (hash: {entry.hash[:16]}...)")
        else:
            snapshots_skipped += 1
            print(f"   📦 Snapshot SKIP (dupliqué)")

        # Enregistrer une action
        action_entry = session.record_action("test_action")
        print(f"   ⚡ ACTION_EXECUTED: {action_entry.content[:30]}...")

        # Enregistrer un outcome
        outcome_entry = session.record_outcome("test_outcome")
        print(f"   📈 ACTION_OUTCOME: {outcome_entry.content[:30]}...")

    print("\n" + "=" * 70)
    print("🔍 VALIDATION DES RÉSULTATS")
    print("=" * 70)

    # Vérifier le shard
    shard_file = test_dir / "shards" / "shard_sessions.jsonl"

    if not shard_file.exists():
        print(f"\n❌ ERREUR: Shard non créé: {shard_file}")
        return 1

    print(f"\n✅ Shard créé: {shard_file}")
    print(f"📏 Taille: {shard_file.stat().st_size} bytes")

    # Lire et analyser les entrées
    entries = storage.read("shard_sessions", limit=50)
    print(f"\n📋 Entrées totales: {len(entries)}")

    # Compter les HOME_SNAPSHOT
    home_snapshots = [e for e in entries if "HOME_SNAPSHOT" in e.content]
    print(f"\n📸 HOME_SNAPSHOT enregistrés: {len(home_snapshots)}")

    for i, entry in enumerate(home_snapshots, 1):
        print(f"\n  {i}. {entry.content}")
        print(f"     Hash: {entry.metadata.get('hash', 'N/A')[:16]}...")
        print(f"     Session: {entry.metadata.get('session_id', 'N/A')[:16]}...")

    # =========================
    # VALIDATION FINALE
    # =========================
    print("\n" + "=" * 70)

    if len(home_snapshots) == 1:
        print("✅ SNAPSHOT DEDUP TEST PASSED")
        print(f"   {snapshots_written} snapshot écrit (1er)")
        print(f"   {snapshots_skipped} snapshots SKIP (dupliqués)")
        print("=" * 70)
        return 0
    else:
        print("❌ SNAPSHOT DEDUP TEST FAILED")
        print(f"   Attendu: 1 snapshot")
        print(f"   Trouvé: {len(home_snapshots)} snapshots")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(run_dedup_test())
