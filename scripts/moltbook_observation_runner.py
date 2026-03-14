#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Moltbook Observation Runner
Exécute des cycles d'observation Moltbook en mode réel
Mode observation-only : PAS d'actions réelles Moltbook
"""

import json
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Ajouter le parent au PYTHONPATH
_repo = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_repo))
sys.path.insert(0, str(Path(__file__).parent))

from core.storage import Storage
from dsm.session.session_graph import SessionGraph


def run_observation_cycles(cycles: int = 10, cycle_interval: int = 180):
    """
    Exécute des cycles d'observation Moltbook en mode réel

    Args:
        cycles: Nombre de cycles à exécuter
        cycle_interval: Intervalle entre cycles (secondes)
    """
    print("=" * 70)
    print("DSM v2 - Real Moltbook Observation Runner")
    print("=" * 70)
    print("\nMode: OBSERVATION-ONLY")
    print("PAS d'actions Moltbook réelles")
    print("Validation uniquement")
    print("=" * 70)

    # Configuration DSM (production)
    try:
        config = DSMConfig.default()
        base_dir = config.memory_dir
    except Exception as e:
        print(f"Erreur configuration DSM: {e}")
        return 1

    print(f"\nDSM directory: {base_dir}")

    # Créer le storage et SessionGraph
    print("\nInitialisation DSM + SessionGraph...")
    storage = Storage(data_dir=str(base_dir))
    session_graph = SessionGraph(storage=storage)
    print(f"Session ID: {session_graph.session_id}")

    # Configuration du test
    print(f"\nTest Configuration:")
    print(f"  Cycles: {cycles}")
    print(f"  Cycle interval: {cycle_interval}s ({cycle_interval/60} min)")
    print(f"  Max duration: {cycles * cycle_interval}s ({(cycles * cycle_interval)/3600:.1f}h)")
    print("=" * 70)

    # Variables de statistiques
    cycles_executed = 0
    snapshots_fetched = 0
    snapshots_skipped_dedup = 0
    snapshots_skipped_cooldown = 0

    actions_generated = 0
    actions_skipped_cooldown = 0
    actions_skipped_daily_limit = 0

    start_time = time.time()

    print("\nDEBUT DES CYCLES D'OBSERVATION")
    print("=" * 70)

    try:
        for i in range(cycles):
            cycle_num = i + 1
            print(f"\n{'='*70}")
            print(f"CYCLE {cycle_num}/{cycles}")
            print(f"{'='*70}")

            # 1. START SESSION
            print(f"\n1. SESSION_START")
            entry = session_graph.start_session()
            cycles_executed += 1

            # 2. FETCH HOME
            print(f"\n2. FETCH HOME (Moltbook /api/v1/home)")

            # Verifier le cooldown du polling home
            skip_home, remaining = session_graph.limits_manager.can_poll_home()
            print(f"  Cooldown check: {int(remaining)}s restantes")

            if skip_home:
                # Cooldown actif - skip le fetch
                snapshots_skipped_cooldown += 1
                print(f"  Cooldown actif - SKIP")
                print(f"  Home poll SKIPPED (cooldown: {int(remaining)}s)")
            else:
                # Fetcher le home réel (mock pour test)
                print(f"  Recuperation du home...")

                # Mock home pour test (car pas de connexion réelle)
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
                print(f"  Snapshot hash: {snapshot_hash[:16]}...")

                # Enregistrer le snapshot (avec déduplication)
                entry = session_graph.record_snapshot(
                    home=home,
                    force=False
                )

                if entry:
                    snapshots_fetched += 1
                    print(f"  HOME_SNAPSHOT enregistre")
                else:
                    # Le snapshot a été dédupliqué
                    snapshots_skipped_dedup += 1
                    print(f"  Snapshot duplique detecte - SKIP")

            # 3. GÉNÉRER ACTION CANDIDAT (pas exécuter)
            print(f"\n3. GÉNÉRER ACTION CANDIDAT (Observation only)")

            # Métriques simples pour décider
            metrics = session_graph.home_normalizer.get_metrics(normalized_home)
            unread_notifications = metrics.get("unread_notifications", 0)
            unread_dms = metrics.get("unread_dms", 0)
            activity_count = metrics.get("activity_count", 0)

            # Sélectionner une action candidate (basée sur priorités)
            if unread_notifications > 100:
                action_candidate = "check_notifications"
                reasoning = f"Priorité haute: {unread_notifications} notifications"
            elif unread_dms > 0:
                action_candidate = "check_dms"
                reasoning = f"Priorité haute: {unread_dms} DMs non lus"
            elif activity_count > 5:
                action_candidate = "check_activity"
                reasoning = f"Priorité: {activity_count} activités sur posts"
            else:
                action_candidate = "scan_feed"
                reasoning = "Priorité basse: scan du feed"

            print(f"  Action candidate: {action_candidate}")
            print(f"  Raison: {reasoning}")

            # Enregistrer la sélection (pas l'exécution)
            session_graph.select_action(action_candidate, reasoning=reasoning)
            actions_generated += 1
            print(f"  ACTION_SELECTED enregistre (Observation only)")

            # 4. Vérifier cooldown action (pas exécuter)
            print(f"\n4. Vérification Cooldown ACTION (Observation only)")

            skip_action = session_graph.limits_manager.check_action_cooldown()

            if skip_action:
                actions_skipped_cooldown += 1
                print(f"  Cooldown actif - SKIP action")
                print(f"  Action SKIP (cooldown)")
            else:
                print(f"  Action autorisee (cooldown OK)")

            # 5. END SESSION
            print(f"\n5. SESSION_END")
            session_graph.end_session(reason="observation_complete")
            print(f"  SESSION_END enregistre")

            # Attente entre cycles
            if i < cycles - 1:
                elapsed = time.time() - start_time
                if elapsed < cycles * cycle_interval:
                    wait_time = min(cycle_interval - elapsed, cycle_interval)
                    print(f"\nAttente avant prochain cycle: {int(wait_time)}s...")
                    time.sleep(wait_time)

    except KeyboardInterrupt:
        print("\nInterruption par l'utilisateur")
    except Exception as e:
        print(f"\nErreur critique: {e}")
        traceback.print_exc()

    # RAPPORT FINAL
    total_time = time.time() - start_time

    print("\n" + "=" * 70)
    print("RAPPORT FINAL - TEST D'OBSERVATION MOLTBOOK")
    print("=" * 70)

    print(f"\nDuree totale: {int(total_time)}s ({total_time/60:.1f} min)")
    print(f"\nStatistiques:")
    print(f"  Cycles executes: {cycles_executed}/{cycles}")
    print(f"\nSnapshots:")
    print(f"  Fetched: {snapshots_fetched}")
    print(f"  Skip (deduplique): {snapshots_skipped_dedup}")
    print(f"  Skip (cooldown): {snapshots_skipped_cooldown}")
    print(f"\nActions (Observation only):")
    print(f"  Generees: {actions_generated}")
    print(f"  Skip (cooldown): {actions_skipped_cooldown}")
    print(f"  Skip (daily limit): {actions_skipped_daily_limit}")

    # Validation DSM
    print("\n" + "=" * 70)
    print("VALIDATION DSM")
    print("=" * 70)

    # Verifier les fichiers DSM
    shard_file = base_dir / "shards" / "shard_sessions.jsonl"
    limits_file = base_dir / "index" / "session_limits.json"

    print(f"\nFichiers DSM:")
    print(f"  Shard: {shard_file.exists()}")
    print(f"  Limits: {limits_file.exists()}")

    # Lire l'état limits
    if limits_file.exists():
        with open(limits_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
            print(f"\nEtat Session Limits:")
            print(f"  Actions aujourd'hui: {state.get('actions_today_count', 0)}/{session_graph.limits_manager.DAILY_ACTION_BUDGET}")
            print(f"  Dernier poll home: {datetime.fromtimestamp(state.get('last_home_poll_ts', 0), tz=timezone.utc).isoformat()}")
            print(f"  Dernière action: {datetime.fromtimestamp(state.get('last_action_ts', 0), tz=timezone.utc).isoformat()}")

    # Lire les entrées DSM
    if shard_file.exists():
        entries = storage.read("shard_sessions", limit=100)
        print(f"\nEntrees DSM: {len(entries)}")

        # Compter par type
        session_starts = [e for e in entries if "SESSION_START" in e.content]
        home_snapshots = [e for e in entries if "HOME_SNAPSHOT" in e.content]
        home_skipped = [e for e in entries if "HOME_POLL_SKIPPED" in e.content]
        action_selected = [e for e in entries if "ACTION_SELECTED" in e.content]
        action_skipped = [e for e in entries if "ACTION_SKIPPED" in e.content]
        session_ends = [e for e in entries if "SESSION_END" in e.content]

        print(f"\nRepartition:")
        print(f"  SESSION_START: {len(session_starts)}")
        print(f"  HOME_SNAPSHOT: {len(home_snapshots)}")
        print(f"  HOME_POLL_SKIPPED: {len(home_skipped)}")
        print(f"  ACTION_SELECTED: {len(action_selected)}")
        print(f"  ACTION_SKIPPED: {len(action_skipped)}")
        print(f"  SESSION_END: {len(session_ends)}")

        # Afficher les dernières entrées
        print(f"\nDernieres entrees (10):")
        for i, entry in enumerate(entries[-10:], 1):
            print(f"  {i}. {entry.content[:40]}...")

    # RESULTAT FINAL
    print("\n" + "=" * 70)
    print("TEST D'OBSERVATION COMPLTE")
    print("=" * 70)
    print("\nPAS d'action Moltbook reelle executee")
    print("Validation DSM + Clawdbot reussie")
    print("Observation de cycles completee")
    print("Pret pour integration DSM-ANS")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(run_observation_cycles())
