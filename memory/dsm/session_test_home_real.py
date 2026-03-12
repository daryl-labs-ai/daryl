#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Session Graph Test Runner (Real Home Endpoint)
Test réel avec /api/v1/home de Moltbook
"""

import sys
from pathlib import Path

# Ajouter le parent au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from core.storage import Storage
from session_graph import SessionGraph
from moltbook_home_client import MoltbookHomeClient


def main():
    """Execute le test Session Graph avec vrai Home endpoint"""

    print("=" * 60)
    print("DSM Session Graph Test Runner (Real Home)")
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

    # Initialiser le client Moltbook Home
    api_key = "moltbook_sk_Wr8D9miMUUWlElGdQGsYxk7zKmYEhJHq"
    print("\n🔧 Initialisation Moltbook Home Client...")
    home_client = MoltbookHomeClient(api_key=api_key)

    # ===============================
    # SESSION START
    # ===============================
    print("\n" + "=" * 60)
    print("📌 SESSION START")
    print("=" * 60)

    entry = session.start_session()
    print(f"✅ {entry.content}")

    # ===============================
    # FETCH HOME SNAPSHOT
    # ===============================
    print("\n" + "=" * 60)
    print("📸 FETCH HOME SNAPSHOT")
    print("=" * 60)

    home = home_client.fetch_home(use_cache=False)

    if not home:
        print("❌ Erreur: Impossible de récupérer le snapshot home")
        return 1

    # Calculer le hash
    snapshot_hash = home_client.compute_hash(home)
    print(f"🔐 Snapshot Hash: {snapshot_hash[:16]}...")

    # Extraire des métriques
    notifs = home_client.get_notifications_count(home)
    dms = home_client.get_unread_dms(home)
    opportunities = home_client.get_high_karma_opportunities(home, min_karma=500)

    print(f"\n📊 Métriques:")
    print(f"   🔔 Notifications: {notifs}")
    print(f"   💬 DMs non lus: {dms}")
    print(f"   ⚡ Opportunités haut karma: {len(opportunities)}")

    # Enregistrer le snapshot
    print(f"\n📝 Enregistrement snapshot DSM...")
    snapshot_entry = session.record_snapshot(
        snapshot_hash=snapshot_hash,
        snapshot_data={
            "notifications": notifs,
            "dms": dms,
            "opportunities_count": len(opportunities),
            "fetched_at": home.get("fetched_at")
        }
    )
    print(f"✅ {snapshot_entry.content}")

    # ===============================
    # SELECT ACTION
    # ===============================
    print("\n" + "=" * 60)
    print("🎯 SELECT ACTION")
    print("=" * 60)

    # Décider de l'action basée sur les données
    if opportunities:
        action = "reply_to_high_karma_post"
        reasoning = f"{len(opportunities)} opportunités haut karma détectées"
    elif dms > 0:
        action = "check_unread_dms"
        reasoning = f"{dms} DMs non lus"
    elif notifs > 0:
        action = "check_notifications"
        reasoning = f"{notifs} notifications non lues"
    else:
        action = "scan_feed"
        reasoning = "Pas d'actions prioritaires, scan du feed"

    print(f"🤖 Action sélectionnée: {action}")
    print(f"💭 Raison: {reasoning}")

    select_entry = session.select_action(action, reasoning=reasoning)
    print(f"✅ {select_entry.content}")

    # ===============================
    # EXECUTE ACTION
    # ===============================
    print("\n" + "=" * 60)
    print("⚡ EXECUTE ACTION")
    print("=" * 60)

    # Simuler l'exécution de l'action
    print(f"🏃 Exécution: {action}")
    action_entry = session.record_action(action)
    print(f"✅ {action_entry.content}")

    # ===============================
    # RECORD OUTCOME
    # ===============================
    print("\n" + "=" * 60)
    print("📈 RECORD OUTCOME")
    print("=" * 60)

    # Simuler un résultat
    if action == "reply_to_high_karma_post":
        outcome = "comment_posted"
        metrics = {
            "karma_gain": 5,
            "engagement": 2,
            "target_post_id": opportunities[0].get("post_id")
        }
    elif action == "check_unread_dms":
        outcome = "dms_replied"
        metrics = {"dms_replied_count": dms}
    else:
        outcome = "scanned"
        metrics = {"posts_scanned": 10}

    print(f"📊 Résultat: {outcome}")
    print(f"📏 Métriques: {metrics}")

    outcome_entry = session.record_outcome(outcome, metrics=metrics)
    print(f"✅ {outcome_entry.content}")

    # ===============================
    # SESSION END
    # ===============================
    print("\n" + "=" * 60)
    print("🏁 SESSION END")
    print("=" * 60)

    end_entry = session.end_session(reason="completed")
    print(f"✅ {end_entry.content}")

    # ===============================
    # VALIDATION
    # ===============================
    print("\n" + "=" * 60)
    print("🔍 VALIDATION DES RÉSULTATS")
    print("=" * 60)

    shard_file = test_dir / "shards" / "shard_sessions.jsonl"

    if shard_file.exists():
        print(f"\n✅ Shard créé: {shard_file}")
        print(f"📏 Taille: {shard_file.stat().st_size} bytes")

        # Lire et afficher les entrées
        entries = storage.read("shard_sessions", limit=20)
        print(f"\n📋 Entrées dans le shard: {len(entries)}")

        for i, entry in enumerate(entries, 1):
            print(f"\n  {i}. {entry.content}")
            metadata = entry.metadata
            entry_type = metadata.get("type", "unknown")
            print(f"     Type: {entry_type}")
            print(f"     Session ID: {metadata.get('session_id', 'N/A')}")
            print(f"     Importance: {metadata.get('importance', 0)}")
            print(f"     Hash: {entry.hash[:16]}...")

        print("\n" + "=" * 60)
        print("✅ DSM Session Graph test COMPLETED (Real Home)")
        print("=" * 60)
    else:
        print(f"\n❌ ERREUR: Shard non créé: {shard_file}")
        print("\n📂 DSM paths diagnostics:")
        print(f"   data_dir: {test_dir}")
        print(f"   shards_dir: {test_dir / 'shards'}")
        print(f"   shards exists: {(test_dir / 'shards').exists()}")

        print("\n" + "=" * 60)
        print("❌ DSM Session Graph test FAILED")
        print("=" * 60)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
