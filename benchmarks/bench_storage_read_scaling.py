#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADR 0001 Phase N+1B — Storage.read scaling probe.

Black-box micro-benchmark that calls Storage.read(shard, offset=K, limit=N) at
varying K on a fixed-size fixture (100 000 entries) to empirically classify the
observed scaling behaviour, in isolation from RR and from any index layer.

The probe does not import RR, does not create any index, does not consume
SessionIndex. It only talks to dsm.core.storage.Storage.

Usage:
    python3 benchmarks/bench_storage_read_scaling.py [--out DIR]

Outputs:
    benchmarks/results/storage_read_probe_<YYYYMMDD>.json
    benchmarks/results/storage_read_probe_<YYYYMMDD>.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dsm.core.storage import Storage  # noqa: E402
from dsm.core.shard_segments import MAX_EVENTS_PER_SEGMENT  # noqa: E402

# ---------------------------------------------------------------------------
# Probe parameters
# ---------------------------------------------------------------------------

FIXTURE_SIZE = 100_000
SEED = 44
LIMIT_MAIN = 100
OFFSETS = [0, 1_000, 10_000, 50_000, 90_000, 99_900]
RUNS_PER_POINT = 50
WARMUP_RUNS = 5

# Secondary sweep: limit sensitivity at fixed offset.
OFFSET_FOR_LIMIT_SWEEP = 50_000
LIMITS_FOR_LIMIT_SWEEP = [10, 100, 1_000]

SEGMENTED_SHARD_ID = "sessions_seg"
MONOLITHIC_SHARD_ID = "sessions_mono"


# ---------------------------------------------------------------------------
# Fixture generation — deterministic, matches the Entry schema used elsewhere.
# ---------------------------------------------------------------------------

def _make_entry_dict(i: int, t0: datetime, span_seconds: float, rng: random.Random) -> Dict[str, Any]:
    """Produce one entry dict in the canonical on-disk JSONL schema."""
    ts_offset = (i / FIXTURE_SIZE) * span_seconds  # monotonic timestamps
    ts = t0 + timedelta(seconds=ts_offset)
    return {
        "id": f"p_{i:06d}",
        "timestamp": ts.isoformat(),
        "session_id": f"session_{(i // 20):04d}",
        "source": rng.choice(["agent_x", "agent_y", "agent_z"]),
        "content": f"probe entry #{i}",
        "shard": "probe",
        "hash": hashlib.sha256(f"probe_{i}".encode()).hexdigest(),
        "prev_hash": None if i == 0 else hashlib.sha256(f"probe_{i-1}".encode()).hexdigest(),
        "metadata": {"event_type": "tool_call", "action_name": f"action_{i % 30}"},
        "version": "v2.0",
    }


def _generate_entries() -> List[Dict[str, Any]]:
    rng = random.Random(SEED)
    t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    span = timedelta(days=30).total_seconds()
    return [_make_entry_dict(i, t0, span, rng) for i in range(FIXTURE_SIZE)]


def _write_monolithic(entries: List[Dict[str, Any]], data_dir: Path) -> None:
    """Write a single shards/<id>.jsonl file with all entries, oldest-first."""
    (data_dir / "shards").mkdir(parents=True, exist_ok=True)
    (data_dir / "integrity").mkdir(parents=True, exist_ok=True)
    path = data_dir / "shards" / f"{MONOLITHIC_SHARD_ID}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _write_segmented(entries: List[Dict[str, Any]], data_dir: Path) -> int:
    """Write N segment files of MAX_EVENTS_PER_SEGMENT entries under shards/<id>/<id>_NNNN.jsonl.
    Returns the number of segments written. Follows the naming convention of
    ShardSegmentManager so Storage.read dispatches to _read_segmented.
    """
    family_dir = data_dir / "shards" / SEGMENTED_SHARD_ID
    family_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "integrity").mkdir(parents=True, exist_ok=True)

    seg_size = MAX_EVENTS_PER_SEGMENT
    n_segments = (len(entries) + seg_size - 1) // seg_size
    for seg_idx in range(n_segments):
        seg_number = seg_idx + 1
        seg_path = family_dir / f"{SEGMENTED_SHARD_ID}_{seg_number:04d}.jsonl"
        start = seg_idx * seg_size
        end = min(start + seg_size, len(entries))
        with open(seg_path, "w", encoding="utf-8") as f:
            for e in entries[start:end]:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return n_segments


