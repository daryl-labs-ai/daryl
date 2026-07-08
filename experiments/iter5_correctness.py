#!/usr/bin/env python3
"""Iteration 5 — correctness proof for reverse-scan resolve.

For 200 random target ids, verify that reverse-scan resolve returns the SAME
Entry (id + content + timestamp) as the real resolve_entries. Also multi-id
batch resolve to confirm set semantics. This is the gating correctness check.
"""
from __future__ import annotations
import json, random, shutil, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
from dsm.core.storage import Storage
from dsm.core.shard_segments import MAX_EVENTS_PER_SEGMENT
from dsm.rr.index.rr_index_builder import RRIndexBuilder
from dsm.rr.navigator.rr_navigator import RRNavigator

N = 50_000
SHARD_ID = "sessions_seg"


def make_entries(n):
    rng = random.Random(44)
    t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    span = timedelta(days=30).total_seconds()
    return [{"id": f"p_{i:06d}",
             "timestamp": (t0 + timedelta(seconds=(i / n) * span)).isoformat(),
             "session_id": f"session_{(i // 20):04d}",
             "source": rng.choice(["ax", "ay", "az"]),
             "content": f"#{i}", "shard": SHARD_ID, "hash": "h" * 64,
             "prev_hash": ("p" * 64) if i else None,
             "metadata": {"event_type": "tool_call", "action_name": f"a_{i % 30}"},
             "version": "v2.0"} for i in range(n)]


def write_segmented(entries, dd):
    fam = dd / "shards" / SHARD_ID
    fam.mkdir(parents=True, exist_ok=True)
    (dd / "integrity").mkdir(parents=True, exist_ok=True)
    seg = MAX_EVENTS_PER_SEGMENT
    for k in range((len(entries) + seg - 1) // seg):
        s, e = k * seg, min((k + 1) * seg, len(entries))
        with open(fam / f"{SHARD_ID}_{k+1:04d}.jsonl", "w", encoding="utf-8") as f:
            for r in entries[s:e]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def resolve_reverse_batch(nav, records, limit=None):
    """Reverse-scan batch resolve with per-shard early exit + dedup."""
    if not records:
        return []
    storage = nav._storage
    by_shard = {}
    for rec in records:
        by_shard.setdefault(rec.get("shard_id", ""), []).append(rec.get("entry_id"))
    out = []
    seen = set()
    for shard_id, ids in by_shard.items():
        needed = {i for i in ids if i} - seen
        if not needed:
            continue
        for event in storage.segment_manager.iter_shard_events_reverse(shard_id):
            eid = event.get("id")
            if eid and eid in needed and eid not in seen:
                out.append(storage._entry_from_event_data(event))
                seen.add(eid)
                needed.discard(eid)
                if limit is not None and len(out) >= limit:
                    return out[:limit]
            if not needed:
                break
        if limit is not None and len(out) >= limit:
            return out[:limit]
    return out if limit is None else out[:limit]


def fp(e):
    if e is None:
        return None
    return (e.id, e.content, e.timestamp.isoformat() if hasattr(e.timestamp, "isoformat") else str(e.timestamp))


def main():
    entries = make_entries(N)
    tmp = Path(tempfile.mkdtemp(prefix="i5_"))
    idx = tmp / "index"
    try:
        write_segmented(entries, tmp)
        storage = Storage(data_dir=str(tmp))
        b = RRIndexBuilder(storage=storage, index_dir=str(idx), batch_size=5000)
        b.build()
        nav = RRNavigator(index_builder=b, storage=storage)

        rng = random.Random(99)
        targets = [rng.randrange(N) for _ in range(200)]
        mismatches = 0
        for t in targets:
            tid = f"p_{t:06d}"
            recs = [{"shard_id": SHARD_ID, "entry_id": tid}]
            real = nav.resolve_entries(recs, limit=10)
            proto = resolve_reverse_batch(nav, recs, limit=10)
            if fp(real[0] if real else None) != fp(proto[0] if proto else None):
                mismatches += 1
                if mismatches <= 3:
                    print(f"  MISMATCH idx={t}: real={fp(real[0] if real else None)} proto={fp(proto[0] if proto else None)}")
        print(f"=== single-id correctness: {len(targets)-mismatches}/{len(targets)} match ===")

        # batch test: resolve 50 ids at once
        batch_ids = [f"p_{rng.randrange(N):06d}" for _ in range(50)]
        recs = [{"shard_id": SHARD_ID, "entry_id": i} for i in batch_ids]
        real = {e.id for e in nav.resolve_entries(recs, limit=100)}
        proto = {e.id for e in resolve_reverse_batch(nav, recs, limit=100)}
        print(f"=== batch correctness: real={len(real)} proto={len(proto)} set_match={real==proto} ===")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
