#!/usr/bin/env python3
"""Trust Boundary 3 — id field + exchange.py receipt resolution."""
from __future__ import annotations
import json, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.exchange import TaskReceipt, verify_receipt_against_storage


def make_entry(i):
    return Entry(
        id=f"entry_{i:04d}", timestamp=datetime(2026, 3, 15, 10, 0, i, tzinfo=timezone.utc),
        session_id="session_0001", source="agent_x",
        content=f"Transaction {i}: transfer 100 units", shard="receipts",
        hash="", prev_hash=None,
        metadata={"event_type": "transfer", "action_name": f"tx_{i}"},
        version="v2.0",
    )

def find_jsonl(d):
    for p in d.glob("shards/**/*.jsonl"): return p

def mutate_id(jsonl, old, new):
    lines, n = [], 0
    with open(jsonl, "r") as f:
        for line in f:
            if not line.strip(): lines.append(line); continue
            obj = json.loads(line)
            if obj.get("id") == old:
                obj["id"] = new; n += 1
            lines.append(json.dumps(obj, ensure_ascii=False) + "\n")
    with open(jsonl, "w") as f: f.writelines(lines)
    return n

def main():
    tmp = Path(tempfile.mkdtemp(prefix="tb3_"))
    try:
        storage = Storage(data_dir=str(tmp))
        SHARD = "receipts"
        for i in range(5):
            storage.append(make_entry(i))

        entries = storage.read(SHARD, limit=100)
        entry_02 = entries[2]
        entry_04 = entries[4]

        receipt = TaskReceipt(
            receipt_id="rcpt_001", issuer_agent_id="agent_x",
            task_description="Task for entry_0002",
            entry_id="entry_0002", entry_hash=entry_02.hash,
            shard_id=SHARD, shard_tip_hash="tip_hash",
            shard_entry_count=5,
            timestamp="2026-03-15T10:00:02+00:00",
            receipt_hash="fake_receipt_hash",
        )

        print("=== ID MUTATION + RECEIPT RESOLUTION ===")
        print(f"  Receipt.entry_id = {receipt.entry_id}")

        # verify_receipt_against_storage reads entries and matches by e.id == receipt.entry_id
        vr_before = verify_receipt_against_storage(storage, receipt)
        print(f"  verify_receipt AVANT mutation:")
        print(f"    entry_found={vr_before.get('entry_found')}")
        print(f"    entry_match={vr_before.get('entry_match')}")
        print(f"    status={vr_before.get('status')}")

        jsonl = find_jsonl(tmp)
        n = mutate_id(jsonl, "entry_0002", "entry_0004")
        print(f"\n  {n} entry mutée: entry_0002 → entry_0004")

        vr_after = verify_receipt_against_storage(storage, receipt)
        print(f"  verify_receipt APRÈS mutation:")
        print(f"    entry_found={vr_after.get('entry_found')}")
        print(f"    entry_match={vr_after.get('entry_match')}")
        print(f"    status={vr_after.get('status')}")

        if vr_before.get('entry_found') and not vr_after.get('entry_found'):
            print(f"\n  ╔════════════════════════════════════════════════╗")
            print(f"  ║  TRUST IMPACT: receipt orpheline — association    ║")
            print(f"  ║  receipt↔entry rompue de façon non détectable.    ║")
            print(f"  ╚════════════════════════════════════════════════╝")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()
