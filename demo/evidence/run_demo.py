#!/usr/bin/env python3
"""
DARYL Evidence Demo — Preuve d'intégrité DSM

Démontre ce que DSM peut et ne peut pas prouver.

Scénario :
- Deux versions de questionnaire (Q16, Q17)
- Une recommandation R42 déclarant être basée sur Q17
- Un manifeste M61 liant ces objets
- Vérification VALIDE
- Altération d'un octet de Q17
- Vérification INVALIDE

Usage:
    python run_demo.py
    python run_demo.py --keep-data  # Conserver le répertoire de données
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Assurer l'import du package dsm
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.verify import verify_shard

DEMO_DIR = Path(__file__).parent
SHARD_ID = "evidence_demo"


def print_box(title: str, content: str = "", style: str = "─") -> None:
    """Affiche un encadré."""
    width = 60
    print(f"\n{style * width}")
    print(f"  {title}")
    if content:
        print(f"{style * width}")
        for line in content.strip().split("\n"):
            print(f"  {line}")
    print(f"{style * width}")


def load_document(filename: str) -> dict:
    """Charge un document JSON depuis le répertoire de la démo."""
    path = DEMO_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def record_document(storage: Storage, doc: dict, role: str) -> Entry:
    """Enregistre un document dans DSM et retourne l'entrée."""
    entry = Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="evidence-demo-session",
        source="evidence-demo",
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


def print_verify_result(result: dict, label: str) -> None:
    """Affiche le résultat de vérification."""
    status = result["status"]
    status_str = status.value if hasattr(status, "value") else str(status)
    symbol = "✓" if status_str == "OK" else "✗"
    
    print(f"\n  [{label}]")
    print(f"  {symbol} Status       : {status_str}")
    print(f"    Entrées      : {result['total_entries']}")
    print(f"    Vérifiées    : {result['verified']}")
    print(f"    Altérées     : {result['tampered']}")
    print(f"    Ruptures     : {result['chain_breaks']}")


def tamper_q17_content(storage: Storage) -> bool:
    """
    Altère un octet du contenu de Q17 dans le fichier segment.
    Retourne True si l'altération a réussi.
    """
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
            original_title = content.get("title", "")
            content["title"] = original_title.replace("Version 17", "Version 17-bis")
            entry_data["content"] = json.dumps(content, ensure_ascii=False, sort_keys=True)
            tampered = True
            print(f"  Altération : '{original_title}' → '{content['title']}'")
        
        new_lines.append(
            json.dumps(entry_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        )
    
    if tampered:
        with open(segment_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    
    return tampered


def print_limits() -> None:
    """Affiche les limites de ce que DSM prouve."""
    limits = """
CE QUE DSM PROUVE :
  ✓ L'état enregistré n'a pas été modifié depuis l'enregistrement
  ✓ La relation "R42 se déclare basée sur Q17" est intacte
  ✓ Toute modification post-hoc est détectée

CE QUE DSM NE PROUVE PAS :
  ✗ Que le conseiller a réellement utilisé le questionnaire Q17
  ✗ Que R42 est une recommandation pertinente ou de qualité
  ✗ Que R42 est conforme à une réglementation (AI Act, AMF, etc.)
  ✗ Que les réponses du client sont véridiques
  ✗ Que le processus de conseil était adéquat

DSM garantit l'INTÉGRITÉ de l'état enregistré.
DSM ne garantit pas la VÉRACITÉ ni la CONFORMITÉ du contenu.
"""
    print_box("LIMITES DE LA PREUVE DSM", limits, "═")


def main():
    parser = argparse.ArgumentParser(description="DARYL Evidence Demo")
    parser.add_argument("--keep-data", action="store_true", help="Conserver le répertoire de données")
    args = parser.parse_args()

    tmp_dir = tempfile.mkdtemp(prefix="daryl_evidence_demo_")
    data_dir = os.path.join(tmp_dir, "dsm_data")

    try:
        print_box("DARYL EVIDENCE DEMO", "Démonstration de preuve d'intégrité DSM", "═")

        print("\n  Répertoire de données : " + data_dir)

        storage = Storage(data_dir=data_dir)

        print_box("ÉTAPE 1 — Enregistrement des documents")

        q16 = load_document("Q16.json")
        q17 = load_document("Q17.json")
        r42 = load_document("R42.json")
        m61 = load_document("M61.json")

        e_q16 = record_document(storage, q16, "questionnaire_v16")
        print(f"  → Q16 enregistré : {e_q16.hash[:16]}...")

        e_q17 = record_document(storage, q17, "questionnaire_v17")
        print(f"  → Q17 enregistré : {e_q17.hash[:16]}...")

        e_r42 = record_document(storage, r42, "recommendation")
        print(f"  → R42 enregistré : {e_r42.hash[:16]}...")
        print(f"    (déclare based_on = Q17)")

        e_m61 = record_document(storage, m61, "manifest")
        print(f"  → M61 enregistré : {e_m61.hash[:16]}...")

        print_box("ÉTAPE 2 — Vérification initiale")
        result_clean = verify_shard(storage, SHARD_ID)
        print_verify_result(result_clean, "VÉRIFICATION INITIALE")

        status_str = result_clean["status"].value if hasattr(result_clean["status"], "value") else str(result_clean["status"])
        if status_str == "OK":
            print("\n  ✓ Chaîne intacte. Tous les documents sont vérifiés.")
        else:
            print("\n  ✗ Problème détecté lors de la vérification initiale.")
            return 1

        print_box("ÉTAPE 3 — Altération de Q17")
        print("  Simulation d'une modification post-hoc...")
        
        if not tamper_q17_content(storage):
            print("  ⚠ Impossible de localiser Q17 pour l'altération.")
            return 1
        
        print("  → Le hash stocké ne correspond plus au contenu")

        print_box("ÉTAPE 4 — Vérification après altération")
        result_tampered = verify_shard(storage, SHARD_ID)
        print_verify_result(result_tampered, "VÉRIFICATION APRÈS ALTÉRATION")

        status_str = result_tampered["status"].value if hasattr(result_tampered["status"], "value") else str(result_tampered["status"])
        if status_str != "OK":
            print("\n  ✗ Altération détectée. L'intégrité de la chaîne est compromise.")
        else:
            print("\n  (Inattendu : la vérification a réussi malgré l'altération)")

        print_limits()

        print_box("RÉSUMÉ", f"""
Documents enregistrés : 4 (Q16, Q17, R42, M61)
Vérification initiale : VALIDE
Après altération      : INVALIDE
Entrées altérées      : {result_tampered['tampered']}
Ruptures de chaîne    : {result_tampered['chain_breaks']}
""")

        if args.keep_data:
            print(f"\n  Données conservées : {data_dir}")
        
        return 0

    finally:
        if not args.keep_data:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
