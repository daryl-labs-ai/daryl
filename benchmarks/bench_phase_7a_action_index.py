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
from typing import Any, Callable, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dsm.core.storage import Storage  # noqa: E402
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


def _build_dataset(dataset_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build dataset in-memory: returns dict with `entries` (list of JSON-ready dicts),
    `action_names` (full list), `top_action`, `rare_action`, `session_ids`, etc.
    """
    rng = random.Random(dataset_cfg["seed"])
    n_actions = dataset_cfg["n_actions"]

    action_names = [f"action_{i:04d}" for i in range(n_actions)]
    weights = _action_weights(n_actions, dataset_cfg["distribution"], dataset_cfg["zipf_s"])
    event_types = [et for et, _ in EVENT_TYPE_POOL]
    event_weights = [w for _, w in EVENT_TYPE_POOL]

    session_ids = [f"session_{i:04d}" for i in range(N_SESSIONS)]
    agents = ["agent_alpha", "agent_beta", "agent_gamma"]
    t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    span = timedelta(days=TIME_SPAN_DAYS).total_seconds()

    entries: List[Dict[str, Any]] = []
    action_counts: Dict[str, int] = {}

    for i in range(N_ENTRIES):
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
) -> Dict[str, Any]:
    """
    Run a build N times on fresh temp dirs; return stats in seconds.
    Each run wipes the temp dir, re-materialises the JSONL, then calls the factory
    which returns the callable to time.
    """
    samples: List[float] = []
    for _ in range(n_runs):
        tmp = Path(tempfile.mkdtemp(prefix="bench_phase7a_build_"))
        try:
            _materialize_dataset(entries, tmp)
            call = build_fn_factory(tmp)
            samples.append(_time_call(call))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return _stats(samples, label)


def _run_query_series(
    label: str,
    call: Callable[[], Any],
    warmup: int = 5,
    n_runs: int = 100,
) -> Dict[str, Any]:
    """Run a query call `warmup + n_runs` times; return stats for the last n_runs."""
    for _ in range(warmup):
        call()
    samples: List[float] = []
    for _ in range(n_runs):
        samples.append(_time_call(call))
    return _stats(samples, label)


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

def _prepare_query_env(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build fresh indexes on disk and return resolved query callables for all 4 variants."""
    tmp = Path(tempfile.mkdtemp(prefix="bench_phase7a_query_"))
    _materialize_dataset(entries, tmp)

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

def bench_dataset(dataset_cfg: Dict[str, Any]) -> Dict[str, Any]:
    ds = _build_dataset(dataset_cfg)
    entries = ds["entries"]

    # -- Build phase -----------------------------------------------------
    si_build = _run_build_series(
        "SessionIndex_build",
        entries,
        lambda tmp: _session_index_build_factory(tmp),
        n_runs=5,
    )
    rr_baseline = _run_build_series(
        "RR_baseline_build",
        entries,
        lambda tmp: _rr_build_factory(tmp, enable_action_index=False),
        n_runs=5,
    )
    rr_with_action = _run_build_series(
        "RR_with_action_build",
        entries,
        lambda tmp: _rr_build_factory(tmp, enable_action_index=True),
        n_runs=5,
    )
    delta_build_ms = rr_with_action["median_ms"] - rr_baseline["median_ms"]

    # -- Query phase -----------------------------------------------------
    env = _prepare_query_env(entries)
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
            query_results[label] = _run_query_series(label, call, warmup=5, n_runs=100)

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

    dataset_pass = build_gate_pass and all(g["pass"] for g in query_gates.values())

    return {
        "cfg": dataset_cfg,
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
        },
        "queries": query_results,
        "query_row_counts": hit_counts,
        "query_gates": query_gates,
        "dataset_pass": dataset_pass,
    }


def render_markdown(results: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Phase 7a benchmark — RR action_name index vs SessionIndex")
    lines.append("")
    lines.append(f"- Run timestamp (UTC): {results['run_utc']}")
    lines.append(f"- Prototype branch: {results['branch']}")
    lines.append(f"- Commit SHA: {results['commit_sha']}")
    lines.append(f"- Python: {results['python']}")
    lines.append(f"- Platform: {results['platform']}")
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
    parser = argparse.ArgumentParser(description="Phase 7a benchmark")
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "benchmarks" / "results"),
        help="Directory for JSON / MD outputs (default: benchmarks/results)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Any] = {
        **_env_meta(),
        "n_entries_per_dataset": N_ENTRIES,
        "n_sessions": N_SESSIONS,
        "time_span_days": TIME_SPAN_DAYS,
        "event_type_pool": EVENT_TYPE_POOL,
        "datasets": [],
    }

    for cfg in (DATASET_A, DATASET_B):
        print(f"[bench] running dataset {cfg['label']} ({cfg['description']})", flush=True)
        t0 = time.monotonic()
        ds_result = bench_dataset(cfg)
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
    json_path = out_dir / f"phase_7a_action_index_{stamp}.json"
    md_path = out_dir / f"phase_7a_action_index_{stamp}.md"
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
