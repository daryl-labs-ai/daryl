#!/usr/bin/env python3
"""Iteration 2b — prove session/agent/shard divergence is ONLY list ordering."""
from __future__ import annotations
import json, random, shutil, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
from dsm.core.storage import Storage
from dsm.core.shard_segments import MAX_EVENTS_PER_SEGMENT
from dsm.rr.index.rr_index_builder import RRIndexBuilder, _entry_to_index_record

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


def singlepass(storage):
    session_index, agent_index, timeline, shard_index, action_index = {}, {}, [], {}, {}
    for meta in storage.list_shards():
        sid = meta.shard_id
        evs = list(storage.segment_manager.iter_shard_events(sid))
        total = len(evs)
        for fp, event in enumerate(evs):
            entry = storage._entry_from_event_data(event)
            rec = _entry_to_index_record(entry, sid, total - 1 - fp)
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


def as_multiset(d):
    if isinstance(d, dict):
        return {k: json.dumps(sorted(v, key=lambda r: json.dumps(r, sort_keys=True)),
                              sort_keys=True) for k, v in d.items()}
    return json.dumps(sorted(d, key=lambda r: json.dumps(r, sort_keys=True)), sort_keys=True)


tmp = Path(tempfile.mkdtemp(prefix="i2b_"))
idx = tmp / "index"
try:
    write_segmented(make_entries(N), tmp)
    storage = Storage(data_dir=str(tmp))
    b = RRIndexBuilder(storage=storage, index_dir=str(idx), batch_size=5000)
    b.build()
    real = dict(session=b.session_index, agent=b.agent_index, timeline=b.timeline_index,
                shard=b.shard_index, action=b.action_index)
    proto = singlepass(storage)
    print("=== multiset equivalence (ordering-independent) ===")
    for key in ("session", "agent", "timeline", "shard", "action"):
        print(f"  {key:9}: multiset_match={as_multiset(real[key]) == as_multiset(proto[key])}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
