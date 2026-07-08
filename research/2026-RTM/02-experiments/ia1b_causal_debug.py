#!/usr/bin/env python3
"""Debug: pourquoi verify_causal_chain retourne BROKEN sur un handoff légitime?"""
import sys, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from dsm.causal import create_dispatch_hash, DispatchRecord, verify_dispatch_hash, verify_causal_chain

entry_hash = "v1:abc123"
task_params = {"task": "deploy"}
ts = datetime.now(timezone.utc).isoformat()
dh = create_dispatch_hash(entry_hash, task_params, ts)
rec = DispatchRecord(dispatch_hash=dh, dispatcher_agent_id="A",
    dispatcher_entry_hash=entry_hash, target_agent_id="B",
    task_params=task_params, timestamp=ts)

print("=== dispatch integrity seul ===")
dvr = verify_dispatch_hash(rec)
print(f"  verify_dispatch_hash: {dvr}")
print(f"  rec.dispatch_hash == dh: {rec.dispatch_hash == dh}")

print("\n=== causal chain avec receipt.dispatch_hash = dh (légitime) ===")
# verify_causal_chain(dispatch_record, intent_hash, receipt_dispatch_hash)
vc = verify_causal_chain(rec, "intent_hash_placeholder", dh)
print(f"  status={vc['status']}, details={vc['details']}")
print(f"  rec.dispatch_hash: {rec.dispatch_hash[:16]}...")
print(f"  passed dispatch:   {dh[:16]}...")
print(f"  equal: {rec.dispatch_hash == dh}")
