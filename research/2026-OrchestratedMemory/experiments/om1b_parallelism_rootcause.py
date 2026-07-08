#!/usr/bin/env python3
"""OrchestratedMemory Axe 1b — Root cause: why no parallel speedup?

Axe 1 found throughput is flat (~550 writes/sec) regardless of worker count.
Two candidate causes:
  (a) Python GIL serializing CPU work in admit()
  (b) FileLock contention serializing shard writes

If (a): scaling workers within one process can't help — only processes can.
If (b): each agent writes its OWN lane shard, so different agents should NOT
         contend on the same lock. If they do, the lane isolation is incomplete.

This experiment isolates the cause by comparing:
  - same-shard concurrent writes (forces lock contention if (b))
  - different-shard concurrent writes (should parallelize if (b), not if (a))
"""
from __future__ import annotations
import shutil, sys, tempfile, time, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage
from dsm.core.models import Entry


def make_entry(agent_id, i, shard):
    return Entry(
        id=f"{agent_id}_e{i:05d}", timestamp=datetime.now(timezone.utc),
        session_id=f"sess_{agent_id}", source=agent_id,
        content=f"{agent_id} entry {i}", shard=shard,
        hash="", prev_hash=None,
        metadata={"event_type": "decision"}, version="v2.0",
    )


def write_batch(storage, agent_id, n, shard):
    for i in range(n):
        storage.append(make_entry(agent_id, i, shard))


def time_concurrent(storage, agent_ids, n_per_agent, shard_mode, workers):
    """shard_mode: 'same' = all write to one shard; 'distinct' = each own shard."""
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = []
        for aid in agent_ids:
            shard = "shared_shard" if shard_mode == "same" else f"shard_{aid}"
            futs.append(ex.submit(write_batch, storage, aid, n_per_agent, shard))
        for f in as_completed(futs):
            f.result()
    return time.monotonic() - t0


def main():
    print("=" * 90)
    print("AXE 1b — Root cause: GIL vs FileLock contention")
    print("=" * 90)
    print()
    print("Si FileLock (b): different-shard doit être plus rapide que same-shard.")
    print("Si GIL (a): same et different doivent être identiques (no speedup).")
    print()

    agents = [f"agent_{i}" for i in range(5)]
    N = 100  # entries per agent

    for workers in [1, 5]:
        # Same shard (forces lock contention)
        tmp1 = Path(tempfile.mkdtemp(prefix=f"om1b_same_w{workers}_"))
        try:
            s1 = Storage(data_dir=str(tmp1))
            t_same = time_concurrent(s1, agents, N, "same", workers)
        finally:
            shutil.rmtree(tmp1, ignore_errors=True)

        # Distinct shards (no lock should be shared)
        tmp2 = Path(tempfile.mkdtemp(prefix=f"om1b_diff_w{workers}_"))
        try:
            s2 = Storage(data_dir=str(tmp2))
            t_diff = time_concurrent(s2, agents, N, "distinct", workers)
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

        ratio = t_same / t_diff if t_diff > 0 else float("inf")
        verdict = "FileLock contention (distinct faster)" if ratio > 1.3 else "GIL-bound (similar)"
        print(f"workers={workers}: same_shard={t_same*1000:.0f}ms  distinct_shards={t_diff*1000:.0f}ms  ratio={ratio:.2f}x  → {verdict}")

    # Also measure raw append() latency (no orchestrator) to isolate storage cost
    print()
    print("=== Raw Storage.append() latency (no orchestrator, no policy) ===")
    tmp3 = Path(tempfile.mkdtemp(prefix="om1b_raw_"))
    try:
        s3 = Storage(data_dir=str(tmp3))
        samples = []
        for i in range(200):
            e = make_entry("raw", i, "raw_shard")
            t0 = time.perf_counter()
            s3.append(e)
            samples.append((time.perf_counter() - t0) * 1000)
        print(f"  median: {statistics.median(samples):.3f} ms  mean: {statistics.mean(samples):.3f} ms  max: {max(samples):.3f} ms")
        print(f"  → ~{1000/statistics.median(samples):.0f} appends/sec theoretical max per single writer")
    finally:
        shutil.rmtree(tmp3, ignore_errors=True)


if __name__ == "__main__":
    main()
