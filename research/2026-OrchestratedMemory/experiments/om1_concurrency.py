#!/usr/bin/env python3
"""OrchestratedMemory Axe 1 — Concurrence via l'orchestrateur central.

Hypothèse à falsifier:
  Le DSM orchestré peut supporter plusieurs writers concurrents avec une
  latence d'admission stable et un throughput linéaire.

Mesures:
  - throughput (writes/sec) pour N agents
  - latence d'admission moyenne (ms)
  - taux de rejet (%)
  - capacité de ré-lecture post-write
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
from dsm.identity.identity_registry import IdentityRegistry
from dsm.orchestrator import NeutralOrchestrator, RuleSet
from dsm.sovereignty import SovereigntyPolicy
from dsm.lanes import LaneGroup


def make_entry(agent_id: str, i: int) -> Entry:
    return Entry(
        id=f"{agent_id}_e{i:05d}",
        timestamp=datetime.now(timezone.utc),
        session_id=f"sess_{agent_id}",
        source=agent_id,
        content=f"{agent_id} wrote entry {i}",
        shard="private",
        hash="",
        prev_hash=None,
        metadata={"event_type": "decision", "action_name": f"act_{i%10}"},
        version="v2.0",
    )


def setup_stack(tmp: Path):
    storage = Storage(data_dir=str(tmp))
    identity = IdentityRegistry(storage=storage)
    policy = SovereigntyPolicy(storage=storage)
    orchestrator = NeutralOrchestrator(
        storage=storage, rules=RuleSet.default(),
        identity=identity, policy=policy,
    )
    lanes = LaneGroup(storage, identity, policy, orchestrator)
    return storage, identity, policy, orchestrator, lanes


def register_agents(identity, policy, lanes, agent_ids, owner="owner"):
    for aid in agent_ids:
        identity.register(
            agent_id=aid, public_key=f"pk_{aid}", owner_id=owner,
            owner_signature=f"sig_{owner}", model="test-model",
        )
        lanes.register_lane(aid)
    # Sovereignty policy: allow all registered agents + the event types they emit.
    # Without this, SovereigntyCheckRule fails closed (deny by default) — a security property.
    policy.set(
        owner_id=owner, owner_signature=f"sig_{owner}",
        policy={
            "agents": list(agent_ids),
            "min_trust_score": 0.3,
            "allowed_types": ["decision", "observation", "tool_call", "action_result"],
            "approval_required": [],
            "cross_ai": True,
        },
    )


def experiment_sequential(lanes, agent_ids, entries_per_agent):
    """Single-threaded baseline: each agent pushes sequentially."""
    t0 = time.monotonic()
    total_admitted, total_rejected = 0, 0
    for aid in agent_ids:
        entries = [make_entry(aid, i) for i in range(entries_per_agent)]
        result = lanes.push(aid, "owner", entries)
        total_admitted += len(result.admitted)
        total_rejected += len(result.rejected)
    elapsed = time.monotonic() - t0
    return total_admitted, total_rejected, elapsed


def experiment_threaded(lanes, agent_ids, entries_per_agent, workers):
    """Multi-threaded: agents push concurrently via ThreadPoolExecutor."""
    t0 = time.monotonic()
    total_admitted, total_rejected = 0, 0

    def push_one(aid):
        entries = [make_entry(aid, i) for i in range(entries_per_agent)]
        result = lanes.push(aid, "owner", entries)
        return len(result.admitted), len(result.rejected)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(push_one, aid) for aid in agent_ids]
        for f in as_completed(futures):
            a, r = f.result()
            total_admitted += a
            total_rejected += r
    elapsed = time.monotonic() - t0
    return total_admitted, total_rejected, elapsed


def measure_admission_latency(orchestrator, n=200):
    """Measure admit() latency directly (no shard write)."""
    samples = []
    for i in range(n):
        e = make_entry("probe", i)
        t0 = time.perf_counter()
        orchestrator.admit(e, "probe", "owner")
        samples.append((time.perf_counter() - t0) * 1000)
    return statistics.median(samples), statistics.mean(samples), max(samples)


def main():
    print("=" * 90)
    print("AXE 1 — CONCURRENCE: plusieurs writers via l'orchestrateur central")
    print("=" * 90)
    print()

    # === Setup: 5 agents registered ===
    tmp = Path(tempfile.mkdtemp(prefix="om1_"))
    try:
        storage, identity, policy, orchestrator, lanes = setup_stack(tmp)
        agents = [f"agent_{i}" for i in range(5)]
        register_agents(identity, policy, lanes, agents)
        print(f"Setup: {len(agents)} agents registered, each with own lane")
        print()

        # === Admission latency (direct, no shard write) ===
        print("=== Latence d'admission NeutralOrchestrator.admit() (n=200) ===")
        med, mean, mx = measure_admission_latency(orchestrator, n=200)
        print(f"  median: {med:.3f} ms   mean: {mean:.3f} ms   max: {mx:.3f} ms")
        print()

        # === Sequential baseline ===
        print("=== Throughput séquentiel (1 thread, 5 agents × 100 entries) ===")
        adm, rej, el = experiment_sequential(lanes, agents, 100)
        total = adm + rej
        print(f"  admitted={adm}  rejected={rej}  total={total}")
        print(f"  elapsed={el*1000:.1f} ms")
        print(f"  throughput: {adm/el:.0f} writes/sec")
        print(f"  reject rate: {rej/(total)*100:.1f}%")
        print()

        # === Threaded concurrency (2, 5, 10 workers) ===
        for workers in [2, 5, 10]:
            tmp2 = Path(tempfile.mkdtemp(prefix=f"om1_w{workers}_"))
            try:
                storage2, identity2, policy2, orch2, lanes2 = setup_stack(tmp2)
                register_agents(identity2, policy2, lanes2, agents)
                adm, rej, el = experiment_threaded(lanes2, agents, 100, workers)
                total = adm + rej
                print(f"=== Throughput concurrent ({workers} workers, 5 agents × 100 entries) ===")
                print(f"  admitted={adm}  rejected={rej}  total={total}")
                print(f"  elapsed={el*1000:.1f} ms")
                print(f"  throughput: {adm/el:.0f} writes/sec")
                print(f"  reject rate: {rej/(total)*100:.1f}%")
                print(f"  speedup vs sequential: {(adm/el) / (500/ el):.2f}x")
                print()
            finally:
                shutil.rmtree(tmp2, ignore_errors=True)

        # === Capacity check: can we read back what we wrote? ===
        print("=== Capacité de ré-lecture (5 agents, 100 entries each) ===")
        recent = lanes.recent(limit=500)
        print(f"  lanes.recent(limit=500) returned {len(recent)} entries")
        agents_in_recent = set(r.get("agent_id") for r in recent if isinstance(r, dict))
        print(f"  agents distincts retrouvés: {len(agents_in_recent)}")
        print(f"  → {'OK' if len(recent) == 500 and len(agents_in_recent) == 5 else 'MISMATCH'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
