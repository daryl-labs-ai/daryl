#!/usr/bin/env python3
"""Falsification 1 — I/V/C/P est-il minimal? C se déduit-il de V?

Hypothèse à tester (POUR réduire le modèle): C ⊆ V.
Si V=Y alors C=Y nécessairement → C est redondante → modèle à 3 propriétés suffit.

Falsification (POUR garder C): trouver une arête où V=Y mais C=N.
  → Vérifier la cohérence de l'arête N'IMPLIQUE PAS détecter un target manquant.
  → V et C sont orthogonales.

On examine les 3 arêtes qui ont V=Y dans la matrice de la Boucle 5:
  - Receipt.entry_hash  (V=Y, C=Y) — les deux
  - Dispatch.dispatch_hash (V=Y, C=N candidate) — verify_dispatch_hash recomputes
  - Attestation.input_hash (V=Y, C=N candidate)
  - Entry.prev_hash (V=Y, C=N) — verify_chain checks prev matches

Pour chaque arête V=Y: que fait réellement la fonction de verify?
  - vérifie-t-elle que le target EXISTE physiquement (C)?
  - ou vérifie-t-elle seulement que la VALEUR de l'arête est cohérente (V)?
"""
from __future__ import annotations
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

# === Test concret: Entry.prev_hash ===
# verify_chain vérifie: entry.prev_hash == last_valid_hash (cohérence V)
# MAIS si le target (l'entry précédente) est SUPPRIMÉ/tronqué:
#   - entry.prev_hash pointe vers un hash qui n'existe plus
#   - verify_chain accepte toujours si la chaîne RESTANTE est cohérente
# C'est exactement ce que la doc verify.py dit:
#   "the internal prev_hash chain only proves that whatever entries are
#    present form a valid sequence — it CANNOT detect deletion of a suffix"

import shutil, tempfile, json
from datetime import datetime, timezone
from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.core.signing import Signing


tmp = Path(tempfile.mkdtemp(prefix="f1_"))
try:
    storage = Storage(data_dir=str(tmp))
    SHARD = "test_chain"
    # Write a 5-entry chain
    prev = None
    entries = []
    for i in range(5):
        e = Entry(id=f"e{i}", timestamp=datetime(2026,3,1,10,0,i,tzinfo=timezone.utc),
                  session_id="s1", source="A", content=f"c{i}", shard=SHARD,
                  hash="", prev_hash=prev, metadata={}, version="v2.0")
        result = storage.append(e)
        entries.append(result)
        prev = result.hash

    print("=== TEST C ⊆ V : Entry.prev_hash ===")
    print(f"  Chaîne de 5 entries écrite. hashes:")
    for i, e in enumerate(entries):
        print(f"    e{i}: hash={e.hash[:20]}... prev_hash={str(e.prev_hash)[:20] if e.prev_hash else 'None'}...")

    # verify_chain on the full chain — V=Y
    full_chain = list(reversed(storage.read(SHARD, limit=100)))
    result_full = Signing.verify_chain(full_chain)
    print(f"\n  verify_chain(full 5): verified={result_full['verified']} corrupted={result_full['corrupted']} tampered={result_full['tampering_detected']}")

    # Now TRUNCATE: remove e2 (middle entry) from disk
    # Simulate by reading only [e0,e1,e3,e4] — e2's hash gone, e3.prev_hash dangles
    jsonl = next((tmp/"shards"/SHARD).glob("*.jsonl"))
    lines = []
    with open(jsonl) as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                if obj.get("id") != "e2":  # drop e2
                    lines.append(line)
            else:
                lines.append(line)
    open(jsonl, "w").writelines(lines)

    truncated = list(reversed(storage.read(SHARD, limit=100)))
    print(f"\n  Après suppression de e2: {len(truncated)} entries restantes")
    print(f"    e3.prev_hash pointe vers e2 (supprimé): {truncated[-2].prev_hash[:20] if truncated[-2].prev_hash else 'None'}...")

    # verify_chain on truncated — V check still passes? C check?
    result_trunc = Signing.verify_chain(truncated)
    print(f"\n  verify_chain(truncated, e2 manquant):")
    print(f"    verified={result_trunc['verified']} corrupted={result_trunc['corrupted']} tampered={result_trunc['tampering_detected']}")

    # The KEY question: does verify_chain detect that e2 is GONE?
    # V (Verifiability): "is the edge value coherent?" — e3.prev_hash != e2.hash (gone)
    #   but e3.prev_hash still equals what e1 expected? NO — e3.prev_hash points to e2.hash
    #   which is no longer in the list. verify_chain compares prev_hash to last_valid_hash.
    if result_trunc["corrupted"] > 0:
        print(f"\n  → V a détecté l'incohérence (corrupted={result_trunc['corrupted']})")
        print(f"  → Mais est-ce C (target manquant) ou V (valeur incohérente)?")
        print(f"  → C'est V: verify_chain compare e3.prev_hash à e1.hash (le dernier vu)")
        print(f"    Ces deux valeurs diffèrent → flagged comme 'corrupted'")
        print(f"    C'est une détection de COHÉRENCE (V), pas d'EXISTENCE (C)")
    else:
        print(f"\n  → V n'a RIEN détecté! La chaîne restante est encore 'cohérente'")
        print(f"  → C'est exactement la limite documentée dans verify.py:")
        print(f"    'cannot detect deletion of a suffix'")

    # === Le test décisif: suffix deletion (cas le plus simple de dangling) ===
    print(f"\n=== TEST DÉCISIF: suppression du SUFFIX (e3,e4) ===")
    # Reset: rewrite full chain
    storage2_dir = tmp / "v2"
    storage2_dir.mkdir()
    storage2 = Storage(data_dir=str(storage2_dir))
    prev = None
    entries2 = []
    for i in range(5):
        e = Entry(id=f"e{i}", timestamp=datetime(2026,3,1,10,0,i,tzinfo=timezone.utc),
                  session_id="s1", source="A", content=f"c{i}", shard=SHARD,
                  hash="", prev_hash=prev, metadata={}, version="v2.0")
        result = storage2.append(e)
        entries2.append(result)
        prev = result.hash

    # Delete suffix: keep only e0, e1
    jsonl2 = next((storage2_dir/"shards"/SHARD).glob("*.jsonl"))
    kept = []
    with open(jsonl2) as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                if obj.get("id") in ("e0", "e1"):
                    kept.append(line)
            else:
                kept.append(line)
    open(jsonl2, "w").writelines(kept)

    suffix_truncated = list(reversed(storage2.read(SHARD, limit=100)))
    result_suffix = Signing.verify_chain(suffix_truncated)
    print(f"  Chaîne après suppression suffix (e0,e1 seulement): {len(suffix_truncated)} entries")
    print(f"  verify_chain: verified={result_suffix['verified']} corrupted={result_suffix['corrupted']} tampered={result_suffix['tampering_detected']}")

    if result_suffix["corrupted"] == 0 and result_suffix["tampering_detected"] == 0:
        print(f"\n  ╔══════════════════════════════════════════════════════════╗")
        print(f"  ║  C ⊄ V DÉMONTRÉ                                          ║")
        print(f"  ║  V=Y (verify_chain passe) mais le target e2,e3,e4 manque ║")
        print(f"  ║  → Completeness n'est PAS déductible de Verifiability    ║")
        print(f"  ║  → I/V/C/P est MINIMAL (C est indépendante de V)         ║")
        print(f"  ╚══════════════════════════════════════════════════════════╝")
    else:
        print(f"\n  → V a détecté la truncation → C pourrait être ⊆ V")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
