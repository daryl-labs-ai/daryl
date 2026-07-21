"""Swarm v0.1 replay tests — pure derivations, no kernel, no I/O.

Proves the semantic core: latest-wins with history preserved, DECLARED
supersession applied only when valid and unambiguous, explicit vs derived
conflicts, review polarity, computed check coverage, orphans/diagnostics —
and that no claim is ever turned into a stored truth.
"""

from __future__ import annotations

import pytest

from prl.swarm import (
    ConflictRecord,
    DecisionReceipt,
    ReviewReceipt,
    RunProjection,
    SwarmRun,
    TaskNode,
    WorkReceipt,
    project_run,
)
from prl.swarm.replay import DERIVED_CONFLICT_KINDS, DIAGNOSTIC_KINDS, SUPERSESSION_MATRIX

RUN = "swarm_run_r1"


def _run(**over) -> SwarmRun:
    base = dict(
        swarm_run_id=RUN,
        subject_id="subject:r",
        orchestrator_id="agent:orch",
        objective="replay tests",
        started_at="2026-07-21T12:00:00.000Z",
    )
    base.update(over)
    return SwarmRun(**base)


def _task(tid="task:1", **over) -> TaskNode:
    base = dict(
        task_node_id=tid,
        swarm_run_id=RUN,
        role="worker",
        objective="do the thing",
        status="delegated",
        created_at="2026-07-21T12:00:01.000Z",
    )
    base.update(over)
    return TaskNode(**base)


def _work(wid="work:1", tid="task:1", **over) -> WorkReceipt:
    base = dict(
        work_id=wid,
        swarm_run_id=RUN,
        claimed_actions=("edited file",),
        task_node_id=tid,
        agent_id="agent:worker",
        created_at="2026-07-21T12:00:02.000Z",
    )
    base.update(over)
    return WorkReceipt(**base)


def _review(rid="review:1", ref="work:1", verdict="approve", **over) -> ReviewReceipt:
    base = dict(
        review_id=rid,
        swarm_run_id=RUN,
        reviewed_ref=ref,
        lens="correctness",
        reviewer_agent_id="agent:reviewer",
        verdict=verdict,
        created_at="2026-07-21T12:00:03.000Z",
    )
    base.update(over)
    return ReviewReceipt(**base)


def _decision(did="dec:1", **over) -> DecisionReceipt:
    base = dict(
        decision_id=did,
        swarm_run_id=RUN,
        subject_id="subject:r",
        decision="use approach A",
        status="proposed",
        agent_id="agent:planner",
        created_at="2026-07-21T12:00:04.000Z",
    )
    base.update(over)
    return DecisionReceipt(**base)


def _diag_kinds(proj: RunProjection) -> list[str]:
    return [d.kind for d in proj.diagnostics]


# --- determinism -------------------------------------------------------------


def test_projection_is_deterministic():
    records = [
        _run(),
        _task(),
        _work(),
        _review(),
        _decision(),
        ConflictRecord(
            conflict_id="conf:1",
            swarm_run_id=RUN,
            competing_refs=("dec:1", "work:1"),
            conflict_type="decision",
            state="open",
        ),
    ]
    p1, p2 = project_run(records), project_run(records)
    assert p1 == p2  # dataclass equality over every derived field


# --- latest-wins with history preserved --------------------------------------


def test_task_latest_wins_keeps_history():
    records = [
        _run(),
        _task(status="delegated"),
        _task(status="in_progress"),
        _task(status="claimed_done"),
    ]
    view = project_run(records).tasks["task:1"]
    assert view.status == "claimed_done"
    assert view.status_history == ("delegated", "in_progress", "claimed_done")


def test_decision_line_latest_wins_keeps_history():
    records = [_run(), _decision(status="proposed"), _decision(status="accepted")]
    standing = project_run(records).decisions["dec:1"]
    assert standing.status == "accepted"
    assert standing.history == ("proposed", "accepted")


# --- supersession rule --------------------------------------------------------


