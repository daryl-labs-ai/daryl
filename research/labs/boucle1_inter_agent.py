#!/usr/bin/env python3
"""Boucle 1 — Scénario minimal inter-agent: developer → zcode → claude → cursor → gpt.

Chaque agent:
  1. Lit l'état du projet depuis DSM (read_recent)
  2. Produit une décision
  3. L'écrit dans DSM (append)
  4. Émet un receipt pour l'agent suivant

L'agent suivant reçoit le receipt, le vérifie, puis reprend.

Question: DSM peut-il reconstruire une continuité de projet entre 5 agents ?
"""
import sys, json, tempfile, shutil
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.verify import verify_shard
from dsm.exchange import issue_receipt, verify_receipt, verify_receipt_against_storage
from dsm.causal import create_dispatch_hash, DispatchRecord, verify_causal_chain

SHARD = "project_memory"

def make_entry(agent_id, content, action, prev_hash=None, dispatch_hash=None):
    metadata = {"event_type": "decision", "agent_id": agent_id, "action_name": action}
    if dispatch_hash:
        metadata["dispatch_hash"] = dispatch_hash
    return Entry(
        id=f"{agent_id}_{datetime.now(timezone.utc).strftime('%H%M%S%f')}",
        timestamp=datetime.now(timezone.utc),
        session_id=f"sess_{agent_id}",
        source=agent_id,
        content=content,
        shard=SHARD,
        hash="",
        prev_hash=prev_hash,
        metadata=metadata,
        version="v2.0",
    )

def agent_turn(storage, agent_id, task, prev_entry=None, prev_receipt=None):
    """Simulate one agent's turn: read → decide → write → receipt."""
    print(f"\n{'='*60}")
    print(f"  AGENT: {agent_id}")
    print(f"{'='*60}")

    # Step 1: Read project state
    recent = storage.read(SHARD, limit=10)
    print(f"  read recent: {len(recent)} entries")

    # Step 2: Verify previous receipt if provided
    if prev_receipt:
        vr = verify_receipt(prev_receipt)
        vs = verify_receipt_against_storage(storage, prev_receipt)
        print(f"  verify prev receipt: integrity={vr['status']}, storage={vs['status']}")
        if vs['status'] != 'CONFIRMED':
            print(f"  ⚠️ RECEIPT NOT CONFIRMED — agent cannot trust predecessor!")
            return None, None

    # Step 3: Produce decision
    content = f"[{agent_id}] {task}"
    prev_hash = prev_entry.hash if prev_entry else None

    # Create dispatch link if there's a predecessor
    dispatch_hash = None
    if prev_entry:
        dispatch_hash = create_dispatch_hash(prev_entry.hash, {"task": task, "to": agent_id})

    entry = make_entry(agent_id, content, task, prev_hash=prev_hash, dispatch_hash=dispatch_hash)
    written = storage.append(entry)
    print(f"  wrote: \"{content}\"")
    print(f"  hash: {written.hash[:24]}...")

    # Step 4: Issue receipt for next agent
    receipt = issue_receipt(
        storage, agent_id=agent_id, entry_id=written.id,
        shard_id=SHARD, task_description=task,
        dispatch_hash=dispatch_hash,
    )
    print(f"  receipt issued: entry_hash={receipt.entry_hash[:24]}...")

    return written, receipt

def main():
    tmp = Path(tempfile.mkdtemp(prefix="boucle1_"))
    try:
        storage = Storage(data_dir=str(tmp))

        # === The 5-agent chain ===
        agents = [
            ("developer", "Define project: build auth module with Ed25519"),
            ("zcode", "Design auth module API surface (login, verify, rotate)"),
            ("claude_code", "Implement auth.py with Ed25519 signing + key rotation"),
            ("cursor", "Review auth.py: fix key rotation race condition at line 47"),
            ("gpt", "Write tests for auth.py: cover rotate, verify, revoke"),
        ]

        prev_entry = None
        prev_receipt = None
        all_receipts = []

        for agent_id, task in agents:
            entry, receipt = agent_turn(storage, agent_id, task, prev_entry, prev_receipt)
            if entry is None:
                print(f"\nCHAIN BROKEN at {agent_id}")
                break
            prev_entry = entry
            prev_receipt = receipt
            all_receipts.append((agent_id, receipt))

        # === Final verification ===
        print(f"\n{'='*60}")
        print(f"  CHAIN VERIFICATION")
        print(f"{'='*60}")

        # Verify the whole shard
        vr = verify_shard(storage, SHARD)
        print(f"  verify_shard: {vr.get('status')}")
        print(f"  entries checked: {vr.get('total_entries', '?')}")

        # Verify all receipts
        print(f"\n  Receipt chain verification:")
        all_ok = True
        for agent_id, receipt in all_receipts:
            vr = verify_receipt(receipt)
            vs = verify_receipt_against_storage(storage, receipt)
            ok = vr['status'] == 'INTACT' and vs['status'] == 'CONFIRMED'
            all_ok &= ok
            print(f"    {agent_id:12}: receipt={vr['status']}, storage={vs['status']} {'✓' if ok else '✗'}")

        # === Continuity reconstruction test ===
        print(f"\n  Continuity reconstruction (fresh read):")
        recent = storage.read(SHARD, limit=10)
        print(f"  {len(recent)} entries recovered (newest first):")
        for e in reversed(recent):  # chronological
            agent = e.source
            content = e.content[:60]
            has_dispatch = "dispatch_hash" in (e.metadata or {})
            print(f"    [{agent:12}] {content} {'⚡dispatch' if has_dispatch else ''}")

        print(f"\n{'='*60}")
        print(f"  VERDICT")
        print(f"{'='*60}")
        print(f"  Chain intact: {all_ok}")
        print(f"  Shard verified: {vr.get('status') == 'VerifyStatus.OK'}")
        print(f"  All receipts confirmed: {all_ok}")
        entries = storage.read(SHARD, limit=100)
        print(f"  Total entries: {len(entries)}")
        print(f"  → DSM {'CAN' if all_ok else 'CANNOT'} reconstruct inter-agent continuity")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
