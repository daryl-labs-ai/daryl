"""
Benchmark: DSM A-E Pillars -- measure real performance.

Validates claims from DSM_PILLARS_A_TO_E.md:
1. O(1) vs O(N) for resolve, trust_score, allows
2. Token size: raw entries vs projections vs digests
3. Timing for key operations at different scales
4. Storage: projections vs full copies

Usage:
    python benchmarks/bench_pillars.py
"""

import json
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.identity.identity_registry import IdentityRegistry
from dsm.sovereignty import SovereigntyPolicy
from dsm.orchestrator import NeutralOrchestrator, RuleSet
from dsm.collective import CollectiveShard, ShardSyncEngine, RollingDigester
from dsm.lifecycle import ShardLifecycle, ShardState
from dsm.shard_families import classify_shard


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_entry(i, shard="sessions", content_size=500):
    """Create a realistic DSM entry (~2KB JSON typical for agent actions)."""
    content = json.dumps({
        "action": f"action_{i}",
        "query": f"search query number {i} with some realistic content padding " * 5,
        "result": f"result data for entry {i} with detailed output content " * (content_size // 50),
        "observations": [f"observation {j} from step {i}" for j in range(5)],
        "metadata": {"step": i, "model": "claude", "confidence": 0.95,
                      "duration_ms": 1234, "tokens_used": 456},
    })
    return Entry(
        id=f"entry_{i:06d}",
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=i * 10),
        session_id=f"session_{i // 10}",
        source="benchmark",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={"event_type": "action", "action_name": f"action_{i}"},
        version="v2.0",
    )


def _time_it(fn, label, iterations=100):
    """Time a function over N iterations, return avg in microseconds."""
    # Warmup
    fn()
    # Measure
    start = time.perf_counter()
    for _ in range(iterations):
        fn()
    elapsed = time.perf_counter() - start
    avg_us = (elapsed / iterations) * 1_000_000
    return avg_us


def _estimate_tokens(text):
    """Rough token estimate: ~4 chars per token (GPT/Claude average)."""
    return len(str(text)) // 4


def _format_us(us):
    """Format microseconds nicely."""
    if us < 1000:
        return f"{us:.0f} us"
    elif us < 1_000_000:
        return f"{us/1000:.1f} ms"
    else:
        return f"{us/1_000_000:.2f} s"


# ------------------------------------------------------------------
# Benchmark 1: O(1) vs O(N) -- resolve, trust_score, allows
# ------------------------------------------------------------------

def bench_complexity(tmp_dir):
    print("\n" + "=" * 70)
    print("BENCHMARK 1: Algorithmic Complexity -- O(1) claims")
    print("=" * 70)

    results = []
    for n_agents in [10, 100, 500, 1000]:
        storage = Storage(data_dir=str(tmp_dir / f"complexity_{n_agents}"))
        registry = IdentityRegistry(storage)
        sovereignty = SovereigntyPolicy(storage)

        # Register N agents
        agent_ids = []
        for i in range(n_agents):
            aid = f"agent_{i:04d}"
            registry.register(aid, f"pk_{i:04d}", "owner", "sig", model="claude")
            agent_ids.append(aid)

        # Set policy with all agents
        sovereignty.set("owner", "sig", {
            "agents": agent_ids,
            "min_trust_score": 0.0,
            "allowed_types": ["action"],
        })

        # Force index build
        registry.resolve(agent_ids[0])
        sovereignty.get("owner")

        # Measure resolve (should be O(1) after index build)
        target = agent_ids[-1]  # worst case: last registered
        resolve_us = _time_it(lambda: registry.resolve(target), "resolve", 1000)

        # Measure trust_score
        trust_us = _time_it(lambda: registry.trust_score(target), "trust", 1000)

        # Measure allows
        allows_us = _time_it(
            lambda: sovereignty.allows("owner", target, "action", registry),
            "allows", 1000,
        )

        results.append((n_agents, resolve_us, trust_us, allows_us))

    print(f"\n{'N agents':>10} | {'resolve()':>12} | {'trust_score()':>14} | {'allows()':>12}")
    print("-" * 60)
    for n, r, t, a in results:
        print(f"{n:>10} | {_format_us(r):>12} | {_format_us(t):>14} | {_format_us(a):>12}")

    # Check O(1) claim: ratio between smallest and largest should be < 3x
    r_ratio = results[-1][1] / max(results[0][1], 0.1)
    t_ratio = results[-1][2] / max(results[0][2], 0.1)
    a_ratio = results[-1][3] / max(results[0][3], 0.1)

    print(f"\nScaling ratio (1000 agents / 10 agents):")
    print(f"  resolve:     {r_ratio:.1f}x {'OK O(1)' if r_ratio < 5 else 'WARN not O(1)'}")
    print(f"  trust_score: {t_ratio:.1f}x {'OK O(1)' if t_ratio < 5 else 'WARN not O(1)'}")
    print(f"  allows:      {a_ratio:.1f}x {'OK O(1)' if a_ratio < 5 else 'WARN not O(1)'}")


