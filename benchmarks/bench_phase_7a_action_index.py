#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Benchmark — ADR 0001 Phase 7a : RR action_name index prototype vs SessionIndex baseline.

Measures, on two fixture datasets (low/high action_name cardinality):
  - Build time : SessionIndex_build, RR_baseline_build (no action_index),
    RR_with_action_build (prototype). Incremental delta_build = RR_with - RR_baseline
    is the official gate; absolute RR_with / SessionIndex_build is reported as an
    operational concern when > 3x.
  - Query latency on 4 variants per dataset (top / rare / combined-session /
    combined-timerange), each run 100 times after 5 warmup runs, median / p95 / max.

Runs on a fresh tempdir per build run, and a single tempdir per query series
(build once, query many). No mocking; everything goes through the real
Storage / RRIndexBuilder / SessionIndex code paths on disk.

Usage:
    python3 benchmarks/bench_phase_7a_action_index.py [--out OUTDIR]

Outputs:
    benchmarks/results/phase_7a_action_index_<YYYYMMDD>.json
    benchmarks/results/phase_7a_action_index_<YYYYMMDD>.md
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dsm.core.models import Entry  # noqa: E402
from dsm.core.storage import Storage  # noqa: E402
from dsm.rr import _profiler as _rr_profiler  # noqa: E402
from dsm.rr.index import RRIndexBuilder  # noqa: E402
from dsm.rr.navigator import RRNavigator  # noqa: E402
from dsm.rr.query import RRQueryEngine  # noqa: E402
from dsm.session.session_index import SessionIndex  # noqa: E402


# ---------------------------------------------------------------------------
# Dataset generation — deterministic, seeded.
# ---------------------------------------------------------------------------

N_ENTRIES = 10_000
N_SESSIONS = 500
TIME_SPAN_DAYS = 30
# Default target: ~20 entries per session. Sessions scale linearly with fixture_size.
ENTRIES_PER_SESSION_TARGET = 20
EVENT_TYPE_POOL: List[Tuple[str, float]] = [
    ("session_start", 0.05),
    ("tool_call", 0.70),
    ("snapshot", 0.05),
    ("session_end", 0.05),
    ("note", 0.15),
]

# Dataset A: low cardinality, 30 action_names, Zipf-like (s = 1.1).
DATASET_A = {
    "label": "A_low_card_zipf",
    "description": "10 000 entries, 500 sessions, 30 action_names Zipf s=1.1",
    "n_actions": 30,
    "distribution": "zipf",
    "zipf_s": 1.1,
    "seed": 42,
}

# Dataset B: high cardinality, 1 000 action_names, quasi-uniform.
DATASET_B = {
    "label": "B_high_card_uniform",
    "description": "10 000 entries, 500 sessions, 1 000 action_names quasi-uniform",
    "n_actions": 1_000,
    "distribution": "uniform",
    "zipf_s": None,
    "seed": 43,
}


def _action_weights(n: int, mode: str, zipf_s: float | None) -> List[float]:
    if mode == "uniform":
        return [1.0] * n
    if mode == "zipf":
        s = zipf_s or 1.1
        return [1.0 / ((rank + 1) ** s) for rank in range(n)]
    raise ValueError(f"unknown distribution {mode!r}")


