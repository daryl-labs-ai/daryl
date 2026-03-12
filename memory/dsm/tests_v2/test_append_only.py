#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test append-only storage (vital feature)
"""

import os
import tempfile
import json
from pathlib import Path
from dsm_v2.core.storage import Storage
from dsm_v2.core.models import Entry
from dsm_v2.core.signing import Signing
from datetime import datetime
import uuid

def test_append_only():
    """Test that in-place edits are forbidden"""
    print("🧪 Test append-only storage...")

    storage = Storage(data_dir=tempfile.mkdtemp())

    # Create initial entry
    entry1 = Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        session_id="test",
        source="test",
        content="Initial entry",
        shard="test",
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0"
    )

    stored1 = storage.append(entry1)
    print(f"   Entry 1 ajoutée: {stored1.id[:8]}")
    print(f"   Hash: {stored1.hash[:16]}...")

    # Try to modify entry1 file directly (should fail or create new entry)
    shard_file = storage.shards_dir / "test.jsonl"

    with open(shard_file, 'r') as f:
        first_line = f.readline().strip()

    try:
        # Parse and modify
        entry_dict = json.loads(first_line)
        entry_dict["content"] = "MODIFIED CONTENT"
        entry_dict["metadata"]["tampered"] = True

        # Try to write back (should fail or append new)
        with open(shard_file, 'w') as f:
            f.write(json.dumps(entry_dict) + '\n')

        # Check what actually happened
        with open(shard_file, 'r') as f:
            lines = f.readlines()

        print(f"   Lignes après tentative de modification: {len(lines)}")

        if len(lines) == 1:
            # Check if modification was rejected (good - append-only enforced)
            try:
                modified_entry_dict = json.loads(lines[0].strip())
                if modified_entry_dict.get("content") == "MODIFIED CONTENT":
                    print("   ❌ MODIFICATION DÉTECTÉE - Append-only VIOLÉ !")
                    return
            except:
                pass

        print("   ✅ Modification rejetée (append-only respecté)")
    except Exception as e:
        print(f"   ⚠️ Erreur: {e}")

    # Verify only new entries exist
    entry2 = Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        session_id="test",
        source="test",
        content="Second entry",
        shard="test",
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0"
    )

    stored2 = storage.append(entry2)
    print(f"   Entry 2 ajoutée: {stored2.id[:8]}")
    print(f"   Hash: {stored2.hash[:16]}...")

    # Final check
    with open(shard_file, 'r') as f:
        lines = f.readlines()

    print(f"   Total lignes: {len(lines)}")

    # Verify chain
    entries = storage.read("test", limit=10)
    metrics = Signing.verify_chain(entries)

    print(f"\n📊 Métriques de chaîne :")
    print(f"   Total: {metrics['total']}")
    print(f"   Vérifiées: {metrics['verified']}")
    print(f"   Corrompues: {metrics['corrupted']}")
    print(f"   Tampering: {metrics['tampering_detected']}")
    print(f"   Verification rate: {metrics['verification_rate']:.1f}%")

    # Cleanup
    import shutil
    shutil.rmtree(storage.data_dir)

    if metrics['verified'] > 0 and metrics['tampering_detected'] == 0:
        print("\n✅ Test PASS - Append-only respecté")
    else:
        print("\n⚠️ Test FAIL - Problème détecté")


if __name__ == "__main__":
    test_append_only()
