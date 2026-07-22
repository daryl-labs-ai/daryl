"""B1 — swarm benchmark contracts: parity primitives, manifest, case corpus.

Guards the frozen decisions of `benchmarks/swarm/PARITY_SPEC_V0_1.md`:
functional (never positional) homologous-step matching, the pre-registered
thresholds, condition coherence (A / Bprime / B), and the 12-case deterministic
corpus — including the strong cross-check that every MECHANICAL planted fault
is actually derived by the canonical replay (`prl.swarm.replay`) from the
case's own emitted records, and that the nominal case derives zero diagnostics.
Pure tests: no kernel storage, no writer, no provider.
"""

from __future__ import annotations

import json

import pytest

from benchmarks.swarm.harness.cases import (
    CASES_DIR,
    HARNESS_FLAGS,
    BenchmarkCase,
    load_cases,
)
from benchmarks.swarm.harness.manifest import (
    Budget,
    Grounding,
    InstanceRef,
    Models,
    RunManifest,
    Topology,
)
from benchmarks.swarm.harness.parity import (
    DEFAULT_THRESHOLDS,
    STEP_KINDS,
    BehavioralParity,
    ParityThresholds,
    is_confounded,
    match_steps,
    sequence_divergence,
    step_uid,
)
from prl.swarm import from_swarm_entry, project_run
from prl.swarm.replay import DIAGNOSTIC_KINDS
from prl.types import Carrier


# --- parity primitives -------------------------------------------------------


def test_step_uid_closed_sets():
    u = step_uid("worker", "submit_work", "task:1", 2)
    assert u == ("worker", "submit_work", "task:1", 2)
    with pytest.raises(ValueError, match="closed set"):
        step_uid("worker", "think_hard")
    with pytest.raises(ValueError, match="attempt"):
        step_uid("worker", "implement", attempt=0)


def test_matching_is_functional_not_positional():
    a = [step_uid("planner", "plan"), step_uid("worker", "implement", "task:1"),
         step_uid("reviewer", "review", "task:1")]
    # same steps, different order + one extra recorder-side step in b
    b = [step_uid("reviewer", "review", "task:1"), step_uid("planner", "plan"),
         step_uid("worker", "implement", "task:1"),
         step_uid("orchestrator", "run_setup")]
    homologous, only_a, only_b = match_steps(a, b)
    assert homologous == a           # matched despite reordering
    assert only_a == []
    assert only_b == [step_uid("orchestrator", "run_setup")]


def test_retry_shifts_nothing():
    a = [step_uid("worker", "implement", "task:1", 1)]
    b = [step_uid("worker", "implement", "task:1", 1),
         step_uid("worker", "implement", "task:1", 2)]
    homologous, only_a, only_b = match_steps(a, b)
    assert homologous == a
    assert only_b == [step_uid("worker", "implement", "task:1", 2)]


def test_sequence_divergence_metric():
    assert sequence_divergence([], []) == 0.0
    assert sequence_divergence(["plan", "implement"], ["plan", "implement"]) == 0.0
    assert sequence_divergence(["plan"], ["review"]) == 1.0
    d = sequence_divergence(["plan", "implement", "review"], ["plan", "review"])
    assert 0.0 < d < 1.0
    # symmetry
    assert d == sequence_divergence(["plan", "review"], ["plan", "implement", "review"])


def test_preregistered_thresholds_frozen_values():
    t = DEFAULT_THRESHOLDS
    assert t.spec_version == "parity.v0.1"
    assert t.prompt_hash_verification_required is True
    assert t.deterministic_trace_equality_required is True
    assert t.max_call_count_delta_abs == 2
    assert t.max_call_count_delta_ratio == 0.10
    assert t.max_call_sequence_divergence == 0.15
    assert t.max_retries_delta == 2
    assert t.max_decision_outcome_divergence == 0.20
    with pytest.raises(Exception):
        ParityThresholds(max_call_sequence_divergence=1.5)


def test_confounded_derivation():
    ok = BehavioralParity(prompt_hash_verification=True,
                          call_count_delta={"worker": 1}, call_count_a={"worker": 20})
    assert is_confounded(ok) == (False, ())

    shifted = BehavioralParity(prompt_hash_verification=True,
                               call_count_delta={"worker": 5}, call_count_a={"worker": 20},
                               call_sequence_divergence=0.30)
    confounded, reasons = is_confounded(shifted)
    assert confounded and len(reasons) == 2

    hard = BehavioralParity(prompt_hash_verification=False)
    confounded, reasons = is_confounded(hard)
    assert confounded and "HARD GATE" in reasons[0]


# --- manifest ----------------------------------------------------------------