def test_valid_supersession_applied():
    records = [
        _run(),
        _decision("dec:1", status="accepted"),
        _decision("dec:2", supersedes="dec:1", status="accepted"),
    ]
    proj = project_run(records)
    assert proj.decisions["dec:1"].superseded_by == "dec:2"
    assert proj.decisions["dec:2"].superseded_by is None
    # the old record is preserved, not deleted
    assert proj.decisions["dec:1"].history == ("accepted",)
    assert "supersession_cycle" not in _diag_kinds(proj)


def test_missing_supersession_target_is_diagnosed_not_applied():
    proj = project_run([_run(), _decision("dec:2", supersedes="dec:ghost")])
    kinds = _diag_kinds(proj)
    assert "missing_reference" in kinds
    assert proj.decisions["dec:2"].superseded_by is None


def test_self_supersession_diagnosed():
    proj = project_run([_run(), _decision("dec:1", supersedes="dec:1")])
    assert "self_supersession" in _diag_kinds(proj)
    assert proj.decisions["dec:1"].superseded_by is None


def test_supersession_cycle_detected_and_withheld():
    records = [
        _run(),
        _decision("dec:1", supersedes="dec:2"),
        _decision("dec:2", supersedes="dec:1"),
    ]
    proj = project_run(records)
    assert "supersession_cycle" in _diag_kinds(proj)
    assert proj.decisions["dec:1"].superseded_by is None
    assert proj.decisions["dec:2"].superseded_by is None
    assert proj.decisions["dec:1"].supersession_ambiguous
    # a cycle is also a derived conflict
    assert any(d.kind == "supersession_cycle" for d in proj.derived_conflicts)


def test_concurrent_supersession_branches_not_resolved():
    records = [
        _run(),
        _decision("dec:1"),
        _decision("dec:2a", supersedes="dec:1"),
        _decision("dec:2b", supersedes="dec:1"),
    ]
    proj = project_run(records)
    assert proj.decisions["dec:1"].superseded_by is None  # withheld, not chosen
    assert proj.decisions["dec:1"].supersession_ambiguous
    assert any(d.kind == "concurrent_supersession" for d in proj.derived_conflicts)


def test_supersession_type_matrix_enforced():
    assert SUPERSESSION_MATRIX == {"decision": frozenset({"decision"})}
    records = [_run(), _task(), _work(), _decision("dec:1", supersedes="work:1")]
    proj = project_run(records)
    assert "supersession_type_mismatch" in _diag_kinds(proj)
    assert proj.decisions["dec:1"].superseded_by is None


def test_cross_run_records_excluded_and_diagnosed():
    foreign = _decision("dec:x", swarm_run_id="swarm_run_other")
    proj = project_run([_run(), _decision("dec:1"), foreign])
    assert "cross_run_record" in _diag_kinds(proj)
    assert "dec:x" not in proj.decisions


# --- reviews ------------------------------------------------------------------


def test_review_positive_negative_divergent():
    base = [_run(), _task(), _work()]
    pos = project_run(base + [_review("review:1", verdict="approve")])
    neg = project_run(base + [_review("review:1", verdict="reject")])
    div = project_run(
        base
        + [
            _review("review:1", verdict="approve"),
            _review("review:2", verdict="reject"),
        ]
    )
    unpol = project_run(base + [_review("review:1", verdict="inconclusive")])
    none = project_run(base)

    assert pos.tasks["task:1"].review_signal == "positive"
    assert neg.tasks["task:1"].review_signal == "negative"
    assert div.tasks["task:1"].review_signal == "divergent"
    assert unpol.tasks["task:1"].review_signal == "unpolarized"
    assert none.tasks["task:1"].review_signal == "none"
    assert any(d.kind == "reviews_divergent" for d in div.derived_conflicts)
    assert not div.tasks["task:1"].work_ids == ()  # work still attached


def test_work_states_distinguished():
    no_work = project_run([_run(), _task()])
    claimed = project_run([_run(), _task(), _work()])
    reviewed = project_run([_run(), _task(), _work(), _review()])
    assert no_work.tasks["task:1"].work_state == "no_work_claimed"
    assert claimed.tasks["task:1"].work_state == "work_claimed"
    assert reviewed.tasks["task:1"].work_state == "work_reviewed"


