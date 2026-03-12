#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Stress Test
1000 sessions × 3 events = 3000 transactions
Validates integrity, atomic writes, hash chaining
"""

import sys
import hashlib
import random
import time
from pathlib import Path

# Ajouter le parent au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from core.storage import Storage
from session_graph import SessionGraph


def run_stress_test():
    """Execute le test de stress DSM"""

    print("=" * 70)
    print("DSM v2 Stress Test")
    print("=" * 70)
    print(f"Sessions: 1000")
    print(f"Events/session: 3 (snapshot + action + outcome)")
    print(f"Total transactions: 3000")
    print("=" * 70)

    # Configuration DSM isolé
    test_dir = Path.home() / "clawdbot_dsm_test" / "memory"
    print(f"\n📂 DSM test directory: {test_dir}")

    # Créer le storage isolé
    print("\n🔧 Initialisation DSM Storage...")
    storage = Storage(data_dir=str(test_dir))

    # Configuration du test
    SESSIONS = 1000
    ACTIONS = ["reply_to_post", "write_post", "follow_user", "like_post", "upvote_post"]
    CLEAN_OLD_DATA = True  # Nettoyer les données précédentes

    print(f"📝 Actions disponibles: {ACTIONS}")
    print(f"📂 Nettoyage données précédentes: {CLEAN_OLD_DATA}")

    # Nettoyer le shard si demandé
    if CLEAN_OLD_DATA:
        shard_file = test_dir / "shards" / "shard_sessions.jsonl"
        if shard_file.exists():
            print(f"🧹 Nettoyage: {shard_file}")
            shard_file.unlink()
            print(f"✅ Shard supprimé")

        # Nettoyer aussi le fichier d'intégrité
        integrity_file = test_dir / "integrity" / "shard_sessions_last_hash.json"
        if integrity_file.exists():
            integrity_file.unlink()
            print(f"✅ Intégrité supprimée")

    print(f"\n🚀 Lancement du stress test...\n")

    start_time = time.time()

    # =========================
    # STRESS TEST LOOP
    # =========================
    for i in range(SESSIONS):
        # Créer une nouvelle session pour chaque itération
        session = SessionGraph(storage)

        # Simuler un snapshot
        snapshot = {
            "notifications": random.randint(0, 10),
            "dms": random.randint(0, 5)
        }
        snapshot_hash = hashlib.sha256(str(snapshot).encode()).hexdigest()
        session.record_snapshot(snapshot_hash)

        # Sélectionner et exécuter une action
        action = random.choice(ACTIONS)
        session.record_action(action)

        # Enregistrer un résultat
        outcome = f"karma_gain={random.randint(0, 10)}"
        session.record_outcome(outcome)

        # Progression
        if (i + 1) % 100 == 0:
            print(f"✅ {i + 1} sessions complétées ({((i + 1) / SESSIONS * 100):.1f}%)")

    end_time = time.time()
    execution_time = end_time - start_time

    # =========================
    # VALIDATION
    # =========================
    print("\n" + "=" * 70)
    print("🔍 VALIDATION DES RÉSULTATS")
    print("=" * 70)

    # Vérifier le shard
    shard_file = test_dir / "shards" / "shard_sessions.jsonl"

    if not shard_file.exists():
        print(f"\n❌ ERREUR: Shard non créé: {shard_file}")
        return 1

    print(f"\n✅ Shard créé: {shard_file}")
    print(f"📏 Taille: {shard_file.stat().st_size} bytes ({shard_file.stat().st_size / 1024:.2f} KB)")

    # Compter les transactions
    with open(shard_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    transaction_count = len(lines)
    print(f"\n📊 Transactions enregistrées: {transaction_count}")

    # Transactions attendues (nettoyage actif)
    expected_transactions = SESSIONS * 3  # 3 events par session

    # Vérifier l'intégrité
    integrity_file = test_dir / "integrity" / "shard_sessions_last_hash.json"

    if integrity_file.exists():
        print(f"✅ Fichier d'intégrité: {integrity_file}")

        with open(integrity_file, 'r', encoding='utf-8') as f:
            integrity = f.read()
            print(f"🔐 Contenu:\n{integrity}")
    else:
        print(f"❌ ERREUR: Fichier d'intégrité non créé")
        return 1

    # =========================
    # PERFORMANCE METRICS
    # =========================
    print("\n" + "=" * 70)
    print("📈 MÉTRIQUES DE PERFORMANCE")
    print("=" * 70)

    print(f"\n⏱️  Temps d'exécution: {execution_time:.2f} secondes")
    print(f"📝 Sessions complétées: {SESSIONS}")
    print(f"📊 Transactions totales: {transaction_count}")
    print(f"🚀 Vitesse d'écriture: {transaction_count / execution_time:.1f} events/sec")
    print(f"📏 Taille moyenne/transaction: {shard_file.stat().st_size / transaction_count:.1f} bytes")

    # Vérifier que toutes les transactions sont présentes
    print("\n📊 Vérification des transactions...")
    print(f"   Attendu: {expected_transactions}")
    print(f"   Enregistré: {transaction_count}")

    if transaction_count == expected_transactions:
        print(f"\n✅ TOUS LES ÉVÉNEMENTS ENREGISTRÉS: {transaction_count}/{expected_transactions}")
    else:
        print(f"\n⚠️  Événements manquants: {expected_transactions - transaction_count}")

    # Vérifier l'intégrité des hash
    print("\n🔍 Vérification de la chaîne de hash...")

    hash_errors = 0
    prev_hash = None

    for i, line in enumerate(lines[-100:]):  # Vérifier les 100 dernières
        try:
            import json
            data = json.loads(line.strip())
            current_hash = data.get("hash")
            recorded_prev_hash = data.get("prev_hash")

            if prev_hash and recorded_prev_hash != prev_hash:
                print(f"❌ Erreur hash à la ligne {i}: prev_hash ne correspond pas")
                hash_errors += 1

            prev_hash = current_hash
        except Exception as e:
            print(f"⚠️  Erreur parsing ligne {i}: {e}")

    if hash_errors == 0:
        print(f"✅ Chaîne de hash INTACTE (100 dernières transactions vérifiées)")
    else:
        print(f"❌ {hash_errors} erreurs de hash détectées")

    # =========================
    # RÉSULTAT FINAL
    # =========================
    print("\n" + "=" * 70)

    if (
        shard_file.exists() and
        transaction_count == expected_transactions and
        hash_errors == 0 and
        integrity_file.exists()
    ):
        print("✅ DSM STRESS TEST PASSED")
        print("=" * 70)
        return 0
    else:
        print("❌ DSM STRESS TEST FAILED")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(run_stress_test())
