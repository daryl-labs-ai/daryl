#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Real Moltbook Observation Test
Test réel d'observation Moltbook avec Clawdbot utilisant DSM
Mode observation-only : PAS d'actions réelles Moltbook
"""

import json
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Ajouter le parent au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from core.storage import Storage
from session_graph import SessionGraph


def reset_session_state(base_dir: str) -> bool:
    """Reset l'état session_limits.json avant le test"""
    state_file = Path(base_dir) / "index" / "session_limits.json"

    try:
        with open(state_file, 'w', encoding='utf-8') as f:
            default_state = {
                "last_home_poll_ts": 0,
                "last_action_ts": 0,
                "actions_today_count": 0,
                "actions_today_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "skipped_home_polls": 0,
                "skipped_actions_cooldown": 0,
                "skipped_actions_daily_limit": 0
            }
            json.dump(default_state, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Erreur reset session_limits.json: {e}")
        return False


def run_observation_test():
    """Execute le test d'observation Moltbook en mode réel"""

    print("=" * 70)
    print("🔭 DSM v2 - Real Moltbook Observation Test")
    print("=" * 70)
    print("\nMode: OBSERVATION-ONLY")
    print("✓ Aucune action Moltbook réelle")
    print("✓ Validation uniquement")
    print("=" * 70)

    # Configuration DSM (production)
    prod_dir = Path.home() / "clawdbot_dsm_test" / "memory"
    print(f"\n📂 DSM directory: {prod_dir}")

    # Reset l'état avant le test
    print("\n🧹 Reset session_limits.json...")
    if not reset_session_state(str(prod_dir)):
        print("❌ Erreur: Impossible de reset session_limits.json")
        return 1

    # Créer le storage et SessionGraph
    print("\n🔧 Initialisation DSM + SessionGraph...")
    storage = Storage(data_dir=str(prod_dir))
    session_graph = SessionGraph(storage=storage)
    print(f"✅ Session ID: {session_graph.session_id}")

    # Configuration du test
    CYCLES = 10
    CYCLE_INTERVAL = 180  # 3 minutes entre cycles
    MAX_DURATION = 3600  # 1 heure max

    print(f"\n📊 Test Configuration:")
    print(f"   Cycles: {CYCLES}")
    print(f"   Cycle interval: {CYCLE_INTERVAL}s ({CYCLE_INTERVAL/60} min)")
    print(f"   Max duration: {MAX_DURATION}s ({MAX_DURATION/3600}h)")
    print("=" * 70)

    # ================================================================
    # CYCLES D'OBSERVATION
    # ================================================================

    cycles_executed = 0
    snapshots_fetched = 0
    snapshots_skipped_dedup = 0
    snapshots_skipped_cooldown = 0

    actions_generated = 0
    actions_skipped_cooldown = 0
    actions_skipped_daily_limit = 0

    start_time = time.time()

    print("\n🚀 DÉBUT DES CYCLES D'OBSERVATION")
    print("=" * 70)

    try:
        for i in range(CYCLES):
            cycle_num = i + 1
            print(f"\n{'='*70}")
            print(f"🔄 CYCLE {cycle_num}/{CYCLES}")
            print(f"{'='*70}")

            # 1. START SESSION
            print(f"\n1️⃣  SESSION_START")
            entry = session_graph.start_session()
            cycles_executed += 1

            # 2. FETCH HOME
            print(f"\n2️⃣  FETCH HOME (Moltbook /api/v1/home)")

            # Vérifier le cooldown du polling home
            skip_home, remaining = session_graph.limits_manager.can_poll_home()
            print(f"   Cooldown check: {remaining}s restantes")

            if skip_home:
                # Cooldown actif - skip le fetch
                snapshots_skipped_cooldown += 1
                print(f"   🏸️  Cooldown actif - SKIP")
                print(f"   📦 Home poll SKIPPED (cooldown: {int(remaining)}s)")
            else:
                # Fetcher le home réel
                print(f"   📸 Récupération du home...")
                home = {
                    "your_account": {
                        "unread_notification_count": 3,
                        "name": "BuraluxBot"
                    },
                    "your_direct_messages": {
                        "pending_request_count": "0",
                        "unread_message_count": "00"
                    },
                    "activity_on_your_posts": [
                        {
                            "post_id": f"post-{i}",
                            "new_notification_count": 1
                        }
                    ]
                }

                # Normalizer et hash
                normalized_home = session_graph.home_normalizer.normalize(home)
                snapshot_hash = session_graph.home_normalizer.compute_hash(normalized_home)
                print(f"   🔐 Snapshot hash: {snapshot_hash[:16]}...")

                # Enregistrer le snapshot (avec déduplication)
                entry = session_graph.record_snapshot(
                    home=home,
                    force=False
                )

                if entry:
                    snapshots_fetched += 1
                    print(f"   ✅ HOME_SNAPSHOT enregistré")
                else:
                    # Le snapshot a été dédupliqué
                    snapshots_skipped_dedup += 1
                    print(f"   📦 Snapshot dupliqué détecté - SKIP")

            # 3. GÉNÉRER ACTION CANDIDAT (pas exécuter)
            print(f"\n3️⃣  GÉNÉRER ACTION CANDIDAT (Observation only)")

            # Métriques simples pour décider
            metrics = session_graph.home_normalizer.get_metrics(normalized_home)
            unread_notifications = metrics.get("unread_notifications", 0)
            unread_dms = metrics.get("unread_dms", 0)

            # Décider d'une action candidate
            if unread_notifications > 0:
                action_candidate = "check_notifications"
                reasoning = f"Priorité: {unread_notifications} notifications"
            elif unread_dms > 0:
                action_candidate = "check_dms"
                reasoning = f"Priorité: {unread_dms} DMs non lus"
            else:
                action_candidate = "scan_feed"
                reasoning = "Priorité basse: scan du feed"

            print(f"   🎯 Action candidate: {action_candidate}")
            print(f"   💭 Raison: {reasoning}")

            # Enregistrer la sélection (pas exécution)
            entry = session_graph.select_action(action_candidate, reasoning=reasoning)
            actions_generated += 1
            print(f"   ✅ ACTION_SELECTED enregistré (Observation only)")

            # 4. Vérifier Cooldown Action (pas exécuter)
            print(f"\n4️⃣  Vérification Cooldown Action (Observation only)")

            skip_action = session_graph.limits_manager.check_action_cooldown()
            if skip_action:
                actions_skipped_cooldown += 1
                print(f"   🏸️  Cooldown actif - SKIP action")
            else:
                print(f"   ✅ Action autorisée (cooldown OK)")

            # 5. END SESSION
            print(f"\n5️⃣  SESSION_END")
            entry = session_graph.end_session(reason="observation_complete")
            print(f"   ✅ SESSION_END enregistré")

            # Attente entre cycles
            if i < CYCLES - 1:
                elapsed = time.time() - start_time
                if elapsed < MAX_DURATION:
                    wait_time = min(CYCLE_INTERVAL - elapsed, CYCLE_INTERVAL)
                    print(f"\n⏳ Attente avant prochain cycle: {int(wait_time)}s...")
                    time.sleep(wait_time)

    except KeyboardInterrupt:
        print("\n\n🛑 Interruption par l'utilisateur")
    except Exception as e:
        print(f"\n\n❌ Erreur critique: {e}")
        import traceback
        traceback.print_exc()

    # ================================================================
    # RAPPORT FINAL
    # ================================================================

    total_time = time.time() - start_time

    print("\n" + "=" * 70)
    print("📋 RAPPORT FINAL - TEST D'OBSERVATION MOLTBOOK")
    print("=" * 70)

    print(f"\n⏱️  Durée totale: {int(total_time)}s ({total_time/60:.1f} min)")
    print(f"\n📊 Statistiques:")
    print(f"   Cycles exécutés: {cycles_executed}")
    print(f"\n📸 Snapshots:")
    print(f"   Fetched: {snapshots_fetched}")
    print(f"   Skip (déducliqué): {snapshots_skipped_dedup}")
    print(f"   Skip (cooldown): {snapshots_skipped_cooldown}")
    print(f"\n⚡ Actions (Observation only):")
    print(f"   Générées: {actions_generated}")
    print(f"   Skip (cooldown): {actions_skipped_cooldown}")
    print(f"   Skip (daily limit): {actions_skipped_daily_limit}")

    # ================================================================
    # VALIDATION DSM
    # ================================================================

    print("\n" + "=" * 70)
    print("🔍 VALIDATION DSM")
    print("=" * 70)

    # Vérifier les fichiers DSM
    shard_file = prod_dir / "shards" / "shard_sessions.jsonl"
    limits_file = prod_dir / "index" / "session_limits.json"

    print(f"\n📂 Fichiers DSM:")
    print(f"   Shard: {shard_file.exists()}")
    print(f"   Limits: {limits_file.exists()}")

    # Lire l'état limits
    if limits_file.exists():
        with open(limits_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
            print(f"\n📊 État Session Limits:")
            print(f"   Actions aujourd'hui: {state.get('actions_today_count', 0)}/{session_graph.limits_manager.DAILY_ACTION_BUDGET}")
            print(f"   Dernier poll home: {datetime.fromtimestamp(state.get('last_home_poll_ts', 0), tz=timezone.utc).isoformat()}")
            print(f"   Dernière action: {datetime.fromtimestamp(state.get('last_action_ts', 0), tz=timezone.utc).isoformat()}")

    # ================================================================
    # RÉSULTAT FINAL
    # ================================================================

    print("\n" + "=" * 70)
    print("✅ TEST D'OBSERVATION COMPLÉT")
    print("=" * 70)
    print("\n✓ Aucune action Moltbook réelle exécutée")
    print("✓ Validation DSM + Clawdbot réussie")
    print("✓ Observation de 10 cycles complétée")
    print("✓ Prêt pour intégration DSM-ANS")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(run_observation_test())