def _build_dataset(
    dataset_cfg: Dict[str, Any],
    fixture_size: int = N_ENTRIES,
    n_sessions: int = N_SESSIONS,
) -> Dict[str, Any]:
    """
    Build dataset in-memory: returns dict with `entries` (list of JSON-ready dicts),
    `action_names` (full list), `top_action`, `rare_action`, `session_ids`, etc.

    fixture_size and n_sessions default to the Phase 7a 10 000-entry constants for
    backwards compatibility with the original Phase 7a invocation; callers that
    parameterise them (e.g. Phase 7a.5 at 100 000 entries) should keep the
    ~20-entries-per-session ratio by scaling n_sessions linearly.
    """
    rng = random.Random(dataset_cfg["seed"])
    n_actions = dataset_cfg["n_actions"]

    action_names = [f"action_{i:04d}" for i in range(n_actions)]
    weights = _action_weights(n_actions, dataset_cfg["distribution"], dataset_cfg["zipf_s"])
    event_types = [et for et, _ in EVENT_TYPE_POOL]
    event_weights = [w for _, w in EVENT_TYPE_POOL]

    session_ids = [f"session_{i:04d}" for i in range(n_sessions)]
    agents = ["agent_alpha", "agent_beta", "agent_gamma"]
    t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    span = timedelta(days=TIME_SPAN_DAYS).total_seconds()

    entries: List[Dict[str, Any]] = []
    action_counts: Dict[str, int] = {}

    for i in range(fixture_size):
        ts_offset = rng.random() * span
        ts = t0 + timedelta(seconds=ts_offset)
        session_id = rng.choice(session_ids)
        source = rng.choice(agents)
        event_type = rng.choices(event_types, weights=event_weights, k=1)[0]

        metadata: Dict[str, Any] = {"event_type": event_type}
        if event_type == "tool_call":
            aname = rng.choices(action_names, weights=weights, k=1)[0]
            metadata["action_name"] = aname
            metadata["success"] = rng.random() < 0.95
            action_counts[aname] = action_counts.get(aname, 0) + 1
        else:
            # Occasional action_name on non-tool_call (mirrors real traffic noise).
            if rng.random() < 0.02:
                aname = rng.choices(action_names, weights=weights, k=1)[0]
                metadata["action_name"] = aname
                action_counts[aname] = action_counts.get(aname, 0) + 1

        entry = {
            "id": f"e_{i:06d}",
            "timestamp": ts.isoformat(),
            "session_id": session_id,
            "source": source,
            "content": f"entry #{i}",
            "shard": "sessions",
            "hash": "",
            "prev_hash": None,
            "metadata": metadata,
            "version": "v2.0",
        }
        entries.append(entry)

    entries.sort(key=lambda e: e["timestamp"])

    # Deterministic picks for top / rare / combined queries.
    if action_counts:
        ranked = sorted(action_counts.items(), key=lambda kv: kv[1], reverse=True)
        top_action = ranked[0][0]
        # Rare = first action within the bottom 10% of counts (by rank).
        bottom_rank_start = max(1, int(len(ranked) * 0.9))
        rare_action = ranked[bottom_rank_start][0]
    else:
        top_action = action_names[0]
        rare_action = action_names[-1]

    # Session for C1: pick one session that has top_action in it deterministically.
    session_pool: Dict[str, int] = {}
    for e in entries:
        meta = e["metadata"]
        if meta.get("action_name") == top_action:
            session_pool[e["session_id"]] = session_pool.get(e["session_id"], 0) + 1
    if session_pool:
        c1_session = sorted(session_pool.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    else:
        c1_session = session_ids[0]

    # Time window for C2: [t0+10d, t0+20d] covers middle third of the span.
    c2_start_dt = t0 + timedelta(days=10)
    c2_end_dt = t0 + timedelta(days=20)

    return {
        "cfg": dataset_cfg,
        "entries": entries,
        "action_names": action_names,
        "action_counts": action_counts,
        "top_action": top_action,
        "rare_action": rare_action,
        "c1_session": c1_session,
        "c2_start": c2_start_dt.isoformat(),
        "c2_end": c2_end_dt.isoformat(),
        "distinct_actions_seen": len(action_counts),
    }


def _materialize_dataset(entries: List[Dict[str, Any]], target_dir: Path) -> None:
    """Write entries as a monolithic JSONL shard under target_dir/shards/sessions.jsonl."""
    shards_dir = target_dir / "shards"
    integrity_dir = target_dir / "integrity"
    shards_dir.mkdir(parents=True, exist_ok=True)
    integrity_dir.mkdir(parents=True, exist_ok=True)
    shard_path = shards_dir / "sessions.jsonl"
    with open(shard_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _entry_from_dict(d: Dict[str, Any]) -> Entry:
    """Reconstitute an Entry from a bench-generated dict. Timestamps are ISO strings
    in the dataset dicts; Entry expects a datetime. Hash is left empty so that
    Storage.append computes the canonical entry hash itself."""
    ts_raw = d["timestamp"]
    if isinstance(ts_raw, str):
        ts = datetime.fromisoformat(ts_raw)
    else:
        ts = ts_raw
    return Entry(
        id=d.get("id", ""),
        timestamp=ts,
        session_id=d.get("session_id", ""),
        source=d.get("source", ""),
        content=d.get("content", ""),
        shard=d.get("shard", "sessions"),
        hash="",
        prev_hash=None,
        metadata=d.get("metadata", {}),
        version=d.get("version", "v2.0"),
    )


def _build_segmented_golden(
    entries: List[Dict[str, Any]],
    shard_id: str = "sessions",
    max_events_per_segment: Optional[int] = None,
) -> tuple:
    """Generate a golden segmented fixture via Storage.append() (the production path).

    Returns (golden_dir: Path, verification: dict). Caller is responsible for
    rmtree-ing golden_dir when done.

    Verification dict contents :
      - verified: bool — True iff layout is truly segmented with >= 2 segment files.
      - segments_count: int — count of <family>_NNNN.jsonl files on disk.
      - max_events_per_segment_used: int — threshold actually used by the segment manager.
      - shard_paths: list[str] — relative paths of created segment files (for audit).
      - list_shards_dispatch: str — which read path Storage would choose for this shard.
    """
    golden = Path(tempfile.mkdtemp(prefix="bench_golden_segmented_"))
    storage = Storage(data_dir=str(golden))
    if max_events_per_segment is not None:
        # Instance-level override only — does NOT modify src/dsm/core/shard_segments.py.
        storage.segment_manager.MAX_EVENTS_PER_SEGMENT = max_events_per_segment

    for d in entries:
        entry = _entry_from_dict(d)
        entry.shard = shard_id
        storage.append(entry)

    family_dir = golden / "shards" / shard_id.replace("shard_", "")
    segment_files = sorted(family_dir.glob("*.jsonl"))
    shards_listed = storage.list_shards()

    verification = {
        "verified": family_dir.is_dir() and len(segment_files) >= 2,
        "segments_count": len(segment_files),
        "max_events_per_segment_used": storage.segment_manager.MAX_EVENTS_PER_SEGMENT,
        "shard_paths": [str(p.relative_to(golden)) for p in segment_files],
        "list_shards_names": [sm.shard_id for sm in shards_listed],
        "list_shards_dispatch": "segmented" if family_dir.is_dir() else "monolithic",
    }
    return golden, verification


def _copy_golden_to(target_dir: Path, golden_dir: Path) -> None:
    """Copy the pre-generated segmented golden fixture into target_dir.
    Uses shutil.copytree with dirs_exist_ok so that target_dir (empty) gets
    populated with the same shards/ and integrity/ layout as golden_dir."""
    shutil.copytree(str(golden_dir), str(target_dir), dirs_exist_ok=True)


# ---------------------------------------------------------------------------
# Measurement primitives.
# ---------------------------------------------------------------------------

def _time_call(fn: Callable[[], Any]) -> float:
    """Return elapsed seconds for a single call."""
    t0 = time.monotonic()
    fn()
    return time.monotonic() - t0


def _run_build_series(
    label: str,
    entries: List[Dict[str, Any]],
    build_fn_factory: Callable[[Path], Callable[[], Any]],
    n_runs: int = 5,
    collect_profile: bool = False,
    materialize_fn: Optional[Callable[[Path], None]] = None,
) -> Dict[str, Any]:
    """
    Run a build N times on fresh temp dirs; return stats in seconds.
    Each run wipes the temp dir, re-materialises the JSONL, then calls the factory
    which returns the callable to time.

    When collect_profile=True and the RR profiler is enabled, snapshots the
    profiler state after each run and returns per-run snapshots under the
    "profile_snapshots" key. Caller owns aggregation.

    When materialize_fn is provided (Phase 7a.5-bis), it is called with the fresh
    tmp dir to populate the fixture instead of the default monolithic writer. The
    caller is responsible for shape / determinism of the materialisation.
    """
    if materialize_fn is None:
        materialize_fn = lambda tmp: _materialize_dataset(entries, tmp)
    samples: List[float] = []
    profile_snapshots: List[Dict[str, List[float]]] = []
    for _ in range(n_runs):
        tmp = Path(tempfile.mkdtemp(prefix="bench_phase7a_build_"))
        try:
            materialize_fn(tmp)
            call = build_fn_factory(tmp)
            if collect_profile and _rr_profiler.enabled():
                _rr_profiler.reset()
            samples.append(_time_call(call))
            if collect_profile and _rr_profiler.enabled():
                profile_snapshots.append(_rr_profiler.snapshot())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    stats = _stats(samples, label)
    if profile_snapshots:
        stats["profile_snapshots"] = profile_snapshots
    return stats


def _run_query_series(
    label: str,
    call: Callable[[], Any],
    warmup: int = 5,
    n_runs: int = 100,
    collect_profile: bool = False,
) -> Dict[str, Any]:
    """Run a query call `warmup + n_runs` times; return stats for the last n_runs.

    When collect_profile=True and the RR profiler is enabled, resets the
    profiler AFTER warmup and snapshots at the end of the n_runs timed loop.
    The single snapshot therefore contains n_runs samples per instrumented
    section.
    """
    for _ in range(warmup):
        call()
    if collect_profile and _rr_profiler.enabled():
        _rr_profiler.reset()
    samples: List[float] = []
    for _ in range(n_runs):
        samples.append(_time_call(call))
    stats = _stats(samples, label)
    if collect_profile and _rr_profiler.enabled():
        stats["profile_snapshot"] = _rr_profiler.snapshot()
    return stats


def _stats(samples: List[float], label: str) -> Dict[str, Any]:
    """Return descriptive stats in milliseconds; keep seconds copy for further math."""
    if not samples:
        return {"label": label, "n": 0}
    samples_ms = [s * 1000.0 for s in samples]
    samples_sorted = sorted(samples_ms)
    p95_idx = min(len(samples_sorted) - 1, int(round(0.95 * len(samples_sorted))) - 1)
    return {
        "label": label,
        "n": len(samples),
        "median_ms": statistics.median(samples_ms),
        "mean_ms": statistics.fmean(samples_ms),
        "stdev_ms": statistics.pstdev(samples_ms) if len(samples_ms) > 1 else 0.0,
        "min_ms": min(samples_ms),
        "max_ms": max(samples_ms),
        "p95_ms": samples_sorted[max(0, p95_idx)],
        "raw_seconds_first5": samples[:5],
    }


# ---------------------------------------------------------------------------
# Build-fn factories.
# ---------------------------------------------------------------------------

def _session_index_build_factory(data_dir: Path) -> Callable[[], Any]:
    storage = Storage(data_dir=str(data_dir))
    index_dir = data_dir / "index_session"

    def _call() -> Any:
        # SessionIndex persists on disk and rebuilds cold; matches production path
        # (src/dsm/session/session_index.py:44).
        idx = SessionIndex(str(index_dir), shard_id="sessions")
        return idx.build_from_storage(storage)

    return _call


def _rr_build_factory(data_dir: Path, enable_action_index: bool) -> Callable[[], Any]:
    storage = Storage(data_dir=str(data_dir))
    suffix = "rr_with_action" if enable_action_index else "rr_baseline"
    index_dir = data_dir / f"index_{suffix}"

    def _call() -> Any:
        builder = RRIndexBuilder(
            storage=storage,
            index_dir=str(index_dir),
            enable_action_index=enable_action_index,
        )
        builder.build()
        return builder

    return _call


# ---------------------------------------------------------------------------
# Query runners — build once, query many.
# ---------------------------------------------------------------------------

def _prepare_query_env(
    entries: List[Dict[str, Any]],
    materialize_fn: Optional[Callable[[Path], None]] = None,
) -> Dict[str, Any]:
    """Build fresh indexes on disk and return resolved query callables for all 4 variants.

    materialize_fn (Phase 7a.5-bis) overrides the default monolithic writer when
    provided. Keeps the query-env layout identical to the build-series layout
    across a given benchmark run."""
    tmp = Path(tempfile.mkdtemp(prefix="bench_phase7a_query_"))
    if materialize_fn is None:
        _materialize_dataset(entries, tmp)
    else:
        materialize_fn(tmp)

    si_storage = Storage(data_dir=str(tmp))
    si_index = SessionIndex(str(tmp / "index_session"), shard_id="sessions")
    si_index.build_from_storage(si_storage)

    rr_storage = Storage(data_dir=str(tmp))
    rr_builder = RRIndexBuilder(
        storage=rr_storage,
        index_dir=str(tmp / "index_rr"),
        enable_action_index=True,
    )
    rr_builder.build()
    rr_navigator = RRNavigator(index_builder=rr_builder, storage=rr_storage)
    rr_engine = RRQueryEngine(navigator=rr_navigator)

    return {
        "tmp": tmp,
        "session_index": si_index,
        "rr_engine": rr_engine,
    }


def _make_query_calls(
    env: Dict[str, Any],
    top_action: str,
    rare_action: str,
    c1_session: str,
    c2_start: str,
    c2_end: str,
) -> Dict[str, Callable[[], Any]]:
    si: SessionIndex = env["session_index"]
    rr: RRQueryEngine = env["rr_engine"]
    return {
        # Query top
        "SI_top": lambda: si.get_actions(action_name=top_action, limit=100),
        "RR_top": lambda: rr.query_actions(action_name=top_action, limit=100),
        # Query rare
        "SI_rare": lambda: si.get_actions(action_name=rare_action, limit=100),
        "RR_rare": lambda: rr.query_actions(action_name=rare_action, limit=100),
        # Combined C1 — action_name + session_id
        "SI_c1": lambda: si.get_actions(
            action_name=top_action, session_id=c1_session, limit=100
        ),
        "RR_c1": lambda: rr.query_actions(
            action_name=top_action, session_id=c1_session, limit=100
        ),
        # Combined C2 — action_name + time window
        "SI_c2": lambda: si.get_actions(
            action_name=top_action, start_time=c2_start, end_time=c2_end, limit=100
        ),
        "RR_c2": lambda: rr.query_actions(
            action_name=top_action, start_time=c2_start, end_time=c2_end, limit=100
        ),
    }


# ---------------------------------------------------------------------------
# End-to-end benchmark.
# ---------------------------------------------------------------------------

def bench_dataset(
    dataset_cfg: Dict[str, Any],
    fixture_size: int = N_ENTRIES,
    n_sessions: int = N_SESSIONS,
    fixture_layout: str = "monolithic",
) -> Dict[str, Any]:
    ds = _build_dataset(dataset_cfg, fixture_size=fixture_size, n_sessions=n_sessions)
    entries = ds["entries"]

    # -- Fixture materialisation strategy --------------------------------
    # For monolithic (Phase 7a / 7a.5 compatibility), write raw JSONL per run.
    # For segmented (Phase 7a.5-bis), generate a golden fixture ONCE via
    # Storage.append() and copy it into each fresh tmp dir. This isolates the
    # (very expensive, fsync-per-entry) golden generation from the build
    # measurements while still giving each build run a fresh tmp path.
    golden_dir: Optional[Path] = None
    fixture_layout_meta: Dict[str, Any] = {"fixture_layout": fixture_layout}
    if fixture_layout == "segmented":
        print(
            f"[bench] generating segmented golden fixture via Storage.append() "
            f"({len(entries):,} entries)...",
            flush=True,
        )
        t0 = time.monotonic()
        golden_dir, verification = _build_segmented_golden(entries)
        gen_elapsed = time.monotonic() - t0
        print(
            f"[bench] golden segmented fixture ready in {gen_elapsed:.1f}s — "
            f"segments={verification['segments_count']} "
            f"verified={verification['verified']}",
            flush=True,
        )
        fixture_layout_meta.update({
            "fixture_layout_verified": verification,
            "golden_generation_seconds": gen_elapsed,
        })
        materialize_fn: Optional[Callable[[Path], None]] = (
            lambda tmp: _copy_golden_to(tmp, golden_dir)
        )
        if not verification["verified"]:
            shutil.rmtree(golden_dir, ignore_errors=True)
            raise RuntimeError(
                f"Segmented fixture verification FAILED — "
                f"segments_count={verification['segments_count']} < 2. "
                f"Investigate kernel segment-rotation parameters before continuing."
            )
    else:
        materialize_fn = None  # default monolithic path
        fixture_layout_meta["fixture_layout_verified"] = {"verified": True, "layout": "monolithic"}

    try:
        # -- Build phase -----------------------------------------------------
        si_build = _run_build_series(
            "SessionIndex_build",
            entries,
            lambda tmp: _session_index_build_factory(tmp),
            n_runs=5,
            materialize_fn=materialize_fn,
        )
        rr_baseline = _run_build_series(
            "RR_baseline_build",
            entries,
            lambda tmp: _rr_build_factory(tmp, enable_action_index=False),
            n_runs=5,
            materialize_fn=materialize_fn,
        )
        rr_with_action = _run_build_series(
            "RR_with_action_build",
            entries,
            lambda tmp: _rr_build_factory(tmp, enable_action_index=True),
            n_runs=5,
            collect_profile=True,
            materialize_fn=materialize_fn,
        )
        delta_build_ms = rr_with_action["median_ms"] - rr_baseline["median_ms"]

        # -- Query phase -----------------------------------------------------
        env = _prepare_query_env(entries, materialize_fn=materialize_fn)
        try:
            calls = _make_query_calls(
                env,
                top_action=ds["top_action"],
                rare_action=ds["rare_action"],
                c1_session=ds["c1_session"],
                c2_start=ds["c2_start"],
                c2_end=ds["c2_end"],
            )

            query_results: Dict[str, Any] = {}
            for label, call in calls.items():
                # Collect profiler snapshots only for RR variants — the RR profiler
                # does not instrument SessionIndex and would yield empty snapshots
                # there. Keeping SI runs uninstrumented also avoids any dead-code
                # profiler overhead (nominal but non-zero).
                collect = label.startswith("RR_")
                query_results[label] = _run_query_series(
                    label, call, warmup=5, n_runs=100, collect_profile=collect
                )

            # Expose the returned result counts for transparency.
            hit_counts = {
                "SI_top_rowcount": len(calls["SI_top"]()),
                "RR_top_rowcount": len(calls["RR_top"]()),
                "SI_rare_rowcount": len(calls["SI_rare"]()),
                "RR_rare_rowcount": len(calls["RR_rare"]()),
                "SI_c1_rowcount": len(calls["SI_c1"]()),
                "RR_c1_rowcount": len(calls["RR_c1"]()),
                "SI_c2_rowcount": len(calls["SI_c2"]()),
                "RR_c2_rowcount": len(calls["RR_c2"]()),
            }
        finally:
            shutil.rmtree(env["tmp"], ignore_errors=True)

        # -- Gates -----------------------------------------------------------
        build_gate_ratio = (
            delta_build_ms / si_build["median_ms"] if si_build["median_ms"] > 0 else float("inf")
        )
        build_gate_pass = build_gate_ratio <= 1.0
        absolute_build_ratio = (
            rr_with_action["median_ms"] / si_build["median_ms"]
            if si_build["median_ms"] > 0
            else float("inf")
        )
        build_operational_flag = absolute_build_ratio > 3.0
        # Gate (iii), blocking as of Phase 7a.5 — see
        # docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md > Migration plan > Phase 7a.5.
        # At 10 k this gate passes with margin (observed 6.44×) ; at 100 k it is the operational
        # acceptability check that conditions Phase 7b.
        absolute_gate_pass = absolute_build_ratio <= 10.0

        def _ratio(label_rr: str, label_si: str) -> float:
            si_med = query_results[label_si]["median_ms"]
            rr_med = query_results[label_rr]["median_ms"]
            return rr_med / si_med if si_med > 0 else float("inf")

        query_gates = {
            "top":  {"ratio": _ratio("RR_top",  "SI_top"),  "threshold": 1.5},
            "rare": {"ratio": _ratio("RR_rare", "SI_rare"), "threshold": 1.5},
            "c1":   {"ratio": _ratio("RR_c1",   "SI_c1"),   "threshold": 1.5},
            "c2":   {"ratio": _ratio("RR_c2",   "SI_c2"),   "threshold": 1.5},
        }
        for g in query_gates.values():
            g["pass"] = g["ratio"] <= g["threshold"]

        dataset_pass = (
            build_gate_pass
            and absolute_gate_pass
            and all(g["pass"] for g in query_gates.values())
        )

        # -- Profiler decomposition (Phase 7a.5 root-cause, only when DSM_RR_PROFILE=1) --
        profile_decomposition: Dict[str, Any] = {}
        if _rr_profiler.enabled():
            profile_decomposition = _aggregate_profiles(
                rr_with_action=rr_with_action,
                query_results=query_results,
            )

        return {
            "cfg": dataset_cfg,
            "fixture_layout_meta": fixture_layout_meta,
            "derived": {
                "top_action": ds["top_action"],
                "rare_action": ds["rare_action"],
                "c1_session": ds["c1_session"],
                "c2_start": ds["c2_start"],
                "c2_end": ds["c2_end"],
                "distinct_actions_seen": ds["distinct_actions_seen"],
                "total_entries": len(entries),
            },
            "builds": {
                "SessionIndex_build": si_build,
                "RR_baseline_build": rr_baseline,
                "RR_with_action_build": rr_with_action,
                "delta_build_ms": delta_build_ms,
                "delta_build_ratio_vs_SI": build_gate_ratio,
                "absolute_RR_with_over_SI": absolute_build_ratio,
                "build_gate_pass": build_gate_pass,
                "build_operational_flag_over_3x": build_operational_flag,
                "absolute_gate_pass_under_10x": absolute_gate_pass,
            },
            "queries": query_results,
            "query_row_counts": hit_counts,
            "query_gates": query_gates,
            "dataset_pass": dataset_pass,
            "profile_decomposition": profile_decomposition,
        }
    finally:
        if golden_dir is not None:
            shutil.rmtree(golden_dir, ignore_errors=True)


def _aggregate_profiles(
    rr_with_action: Dict[str, Any],
    query_results: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Phase 7a.5 root-cause aggregation — called only when DSM_RR_PROFILE is enabled.

    Build path: each of the 5 runs produced one snapshot with one sample per
    section (`build:*` / `write:*`). We take the median across the 5 runs per
    section, which mirrors the build series' median-of-5 wall-clock metric.

    Query path: each variant produced one snapshot containing 100 samples per
    instrumented section (`nav:*` / `query_actions:*`). We report median, p95
    and max in µs.
    """
    def ms_stats(samples_s: List[float]) -> Dict[str, float]:
        if not samples_s:
            return {"median_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0, "n": 0}
        samples_ms = [s * 1000.0 for s in samples_s]
        samples_ms.sort()
        p95_idx = min(len(samples_ms) - 1, int(round(0.95 * len(samples_ms))) - 1)
        return {
            "median_ms": statistics.median(samples_ms),
            "p95_ms": samples_ms[max(0, p95_idx)],
            "max_ms": max(samples_ms),
            "n": len(samples_ms),
        }

    def us_stats(samples_s: List[float]) -> Dict[str, float]:
        if not samples_s:
            return {"median_us": 0.0, "p95_us": 0.0, "max_us": 0.0, "n": 0}
        samples_us = [s * 1_000_000.0 for s in samples_s]
        samples_us.sort()
        p95_idx = min(len(samples_us) - 1, int(round(0.95 * len(samples_us))) - 1)
        return {
            "median_us": statistics.median(samples_us),
            "p95_us": samples_us[max(0, p95_idx)],
            "max_us": max(samples_us),
            "n": len(samples_us),
        }

    # --- Build: 5 snapshots, each section may have 1+ samples (sections timed
    # per-batch like `build:storage_read_batch` / `build:populate_indexes`
    # accumulate multiple samples in a single run). For each run we sum the
    # samples of a given section into a per-run total, then take median across
    # the 5 per-run totals. This matches the wall-clock median-of-5 we already
    # report for build_total. ---
    snaps = rr_with_action.get("profile_snapshots", [])
    section_medians: Dict[str, Dict[str, float]] = {}
    if snaps:
        all_sections = set()
        for snap in snaps:
            all_sections.update(snap.keys())
        for sec in sorted(all_sections):
            per_run_totals = [
                sum(snap.get(sec, [])) for snap in snaps if snap.get(sec) is not None
            ]
            # Drop runs where this section did not fire at all (e.g. bucket_sort
            # on disabled action_index — not applicable here since we only
            # profile RR_with_action).
            per_run_totals = [t for t in per_run_totals if t > 0.0 or sec in snaps[0]]
            section_medians[sec] = ms_stats(per_run_totals)
            # Also expose the per-run firing count to detect multi-sample sections.
            sample_counts = [len(snap.get(sec, [])) for snap in snaps]
            section_medians[sec]["samples_per_run_median"] = (
                statistics.median(sample_counts) if sample_counts else 0
            )

    # Deletion of the raw per-run samples from stats to keep the main JSON tidy —
    # the decomposition below is the consolidated view.
    rr_with_action.pop("profile_snapshots", None)

    # --- Query: per-variant, 100 samples per instrumented section ---
    query_decompositions: Dict[str, Dict[str, Any]] = {}
    for label, qr in query_results.items():
        snap = qr.pop("profile_snapshot", None)
        if not snap:
            continue
        section_stats = {sec: us_stats(vals) for sec, vals in snap.items()}
        query_decompositions[label] = {
            "variant": label,
            "runs": qr["n"],
            "query_total_median_ms": qr["median_ms"],
            "sections": section_stats,
        }

    return {
        "build_sections": section_medians,
        "query_decompositions": query_decompositions,
    }


def render_markdown(results: Dict[str, Any]) -> str:
    lines: List[str] = []
    phase = results.get("phase", "7a")
    fixture_size = results.get("fixture_size", N_ENTRIES)
    lines.append(f"# Phase {phase} benchmark — RR action_name index vs SessionIndex")
    lines.append("")
    lines.append(f"- Run timestamp (UTC): {results['run_utc']}")
    lines.append(f"- Prototype branch: {results['branch']}")
    lines.append(f"- Commit SHA: {results['commit_sha']}")
    lines.append(f"- Python: {results['python']}")
    lines.append(f"- Platform: {results['platform']}")
    lines.append(f"- Fixture size per dataset: {fixture_size:,} entries")
    if results.get("comparison_baseline"):
        lines.append(f"- Comparison baseline: `{results['comparison_baseline']}`")
    lines.append("")
    lines.append(f"**Overall verdict: {'PASS' if results['verdict'] == 'PASS' else 'FAIL'}**")
    lines.append("")
    for ds_result in results["datasets"]:
        cfg = ds_result["cfg"]
        lines.append(f"## Dataset {cfg['label']}")
        lines.append("")
        lines.append(f"- {cfg['description']}")
        lines.append(f"- Distribution: {cfg['distribution']}; seed: {cfg['seed']}")
        lines.append(
            f"- Distinct action_names observed: {ds_result['derived']['distinct_actions_seen']}"
        )
        lines.append(f"- Top action: `{ds_result['derived']['top_action']}`  ·  Rare action: `{ds_result['derived']['rare_action']}`")
        lines.append("")
        builds = ds_result["builds"]
        lines.append("### Build")
        lines.append("")
        lines.append(
            "| Metric | median (ms) | p95 (ms) | max (ms) | vs SessionIndex | Gate | Pass |"
        )
        lines.append(
            "|---|---:|---:|---:|---|---|---|"
        )
        si_med = builds["SessionIndex_build"]["median_ms"]
        for name in ("SessionIndex_build", "RR_baseline_build", "RR_with_action_build"):
            b = builds[name]
            ratio = b["median_ms"] / si_med if si_med > 0 else float("inf")
            lines.append(
                f"| {name} | {b['median_ms']:.2f} | {b['p95_ms']:.2f} | {b['max_ms']:.2f} | {ratio:.2f}× | — | — |"
            )
        lines.append(
            f"| **delta_build = RR_with - RR_baseline** | {builds['delta_build_ms']:.2f} | — | — | {builds['delta_build_ratio_vs_SI']:.2f}× | ≤ 1× | {'✅' if builds['build_gate_pass'] else '❌'} |"
        )
        flag = "operational flag (>3×)" if builds["build_operational_flag_over_3x"] else "within 3×"
        lines.append(
            f"| RR_with_action absolute | — | — | — | {builds['absolute_RR_with_over_SI']:.2f}× | ≤ 3× (info) | {flag} |"
        )
        lines.append("")
        lines.append("### Queries")
        lines.append("")
        lines.append(
            "| Variant | SI median (ms) | RR median (ms) | RR p95 (ms) | RR max (ms) | ratio | Gate | Pass | SI rows | RR rows |"
        )
        lines.append(
            "|---|---:|---:|---:|---:|---|---|---|---:|---:|"
        )
        qg = ds_result["query_gates"]
        qr = ds_result["queries"]
        rc = ds_result["query_row_counts"]
        for variant, si_lab, rr_lab, gate_key in (
            ("top",  "SI_top",  "RR_top",  "top"),
            ("rare", "SI_rare", "RR_rare", "rare"),
            ("C1 (action+session)", "SI_c1", "RR_c1", "c1"),
            ("C2 (action+time)",    "SI_c2", "RR_c2", "c2"),
        ):
            si = qr[si_lab]
            rr = qr[rr_lab]
            g = qg[gate_key]
            lines.append(
                f"| {variant} | {si['median_ms']:.4f} | {rr['median_ms']:.4f} | "
                f"{rr['p95_ms']:.4f} | {rr['max_ms']:.4f} | "
                f"{g['ratio']:.2f}× | ≤ {g['threshold']}× | "
                f"{'✅' if g['pass'] else '❌'} | "
                f"{rc[si_lab + '_rowcount']} | {rc[rr_lab + '_rowcount']} |"
            )
        lines.append("")
        lines.append(f"**Dataset {cfg['label']} verdict: {'PASS' if ds_result['dataset_pass'] else 'FAIL'}**")
        lines.append("")
    return "\n".join(lines)


def _env_meta() -> Dict[str, Any]:
    import platform
    import subprocess

    def _git(*args: str) -> str:
        try:
            out = subprocess.check_output(
                ["git", *args], cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL
            )
            return out.decode("utf-8").strip()
        except Exception:
            return ""

    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "commit_sha": _git("rev-parse", "HEAD"),
        "run_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7a / 7a.5 benchmark")
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "benchmarks" / "results"),
        help="Directory for JSON / MD outputs (default: benchmarks/results)",
    )
    parser.add_argument(
        "--fixture-size",
        type=int,
        default=N_ENTRIES,
        help="Entries per dataset (default: 10000 = Phase 7a baseline ; use 100000 for Phase 7a.5).",
    )
    parser.add_argument(
        "--output-suffix",
        default="",
        help="Filename suffix to distinguish runs (e.g. '_100k' for Phase 7a.5). "
             "Empty suffix preserves Phase 7a filenames.",
    )
    parser.add_argument(
        "--fixture-layout",
        choices=["monolithic", "segmented"],
        default="monolithic",
        help="Disk layout of the shard fixture. 'monolithic' (default) matches "
             "Phase 7a / 7a.5 methodology (raw JSONL). 'segmented' generates the "
             "production layout via Storage.append() for Phase 7a.5-bis.",
    )
    args = parser.parse_args()

    fixture_size = args.fixture_size
    if fixture_size <= 0:
        raise SystemExit("--fixture-size must be positive")
    n_sessions = max(1, fixture_size // ENTRIES_PER_SESSION_TARGET)
    fixture_layout = args.fixture_layout
    # Phase-label inference:
    #   default monolithic + no suffix  → "7a"
    #   monolithic + suffix             → "7a.5"
    #   segmented                       → "7a.5-bis"
    if fixture_layout == "segmented":
        phase_label = "7a.5-bis"
    elif args.output_suffix:
        phase_label = "7a.5"
    else:
        phase_label = "7a"

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Rewrite dataset descriptions to reflect the actual fixture size.
    runtime_datasets: List[Dict[str, Any]] = []
    for base_cfg in (DATASET_A, DATASET_B):
        cfg = dict(base_cfg)
        cfg["description"] = (
            f"{fixture_size:,} entries, {n_sessions:,} sessions, "
            f"{cfg['n_actions']} action_names "
            f"{'Zipf s=' + str(cfg['zipf_s']) if cfg['distribution'] == 'zipf' else 'quasi-uniform'}"
        )
        runtime_datasets.append(cfg)

    # Comparison baseline — Phase 7a.5-bis compares against the Phase 7a.5
    # monolithic 100k results, not against Phase 7a 10k.
    if fixture_layout == "segmented":
        comparison_baseline = "phase_7a_5_action_index_100k_20260419.json"
    elif args.output_suffix:
        comparison_baseline = "phase_7a_action_index_20260419.json"
    else:
        comparison_baseline = None

    results: Dict[str, Any] = {
        **_env_meta(),
        "phase": phase_label,
        "fixture_size": fixture_size,
        "n_entries_per_dataset": fixture_size,
        "n_sessions": n_sessions,
        "time_span_days": TIME_SPAN_DAYS,
        "event_type_pool": EVENT_TYPE_POOL,
        "fixture_layout": fixture_layout,
        "comparison_baseline": comparison_baseline,
        "datasets": [],
    }

    for cfg in runtime_datasets:
        print(f"[bench] running dataset {cfg['label']} ({cfg['description']}) "
              f"layout={fixture_layout}", flush=True)
        t0 = time.monotonic()
        ds_result = bench_dataset(
            cfg,
            fixture_size=fixture_size,
            n_sessions=n_sessions,
            fixture_layout=fixture_layout,
        )
        elapsed = time.monotonic() - t0
        print(
            f"[bench] dataset {cfg['label']} done in {elapsed:.2f}s — "
            f"dataset_pass={ds_result['dataset_pass']}",
            flush=True,
        )
        results["datasets"].append(ds_result)

    overall_pass = all(d["dataset_pass"] for d in results["datasets"])
    results["verdict"] = "PASS" if overall_pass else "FAIL"

    stamp = datetime.utcnow().strftime("%Y%m%d")
    suffix = args.output_suffix
    if fixture_layout == "segmented":
        stem_base = "phase_7a_5_bis_action_index"
    elif suffix:
        stem_base = "phase_7a_5_action_index"
    else:
        stem_base = "phase_7a_action_index"
    json_path = out_dir / f"{stem_base}{suffix}_{stamp}.json"
    md_path = out_dir / f"{stem_base}{suffix}_{stamp}.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(results))

    print(f"[bench] wrote {json_path}")
    print(f"[bench] wrote {md_path}")
    print(f"[bench] overall verdict: {results['verdict']}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