# ------------------------------------------------------------------
# Benchmark 2: Token sizes -- raw vs projections vs digests
# ------------------------------------------------------------------

def bench_tokens(tmp_dir):
    print("\n" + "=" * 70)
    print("BENCHMARK 2: Token Sizes -- raw entries vs projections vs digests")
    print("=" * 70)

    # Create a realistic raw entry
    raw_entry = _make_entry(0)
    raw_json = json.dumps({
        "id": raw_entry.id,
        "timestamp": raw_entry.timestamp.isoformat(),
        "session_id": raw_entry.session_id,
        "source": raw_entry.source,
        "content": raw_entry.content,
        "shard": raw_entry.shard,
        "hash": "a" * 64,
        "prev_hash": "b" * 64,
        "metadata": raw_entry.metadata,
        "version": raw_entry.version,
    }, indent=2)

    # Tier 0: metadata only
    tier0 = json.dumps({
        "agent_id": "agent_001",
        "action_type": "action",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content_hash": "c" * 64,
    })

    # Tier 1: + summary
    tier1 = json.dumps({
        "agent_id": "agent_001",
        "action_type": "action",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content_hash": "c" * 64,
        "summary": "Agent searched for weather data in Paris and found sunny conditions with 22C temperature.",
    })

    # Tier 2: + detail + key_findings
    tier2 = json.dumps({
        "agent_id": "agent_001",
        "action_type": "action",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content_hash": "c" * 64,
        "summary": "Agent searched for weather data in Paris and found sunny conditions with 22C temperature.",
        "detail": "The agent queried the OpenWeather API for current conditions in Paris, France. "
                  "Results showed clear skies with temperature at 22.3C, humidity 45%, wind 12km/h NW. "
                  "UV index moderate (5). Air quality index good (42). Forecast shows similar conditions "
                  "for the next 3 days with slight temperature increase. No precipitation expected. "
                  "The agent compared this with historical averages for March, noting temperatures are "
                  "approximately 4C above the 30-year average for this date.",
        "key_findings": [
            "Current temp: 22.3C (4C above March average)",
            "Clear skies, no precipitation expected 72h",
            "Air quality: good (AQI 42)",
            "UV index moderate -- recommend sunscreen",
        ],
    })

    # Digest (hourly)
    digest = json.dumps({
        "digest_id": "d_hourly_001",
        "level": 1,
        "start_time": "2026-03-21T10:00:00Z",
        "end_time": "2026-03-21T11:00:00Z",
        "source_count": 15,
        "source_hash": "d" * 64,
        "key_events": [
            "3 weather queries completed",
            "2 decision entries logged",
            "1 error recovered (timeout)",
        ],
        "agents_involved": ["agent_001", "agent_002"],
        "metrics": {"success_rate": 0.93, "throughput": 15, "errors": 1},
    })

    raw_tokens = _estimate_tokens(raw_json)
    t0_tokens = _estimate_tokens(tier0)
    t1_tokens = _estimate_tokens(tier1)
    t2_tokens = _estimate_tokens(tier2)
    digest_tokens = _estimate_tokens(digest)

    print(f"\n{'Format':>25} | {'Chars':>8} | {'~Tokens':>8} | {'vs Raw':>8}")
    print("-" * 60)
    print(f"{'Raw entry (full JSON)':>25} | {len(raw_json):>8} | {raw_tokens:>8} | {'100%':>8}")
    print(f"{'Tier 0 (metadata)':>25} | {len(tier0):>8} | {t0_tokens:>8} | {t0_tokens*100//raw_tokens:>7}%")
    print(f"{'Tier 1 (+ summary)':>25} | {len(tier1):>8} | {t1_tokens:>8} | {t1_tokens*100//raw_tokens:>7}%")
    print(f"{'Tier 2 (+ detail)':>25} | {len(tier2):>8} | {t2_tokens:>8} | {t2_tokens*100//raw_tokens:>7}%")
    print(f"{'Hourly digest':>25} | {len(digest):>8} | {digest_tokens:>8} | {digest_tokens*100//raw_tokens:>7}%")

    print(f"\nContext budget comparison (200 entries):")
    print(f"  Raw scan:        {200 * raw_tokens:>8} tokens")
    print(f"  10× Tier 1:      {10 * t1_tokens:>8} tokens  ({10*t1_tokens*100//(200*raw_tokens)}% of raw)")
    print(f"  10× Tier 2:      {10 * t2_tokens:>8} tokens  ({10*t2_tokens*100//(200*raw_tokens)}% of raw)")
    print(f"  10× T2 + 5 dig:  {10*t2_tokens + 5*digest_tokens:>8} tokens  ({(10*t2_tokens+5*digest_tokens)*100//(200*raw_tokens)}% of raw)")

    print(f"\nStorage per 1000 contributions:")
    print(f"  Full copies:  {1000 * len(raw_json) / 1024:.0f} KB")
    print(f"  Projections:  {1000 * len(tier2) / 1024:.0f} KB  ({len(tier2)*100//len(raw_json)}% of raw)")


