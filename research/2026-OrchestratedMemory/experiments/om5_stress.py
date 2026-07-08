#!/usr/bin/env python3
"""OrchestratedMemory Axe 5 — Stress: où l'orchestrateur devient bottleneck.

Mesurer le throughput à différentes échelles pour identifier le point
de saturation. On veut savoir:
  - à partir de combien d'entries l'admission ralentit-elle?
  - le cache d'admission (par entry_hash) aide-t-il ou nuit-il à grande échelle?
  - la latence de read (lanes.recent) dégrade-t-elle avec le volume?
"""
from __future__ import annotations
import shutil, sys, tempfile, time, statistics
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.identity.identity_registry import IdentityRegistry
from dsm.orchestrator import NeutralOrchestrator, RuleSet
from dsm.sovereignty import SovereigntyPolicy
from dsm.lanes import LaneGroup


def make_entry(agent_id, i):
    return Entry(
        id=f"{agent_id}_s{i:06d}", timestamp=datetime.now(timezone.utc),
        session_id=f"sess_{agent_id}", source=agent_id,
        content=f"stress entry {i}", shard="private",
        hash="", prev_hash=None,
        metadata={"event_type": "tool_call", "action_name": f"act_{i%20}"},
        version="v2.0",
    )


def setup_stack(tmp, agent_ids):
    storage = Storage(data_dir=str(tmp))
    identity = IdentityRegistry(storage=storage)
    policy = SovereigntyPolicy(storage=storage)
    orch = NeutralOrchestrator(storage=storage, rules=RuleSet.default(),
                                identity=identity, policy=policy)
    lanes = LaneGroup(storage, identity, policy, orch)
    for aid in agent_ids:
        identity.register(agent_id=aid, public_key=f"pk_{aid}",
                          owner_id="owner", owner_signature="sig", model="m")
        lanes.register_lane(aid)
    policy.set(owner_id="owner", owner_signature="sig",
               policy={"agents": list(agent_ids), "min_trust_score": 0.3,
                       "allowed_types": ["tool_call"], "approval_required": [], "cross_ai": True})
    return storage, orch, lanes


def main():
    print("=" * 80)
    print("AXE 5 — STRESS: point de saturation de l'orchestrateur")
    print("=" * 80)
    print()

    # Single agent, increasing volume — measure write throughput + read latency
    print(f"{'volume':>8} | {'write ms':>9} | {'w/sec':>7} | {'read ms':>8} | {'read n':>7}")
    print("-" * 55)

    for volume in [100, 500, 1000, 2000, 5000]:
        tmp = Path(tempfile.mkdtemp(prefix=f"om5_{volume}_"))
        try:
            storage, orch, lanes = setup_stack(tmp, ["agent_A"])

            entries = [make_entry("agent_A", i) for i in range(volume)]
            t0 = time.monotonic()
            result = lanes.push("agent_A", "owner", entries,
                                summary_fn=lambda e: e.content[:30],
                                detail_fn=lambda e: (e.content[:50], []))
            write_time = time.monotonic() - t0

            # Read latency
            t0 = time.monotonic()
            recent = lanes.recent(limit=volume)
            read_time = time.monotonic() - t0

            wps = len(result.admitted) / write_time if write_time > 0 else 0
            print(f"{volume:>8} | {write_time*1000:>8.0f} | {wps:>6.0f} | {read_time*1000:>7.1f} | {len(recent):>7}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print()
    # Now: does admission latency degrade with orchestrator cache size?
    print("=== Latence admit() vs cache size (1 entry par hash unique) ===")
    tmp = Path(tempfile.mkdtemp(prefix="om5_cache_"))
    try:
        storage, orch, lanes = setup_stack(tmp, ["agent_A"])
        for milestone in [100, 500, 1000, 2000, 5000]:
            # Push milestone entries to grow the cache
            if milestone == 100:
                start = 0
            else:
                start = milestone - 100 if milestone > 100 else 0
            entries = [make_entry("agent_A", i) for i in range(start, milestone)]
            lanes.push("agent_A", "owner", entries,
                       summary_fn=lambda e: e.content[:20], detail_fn=lambda e: (e.content[:30], []))

            # Measure admit latency at this cache size
            samples = []
            for i in range(50):
                e = make_entry("agent_A", milestone + i)  # unique hash each time
                t0 = time.perf_counter()
                orch.admit(e, "agent_A", "owner")
                samples.append((time.perf_counter() - t0) * 1000)
            med = statistics.median(samples)
            print(f"  cache~{milestone:>5} entries: admit median = {med:.3f} ms")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
