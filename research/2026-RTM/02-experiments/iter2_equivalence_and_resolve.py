#!/usr/bin/env python3
"""Iteration 2 (fixed) — index equivalence + resolve_entries cost.

Key fix: build() reads newest-first via Storage.read(offset=K), so the recorded
'offset' is the newest-first position. Single-pass must replicate that: read
forward via iter_shard_events, assign offset = (total - 1 - forward_pos).
"""
from __future__ import annotations
import json, random, shutil, sys, tempfile, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
from dsm.core.storage import Storage                          # noqa
from dsm.core.shard_segments import MAX_EVENTS_PER_SEGMENT    # noqa
from dsm.rr.index.rr_index_builder import RRIndexBuilder, _entry_to_index_record  # noqa
from dsm.rr.navigator.rr_navigator import RRNavigator         # noqa

N = 50_000
SHARD_ID = "sessions_seg"


def make_entries(n):
    rng = random.Random(44)
    t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    span = timedelta(days=30).total_seconds()
    out = []
    for i in range(n):
        ts = t0 + timedelta(seconds=(i / n) * span)
        out.append({
            "id": f"p_{i:06d}", "timestamp": ts.isoformat(),
            "session_id": f"session_{(i // 20):04d}",
            "source": rng.choice(["agent_x", "agent_y", "agent_z"]),
            "content": f"probe #{i}", "shard": SHARD_ID,
            "hash": "h"*64, "prev_hash": ("p"*64) if i else None,
            "metadata": {"event_type": "tool_call", "action_name": f"action_{i%30}"},
            "version": "v2.0",
        })
    return out


def write_segmented(entries, data_dir):
    family = data_dir / "shards" / SHARD_ID
    family.mkdir(parents=True, exist_ok=True)
    (data_dir / "integrity").mkdir(parents=True, exist_ok=True)
    seg = MAX_EVENTS_PER_SEGMENT
    for k in range((len(entries) + seg - 1) // seg):
        s, e = k*seg, min((k+1)*seg, len(entries))
        with open(family / f"{SHARD_ID}_{k+1:04d}.jsonl", "w", encoding="utf-8") as f:
            for r in entries[s:e]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def singlepass_index(storage):
    session_index, agent_index, timeline, shard_index, action_index = {}, {}, [], {}, {}
    for meta in storage.list_shards():
        sid = meta.shard_id
        # First count, then assign newest-first offsets
        events = list(storage.segment_manager.iter_shard_events(sid))
        total = len(events)
        for fwd_pos, event in enumerate(events):
            entry = storage._entry_from_event_data(event)
            offset = total - 1 - fwd_pos  # newest-first position, matches build()
            rec = _entry_to_index_record(entry, sid, offset)
            if rec is None:
                continue
            session_index.setdefault(rec["session_id"] or "none", []).append(rec)
            agent_index.setdefault(rec.get("agent") or "unknown", []).append(rec)
            timeline.append(rec)
            shard_index.setdefault(sid, []).append(rec)
            an = (entry.metadata or {}).get("action_name")
            if an:
                action_index.setdefault(an, []).append(rec)
    timeline.sort(key=lambda r: r.get("timestamp", 0))
    return dict(session=session_index, agent=agent_index, timeline=timeline,
                shard=shard_index, action=action_index)


def freeze(d):
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


def main():
    entries = make_entries(N)
    tmp = Path(tempfile.mkdtemp(prefix="i2_"))
    idx_dir = tmp / "index"
    try:
        write_segmented(entries, tmp)
        storage = Storage(data_dir=str(tmp))

        builder = RRIndexBuilder(storage=storage, index_dir=str(idx_dir), batch_size=5000)
        builder.build()
        real = dict(session=builder.session_index, agent=builder.agent_index,
                    timeline=builder.timeline_index, shard=builder.shard_index,
                    action=builder.action_index)
        proto = singlepass_index(storage)

        print("=== (a) Index equivalence (real build vs single-pass, offset-correct) ===")
        all_match = True
        for key in ("session", "agent", "timeline", "shard", "action"):
            match = freeze(real[key]) == freeze(proto[key])
            all_match &= match
            print(f"  {key:9}: match={match}")
        print(f"  => {'FULL EQUIVALENCE (incl. offset field)' if all_match else 'DIVERGENCE'}")

        # ---- (b) resolve_entries per-request cost vs depth ----
        print()
        print("=== (b) resolve_entries() latency vs entry depth (N=50k, batch=5000) ===")
        nav = RRNavigator(index_builder=builder, storage=storage)
        # read() is newest-first; oldest entry (i=0) is at offset N-1 from newest.
        depths = [("newest  (offset ~0)", N-1),
                  ("1/4 deep(offset ~12.5k)", int(N*0.75)),
                  ("middle  (offset ~25k)", int(N*0.5)),
                  ("oldest  (offset ~50k)", 0)]
        print(f"  {'target':28} | {'median ms (n=5)':>15}")
        print("  " + "-"*50)
        for label, oldest_idx in depths:
            target_id = f"p_{oldest_idx:06d}"
            recs = [{"shard_id": SHARD_ID, "entry_id": target_id}]
            samples = []
            for _ in range(5):
                t0 = time.monotonic()
                res = nav.resolve_entries(recs, limit=10)
                samples.append(time.monotonic() - t0)
            samples.sort()
            med = samples[len(samples)//2] * 1000
            print(f"  {label:28} | {med:>12.2f} ms   found={len(res)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
