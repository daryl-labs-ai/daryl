"""B5 smoke orchestration + CLI — paired A/B′/B on ONE case, ONE seed.

Dry-run by default (zero network, zero spend). Live mode requires the FULL
chain: config ``live_execution_authorized=true`` + explicit authorized budget
+ the CLI flag ``--i-authorize-live-spend`` + the API-key env var present (by
NAME). Anything less refuses before any socket is opened.

Usage (from the repo root):

    PYTHONPATH=. .venv/bin/python -m benchmarks.swarm.harness.smoke \
        --config benchmarks/swarm/B5_SMOKE_CONFIG.json \
        --out benchmarks/swarm/runs/b5-smoke-<id> \
        [--live --i-authorize-live-spend]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .campaign import CONDITIONS
from .cases import load_cases
from .live import (
    BudgetGuard,
    CostEstimate,
    LiveCallError,
    Mode,
    SmokeConfig,
    build_provider,
    estimate_smoke_cost,
)
from .metrics import behavioral_parity, run_validity
from .parity import DEFAULT_THRESHOLDS, is_confounded
from .runner import FIXED_STARTED_AT, RunResult, run_case


class SmokeProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    temperature: float
    request_seed: int | None
    seed_honored_observed: bool | None    # from transport results, live only
    api_key_env_name: str                 # NAME only — never the value
    case_id: str
    seed: int
    git_sha: str
    started_at: str
    mode: str
    live_execution_authorized: bool
    authorized_budget_usd: float | None
    condition_order: tuple[str, ...]


class SmokeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_version: str = "swarm-smoke-report.v0.1"
    provenance: SmokeProvenance
    estimate: CostEstimate
    spend: dict
    validity: dict[str, dict]
    stratum: dict[str, str]               # pair A-vs-X -> eligible|confounded|invalid
    parity_reasons: dict[str, tuple[str, ...]]
    caps: dict
    aborted: str | None = None            # STOP reason if the smoke halted


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def run_smoke(
    config: SmokeConfig,
    out_root: Path,
    *,
    mode: Mode = "dry_run",
    started_at: str | None = None,
) -> SmokeReport:
    case = next(c for c in load_cases() if c.case_id == config.case_id)
    guard = BudgetGuard(config.caps, config.price)
    estimate = estimate_smoke_cost(config, case)
    started = started_at or (
        FIXED_STARTED_AT if mode == "dry_run" else
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    )
    out_root.mkdir(parents=True, exist_ok=True)

    results: dict[str, RunResult] = {}
    aborted: str | None = None
    seed_honored: bool | None = None
    for condition in config.condition_order:
        provider = build_provider(config, guard, mode)  # authorization gate per condition
        try:
            results[condition] = run_case(
                case, condition, out_root / condition,
                seed=config.seed, provider=provider, started_at=started,
                starting_commit=_git_sha()[:9],
            )
        except LiveCallError as exc:
            aborted = f"STOP at condition {condition}: {exc}"
            break
        except Exception as exc:  # incl. BudgetExceeded — refuse-before semantics
            aborted = f"STOP at condition {condition}: {type(exc).__name__}: {exc}"
            break
        honored = [r.provider_seed_honored for r in provider.results
                   if r.provider_seed_honored is not None]
        if honored:
            seed_honored = all(honored)

    validity = {c: run_validity(r).model_dump() for c, r in results.items()}
    stratum: dict[str, str] = {}
    reasons: dict[str, tuple[str, ...]] = {}
    if "A" not in results:
        for cond in ("Bprime", "B"):
            stratum[cond] = "invalid"
            reasons[cond] = ("control run missing (smoke aborted)",)
    else:
        for cond in ("Bprime", "B"):
            if cond not in results:
                stratum[cond] = "invalid"
                reasons[cond] = ("run missing (smoke aborted)",)
                continue
            if not validity[cond]["valid"]:
                stratum[cond] = "invalid"
                reasons[cond] = (validity[cond]["reason"],)
                continue
            parity = behavioral_parity(results["A"], results[cond])
            confounded, why = is_confounded(parity, DEFAULT_THRESHOLDS)
            stratum[cond] = "confounded" if confounded else "eligible"
            reasons[cond] = why

    report = SmokeReport(
        provenance=SmokeProvenance(
            provider=config.provider,
            model=config.model,
            temperature=config.temperature,
            request_seed=config.request_seed,
            seed_honored_observed=seed_honored,
            api_key_env_name=config.api_key_env,
            case_id=config.case_id,
            seed=config.seed,
            git_sha=_git_sha(),
            started_at=started,
            mode=mode,
            live_execution_authorized=config.live_execution_authorized,
            authorized_budget_usd=config.authorized_budget_usd,
            condition_order=config.condition_order,
        ),
        estimate=estimate,
        spend=guard.spend_summary(),
        validity=validity,
        stratum=stratum,
        parity_reasons=reasons,
        caps=config.caps.model_dump(),
        aborted=aborted,
    )
    (out_root / "smoke_report.json").write_text(report.model_dump_json(indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DSM Swarm B5 smoke (dry-run by default)")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--i-authorize-live-spend", action="store_true",
                        dest="authorize_flag")
    args = parser.parse_args(argv)

    config = SmokeConfig(**json.loads(Path(args.config).read_text()))
    mode: Mode = "dry_run"
    if args.live:
        if not args.authorize_flag:
            print("REFUSED: --live requires --i-authorize-live-spend", file=sys.stderr)
            return 2
        if not config.live_execution_authorized:
            print("REFUSED: config.live_execution_authorized is false", file=sys.stderr)
            return 2
        mode = "live"

    report = run_smoke(config, Path(args.out), mode=mode)
    print(json.dumps({
        "mode": mode,
        "aborted": report.aborted,
        "spend": report.spend,
        "stratum": report.stratum,
    }, indent=2))
    return 0 if report.aborted is None else 1


if __name__ == "__main__":
    sys.exit(main())
