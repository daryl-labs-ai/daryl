#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Session Graph Test Runner
Test isolé pour valider l'enregistrement de sessions
"""

import hashlib
import sys
from pathlib import Path

# Ajouter le parent au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from core.storage import Storage
from session_graph import SessionGraph


def main():
    """Execute le test Session Graph"""

    print("=" * 60)
    print("DSM Session Graph Test Runner")
    print("=" * 60)

    # Configuration DSM isolé
    test_dir = Path.home() / "clawdbot_dsm_test" / "memory"
    print(f"\n📂 DSM test directory: {test_dir}")
    print(f"📂 Shards directory: {test_dir / 'shards'}")

    # Créer le storage isolé
    print("\n🔧 Initialisation DSM Storage...")
    storage = Storage(data_dir=str(test_dir))

    # Créer le graphe de session
    print("🔧 Initialisation SessionGraph...")
    session = SessionGraph(storage)
    print(f"🆔 Session ID: {session.session_id}")

    # Simuler un snapshot Moltbook
    print("\n📸 Simulation snapshot Moltbook...")
    snapshot = {
        "notifications": 3,
        "dms": 1
    }
    snapshot_hash = hashlib.sha256(str(snapshot).encode()).hexdigest()
    print(f"📦 Snapshot: {snapshot}")
    print(f"🔐 Hash: {snapshot_hash[:16]}...")

    # Enregistrer les transactions
    print("\n📝 Enregistrement transactions DSM...")

    entry1 = session.record_snapshot(snapshot_hash)
    print(f"✅ Snapshot enregistré: {entry1.id[:16]}...")

    entry2 = session.record_action("reply_to_post")
    print(f"✅ Action enregistrée: {entry2.id[:16]}...")

    entry3 = session.record_outcome("karma_gain=3")
    print(f"✅ Outcome enregistré: {entry3.id[:16]}...")

    # Valider les résultats
    print("\n" + "=" * 60)
    print("🔍 Validation des résultats")
    print("=" * 60)

    shard_file = test_dir / "shards" / "shard_sessions.jsonl"

    if shard_file.exists():
        print(f"\n✅ Shard créé: {shard_file}")
        print(f"📏 Taille: {shard_file.stat().st_size} bytes")

        # Lire et afficher les entrées
        entries = storage.read("shard_sessions", limit=10)
        print(f"\n📋 Entrées dans le shard: {len(entries)}")

        for i, entry in enumerate(entries, 1):
            print(f"\n  {i}. {entry.source}")
            print(f"     Content: {entry.content}")
            print(f"     Importance: {entry.metadata.get('importance', 0)}")
            print(f"     Hash: {entry.hash[:16]}...")

        print("\n" + "=" * 60)
        print("✅ DSM Session Graph test COMPLETED")
        print("=" * 60)
    else:
        print(f"\n❌ ERREUR: Shard non créé: {shard_file}")
        print("\n📂 DSM paths diagnostiques:")
        print(f"   data_dir: {test_dir}")
        print(f"   shards_dir: {test_dir / 'shards'}")
        print(f"   shards exists: {(test_dir / 'shards').exists()}")
        print(f"   shards contents: {list((test_dir / 'shards').glob('*')) if (test_dir / 'shards').exists() else 'N/A'}")

        print("\n" + "=" * 60)
        print("❌ DSM Session Graph test FAILED")
        print("=" * 60)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