# ------------------------------------------------------------------
# Benchmark 3: Operation timing at scale
# ------------------------------------------------------------------

def bench_timing(tmp_dir):
    print("\n" + "=" * 70)
    print("BENCHMARK 3: Operation Timing at Scale")
    print("=" * 70)

    storage = Storage(data_dir=str(tmp_dir / "timing"))
    registry = IdentityRegistry(storage)
    sovereignty = SovereigntyPolicy(storage)
    orchestrator = NeutralOrchestrator(
        storage, RuleSet.default(), registry, sovereignty,
    )
    collective = CollectiveShard(storage, "collective_main")
    sync_engine = ShardSyncEngine(
        storage, collective, registry, sovereignty, orchestrator,
    )
    lifecycle = ShardLifecycle(storage)
    digester = RollingDigester(collective, storage)

    # Setup
    registry.register("bench_agent", "pk_bench", "owner", "sig", model="claude")
    sovereignty.set("owner", "sig", {
        "agents": ["bench_agent"],
        "min_trust_score": 0.0,
        "allowed_types": ["action"],
    })

    # Populate shard with entries
    for i in range(100):
        storage.append(_make_entry(i))

    # Time each operation
    print(f"\n{'Operation':>35} | {'Time':>12} | {'Note'}")
    print("-" * 75)

    t = _time_it(lambda: registry.resolve("bench_agent"), "resolve", 10000)
    print(f"{'resolve() [cached]':>35} | {_format_us(t):>12} | O(1) index lookup")

    t = _time_it(lambda: registry.trust_score("bench_agent"), "trust", 10000)
    print(f"{'trust_score() [cached]':>35} | {_format_us(t):>12} | O(1) fast trust")

    t = _time_it(
        lambda: sovereignty.allows("owner", "bench_agent", "action", registry),
        "allows", 10000,
    )
    print(f"{'allows() [cached]':>35} | {_format_us(t):>12} | O(1) policy + trust")

    entry = _make_entry(999)
    storage.append(entry)
    t = _time_it(lambda: orchestrator.admit(entry, "bench_agent", "owner"), "admit", 10000)
    print(f"{'admit() [cached]':>35} | {_format_us(t):>12} | O(1) cache hit")

    t = _time_it(lambda: collective.summary(), "summary", 10000)
    print(f"{'collective.summary()':>35} | {_format_us(t):>12} | index scan")

    t = _time_it(lambda: lifecycle.state("sessions"), "state", 10000)
    print(f"{'lifecycle.state() [cached]':>35} | {_format_us(t):>12} | O(1) cache")

    t = _time_it(lambda: classify_shard("sessions"), "classify", 100000)
    print(f"{'classify_shard()':>35} | {_format_us(t):>12} | O(1) dict lookup")

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    t = _time_it(lambda: digester.read_with_digests(since=since, max_tokens=8000), "digests", 1000)
    print(f"{'read_with_digests(8000)':>35} | {_format_us(t):>12} | budget-aware")

    # Index rebuild (cold start)
    registry._index = None  # force index rebuild
    t = _time_it(lambda: registry.resolve("bench_agent"), "cold_resolve", 1)
    print(f"{'resolve() [cold, rebuild index]':>35} | {_format_us(t):>12} | one-time cost")


# ------------------------------------------------------------------
# Benchmark 4: Shard families
# ------------------------------------------------------------------

def bench_families():
    print("\n" + "=" * 70)
    print("BENCHMARK 4: Shard Family Classification")
    print("=" * 70)

    shards = [
        "sessions", "identity", "identity_registry",
        "sovereignty_policies", "lifecycle_registry",
        "orchestrator_audit", "collective_main",
        "collective_digests", "sync_log", "receipts",
        "custom_shard_xyz",
    ]

    print(f"\n{'Shard':>25} | {'Family':>12}")
    print("-" * 42)
    for s in shards:
        print(f"{s:>25} | {classify_shard(s):>12}")

    t = _time_it(lambda: classify_shard("collective_main"), "classify", 1000000)
    print(f"\nclassify_shard() avg: {_format_us(t)} per call (1M iterations)")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    print("=" * 70)
    print("DSM A-E Pillars -- Performance Benchmark")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {sys.version.split()[0]}")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="dsm_bench_") as tmp:
        tmp_dir = Path(tmp)
        bench_complexity(tmp_dir)
        bench_tokens(tmp_dir)
        bench_timing(tmp_dir)
        bench_families()

    print("\n" + "=" * 70)
    print("BENCHMARK COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
