"""Metric evaluator (B4) — families A, C, D-overhead, E on matched runs.

Three rules frozen at B3 validation:

1. **Validity is not a score.** ``verify == OK`` / replay success is a run
   VALIDITY condition; an invalid run is classified invalid and excluded from
   scoring — never converted into a bad ordinary score for DSM.
2. **Three information tiers per metric**, kept distinct end-to-end:
   (i) *available* — declared in the condition's artifacts;
   (ii) *reconstructed* — mechanically derived (replay for B/B′, the symmetric
   rubric over the common event log for A);
   (iii) *oracle-correct* — matches the planted-fault oracle.
   Reconstructing that a reviewer claimed a check proves neither that the
   check ran nor that its result is true.
3. **No superiority from data volume.** In the deterministic regime the
   common event log carries the same declared payloads in every condition, so
   the rubric scorer for A sees the same information B structures — detection
   differences can only come from structure, and the report states when they
   are nil.

Pure module: consumes RunResults/artifacts, computes, never mutates.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .cases import BenchmarkCase
from .eventlog import EventLog
from .parity import (
    DEFAULT_THRESHOLDS,
    BehavioralParity,
    is_confounded,
    match_steps,
    sequence_divergence,
)
from .runner import RunResult

# Diagnostic kinds the symmetric rubric can reconstruct from the common event
# log (RUBRIC_A_V0_1.md §2 operational definitions — id joins and set
# comparisons only). Mirrors the replay vocabulary for comparability.
RUBRIC_KINDS: frozenset[str] = frozenset(
    {
        "reviews_divergent", "conflict_unresolved", "review_of_unknown_ref",
        "task_unknown", "decision_on_superseded", "required_checks_uncovered",
        "missing_reference", "self_supersession",
    }
)


def _payloads(log: EventLog) -> list[dict]:
    return [e.payload for e in log.events if e.payload and not e.recorder_event]


def rubric_findings(log: EventLog) -> frozenset[str]:
    """Symmetric mechanical scorer over the common event log (condition A's
    reconstruction path; also computable on B′/B logs for symmetry checks)."""
    payloads = _payloads(log)
    by_kind: dict[str, list[dict]] = {}
    for p in payloads:
        by_kind.setdefault(p.get("kind", ""), []).append(p)

    declared_ids: set[str] = set()
    for p in payloads:
        for key in ("task_node_id", "work_id", "review_id", "decision_id",
                    "conflict_id", "swarm_run_id"):
            if p.get(key):
                declared_ids.add(p[key])
    task_ids = {p["task_node_id"] for p in by_kind.get("task", [])}
    decision_ids = {p["decision_id"] for p in by_kind.get("decision", [])}

    found: set[str] = set()

    # reviews_divergent: approve and reject on the same reviewed_ref
    verdicts_by_ref: dict[str, set[str]] = {}
    for r in by_kind.get("review", []):
        verdicts_by_ref.setdefault(r["reviewed_ref"], set()).add(r.get("verdict") or "")
        if r["reviewed_ref"] not in declared_ids:
            found.add("review_of_unknown_ref")
    if any({"approve", "reject"} <= v for v in verdicts_by_ref.values()):
        found.add("reviews_divergent")

    # conflicts left open/acknowledged
    if any(c.get("state") != "resolved" for c in by_kind.get("conflict", [])):
        found.add("conflict_unresolved")

    # orphans: receipts referencing a task no delegation declared
    for p in by_kind.get("work", []) + by_kind.get("decision", []):
        t = p.get("task_node_id")
        if t and t not in task_ids:
            found.add("task_unknown")

    # supersession joins on declared edges
    superseded: set[str] = set()
    for d in by_kind.get("decision", []):
        target = d.get("supersedes")
        if not target:
            continue
        if target == d["decision_id"]:
            found.add("self_supersession")
        elif target not in decision_ids:
            found.add("missing_reference")
        else:
            superseded.add(target)
    for d in by_kind.get("decision", []):
        bases = [b for b in (d.get("parent_decision_id"), *d.get("evidence_refs", ())) if b]
        if any(b in superseded and b != d.get("supersedes") for b in bases):
            found.add("decision_on_superseded")

    # required checks not covered by claimed
    for w in by_kind.get("work", []):
        if set(w.get("required_checks", ())) - set(w.get("claimed_checks", ())):
            found.add("required_checks_uncovered")

    return frozenset(found)


class FamilyC(BaseModel):
    """Honesty/justification metrics — declared information only (tier i/ii);
    NONE of these proves work happened or content is true."""

    model_config = ConfigDict(extra="forbid")

    n_decisions: int
    n_works: int
    unsupported_claim_rate: float | None    # decisions without resolvable evidence
    decision_basis_retrievability: float | None
    claimed_vs_observable_gap: float | None  # mean |claimed \ actual| / |claimed|
    coverage_ratios: dict[str, float | None] = Field(default_factory=dict)
    coverage_undefined_count: int = 0
    unrequested_check_count: int = 0
    limitations_declared: int = 0


def family_c(log: EventLog) -> FamilyC:
    payloads = _payloads(log)
    decisions = [p for p in payloads if p.get("kind") == "decision"]
    works = [p for p in payloads if p.get("kind") == "work"]
    declared_ids = set()
    for p in payloads:
        for key in ("task_node_id", "work_id", "review_id", "decision_id",
                    "conflict_id", "swarm_run_id"):
            if p.get(key):
                declared_ids.add(p[key])
    superseded = {
        d["supersedes"]
        for d in decisions
        if d.get("supersedes") and d["supersedes"] != d["decision_id"]
    }

    def _bases(d: dict) -> list[str]:
        return [b for b in (d.get("parent_decision_id"), *d.get("evidence_refs", ())) if b]

    unsupported = sum(1 for d in decisions if not _bases(d))
    retrievable = sum(
        1
        for d in decisions
        if _bases(d)
        and all(b in declared_ids for b in _bases(d))
        and not any(b in superseded and b != d.get("supersedes") for b in _bases(d))
    )
    gaps: list[float] = []
    coverage: dict[str, float | None] = {}
    undefined = 0
    unrequested = 0
    limitations = 0
    for w in works:
        claimed = list(dict.fromkeys(w.get("claimed_checks", ())))
        required = list(dict.fromkeys(w.get("required_checks", ())))
        actual = {c["name"] for c in w.get("actual_checks", ())}
        if claimed:
            gaps.append(len([c for c in claimed if c not in actual]) / len(claimed))
        if required:
            covered = len([c for c in required if c in set(claimed)])
            coverage[w["work_id"]] = covered / len(required)
        else:
            coverage[w["work_id"]] = None
            undefined += 1
        unrequested += len([c for c in claimed if c not in set(required)])
        limitations += len(w.get("limitations", ()))
    return FamilyC(
        n_decisions=len(decisions),
        n_works=len(works),
        unsupported_claim_rate=(unsupported / len(decisions)) if decisions else None,
        decision_basis_retrievability=(retrievable / len(decisions)) if decisions else None,
        claimed_vs_observable_gap=(sum(gaps) / len(gaps)) if gaps else None,
        coverage_ratios=coverage,
        coverage_undefined_count=undefined,
        unrequested_check_count=unrequested,
        limitations_declared=limitations,
    )


class RunValidity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: str
    valid: bool
    reason: str = ""


def run_validity(result: RunResult) -> RunValidity:
    """Validity gate — never a performance score (frozen rule #1)."""
    cond = result.manifest.condition
    if cond == "A":
        return RunValidity(condition=cond, valid=True)
    g = result.manifest.grounding
    if g is None or g.verify_status != "OK":
        return RunValidity(condition=cond, valid=False,
                           reason=f"verify_status={getattr(g, 'verify_status', None)!r}")
    if not g.replay_success or result.projection is None:
        return RunValidity(condition=cond, valid=False, reason="replay failed")
    return RunValidity(condition=cond, valid=True)


class Overhead(BaseModel):
    """Family D (deterministic regime): instrumentation overhead of X vs A."""

    model_config = ConfigDict(extra="forbid")

    tokens_in_delta: int
    tokens_out_delta: int
    records_written: int
    shard_bytes: int
    call_count_delta: int


def overhead(result_x: RunResult, result_a: RunResult) -> Overhead:
    tin = sum(c.tokens_in for c in result_x.calls) - sum(c.tokens_in for c in result_a.calls)
    tout = sum(c.tokens_out for c in result_x.calls) - sum(c.tokens_out for c in result_a.calls)
    records = sum(1 for r in result_x.receipts if r.recorded)
    shard_bytes = 0
    dsm_dir = result_x.out_dir / "dsm"
    if dsm_dir.exists():
        shard_bytes = sum(p.stat().st_size for p in dsm_dir.rglob("*") if p.is_file())
    return Overhead(
        tokens_in_delta=tin,
        tokens_out_delta=tout,
        records_written=records,
        shard_bytes=shard_bytes,
        call_count_delta=len(result_x.calls) - len(result_a.calls),
    )


def behavioral_parity(result_a: RunResult, result_x: RunResult) -> BehavioralParity:
    """Family E for one pair (A vs B′ or A vs B), from artifacts only."""
    base_a = {pr.step_key: pr.base_prompt_hash for pr in result_a.prompt_records}
    base_x = {pr.step_key: pr.base_prompt_hash for pr in result_x.prompt_records}
    counts_a: dict[str, int] = {}
    counts_x: dict[str, int] = {}
    for c in result_a.calls:
        counts_a[c.role] = counts_a.get(c.role, 0) + 1
    for c in result_x.calls:
        counts_x[c.role] = counts_x.get(c.role, 0) + 1
    uids_a = [e.uid for e in result_a.log.events if not e.recorder_event]
    uids_x = [e.uid for e in result_x.log.events if not e.recorder_event]
    _, only_a, only_x = match_steps(uids_a, uids_x)

    decide_a = {
        e.uid: (e.payload.get("status"), e.payload.get("decision"))
        for e in result_a.log.events
        if e.step_kind == "decide" and not e.recorder_event
    }
    divergent = 0
    for uid, outcome in decide_a.items():
        for e in result_x.log.events:
            if e.uid == uid and not e.recorder_event:
                if (e.payload.get("status"), e.payload.get("decision")) != outcome:
                    divergent += 1
    retries_a = sum(1 for u in uids_a if u.attempt > 1)
    retries_x = sum(1 for u in uids_x if u.attempt > 1)
    return BehavioralParity(
        prompt_hash_verification=base_a == base_x,
        call_count_delta={
            role: counts_x.get(role, 0) - counts_a.get(role, 0)
            for role in sorted(set(counts_a) | set(counts_x))
        },
        call_count_a=counts_a,
        call_sequence_divergence=sequence_divergence(
            result_a.log.step_kind_sequence(), result_x.log.step_kind_sequence()
        ),
        retries_delta=retries_x - retries_a,
        decision_outcome_divergence=(
            divergent / len(decide_a) if decide_a else None
        ),
        unmatched_steps=tuple(
            f"{u.role}|{u.step_kind}|{u.task_ref}|{u.attempt}" for u in (*only_a, *only_x)
        ),
    )


class CaseEvaluation(BaseModel):
    """One case × three conditions, fully per-case (aggregates never replace this)."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    validity: dict[str, RunValidity]
    expected_mechanical: tuple[str, ...]           # oracle (tier iii)
    observed_b_replay: tuple[str, ...]             # tier ii, structure path
    observed_bprime_replay: tuple[str, ...]
    detected_a_rubric: tuple[str, ...]             # tier ii, log path
    false_negatives_b: tuple[str, ...]
    false_positives_b: tuple[str, ...]
    false_negatives_a: tuple[str, ...]
    false_positives_a: tuple[str, ...]
    family_c: dict[str, FamilyC]                   # per condition (tier i/ii)
    parity: dict[str, BehavioralParity]            # "Bprime" and "B" vs A
    stratum: dict[str, str]                        # eligible | confounded | invalid
    overhead: dict[str, Overhead]                  # "Bprime" and "B" vs A


def evaluate_case(
    case: BenchmarkCase, results: dict[str, RunResult]
) -> CaseEvaluation:
    validity = {cond: run_validity(r) for cond, r in results.items()}
    expected = frozenset(
        k
        for f in case.planted_faults
        if f.detection_tier == "mechanical"
        for k in f.expected_diagnostics
    )

    def _replay_kinds(cond: str) -> frozenset[str]:
        proj = results[cond].projection
        return frozenset(d.kind for d in proj.diagnostics) if proj else frozenset()

    observed_b = _replay_kinds("B")
    observed_bp = _replay_kinds("Bprime")
    detected_a = rubric_findings(results["A"].log) & RUBRIC_KINDS

    parity = {
        cond: behavioral_parity(results["A"], results[cond]) for cond in ("Bprime", "B")
    }
    stratum: dict[str, str] = {}
    for cond in ("Bprime", "B"):
        if not validity[cond].valid:
            stratum[cond] = "invalid"
        else:
            confounded, _ = is_confounded(parity[cond], DEFAULT_THRESHOLDS)
            stratum[cond] = "confounded" if confounded else "eligible"

    return CaseEvaluation(
        case_id=case.case_id,
        validity=validity,
        expected_mechanical=tuple(sorted(expected)),
        observed_b_replay=tuple(sorted(observed_b)),
        observed_bprime_replay=tuple(sorted(observed_bp)),
        detected_a_rubric=tuple(sorted(detected_a)),
        false_negatives_b=tuple(sorted(expected - observed_b)),
        false_positives_b=tuple(sorted(observed_b - expected)),
        false_negatives_a=tuple(sorted(expected - detected_a)),
        false_positives_a=tuple(sorted(detected_a - expected)),
        family_c={cond: family_c(r.log) for cond, r in results.items()},
        parity=parity,
        stratum=stratum,
        overhead={
            cond: overhead(results[cond], results["A"]) for cond in ("Bprime", "B")
        },
    )
