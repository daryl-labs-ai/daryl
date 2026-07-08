#!/usr/bin/env python3
"""Iteration 3 — prototype the kernel-respecting fixes and measure.

Fix A (build): single forward pass via iter_shard_events. Already shown 15x.
Fix B (resolve): offset-free resolution. Scan each needed shard's segments
   forward ONCE; build an entry_id -> Entry map; stop scanning a shard once all
   its requested ids are found. No offset pagination, no re-reads.

This file does NOT modify the kernel or RR code. It monkeypatches a prototype
resolve into a navigator subclass for measurement only.
"""
from __future__ import annotations
import json, random, shutil, sys, tempfile, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
from dsm.core.storage import Storage
from dsm.core.shard_segments import MAX_EVENTS_PER_SEGMENT
from dsm.core.models import Entry
from dsm.rr.index.rr_index_builder import RRIndexBuilder, _entry_to_index_record
from dsm.rr.navigator.rr_navigator import RRNavigator

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


def proto_resolve(nav, records, limit=None):
    """Offset-free resolve: scan each shard forward ONCE via iter_shard_events,
    early-exit per shard when all its requested ids are found. Returns same shape."""
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
        for event in storage.segment_manager.iter_shard_events(shard_id):
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


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


def main():
    # ---- Build scaling comparison (already known ~15x; re-confirm cleanly) ----
    print("=== Fix A: build() scaling ===")
    print(f"{'N':>8} | {'real(ms)':>9} | {'proto(ms)':>10} | {'speedup':>8}")
    print("-" * 48)
    for n in (10_000, 50_000, 100_000):
        entries = make_entries(n)
        tmp = Path(tempfile.mkdtemp(prefix=f"i3a_{n}_"))
        idx = tmp / "index"
        try:
            write_segmented(entries, tmp)
            storage = Storage(data_dir=str(tmp))
            # real
            b = RRIndexBuilder(storage=storage, index_dir=str(idx), batch_size=5000)
            t0 = time.monotonic(); b.build(); real_t = time.monotonic() - t0
            # proto (single pass)
            t0 = time.monotonic()
            for _ in range(1):
                sp = {}
                for meta in storage.list_shards():
                    sid = meta.shard_id
                    evs = list(storage.segment_manager.iter_shard_events(sid))
                    tot = len(evs)
                    for fp, ev in enumerate(evs):
                        e = storage._entry_from_event_data(ev)
                        r = _entry_to_index_record(e, sid, tot - 1 - fp)
                _ = sp
            # measure proto build of indexes properly
            t0 = time.monotonic()
            si, ai, tl, shi, ac = {}, {}, [], {}, {}
            for meta in storage.list_shards():
                sid = meta.shard_id
                evs = list(storage.segment_manager.iter_shard_events(sid))
                tot = len(evs)
                for fp, ev in enumerate(evs):
                    e = storage._entry_from_event_data(ev)
                    r = _entry_to_index_record(e, sid, tot - 1 - fp)
                    if r is None:
                        continue
                    si.setdefault(r["session_id"] or "none", []).append(r)
                    ai.setdefault(r.get("agent") or "unknown", []).append(r)
                    tl.append(r); shi.setdefault(sid, []).append(r)
                    an = (e.metadata or {}).get("action_name")
                    if an: ac.setdefault(an, []).append(r)
            tl.sort(key=lambda r: r.get("timestamp", 0))
            proto_t = time.monotonic() - t0
            print(f"{n:>8} | {real_t*1000:>8.1f} | {proto_t*1000:>9.1f} | {real_t/proto_t:>7.2f}x")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---- Resolve comparison at worst-case depth ----
    print()
    print("=== Fix B: resolve_entries() at worst-case depth (oldest entry) ===")
    for n in (25_000, 50_000, 100_000):
        entries = make_entries(n)
        tmp = Path(tempfile.mkdtemp(prefix=f"i3b_{n}_"))
        idx = tmp / "index"
        try:
            write_segmented(entries, tmp)
            storage = Storage(data_dir=str(tmp))
            b = RRIndexBuilder(storage=storage, index_dir=str(idx), batch_size=5000)
            b.build()
            nav = RRNavigator(index_builder=b, storage=storage)
            target_id = f"p_{0:06d}"  # oldest = offset N-1 from newest = worst case
            recs = [{"shard_id": SHARD_ID, "entry_id": target_id}]
            # real (offset-paginated)
            real_samples = []
            for _ in range(5):
                t0 = time.monotonic()
                rreal = nav.resolve_entries(recs, limit=10)
                real_samples.append(time.monotonic() - t0)
            # proto (offset-free, early-exit)
            proto_samples = []
            for _ in range(5):
                t0 = time.monotonic()
                rproto = proto_resolve(nav, recs, limit=10)
                proto_samples.append(time.monotonic() - t0)
            ok = len(rreal) == len(rproto) == 1 and rreal[0].id == rproto[0].id == target_id
            print(f"  N={n:>6}: real={median(real_samples)*1000:>8.1f}ms  "
                  f"proto={median(proto_samples)*1000:>7.1f}ms  "
                  f"speedup={median(real_samples)/median(proto_samples):>6.2f}x  correct={ok}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---- Resolve: best case (newest) to confirm no regression ----
    print()
    print("=== Fix B sanity: resolve at best case (newest entry) ===")
    n = 50_000
    entries = make_entries(n)
    tmp = Path(tempfile.mkdtemp(prefix="i3c_"))
    idx = tmp / "index"
    try:
        write_segmented(entries, tmp)
        storage = Storage(data_dir=str(tmp))
        b = RRIndexBuilder(storage=storage, index_dir=str(idx), batch_size=5000)
        b.build()
        nav = RRNavigator(index_builder=b, storage=storage)
        target_id = f"p_{n-1:06d}"  # newest = offset 0
        recs = [{"shard_id": SHARD_ID, "entry_id": target_id}]
        rs = []
        for _ in range(5):
            t0 = time.monotonic(); nav.resolve_entries(recs, limit=10); rs.append(time.monotonic()-t0)
        ps = []
        for _ in range(5):
            t0 = time.monotonic(); proto_resolve(nav, recs, limit=10); ps.append(time.monotonic()-t0)
        print(f"  newest: real={median(rs)*1000:.2f}ms  proto={median(ps)*1000:.2f}ms  "
              f"ratio={median(ps)/median(rs):.2f}x")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
