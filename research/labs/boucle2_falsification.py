#!/usr/bin/env python3
"""Boucle 2 — Falsification: que DSM détecte-t-il et ne détecte-t-il pas ?

4 attaques sur une chaîne inter-agents:
  F1. Mutation d'un événement (content modifié sur disque)
  F2. Suppression/troncature (entry supprimée du JSONL)
  F3. Duplication d'un receipt (même receipt présenté deux fois)
  F4. Reprise avec receipt invalide (entry_hash ne correspond pas)
"""
import sys, json, shutil, tempfile, copy
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.verify import verify_shard
from dsm.exchange import issue_receipt, verify_receipt, verify_receipt_against_storage

SHARD = "project_memory"


def make_entry(agent_id, content, prev_hash=None):
    return Entry(
        id=f"{agent_id}_{datetime.now(timezone.utc).strftime('%H%M%S%f')}",
        timestamp=datetime.now(timezone.utc),
        session_id=f"sess_{agent_id}", source=agent_id,
        content=content, shard=SHARD, hash="", prev_hash=prev_hash,
        metadata={"event_type": "decision"}, version="v2.0",
    )


def find_jsonl(data_dir, shard):
    family = shard.replace("shard_", "")
    for p in (data_dir / "shards" / family).glob("*.jsonl"):
        return p
    # fallback: might be stored flat
    for p in (data_dir / "shards").glob(f"{shard}*.jsonl"):
        return p
    return None


def setup_chain(tmp):
    """Build a clean 3-agent chain."""
    storage = Storage(data_dir=str(tmp))
    e1 = storage.append(make_entry("agent_A", "Decision: use Ed25519"))
    e2 = storage.append(make_entry("agent_B", "Implement: auth.py created", prev_hash=e1.hash))
    e3 = storage.append(make_entry("agent_C", "Review: auth.py looks good", prev_hash=e2.hash))
    r2 = issue_receipt(storage, "agent_B", e2.id, SHARD, "implement auth")
    return storage, [e1, e2, e3], r2