def test_review_of_unknown_ref_diagnosed():
    proj = project_run([_run(), _review("review:1", ref="work:ghost")])
    assert "review_of_unknown_ref" in _diag_kinds(proj)


# --- explicit vs derived conflicts -------------------------------------------


def test_explicit_conflict_kept_and_flagged_when_open():
    conflict = ConflictRecord(
        conflict_id="conf:1",
        swarm_run_id=RUN,
        competing_refs=("dec:1", "dec:2"),
        conflict_type="decision",
        state="open",
    )
    proj = project_run([_run(), _decision("dec:1"), _decision("dec:2"), conflict])
    assert proj.explicit_conflicts["conf:1"].state == "open"
    assert "conflict_unresolved" in _diag_kinds(proj)
    # an explicit conflict is NOT a derived conflict
    assert all(d.kind != "conflict_unresolved" for d in proj.derived_conflicts)


def test_decision_on_superseded_base_is_derived_conflict():
    records = [
        _run(),
        _decision("dec:1"),
        _decision("dec:2", supersedes="dec:1"),
        _decision("dec:3", evidence_refs=("dec:1",)),
    ]
    proj = project_run(records)
    assert any(d.kind == "decision_on_superseded" for d in proj.derived_conflicts)


# --- check coverage -----------------------------------------------------------


def test_check_coverage_computed_not_trusted():
    work = _work(
        required_checks=("pytest", "ruff", "bandit"),
        claimed_checks=("pytest", "extra-lint"),
    )
    proj = project_run([_run(), _task(), work])
    cov = proj.check_coverage["work:1"]
    assert cov.required == ("pytest", "ruff", "bandit")
    assert cov.claimed == ("pytest", "extra-lint")
    assert cov.missing == ("ruff", "bandit")
    assert cov.unrequested == ("extra-lint",)
    assert cov.ratio == pytest.approx(1 / 3)
    assert any(d.kind == "required_checks_uncovered" for d in proj.derived_conflicts)


def test_check_coverage_undefined_when_nothing_required():
    proj = project_run([_run(), _task(), _work(claimed_checks=("pytest",))])
    cov = proj.check_coverage["work:1"]
    assert cov.ratio is None  # undefined, NOT 1.0
    assert cov.unrequested == ("pytest",)
    assert "required_checks_uncovered" not in _diag_kinds(proj)


def test_full_coverage_is_not_truth():
    """Full declarative coverage never marks anything verified/true."""
    work = _work(required_checks=("pytest",), claimed_checks=("pytest",))
    proj = project_run([_run(), _task(), work])
    assert proj.check_coverage["work:1"].ratio == 1.0
    view = proj.tasks["task:1"]
    assert view.work_state == "work_claimed"  # still a claim
    projected_fields = set(vars(view)) | set(vars(proj))
    for forbidden in ("verified_truth", "proven_fact", "ground_truth"):
        assert forbidden not in projected_fields


# --- orphans, limitations, insufficiency -------------------------------------


def test_orphan_work_on_unknown_task():
    proj = project_run([_run(), _work(tid="task:ghost")])
    assert "task_unknown" in _diag_kinds(proj)
    assert proj.orphan_record_ids == ("work:1",)
    assert "work:1" in proj.works  # kept, not dropped


def test_limitations_aggregated_never_dropped():
    work = _work(limitations=("did not run integration tests",))
    review = _review(limitations=("saw only the diff",))
    proj = project_run([_run(), _task(), work, review])
    assert ("work:1", "did not run integration tests") in proj.limitations
    assert ("review:1", "saw only the diff") in proj.limitations
    assert proj.tasks["task:1"].limitations == (
        "did not run integration tests",
        "saw only the diff",
    )


def test_insufficient_data_run_absent():
    proj = project_run([_task(), _work()])
    assert proj.run is None and proj.run_status is None
    assert proj.swarm_run_id == RUN  # inferred, surfaced as insufficient (no SwarmRun)


def test_diagnostic_kinds_are_closed():
    assert DERIVED_CONFLICT_KINDS <= DIAGNOSTIC_KINDS
