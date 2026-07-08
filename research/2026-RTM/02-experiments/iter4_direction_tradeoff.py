#!/usr/bin/env python3
"""Iteration 4 — full directional characterization + reverse-scan prototype.

Maps resolve_entries latency across target position (0% oldest .. 100% newest)
for three strategies:
  - real    : current RRNavigator.resolve_entries (offset-paginated, newest-first)
  - forward : iter_shard_events forward + early exit (best for OLD entries)
  - reverse : iter_shard_events_reverse + early exit (best for NEW entries)

Reverse-with-early-exit is the hypothesis: it should match real's best case and
dramatically beat real's worst case, with no kernel change.
"""
from __future__ import annotations
import json, random, shutil, sys, tempfile, time
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


def resolve_forward(nav, target_id):
    storage = nav._storage
    for event in storage.segment_manager.iter_shard_events(SHARD_ID):
        if event.get("id") == target_id:
            return storage._entry_from_event_data(event)
    return None


def resolve_reverse(nav, target_id):
    storage = nav._storage
    for event in storage.segment_manager.iter_shard_events_reverse(SHARD_ID):
        if event.get("id") == target_id:
            return storage._entry_from_event_data(event)
    return None


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


def main():
    entries = make_entries(N)
    tmp = Path(tempfile.mkdtemp(prefix="i4_"))
    idx = tmp / "index"
    try:
        write_segmented(entries, tmp)
        storage = Storage(data_dir=str(tmp))
        b = RRIndexBuilder(storage=storage, index_dir=str(idx), batch_size=5000)
        b.build()
        nav = RRNavigator(index_builder=b, storage=storage)

        # positions: 0%=oldest(idx0, offset N-1) ... 100%=newest(idx N-1, offset 0)
        positions = [("0%  (oldest)", 0.0), ("25%", 0.25), ("50%", 0.5), ("75%", 0.75), ("100% (newest)", 1.0)]
        print(f"{'position':16} | {'real(ms)':>9} | {'forward(ms)':>11} | {'reverse(ms)':>11}")
        print("-" * 60)
        for label, frac in positions:
            i = int(frac * (N - 1))
            target = f"p_{i:06d}"
            recs = [{"shard_id": SHARD_ID, "entry_id": target}]
            r = median([_t(lambda: nav.resolve_entries(recs, limit=10)) for _ in range(5)])
            f = median([_t(lambda: resolve_forward(nav, target)) for _ in range(5)])
            v = median([_t(lambda: resolve_reverse(nav, target)) for _ in range(5)])
            print(f"{label:16} | {r*1000:>8.1f} | {f*1000:>10.1f} | {v*1000:>10.1f}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _t(fn):
    t0 = time.monotonic()
    fn()
    return time.monotonic() - t0


if __name__ == "__main__":
    main()
