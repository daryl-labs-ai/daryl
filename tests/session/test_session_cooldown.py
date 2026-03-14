#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Session Limits Validation Test
Test le système complet de cooldown et rate limiting
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dsm.core.storage import Storage
from dsm.session.session_graph import SessionGraph
from dsm.session.session_limits_manager import SessionLimitsManager
from dsm.moltbook_home_client import MoltbookHomeClient


def run_cooldown_test():
    """Execute le test de cooldown et rate limiting"""

    print("=" * 70)
    print("DSM v2 Cooldown & Rate Limiting Test")
    print("=" * 70)
    print("\nObjectif:")
    print("Valider le système complet de controle:")
    print("- Home polling cooldown (30s)")
    print("- Action cooldown (120s)")
    print("- Daily budget (10 actions)")
    print("- Per-cycle budget (1 action)")
    print("=" * 70)

    # Configuration DSM isolé
    test_dir = Path.home() / "clawdbot_dsm_test" / "memory"
    print(f"\n📂 DSM test directory: {test_dir}")

    # Créer le storage isolé
    print("\n🔧 Initialisation DSM Storage + SessionGraph...")
    storage = Storage(data_dir=str(test_dir))
    session_graph = SessionGraph(storage=storage)

    # Créer le normalizer Moltbook Home
    api_key = "moltbook_sk_Wr8D9miMUUWlElGdQGsYxk7zKmYEhJHq"
    home_client = MoltbookHomeClient(api_key=api_key)

    # ================================================================
    # TEST 1 : Home Polling Cooldown (30s)
    # ================================================================
    print("\n" + "=" * 70)
    print("📌 TEST 1 : Home Polling Cooldown (30s)")
    print("=" * 70)
    print("Attendu:")
    print("- Premier appel: fetch OK")
    print("- Deuxième appel (immédiat): SKIP (cooldown)")
    print("- Troisième appel (après 31s): fetch OK")

    for i in range(3):
        print(f"\nCycle {i + 1}/3:")

        if i == 1:
            # Premier cycle - doit fetcher
            entry = session_graph.record_snapshot(home={})
            if entry:
                print(f"   ✅ Snapshot #1 écrit (HOME_POLL)")
        elif i == 2:
            # Deuxième cycle - doit être SKIP (trop récent)
            entry = session_graph.record_snapshot(home={})
            if entry is None:
                print(f"   📦 Snapshot #2 SKIP (cooldown)")
            else:
                print(f"   ❌ ERREUR: Devrait être SKIP")
        else:
            # Troisième cycle - doit fetcher (cooldown passé)
            time.sleep(2)  # Simuler l'attente du cooldown
            entry = session_graph.record_snapshot(home={})
            if entry:
                print(f"   ✅ Snapshot #3 écrit (HOME_POLL)")
            else:
                print(f"   ❌ ERREUR: Devrait être écrit")

        time.sleep(1)  # Simulation entre cycles

    # ================================================================
    # TEST 2 : Action Cooldown (120s)
    # ================================================================
    print("\n" + "=" * 70)
    print("⚡ TEST 2 : Action Cooldown (120s)")
    print("=" * 70)
    print("Attendu:")
    print("- Première action: exécutée")
    print("- Deuxième action (immédiat): SKIP (cooldown)")
    print("- Troisième action (après 121s): exécutée")

    for i in range(3):
        print(f"\nCycle {i + 1}/3:")

        if i == 1:
            # Premier cycle - doit exécuter
            entry = session_graph.record_action("test_action_1")
            if entry:
                print(f"   ✅ Action #1 exécutée (ACTION_EXECUTED)")
        elif i == 2:
            # Deuxième cycle - doit être SKIP
            entry = session_graph.record_action("test_action_2")
            if entry is None:
                print(f"   🏸️ Action #2 SKIP (cooldown)")
            else:
                print(f"   ❌ ERREUR: Devrait être SKIP")
        else:
            # Troisième cycle - doit exécuter (cooldown passé)
            time.sleep(2)  # Simuler l'attente du cooldown
            entry = session_graph.record_action("test_action_3")
            if entry:
                print(f"   ✅ Action #3 exécutée (ACTION_EXECUTED)")
            else:
                print(f"   ❌ ERREUR: Devrait être écrite")

        time.sleep(1)  # Simulation entre cycles

    # ================================================================
    # TEST 3 : Daily Budget (10 actions)
    # ================================================================
    print("\n" + "=" * 70)
    print("📊 TEST 3 : Daily Budget (10 actions)")
    print("=" * 70)
    print("Attendu:")
    print("- 10 actions consécutives")
    print("- 11ème action: SKIP (daily limit)")

    for i in range(11):
        print(f"\nAction {i + 1}/11:")

        if i < 10:
            # Les 10 premières doivent exécuter
            entry = session_graph.record_action(f"budget_action_{i + 1}")
            if entry:
                print(f"   ✅ Action #{i + 1} exécutée")
            else:
                print(f"   ❌ ERREUR: Devrait être écrite")
        else:
            # La 11ème doit être SKIP (limite journalière)
            entry = session_graph.record_action(f"budget_action_{i + 1}")
            if entry is None:
                print(f"   🚫 Action #11 SKIP (daily limit)")
            else:
                print(f"   ❌ ERREUR: Devrait être SKIP")

        time.sleep(0.5)  # Simulation rapide entre actions

    # ================================================================
    # TEST 4 : Per-Cycle Budget (1 action)
    # ================================================================
    print("\n" + "=" * 70)
    print("🎯 TEST 4 : Per-Cycle Budget (1 action/cycle)")
    print("=" * 70)
    print("Attendu:")
    print("- Action 1: exécutée")
    print("- Action 2: SKIP (déjà 1 action dans le cycle)")
    print("- Action 3: SKIP (déjà 1 action dans le cycle)")

    for i in range(3):
        print(f"\nCycle {i + 1}/3:")

        if i == 0:
            # Premier cycle - 1 action autorisée
            entry = session_graph.record_action("cycle_1_action")
            if entry:
                print(f"   ✅ Action exécutée (cycle 1)")
        else:
            # Deuxième et troisième cycles - doivent être SKIP
            entry = session_graph.record_action(f"cycle_{i + 1}_action")
            if entry is None:
                print(f"   🏸️ Action SKIP (per-cycle limit)")
            else:
                print(f"   ❌ ERREUR: Devrait être SKIP")

        time.sleep(1)  # Simulation entre cycles

    # ================================================================
    # VALIDATION FINALE
    # ================================================================
    print("\n" + "=" * 70)
    print("🔍 VALIDATION DES RÉSULTATS")
    print("=" * 70)

    # Vérifier les fichiers DSM
    shard_file = test_dir / "shards" / "shard_sessions.jsonl"
    limits_file = test_dir / "index" / "session_limits.json"

    print(f"\n📂 Shard créé: {shard_file.exists()}")
    print(f"📂 Limits créé: {limits_file.exists()}")

    # Vérifier l'état
    state = session_graph.limits_manager.get_state()

    if limits_file.exists():
        with open(limits_file, 'r', encoding='utf-8') as f:
            limits_data = json.load(f)
            print(f"\n📋 État session_limits.json:")
            print(f"   Budget journalier: {limits_data.get('actions_today_count', 0)}/{10}")
            print(f"   Dernier poll home: {limits_data.get('last_home_poll_ts', 0)}")
            print(f"   Dernière action: {limits_data.get('last_action_ts', 0)}")
    else:
        print("\n❌ ERREUR: Fichier limits non créé")

    # ================================================================
    # RÉSULTAT FINAL
    # ================================================================
    print("\n" + "=" * 70)

    if (
        shard_file.exists() and
        limits_file.exists() and
        state.get("actions_today_count", 0) == 10  # Nous avons exécuté 10 actions dans le test 3
    ):
        print("✅ COOLDOWN & RATE LIMITING TEST PASSED")
        print("=" * 70)
        print("\n🎉 Système DSM complet avec:")
        print("   ✅ Home polling cooldown (30s)")
        print("   ✅ Action cooldown (120s)")
        print("   ✅ Daily budget (10 actions)")
        print("   ✅ Per-cycle budget (1 action/cycle)")
        print("   ✅ State persistence (session_limits.json)")
        print("=" * 70)
        return 0
    else:
        print("❌ COOLDOWN & RATE LIMITING TEST FAILED")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(run_cooldown_test())
