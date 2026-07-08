#!/usr/bin/env python3
"""Trust Boundary 2 — id field + query engine intersection confusion."""
from __future__ import annotations
import json, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.rr.index.rr_index_builder import RRIndexBuilder
from dsm.rr.navigator.rr_navigator import RRNavigator
from dsm.rr.query.rr_query_engine import RRQueryEngine


def make_entry(i, shard, content):
    return Entry(
        id=f"entry_{shard}_{i:04d}",
        timestamp=datetime(2026, 3, 15, 10, 0, i, tzinfo=timezone.utc),
        session_id="session_0001", source="agent_x",
        content=content, shard=shard, hash="", prev_hash=None,
        metadata={"event_type": "tool_call", "action_name": f"action_{i}"},
        version="v2.0",
    )

def mutate_field(jsonl, field, old, new):
    lines, n = [], 0
    with open(jsonl, "r") as f:
        for line in f:
            if not line.strip(): lines.append(line); continue
            obj = json.loads(line)
            if obj.get(field) == old:
                obj[field] = new; n += 1
            lines.append(json.dumps(obj, ensure_ascii=False) + "\n")
    with open(jsonl, "w") as f: f.writelines(lines)
    return n

def find_jsonl(data_dir, shard_id):
    """Find JSONL for a shard using the same family dir logic as storage."""
    family = shard_id.replace("shard_", "")
    pattern = data_dir / "shards" / family / "*.jsonl"
    files = sorted(data_dir.glob(str(pattern).replace(str(data_dir) + "/shards/", "shards/")))
    # Simpler: just find it
    for p in data_dir.glob("shards/**/*.jsonl"):
        if family in str(p):
            return p
    return None

def find_all_jsonl(data_dir):
    return sorted(data_dir.glob("shards/**/*.jsonl"))

def main():
    tmp = Path(tempfile.mkdtemp(prefix="tb2_"))
    try:
        storage = Storage(data_dir=str(tmp))
        idx_dir = tmp / "index"
        SHARD_A, SHARD_B = "shard_a", "shard_b"

        for i in range(3): storage.append(make_entry(i, SHARD_A, f"PLAN_A action {i}"))
        for i in range(3): storage.append(make_entry(i, SHARD_B, f"PLAN_B action {i}"))

        # Show where files are
        all_jsonl = find_all_jsonl(tmp)
        for f in all_jsonl:
            # Read first line to see which shard the entries belong to
            with open(f) as fh:
                first = json.loads(fh.readline())
                print(f"  JSONL: {f.relative_to(tmp)} — first entry.id={first['id']}, shard={first['shard']}")

        builder = RRIndexBuilder(storage=storage, index_dir=str(idx_dir))
        builder.build()
        nav = RRNavigator(index_builder=builder, storage=storage)
        engine = RRQueryEngine(navigator=nav)

        results_before = engine.query(session_id="session_0001", limit=100)
        ids_before = sorted(r.get("entry_id") for r in results_before)
        print(f"\n  AVANT: {len(results_before)} records, ids={ids_before}")

        # Find shard_b JSONL (contains entry_shard_b_* entries)
        target_jsonl = None
        for f in all_jsonl:
            with open(f) as fh:
                for line in fh:
                    if "entry_shard_b" in line:
                        target_jsonl = f
                        break
            if target_jsonl:
                break

        if target_jsonl:
            n = mutate_field(target_jsonl, "id", "entry_shard_b_0001", "entry_shard_a_0001")
            print(f"\n  {n} entry mutée dans {target_jsonl.name}: entry_shard_b_0001 → entry_shard_a_0001")
        else:
            print("  ERREUR: aucun JSONL contenant entry_shard_b trouvé")
            return

        builder.build()
        nav = RRNavigator(index_builder=builder, storage=storage)
        engine = RRQueryEngine(navigator=nav)

        results_after = engine.query(session_id="session_0001", limit=100)
        ids_after = sorted(r.get("entry_id") for r in results_after)
        print(f"  APRÈS: {len(results_after)} records, ids={ids_after}")

        # Check for collisions (same entry_id from different entries)
        seen = {}
        for r in results_after:
            eid = r.get("entry_id")
            seen[eid] = seen.get(eid, 0) + 1
        collisions = {k: v for k, v in seen.items() if v > 1}

        # Direct intersection
        common = engine._intersect_by_entry_id([
            builder.shard_index.get(SHARD_A, []),
            builder.shard_index.get(SHARD_B, []),
        ])
        print(f"\n  Intersection shard_a ∩ shard_b: {len(common)} records")
        for r in common:
            print(f"    entry_id={r.get('entry_id')} shard_id={r.get('shard_id')}")

        print()
        if collisions:
            print("  COLLISIONS détectées — TRUST IMPACT")
        elif len(ids_after) != len(ids_before):
            print(f"  ID SHIFT: {len(ids_before)} → {len(ids_after)} — entrée masquée/ajoutée")
        elif len(common) > 0:
            print(f"  FAUX POSITIF d'intersection: {len(common)} entries de shards différents")
            print("  ╔════════════════════════════════════════════════╗")
            print("  ║  TRUST IMPACT: jointure croisée entre shards     ║")
            print("  ╚════════════════════════════════════════════════╝")
        else:
            print("  Pas d'impact mesurable sur la query dans ce scénario.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()
