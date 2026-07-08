#!/usr/bin/env python3
"""Trust Boundary 1 — shard field + audit.py access control bypass."""
from __future__ import annotations
import json, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.audit import Policy, audit_shard
from dsm.verify import verify_shard


def make_entry(i, shard):
    return Entry(
        id=f"entry_{i:04d}", timestamp=datetime(2026, 3, 15, 10, 0, i, tzinfo=timezone.utc),
        session_id="session_0001", source="agent_x",
        content=f"Action {i}", shard=shard, hash="", prev_hash=None,
        metadata={"event_type": "tool_call", "action_name": f"action_{i % 3}"},
        version="v2.0",
    )

def mutate_shard(jsonl, old, new):
    lines, n = [], 0
    with open(jsonl, "r") as f:
        for line in f:
            if not line.strip(): lines.append(line); continue
            obj = json.loads(line)
            if obj.get("shard") == old:
                obj["shard"] = new; n += 1
            lines.append(json.dumps(obj, ensure_ascii=False) + "\n")
    with open(jsonl, "w") as f: f.writelines(lines)
    return n

def find_jsonl(d):
    for p in d.glob("shards/**/*.jsonl"): return p

def main():
    tmp = Path(tempfile.mkdtemp(prefix="tb1_"))
    try:
        storage = Storage(data_dir=str(tmp))
        SHARD = "forbidden_shard"
        for i in range(5): storage.append(make_entry(i, SHARD))
        jsonl = find_jsonl(tmp)

        policy = Policy(allowed_shards={"allowed_shard"})
        result_before = audit_shard(storage, SHARD, policy)

        print("=== SHARD MUTATION + AUDIT BYPASS ===")
        print(f"  Entries écrites dans: {SHARD}")
        print(f"  Policy.allowed_shards: {{allowed_shard}}")
        print(f"  Violations AVANT: {result_before['violation_count']}")
        for v in result_before["violations"]:
            print(f"    → {v['detail']}")

        n = mutate_shard(jsonl, SHARD, "allowed_shard")
        print(f"\n  {n} entries mutées: shard \"{SHARD}\" → \"allowed_shard\"")

        vr = verify_shard(storage, SHARD)
        print(f"  verify_shard(): {vr.get('status')} (hash chain intact)")

        result_after = audit_shard(storage, SHARD, policy)
        print(f"  Violations APRÈS: {result_after['violation_count']}")

        bypassed = result_before['violation_count'] > 0 and result_after['violation_count'] == 0
        print()
        if bypassed:
            print("  ╔══════════════════════════════════════════╗")
            print("  ║  TRUST IMPACT DÉMONTRÉ: shard             ║")
            print("  ║  shard franchit la frontière de confiance  ║")
            print("  ╚══════════════════════════════════════════╝")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()
