#!/usr/bin/env python3
"""Inter-Agent 1 — Handoff A→B + Forgery attempts.

Scénario:
  Agent A produit une décision (entry_A, hash_A).
  Agent A dispatche vers Agent B via DispatchRecord (dispatch_hash).
  Agent B produit sa propre entry_B qui référence dispatch_hash.
  Agent B reçoit un receipt prouvant qu'il a traité sur la base de A.

Falsifications:
  F1. Un attaquant mute receipt.issuer_agent_id pour se faire passer pour B.
      → receipt_hash doit détecter (issuer est dans le payload).
  F2. Un attaquant mute receipt.dispatch_hash pour casser/rewirer la causalité.
      → receipt_hash ne couvre PAS dispatch_hash (champ optionnel séparé).
  F3. Un attaquant forge un receipt avec entry_hash d'A mais issuer="B".
      → DSM distingue-t-il ownership de l'entry vs ownership du receipt?
"""
from __future__ import annotations
import shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.causal import (
    create_dispatch_hash, create_routing_hash, DispatchRecord,
    verify_dispatch_hash, verify_causal_chain,
)
from dsm.exchange import issue_receipt, verify_receipt, verify_receipt_against_storage
from dsm.attestation import create_attestation


def entry(storage, shard, agent_id, content, prev_hash=None):
    """Write an entry as a given agent."""
    e = Entry(
        id=f"{agent_id}_{datetime.now(timezone.utc).strftime('%H%M%S%f')}",
        timestamp=datetime.now(timezone.utc), session_id=f"sess_{agent_id}",
        source=agent_id, content=content, shard=shard,
        hash="", prev_hash=prev_hash, metadata={"event_type": "decision"},
        version="v2.0",
    )
    return storage.append(e)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="ia1_"))
    try:
        storage = Storage(data_dir=str(tmp))
        SHARD = "collective"

        # --- Setup: Agent A produces a decision ---
        entry_A = entry(storage, SHARD, "agent_A", "Decision: deploy v2.0")
        print("=== SETUP: Handoff A → B ===")
        print(f"  Agent A entry: id={entry_A.id}, hash={entry_A.hash[:24]}...")

        # A dispatches to B
        task_params = {"task": "execute_deploy", "version": "v2.0"}
        dispatch_hash = create_dispatch_hash(entry_A.hash, task_params)
        routing_hash = create_routing_hash(dispatch_hash, router_id="registry_1")
        dispatch_record = DispatchRecord(
            dispatch_hash=dispatch_hash, dispatcher_agent_id="agent_A",
            dispatcher_entry_hash=entry_A.hash, target_agent_id="agent_B",
            task_params=task_params, timestamp=datetime.now(timezone.utc).isoformat(),
            routing_hash=routing_hash, router_id="registry_1",
        )
        print(f"  dispatch_hash: {dispatch_hash[:24]}... (A → B)")
        print(f"  routing_hash:  {routing_hash[:24]}... (registry witness)")
        print()

        # B produces work based on the dispatch
        entry_B = entry(storage, SHARD, "agent_B", "Executed deploy v2.0",
                        prev_hash=entry_A.hash)
        print(f"  Agent B entry: id={entry_B.id}, hash={entry_B.hash[:24]}...")
        print()

        # B issues a receipt for its work, with causal binding
        receipt = issue_receipt(
            storage, agent_id="agent_B", entry_id=entry_B.id,
            shard_id=SHARD, task_description="deploy v2.0 on behalf of A",
            dispatch_hash=dispatch_hash, routing_hash=routing_hash,
        )
        print(f"  Receipt: issuer={receipt.issuer_agent_id}, entry_hash={receipt.entry_hash[:24]}...")
        print(f"           dispatch_hash={receipt.dispatch_hash[:24]}...")
        print()

        # === Handoff verification (positive path) ===
        print("=== HANDOFF VERIFICATION (chemin positif) ===")
        vr = verify_receipt(receipt)
        vs = verify_receipt_against_storage(storage, receipt)
        vc = verify_causal_chain(dispatch_record, entry_B.hash, receipt.dispatch_hash)
        print(f"  verify_receipt:          status={vr['status']}, issuer={vr['issuer']}")
        print(f"  verify_against_storage:  status={vs['status']}, hash_match={vs.get('hash_matches')}")
        print(f"  verify_causal_chain:     status={vc['status']}")
        print()

        # === F1: Forge issuer identity ===
        print("=== F1: FORGERY — muter receipt.issuer_agent_id B→attacker ===")
        forged_receipt_issuer = type(receipt)(
            receipt_id=receipt.receipt_id, issuer_agent_id="attacker_Eve",
            task_description=receipt.task_description, entry_id=receipt.entry_id,
            entry_hash=receipt.entry_hash, shard_id=receipt.shard_id,
            shard_tip_hash=receipt.shard_tip_hash, shard_entry_count=receipt.shard_entry_count,
            timestamp=receipt.timestamp, receipt_hash=receipt.receipt_hash,
            dispatch_hash=receipt.dispatch_hash, routing_hash=receipt.routing_hash,
        )
        vf1 = verify_receipt(forged_receipt_issuer)
        print(f"  verify_receipt après mutation issuer: status={vf1['status']}")
        print(f"  → F1 {'DÉTECTÉ (SAFE)' if vf1['status'] != 'INTACT' else 'NON DÉTECTÉ (BROKEN)'}")
        print()

        # === F2: Forge dispatch_hash (rewire causality) ===
        print("=== F2: FORGERY — muter receipt.dispatch_hash pour rewire la causalité ===")
        fake_dispatch_hash = "0" * 64  # attaquant invente un faux dispatch
        forged_receipt_causal = type(receipt)(
            receipt_id=receipt.receipt_id, issuer_agent_id=receipt.issuer_agent_id,
            task_description=receipt.task_description, entry_id=receipt.entry_id,
            entry_hash=receipt.entry_hash, shard_id=receipt.shard_id,
            shard_tip_hash=receipt.shard_tip_hash, shard_entry_count=receipt.shard_entry_count,
            timestamp=receipt.timestamp, receipt_hash=receipt.receipt_hash,
            dispatch_hash=fake_dispatch_hash, routing_hash=receipt.routing_hash,
        )
        vf2 = verify_receipt(forged_receipt_causal)
        print(f"  verify_receipt après mutation dispatch_hash: status={vf2['status']}")
        # The causal chain verification uses the (mutated) dispatch_hash on the receipt
        vc2 = verify_causal_chain(dispatch_record, entry_B.hash, fake_dispatch_hash)
        print(f"  verify_causal_chain avec faux dispatch: status={vc2['status']}")
        vf2_receipt_ok = vf2['status'] == 'INTACT'
        vf2_causal_broken = vc2['status'] == 'BROKEN'
        if vf2_receipt_ok:
            print(f"  → Le receipt reste INTACT malgré la mutation du dispatch_hash!")
            print(f"    (dispatch_hash n'est pas dans receipt_hash payload)")
            if vf2_causal_broken:
                print(f"    MAIS verify_causal_chain le détecte via le dispatch_record réel.")
                print(f"  → F2: receipt integrity AMBIGUOUS, causal chain détecte — dépend du vérifieur")
            else:
                print(f"  → F2: BROKEN — ni receipt ni causal ne détectent")
        else:
            print(f"  → F2 DÉTECTÉ (SAFE)")
        print()

        # === F3: Ownership confusion — entry owned by A, receipt issued by B ===
        print("=== F3: OWNERSHIP CONFUSION ===")
        print("  Scenario: receipt issued by B points to entry_hash of A's entry")
        receipt_cross = issue_receipt(
            storage, agent_id="agent_B", entry_id=entry_A.id,
            shard_id=SHARD, task_description="B claims A's work",
            dispatch_hash=dispatch_hash,
        )
        vf3 = verify_receipt(receipt_cross)
        vs3 = verify_receipt_against_storage(storage, receipt_cross)
        print(f"  Receipt: issuer=agent_B, entry_id={entry_A.id} (owned by agent_A)")
        print(f"  verify_receipt:          status={vf3['status']}")
        print(f"  verify_against_storage:  status={vs3['status']}, hash_match={vs3.get('hash_matches')}")
        # Does DSM record who originally produced entry_A?
        entries_in_shard = storage.read(SHARD, limit=100)
        entry_a_source = next((e.source for e in entries_in_shard if e.id == entry_A.id), None)
        print(f"  Original entry_A.source field: {entry_a_source}")
        print(f"  Receipt claims issuer: agent_B")
        if entry_a_source == "agent_A" and vf3['status'] == 'INTACT':
            print(f"  → F3: DSM ne lie PAS receipt.issuer à entry.source.")
            print(f"    Un receipt valide peut être émis par B sur une entry de A.")
            print(f"    ownership de l'entry ≠ ownership du receipt (AMBIGUOUS)")
        else:
            print(f"  → F3: résultat inattendu source={entry_a_source} status={vf3['status']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