# ---------------------------------------------------------------------------
# Measurement primitives.
# ---------------------------------------------------------------------------

def _time_call(fn: Callable[[], Any]) -> float:
    t0 = time.monotonic()
    fn()
    return time.monotonic() - t0


def _stats(samples_s: List[float]) -> Dict[str, float]:
    ms = sorted(s * 1000.0 for s in samples_s)
    p95_idx = min(len(ms) - 1, int(round(0.95 * len(ms))) - 1)
    return {
        "median_ms": statistics.median(ms),
        "mean_ms": statistics.fmean(ms),
        "p95_ms": ms[max(0, p95_idx)],
        "max_ms": max(ms),
        "min_ms": min(ms),
        "stdev_ms": statistics.pstdev(ms) if len(ms) > 1 else 0.0,
        "n": len(ms),
    }


def _fingerprint_entries(entries) -> str:
    """Stable fingerprint of returned entries (sha256 of concatenated ids in result order)."""
    h = hashlib.sha256()
    for e in entries:
        eid = getattr(e, "id", None)
        if eid is None:
            eid = ""
        h.update(eid.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _measure_point(
    storage: Storage,
    shard_id: str,
    offset: int,
    limit: int,
    runs: int,
    warmup: int,
) -> Dict[str, Any]:
    """
    Warmup then time `runs` calls. Verify entries_returned and fingerprint stability
    across runs. Fingerprint computed on the first timed run; subsequent runs must
    match or the point is flagged unstable.
    """
    # Warmup — not timed.
    for _ in range(warmup):
        storage.read(shard_id, offset=offset, limit=limit)

    samples: List[float] = []
    first_fp: str | None = None
    entries_returned: int | None = None
    fingerprint_stable = True
    fingerprint_divergence_run: int | None = None

    for run_idx in range(runs):
        t0 = time.monotonic()
        result = storage.read(shard_id, offset=offset, limit=limit)
        elapsed = time.monotonic() - t0
        samples.append(elapsed)

        if run_idx == 0:
            first_fp = _fingerprint_entries(result)
            entries_returned = len(result)
        else:
            fp = _fingerprint_entries(result)
            if first_fp is not None and fp != first_fp and fingerprint_stable:
                fingerprint_stable = False
                fingerprint_divergence_run = run_idx

    stats = _stats(samples)
    stats.update({
        "offset": offset,
        "limit": limit,
        "entries_returned": entries_returned,
        "fingerprint_first_run": first_fp,
        "fingerprint_stable": fingerprint_stable,
        "fingerprint_divergence_run": fingerprint_divergence_run,
    })
    return stats


# ---------------------------------------------------------------------------
# Per-mode orchestration.
# ---------------------------------------------------------------------------

def _run_mode(
    mode_label: str,
    shard_id: str,
    fixture_writer: Callable[[List[Dict[str, Any]], Path], Any],
) -> Dict[str, Any]:
    entries = _generate_entries()

    tmp = Path(tempfile.mkdtemp(prefix=f"probe_{mode_label}_"))
    try:
        extra = fixture_writer(entries, tmp)
        fixture_meta: Dict[str, Any] = {"tmp_dir": str(tmp)}
        if mode_label == "segmented":
            fixture_meta["segments_written"] = extra

        storage = Storage(data_dir=str(tmp))

        # Main sweep — offset varies, limit fixed.
        main_points = []
        for offset in OFFSETS:
            main_points.append(
                _measure_point(
                    storage=storage,
                    shard_id=shard_id,
                    offset=offset,
                    limit=LIMIT_MAIN,
                    runs=RUNS_PER_POINT,
                    warmup=WARMUP_RUNS,
                )
            )

        # Secondary sweep — offset fixed at 50 000, limit varies.
        limit_sweep_points = []
        for lim in LIMITS_FOR_LIMIT_SWEEP:
            limit_sweep_points.append(
                _measure_point(
                    storage=storage,
                    shard_id=shard_id,
                    offset=OFFSET_FOR_LIMIT_SWEEP,
                    limit=lim,
                    runs=RUNS_PER_POINT,
                    warmup=WARMUP_RUNS,
                )
            )

        # Slope analysis — time per offset skipped, relative to offset=0.
        baseline_ms = main_points[0]["median_ms"]
        slope_table: Dict[str, Dict[str, Any]] = {}
        for pt in main_points[1:]:
            k = pt["offset"]
            delta_ms = pt["median_ms"] - baseline_ms
            slope_table[f"K={k}"] = {
                "offset": k,
                "delta_ms": delta_ms,
                "us_per_offset_skipped": (delta_ms * 1000.0) / k if k > 0 else None,
            }

        # Classification rule:
        # - All µs/K within ±20 % of the mean → flat.
        # - µs/K non-zero, roughly proportional to K → linear-like (constant slope).
        # - µs/K grows with K → super-linear-like.
        ratios = [v["us_per_offset_skipped"] for v in slope_table.values() if v["us_per_offset_skipped"] is not None]
        if not ratios or all(r < 0.1 for r in ratios):
            # All µs/K effectively zero → flat.
            growth_pattern = "flat"
            constant = True
        else:
            mean_ratio = statistics.fmean(ratios)
            spread = max(ratios) - min(ratios)
            rel_spread = spread / mean_ratio if mean_ratio > 0 else float("inf")
            # Is the ratio monotonically increasing with K? (super-linear signature)
            ks_sorted = sorted(slope_table.keys(), key=lambda s: slope_table[s]["offset"])
            ratios_sorted = [slope_table[k]["us_per_offset_skipped"] for k in ks_sorted]
            monotone_increasing = all(
                ratios_sorted[i + 1] > ratios_sorted[i] * 1.2 for i in range(len(ratios_sorted) - 1)
            )
            if rel_spread <= 0.20:
                growth_pattern = "linear-like"
                constant = True
            elif monotone_increasing:
                growth_pattern = "super-linear-like"
                constant = False
            else:
                growth_pattern = "other / unclear"
                constant = False

        return {
            "mode": mode_label,
            "shard_id": shard_id,
            "fixture": fixture_meta,
            "points": main_points,
            "limit_sensitivity_at_offset_50k": limit_sweep_points,
            "slope_analysis": {
                "baseline_median_ms_at_offset_0": baseline_ms,
                "per_offset_ratios_us": slope_table,
                "growth_pattern": growth_pattern,
                "constant": constant,
            },
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Markdown rendering.
# ---------------------------------------------------------------------------

def _render_md(results: Dict[str, Any]) -> str:
    out: List[str] = []
    out.append("# Storage.read scaling probe — ADR 0001 Phase N+1B")
    out.append("")
    out.append(f"- Date (UTC): {results['run_utc']}")
    out.append(f"- Branch: {results['branch']}")
    out.append(f"- Commit SHA: {results['commit_sha']}")
    out.append(f"- Python: {results['python']}")
    out.append(f"- Platform: {results['platform']}")
    out.append(f"- Fixture size: {results['fixture_size']:,} entries  ·  seed: {results['seed']}")
    out.append(f"- Runs per point: {results['runs_per_point']} timed + {results['warmup_runs']} warmup")
    out.append("")

    for mode in ("segmented", "monolithic"):
        mode_result = results["modes"][mode]
        out.append(f"## Mode {mode}")
        out.append("")
        fm = mode_result["fixture"]
        if mode == "segmented":
            out.append(f"- Segments written: {fm.get('segments_written')}")
        out.append("")
        out.append("### Main sweep — varying offset, limit=100")
        out.append("")
        out.append("| Offset K | median (ms) | p95 (ms) | max (ms) | stdev (ms) | entries returned | fingerprint stable |")
        out.append("|---:|---:|---:|---:|---:|---:|:-:|")
        for pt in mode_result["points"]:
            stable = "✅" if pt["fingerprint_stable"] else f"❌ diverged at run {pt['fingerprint_divergence_run']}"
            out.append(
                f"| {pt['offset']:,} | {pt['median_ms']:.4f} | {pt['p95_ms']:.4f} | "
                f"{pt['max_ms']:.4f} | {pt['stdev_ms']:.4f} | {pt['entries_returned']} | {stable} |"
            )
        out.append("")

        sa = mode_result["slope_analysis"]
        out.append("### Slope analysis")
        out.append("")
        out.append(f"- Baseline at offset=0 : {sa['baseline_median_ms_at_offset_0']:.4f} ms")
        out.append("")
        out.append("| Offset K | Δ vs K=0 (ms) | Δ / K (µs per offset skipped) |")
        out.append("|---:|---:|---:|")
        per = sa["per_offset_ratios_us"]
        for key in sorted(per.keys(), key=lambda s: per[s]["offset"]):
            e = per[key]
            us = e["us_per_offset_skipped"]
            us_str = f"{us:.4f}" if us is not None else "—"
            out.append(f"| {e['offset']:,} | {e['delta_ms']:.4f} | {us_str} |")
        out.append("")
        out.append(f"- Growth pattern : **{sa['growth_pattern']}**")
        out.append(f"- Empirical classification : `{sa['growth_pattern']}`")
        out.append("")

        out.append("### Limit sensitivity sweep — fixed offset=50 000")
        out.append("")
        out.append("| Limit | median (ms) | p95 (ms) | max (ms) | entries returned |")
        out.append("|---:|---:|---:|---:|---:|")
        for pt in mode_result["limit_sensitivity_at_offset_50k"]:
            out.append(
                f"| {pt['limit']:,} | {pt['median_ms']:.4f} | {pt['p95_ms']:.4f} | "
                f"{pt['max_ms']:.4f} | {pt['entries_returned']} |"
            )
        out.append("")

    # Cross-mode comparison
    out.append("## Cross-mode comparison (main sweep)")
    out.append("")
    out.append("| Offset K | segmented median (ms) | monolithic median (ms) | Ratio mono / seg |")
    out.append("|---:|---:|---:|---:|")
    seg_pts = {p["offset"]: p for p in results["modes"]["segmented"]["points"]}
    mono_pts = {p["offset"]: p for p in results["modes"]["monolithic"]["points"]}
    for k in sorted(seg_pts.keys()):
        s = seg_pts[k]["median_ms"]
        m = mono_pts[k]["median_ms"]
        ratio = m / s if s > 0 else float("inf")
        out.append(f"| {k:,} | {s:.4f} | {m:.4f} | {ratio:.2f}× |")
    out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Entry-point.
# ---------------------------------------------------------------------------

def _env_meta() -> Dict[str, Any]:
    import platform

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
    parser = argparse.ArgumentParser(description="Storage.read scaling probe (ADR 0001 N+1B)")
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "benchmarks" / "results"),
        help="Directory for JSON / MD outputs (default: benchmarks/results)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[probe] generating fixtures ({FIXTURE_SIZE:,} entries, seed={SEED})", flush=True)
    print(f"[probe] max events per segment (from kernel): {MAX_EVENTS_PER_SEGMENT:,}", flush=True)

    results: Dict[str, Any] = {
        **_env_meta(),
        "phase": "N+1B",
        "fixture_size": FIXTURE_SIZE,
        "limit_main_sweep": LIMIT_MAIN,
        "offsets_main_sweep": OFFSETS,
        "offset_for_limit_sweep": OFFSET_FOR_LIMIT_SWEEP,
        "limits_for_limit_sweep": LIMITS_FOR_LIMIT_SWEEP,
        "seed": SEED,
        "runs_per_point": RUNS_PER_POINT,
        "warmup_runs": WARMUP_RUNS,
        "modes": {},
    }

    for mode_label, shard_id, writer in (
        ("segmented", SEGMENTED_SHARD_ID, _write_segmented),
        ("monolithic", MONOLITHIC_SHARD_ID, _write_monolithic),
    ):
        print(f"[probe] running mode={mode_label} shard_id={shard_id}", flush=True)
        t0 = time.monotonic()
        results["modes"][mode_label] = _run_mode(mode_label, shard_id, writer)
        elapsed = time.monotonic() - t0
        print(f"[probe] mode={mode_label} done in {elapsed:.1f}s", flush=True)

    stamp = datetime.utcnow().strftime("%Y%m%d")
    json_path = out_dir / f"storage_read_probe_{stamp}.json"
    md_path = out_dir / f"storage_read_probe_{stamp}.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_render_md(results))

    print(f"[probe] wrote {json_path}")
    print(f"[probe] wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