def _manifest(condition, grounding=None, block=""):
    return RunManifest(
        run_id=f"run:c01:seed0:{condition}",
        pair_id="c01:seed0",
        condition=condition,
        instance=InstanceRef(id="c01-nominal", instance_ref="benchmarks/swarm/cases/01_c01-nominal.json"),
        starting_commit="82b47948f",
        orchestrator_id="orch:bench-v1",
        models=Models(
            planner=Carrier(provider="fake", model="fake-planner"),
            workers=(Carrier(provider="fake", model="fake-worker-1"),),
            reviewers=(Carrier(provider="fake", model="fake-reviewer-1"),),
        ),
        budget=Budget(max_total_tokens=1000, max_usd=0.0, max_wall_seconds=60),
        seed=0,
        topology=Topology(planners=1, workers=1, reviewers=1),
        grounding=grounding,
        grounding_block_text=block,
        grounding_block_hash="sha256:x" if block else "",
        started_at="2026-07-22T10:00:00.000Z",
    )


def test_manifest_condition_a_valid():
    m = _manifest("A")
    assert m.parity_thresholds == DEFAULT_THRESHOLDS


def test_manifest_bprime_requires_orchestrator_emitter_and_no_block():
    g = Grounding(emitter="orchestrator_emitter", shard="swarm_c01")
    m = _manifest("Bprime", grounding=g)
    assert m.grounding.kernel_version == "1.0"
    with pytest.raises(Exception, match="byte-identical"):
        _manifest("Bprime", grounding=g, block="you may emit records")
    with pytest.raises(Exception, match="orchestrator"):
        _manifest("Bprime", grounding=Grounding(emitter="swarm_recorder", shard="s"))


def test_manifest_b_requires_recorder_and_a_refuses_grounding():
    m = _manifest("B", grounding=Grounding(emitter="swarm_recorder", shard="swarm_c01"),
                  block="declared grounding block")
    assert m.grounding.emitter == "swarm_recorder"
    with pytest.raises(Exception, match="grounding"):
        _manifest("A", grounding=Grounding(emitter="swarm_recorder", shard="s"))
    with pytest.raises(Exception):
        _manifest("B")  # grounding missing


def test_manifest_rejects_unknown_fields_and_stale_contracts():
    with pytest.raises(Exception):
        Grounding(emitter="swarm_recorder", shard="s", kernel_version="unknown")
    with pytest.raises(Exception):
        Grounding(emitter="swarm_recorder", shard="s", verify_status="CHAIN_OK")


# --- case corpus -------------------------------------------------------------


def test_corpus_loads_with_twelve_unique_cases():
    cases = load_cases()
    assert len(cases) == 12
    assert len({c.case_id for c in cases}) == 12
    # deterministic: loading twice yields equal objects
    assert cases == load_cases()


def test_every_case_has_unique_functional_uids_and_valid_steps():
    for case in load_cases():
        uids = [e.uid for e in case.events]
        assert len(set(uids)) == len(uids), case.case_id
        assert all(e.step_kind in STEP_KINDS for e in case.events), case.case_id


def test_mechanical_faults_are_derived_by_canonical_replay():
    """The strong B1 cross-check: for every case, decode its own emitted
    records and run the canonical replay — every expected MECHANICAL
    diagnostic must appear, and the nominal case must derive zero."""
    for case in load_cases():
        records = [
            from_swarm_entry(
                {"metadata": {"action_name": e.emit.action_name},
                 "content": json.dumps(e.emit.payload)}
            )
            for e in case.events
            if e.emit is not None
        ]
        proj = project_run(records, swarm_run_id=case.swarm_run_id)
        kinds = {d.kind for d in proj.diagnostics}
        expected = {
            k
            for f in case.planted_faults
            if f.detection_tier == "mechanical"
            for k in f.expected_diagnostics
        }
        missing = expected - kinds
        assert not missing, f"{case.case_id}: replay missed {sorted(missing)} (got {sorted(kinds)})"
        if case.case_id == "c01-nominal":
            assert kinds == set(), f"nominal case must be diagnostic-free, got {sorted(kinds)}"
        if case.case_id == "c07-false-result-coherent-trace":
            # the dissociation case: coherent receipts => zero replay diagnostics
            assert kinds == set(), "c07 receipts must stay coherent (trace != truth)"


def test_fault_tiers_reference_closed_vocabularies():
    for case in load_cases():
        for fault in case.planted_faults:
            assert set(fault.expected_diagnostics) <= DIAGNOSTIC_KINDS
            assert set(fault.expected_harness_flags) <= HARNESS_FLAGS


def test_case_rejects_run_mismatch_and_duplicate_uids():
    case = load_cases()[0]
    data = case.model_dump()
    data["swarm_run_id"] = "swarm_run_other"
    with pytest.raises(Exception, match="swarm_run_id"):
        BenchmarkCase(**data)
    data2 = case.model_dump()
    data2["events"] = [data2["events"][0], data2["events"][0]]
    with pytest.raises(Exception):
        BenchmarkCase(**data2)
