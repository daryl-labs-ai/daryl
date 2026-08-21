#!/usr/bin/env python3
"""
Test automatisé pour la démo d'évidence DARYL.

Vérifie que :
1. La vérification initiale est VALIDE (OK)
2. Après altération, la vérification est INVALIDE (TAMPERED)

Usage:
    python test_demo.py
    pytest test_demo.py -v
"""

import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.verify import verify_shard

DEMO_DIR = Path(__file__).parent
SHARD_ID = "evidence_demo_test"


def load_document(filename: str) -> dict:
    """Charge un document JSON."""
    path = DEMO_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def record_document(storage: Storage, doc: dict, role: str) -> Entry:
    """Enregistre un document dans DSM."""
    entry = Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="test-session",
        source="test",
        content=json.dumps(doc, ensure_ascii=False, sort_keys=True),
        shard=SHARD_ID,
        hash="",
        prev_hash=None,
        metadata={
            "document_type": doc.get("document_type", "unknown"),
            "document_id": doc.get("document_id", "unknown"),
            "role": role,
        },
        version="v2.0",
    )
    return storage.append(entry)


def tamper_q17(storage: Storage) -> bool:
    """Altère Q17 dans le stockage."""
    shard_dir = storage.shards_dir / SHARD_ID
    segment_files = sorted(shard_dir.glob("*.jsonl"))
    
    if not segment_files:
        return False
    
    segment_file = segment_files[0]
    
    with open(segment_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    tampered = False
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            new_lines.append(line)
            continue
        
        try:
            entry_data = json.loads(stripped)
        except json.JSONDecodeError:
            new_lines.append(line)
            continue
        
        meta = entry_data.get("metadata", {})
        if not tampered and meta.get("document_id") == "Q17":
            content = json.loads(entry_data["content"])
            content["title"] = content.get("title", "").replace("17", "17-tampered")
            entry_data["content"] = json.dumps(content, ensure_ascii=False, sort_keys=True)
            tampered = True
        
        new_lines.append(
            json.dumps(entry_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        )
    
    if tampered:
        with open(segment_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    
    return tampered


def get_status_str(result: dict) -> str:
    """Extrait le statut comme string."""
    status = result["status"]
    return status.value if hasattr(status, "value") else str(status)


def test_evidence_demo_valid_then_invalid():
    """Test principal : VALID → altération → INVALID."""
    tmp_dir = tempfile.mkdtemp(prefix="daryl_test_")
    
    try:
        storage = Storage(data_dir=os.path.join(tmp_dir, "dsm_data"))
        
        q16 = load_document("Q16.json")
        q17 = load_document("Q17.json")
        r42 = load_document("R42.json")
        m61 = load_document("M61.json")
        
        record_document(storage, q16, "questionnaire_v16")
        record_document(storage, q17, "questionnaire_v17")
        record_document(storage, r42, "recommendation")
        record_document(storage, m61, "manifest")
        
        result_clean = verify_shard(storage, SHARD_ID)
        status_clean = get_status_str(result_clean)
        
        assert status_clean == "OK", f"Vérification initiale devrait être OK, got {status_clean}"
        assert result_clean["total_entries"] == 4, "Devrait avoir 4 entrées"
        assert result_clean["verified"] == 4, "Toutes les entrées devraient être vérifiées"
        assert result_clean["tampered"] == 0, "Aucune entrée ne devrait être altérée"
        
        assert tamper_q17(storage), "L'altération de Q17 devrait réussir"
        
        result_tampered = verify_shard(storage, SHARD_ID)
        status_tampered = get_status_str(result_tampered)
        
        assert status_tampered == "TAMPERED", f"Après altération devrait être TAMPERED, got {status_tampered}"
        assert result_tampered["tampered"] >= 1, "Au moins une entrée devrait être détectée comme altérée"
        
        print("✓ Test passé : VALID → INVALID fonctionne correctement")
        
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_r42_declares_based_on_q17():
    """Vérifie que R42 déclare bien être basé sur Q17."""
    r42 = load_document("R42.json")
    assert r42.get("based_on") == "Q17", "R42 devrait déclarer based_on = Q17"
    print("✓ Test passé : R42 déclare based_on = Q17")


def test_manifest_binds_all_documents():
    """Vérifie que le manifeste lie tous les documents."""
    m61 = load_document("M61.json")
    bound_ids = {obj["document_id"] for obj in m61.get("bound_objects", [])}
    expected = {"Q16", "Q17", "R42"}
    assert expected.issubset(bound_ids), f"Le manifeste devrait lier {expected}, found {bound_ids}"
    print("✓ Test passé : M61 lie Q16, Q17 et R42")


def main():
    """Exécute tous les tests (mode standalone)."""
    tests = [
        test_r42_declares_based_on_q17,
        test_manifest_binds_all_documents,
        test_evidence_demo_valid_then_invalid,
    ]
    
    passed = 0
    failed = 0
    
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_fn.__name__}: Exception - {e}")
            failed += 1
    
    print(f"\n{passed}/{len(tests)} tests passés")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
