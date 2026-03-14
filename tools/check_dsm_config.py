#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vérification de la configuration DSM
"""

import sys
from pathlib import Path


def check_dsm_config():
    """Vérifie la configuration DSM"""
    print("\n" + "=" * 70)
    print("🔍 CONFIGURATION DSM")
    print("=" * 70)

    # Répertoire DSM (production)
    prod_base_dir = Path.home() / "clawdbot_dsm_test" / "memory"
    print(f"\n📂 Répertoire DSM (Production): {prod_base_dir}")

    # Vérifier les sous-répertoires
    print(f"\n📂 Sous-répertoires:")
    shards_dir = prod_base_dir / "shards"
    index_dir = prod_base_dir / "index"
    events_dir = prod_base_dir / "events"

    print(f"   📂 shards: {shards_dir.exists()}")
    print(f"   📂 index: {index_dir.exists()}")
    print(f"   📂 events: {events_dir.exists()}")

    # Fichiers DSM importants
    print(f"\n📋 Fichiers DSM importants:")
    session_shard = shards_dir / "shard_sessions.jsonl"
    audience_shard = shards_dir / "shard_audience.jsonl"

    print(f"   📂 shard_sessions.jsonl: {session_shard.exists()}")
    print(f"   📂 shard_audience.jsonl: {audience_shard.exists()}")

    # Configuration de test (environnement isolé)
    test_base_dir = Path.cwd() / "clawdbot_dsm_test" / "memory"
    print(f"\n📂 Répertoire DSM (Test): {test_base_dir}")

    # Fichiers DSM de test
    print(f"\n📋 Fichiers DSM (Test):")
    test_session_shard = test_base_dir / "shards" / "shard_sessions.jsonl"
    test_audience_shard = test_base_dir / "shards" / "shard_audience.jsonl"
    test_limits_file = test_base_dir / "index" / "session_limits.json"

    print(f"   📂 shard_sessions.jsonl (Test): {test_session_shard.exists()}")
    print(f"   📂 shard_audience.jsonl (Test): {test_audience_shard.exists()}")
    print(f"   📂 session_limits.json (Test): {test_limits_file.exists()}")

    # Variables d'environnement
    print(f"\n📊 Variables d'environnement:")
    print(f"   DSM_BASE_DIR: {Path.home() / 'clawdbot_dsm_test' / 'memory'}")
    print(f"   PYTHONPATH: {sys.path[0]}")

    print("\n✅ Configuration DSM vérifiée")
    print("=" * 70)


if __name__ == "__main__":
    check_dsm_config()
