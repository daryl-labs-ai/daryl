"""Mechanical campaign (B4) — 12 cases × A/B′/B, deterministic, zero spend.

Runs every case under the three conditions with the FakeProvider, evaluates
families A/C/D/E per case, applies the validity and parity gates, and writes a
descriptive report. The PER-CASE table is the primary output: with 12
scenarios, aggregates are secondary, labelled descriptive, and never mask a
case. No live claim, no truth claim, no significance claim.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .cases import load_cases
from .metrics import CaseEvaluation, evaluate_case
from .runner import run_case

CONDITIONS = ("A", "Bprime", "B")


class CampaignReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_version: str = "swarm-bench-campaign.v0.1"
    regime: str = "deterministic (FakeProvider) — instrument validation, no live claim"
    n_cases: int
    evaluations: tuple[CaseEvaluation, ...]
    # descriptive aggregates — SECONDARY to the per-case table
    aggregates: dict[str, float | int]


def _aggregates(evaluations: tuple[CaseEvaluation, ...]) -> dict[str, float | int]:
    n = len(evaluations)
    total_expected = sum(len(e.expected_mechanical) for e in evaluations)
    return {
        "cases": n,
        "runs_valid": sum(
            1 for e in evaluations for v in e.validity.values() if v.valid
        ),
        "runs_total": 3 * n,
        "pairs_eligible": sum(
            1 for e in evaluations for s in e.stratum.values() if s == "eligible"
        ),
        "pairs_confounded": sum(
            1 for e in evaluations for s in e.stratum.values() if s == "confounded"
        ),
        "expected_mechanical_faults": total_expected,
        "false_negatives_b": sum(len(e.false_negatives_b) for e in evaluations),
        "false_positives_b": sum(len(e.false_positives_b) for e in evaluations),
        "false_negatives_a": sum(len(e.false_negatives_a) for e in evaluations),
        "false_positives_a": sum(len(e.false_positives_a) for e in evaluations),
        "total_records_written_b": sum(
            e.overhead["B"].records_written for e in evaluations
        ),
        "total_tokens_in_delta_b": sum(
            e.overhead["B"].tokens_in_delta for e in evaluations
        ),
        "total_tokens_in_delta_bprime": sum(
            e.overhead["Bprime"].tokens_in_delta for e in evaluations
        ),
    }


def run_campaign(out_root: Path) -> CampaignReport:
    evaluations: list[CaseEvaluation] = []
    for case in load_cases():
        results = {
            cond: run_case(case, cond, out_root / case.case_id / cond)
            for cond in CONDITIONS
        }
        evaluations.append(evaluate_case(case, results))
    report = CampaignReport(
        n_cases=len(evaluations),
        evaluations=tuple(evaluations),
        aggregates=_aggregates(tuple(evaluations)),
    )
    (out_root / "campaign_report.json").write_text(report.model_dump_json(indent=2) + "\n")
    (out_root / "REPORT.md").write_text(render_report_md(report))
    return report


def _fmt(items: tuple[str, ...]) -> str:
    return ", ".join(items) if items else "—"


def render_report_md(report: CampaignReport) -> str:
    lines: list[str] = []
    a = lines.append
    a("# DSM Swarm Benchmark — Mechanical Campaign Report (deterministic regime)")
    a("")
    a("**What this is:** instrument validation on 12 planted-fault scenarios, "
      "FakeProvider, zero cost. **What this is not:** a live result, a truth "
      "claim, or a significance claim.")
    a("")
    a("## Information tiers (read every metric through these)")
    a("")
    a("1. **available** — declared in the condition's artifacts;")
    a("2. **reconstructed** — mechanically derived (replay for B/B′; the "
      "symmetric rubric over the common event log for A);")
    a("3. **oracle-correct** — matches the planted-fault oracle.")
    a("")
    a("Reconstructing that a reviewer claimed a check proves neither that the "
      "check ran nor that its result is true. `verify == OK` is a run "
      "**validity condition**, never a performance score: an invalid run is "
      "excluded, not scored low.")
    a("")
    a("## Per-case results (primary output)")
    a("")
    a("| case | valid A/B′/B | expected (oracle) | observed B (replay) | FP/FN B "
      "| detected A (rubric) | FP/FN A | claimed gap | stratum B′/B | Δtok_in B′/B | records B |")
    a("|---|---|---|---|---|---|---|---|---|---|---|")
    for e in report.evaluations:
        valid = "/".join("✓" if e.validity[c].valid else "✗" for c in CONDITIONS)
        gap = e.family_c["A"].claimed_vs_observable_gap
        a(
            f"| {e.case_id} | {valid} | {_fmt(e.expected_mechanical)} "
            f"| {_fmt(e.observed_b_replay)} "
            f"| {len(e.false_positives_b)}/{len(e.false_negatives_b)} "
            f"| {_fmt(e.detected_a_rubric)} "
            f"| {len(e.false_positives_a)}/{len(e.false_negatives_a)} "
            f"| {'—' if gap is None else f'{gap:.2f}'} "
            f"| {e.stratum['Bprime']}/{e.stratum['B']} "
            f"| {e.overhead['Bprime'].tokens_in_delta}/{e.overhead['B'].tokens_in_delta} "
            f"| {e.overhead['B'].records_written} |"
        )
    a("")
    a("## Aggregates (descriptive only — the table above is authoritative)")
    a("")
    for key, value in report.aggregates.items():
        a(f"- {key}: {value}")
    a("")
    a("## Honest finding (deterministic regime)")
    a("")
    a("In this regime the common event log carries the same declared payloads "
      "in every condition, so A's rubric reconstruction and B's replay see the "
      "same information; equal detection here validates the instrument and the "
      "measurement symmetry — it does NOT measure DSM's value on degraded or "
      "unstructured logs, which is what the live phases examine. B's overhead "
      "(grounding-block tokens, records, shard bytes) is real and reported; "
      "B′'s token overhead is zero by construction (no prompt channel).")
    a("")
    return "\n".join(lines)