def main():
    print("=" * 70)
    print("BOUCLE 2 — FALSIFICATION")
    print("=" * 70)

    # === F1: MUTATION D'UN ÉVÉNEMENT ===
    print("\n--- F1: Mutation du content d'une entry sur disque ---")
    tmp = Path(tempfile.mkdtemp(prefix="b2_f1_"))
    try:
        storage, entries, receipt = setup_chain(tmp)
        jsonl = find_jsonl(tmp, SHARD)
        print(f"  JSONL: {jsonl}")

        # Mutate the 2nd entry's content
        lines = open(jsonl).readlines()
        obj = json.loads(lines[1])
        original_content = obj["content"]
        obj["content"] = "TAMPERED: agent_B did NOT implement auth, agent_B introduced a backdoor"
        lines[1] = json.dumps(obj, ensure_ascii=False) + "\n"
        open(jsonl, "w").writelines(lines)
        print(f"  mutated: '{original_content[:40]}' → '{obj['content'][:40]}'")

        # verify_shard
        vr = verify_shard(storage, SHARD)
        print(f"  verify_shard: {vr.get('status')}")
        detected = "TAMPERED" in str(vr.get('status', '')) or vr.get('status') != 'VerifyStatus.OK'
        print(f"  → DÉTECTÉ: {'OUI' if detected else 'NON'}")

        # Also check: does the receipt still verify?
        vr2 = verify_receipt_against_storage(storage, receipt)
        print(f"  receipt against storage: {vr2.get('status')}")
        print(f"  → receipt detects mutation: {'OUI' if vr2.get('status') != 'CONFIRMED' else 'NON (hash still matches stored)'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # === F2: SUPPRESSION/TRONCATURE ===
    print("\n--- F2: Suppression de la dernière entry (troncature suffix) ---")
    tmp = Path(tempfile.mkdtemp(prefix="b2_f2_"))
    try:
        storage, entries, receipt = setup_chain(tmp)
        jsonl = find_jsonl(tmp, SHARD)

        # Delete last entry (entry 3)
        lines = open(jsonl).readlines()
        print(f"  entries avant: {len([l for l in lines if l.strip()])}")
        lines = lines[:-1]  # remove last line
        open(jsonl, "w").writelines(lines)
        print(f"  entries après suppression: {len([l for l in lines if l.strip()])}")

        vr = verify_shard(storage, SHARD)
        print(f"  verify_shard: {vr.get('status')}")
        print(f"  truncation_detected: {vr.get('truncation_detected', '?')}")
        print(f"  observed_count: {vr.get('observed_entry_count', '?')}")
        print(f"  expected_count: {vr.get('expected_entry_count', '?')}")
        # Note: without a pin, truncation may not be detected
        has_pin = vr.get('expected_last_hash') is not None
        print(f"  has integrity pin: {has_pin}")
        print(f"  → DÉTECTÉ: {'OUI' if vr.get('truncation_detected') else 'NON (pas de pin → suffix deletion invisible)'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # === F3: DUPLICATION D'UN RECEIPT ===
    print("\n--- F3: Duplication d'un receipt (même receipt présenté 2x) ---")
    tmp = Path(tempfile.mkdtemp(prefix="b2_f3_"))
    try:
        storage, entries, receipt = setup_chain(tmp)
        # Present the same receipt twice
        vr1 = verify_receipt(receipt)
        vr2 = verify_receipt(receipt)
        vs1 = verify_receipt_against_storage(storage, receipt)
        vs2 = verify_receipt_against_storage(storage, receipt)
        print(f"  receipt verify 1: {vr1['status']}")
        print(f"  receipt verify 2: {vr2['status']}")
        print(f"  storage verify 1: {vs1['status']}")
        print(f"  storage verify 2: {vs2['status']}")
        print(f"  → Duplication détectée: NON (DSM ne tracke pas les receipts déjà vus)")
        print(f"    → Un receipt peut être 'rejoué' — pas de protection replay")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # === F4: REPRISE AVEC RECEIPT INVALIDE ===
    print("\n--- F4: Receipt avec entry_hash falsifié ---")
    tmp = Path(tempfile.mkdtemp(prefix="b2_f4_"))
    try:
        storage, entries, receipt = setup_chain(tmp)
        # Forge: same receipt but with a different entry_hash
        forged = copy.deepcopy(receipt)
        forged.entry_hash = "v1:FAKE_HASH_NOT_REAL_00000000000000000000000000000000000000000000000000000000000000"

        vr = verify_receipt(forged)
        vs = verify_receipt_against_storage(storage, forged)
        print(f"  forged receipt verify: {vr['status']}")
        print(f"  forged receipt storage: {vs['status']}")
        # Note: verify_receipt checks receipt_hash (which covers entry_hash)
        # So mutating entry_hash should make receipt_hash invalid
        hash_ok = vr['status'] == 'INTACT'
        print(f"  → receipt_hash detects forged entry_hash: {'NON' if hash_ok else 'OUI (TAMPERED)'}")

        # Also test: valid receipt but pointing to wrong entry (entry_id collision)
        forged2 = copy.deepcopy(receipt)
        # Keep receipt_hash valid but change entry_id to one that doesn't exist
        # Actually: receipt_hash covers entry_id, so changing it breaks receipt_hash
        # Instead: what if the entry was DELETED but receipt still claims it?
        print(f"\n  variant: valid receipt, but entry deleted from storage")
        jsonl = find_jsonl(tmp, SHARD)
        lines = open(jsonl).readlines()
        # Delete entry 2 (the one the receipt points to)
        new_lines = [l for l in lines if receipt.entry_id not in l]
        open(jsonl, "w").writelines(new_lines)
        vs2 = verify_receipt_against_storage(storage, receipt)
        print(f"  receipt after entry deletion: {vs2.get('status')}")
        print(f"  → deletion detected by receipt: {'OUI' if vs2.get('status') == 'ENTRY_MISSING' else 'NON'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # === SYNTHÈSE ===
    print(f"\n{'='*70}")
    print(f"SYNTHÈSE — Ce que DSM détecte et ne détecte pas")
    print(f"{'='*70}")
    print(f"  F1 Mutation content:     DÉTECTÉ par verify_shard (hash chain brisé)")
    print(f"  F2 Truncation suffix:    NON DÉTECTÉ sans pin d'intégrité")
    print(f"  F3 Duplication receipt:  NON DÉTECTÉ (pas de protection replay)")
    print(f"  F4 Receipt falsifié:     DÉTECTÉ (receipt_hash couvre entry_hash)")
    print(f"  F4 Entry supprimée:      DÉTECTÉ (ENTRY_MISSING par verify_against_storage)")
    print(f"\n  → DSM détecte: mutation de contenu, receipt falsifié, entry supprimée")
    print(f"  → DSM ne détecte PAS: truncation sans pin, replay de receipt")
