#!/usr/bin/env python3
"""Iteration 1 — RR index build scaling probe.

Hypothesis: RRIndexBuilder.build() is O(N^2 / batch) because it paginates via
Storage.read(offset=K) which is itself O(K).

This script:
  1. Generates segmented fixtures of sizes [10k, 25k, 50k, 100k].
  2. Times RRIndexBuilder.build() on each (the REAL, current code path).
  3. Times a single-pass prototype that uses iter_shard_events (no offset cost).
  4. Reports the scaling exponent and speedup.

Nothing here modifies the kernel or RR code — it imports them as-is.
"""
from __future__ import annotations
import json, random, shutil, sys, tempfile, time, math
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
from dsm.core.storage import Storage                          # noqa
from dsm.core.shard_segments import MAX_EVENTS_PER_SEGMENT    # noqa
from dsm.rr.index.rr_index_builder import RRIndexBuilder, _entry_to_index_record  # noqa

SIZES = [10_000, 25_000, 50_000, 100_000]
SEED = 44
SHARD_ID = "sessions_seg"
RUNS = 2  # build is expensive; 2 runs for stability check


def make_entries(n: int):
    rng = random.Random(SEED)
    t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    span = timedelta(days=30).total_seconds()
    out = []
    for i in range(n):
        ts = t0 + timedelta(seconds=(i / n) * span)
        out.append({
            "id": f"p_{i:06d}", "timestamp": ts.isoformat(),
            "session_id": f"session_{(i // 20):04d}",
            "source": rng.choice(["agent_x", "agent_y", "agent_z"]),
            "content": f"probe entry #{i}", "shard": SHARD_ID,
            "hash": "h" * 64, "prev_hash": ("p" * 64) if i else None,
            "metadata": {"event_type": "tool_call", "action_name": f"action_{i % 30}"},
            "version": "v2.0",
        })
    return out


def write_segmented(entries, data_dir: Path):
    family = data_dir / "shards" / SHARD_ID
    family.mkdir(parents=True, exist_ok=True)
    (data_dir / "integrity").mkdir(parents=True, exist_ok=True)
    seg = MAX_EVENTS_PER_SEGMENT
    nseg = (len(entries) + seg - 1) // seg
    for k in range(nseg):
        s, e = k * seg, min((k + 1) * seg, len(entries))
        p = family / f"{SHARD_ID}_{k+1:04d}.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for rec in entries[s:e]:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def time_build(storage, index_dir):
    builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir), batch_size=5000)
    t0 = time.monotonic()
    builder.build()
    return time.monotonic() - t0, builder


def time_singlepass(storage, index_dir):
    """Prototype: single forward pass via iter_shard_events, no offset cost.
    Builds the SAME indexes (sessions, agents, timeline, shards, action) but reads
    each segment only once. Does not touch the kernel."""
    session_index, agent_index, timeline, shard_index, action_index = {}, {}, [], {}, {}
    n = 0
    t0 = time.monotonic()
    for meta in storage.list_shards():
        sid = meta.shard_id
        pos = 0
        for event in storage.segment_manager.iter_shard_events(sid):
            entry = storage._entry_from_event_data(event)
            rec = _entry_to_index_record(entry, sid, pos)
            pos += 1
            if rec is None:
                continue
            n += 1
            s = rec["session_id"] or "none"
            session_index.setdefault(s, []).append(rec)
            a = rec.get("agent") or "unknown"
            agent_index.setdefault(a, []).append(rec)
            timeline.append(rec)
            shard_index.setdefault(sid, []).append(rec)
            an = (entry.metadata or {}).get("action_name")
            if an:
                action_index.setdefault(an, []).append(rec)
    elapsed = time.monotonic() - t0
    timeline.sort(key=lambda r: r.get("timestamp", ""))
    return elapsed, n


def regress_loglog(sizes, times):
    """Fit log(time) = a*log(size) + b -> returns exponent a."""
    xs = [math.log(s) for s in sizes]
    ys = [math.log(t) for t in times]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den else float("nan")


def main():
    print(f"{'size':>8} | {'build(ms)':>10} | {'single(ms)':>11} | {'speedup':>8}")
    print("-" * 56)
    build_times, single_times, used_sizes = [], [], []
    for n in SIZES:
        entries = make_entries(n)
        tmp = Path(tempfile.mkdtemp(prefix=f"i1_{n}_"))
        idx_dir = tmp / "index"
        try:
            write_segmented(entries, tmp)
            storage = Storage(data_dir=str(tmp))
            # warmup run (cache filesystem)
            time_build(storage, idx_dir)
            bt = min(time_build(storage, idx_dir)[0] for _ in range(RUNS))
            st, _ = time_singlepass(storage, idx_dir)
            speedup = bt / st if st > 0 else float("inf")
            build_times.append(bt); single_times.append(st); used_sizes.append(n)
            print(f"{n:>8} | {bt*1000:>10.1f} | {st*1000:>11.1f} | {speedup:>7.2f}x")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # scaling exponents
    if len(used_sizes) >= 2:
        exp_build = regress_loglog(used_sizes, build_times)
        exp_single = regress_loglog(used_sizes, single_times)
        print()
        print(f"scaling exponent  build   : {exp_build:.3f}  (1.0=linear, 2.0=quadratic)")
        print(f"scaling exponent  single  : {exp_single:.3f}")
        ratio = build_times[-1] / single_times[-1] if single_times[-1] else float("inf")
        print(f"speedup at N={used_sizes[-1]:,}: {ratio:.2f}x")


if __name__ == "__main__":
    main()
