"""B2 — recorders + common event log: deterministic H6/G1 gates.

Proves, with the real kernel on temporary stores and the 12-case corpus:
* the common event log is walk-owned and condition-symmetric — recorders never
  produce it;
* G1 (HARD): trace(B′) \\ recorder_events == trace(A), exactly, for every case;
* G3 (HARD): same condition + same case ⇒ identical trace hash AND identical
  replay projection;
* the NoOpRecorder records nothing; the SwarmRecorder writes only through the
  bounded writer (refusals propagate, nothing half-appended); the
  OrchestratorEmitter serializes verbatim and can never invent a receipt;
* B′ and B produce semantically identical record sets in the deterministic
  regime (byte-parity of decoded records).

G2 (grounding-block prompt difference) needs prompts, hence the B3 runner —
deliberately absent here.
"""

from __future__ import annotations

import pytest

from dsm.core.storage import Storage
from dsm.status import VerifyStatus
from dsm.verify import verify_shard

from benchmarks.swarm.harness.cases import load_cases
from benchmarks.swarm.harness.recorder import (
    BaseRecorder,
    NoOpRecorder,
    OrchestratorEmitter,
    RecorderReceipt,
    SwarmRecorder,
)
from benchmarks.swarm.harness.walk import walk_case
from prl.exceptions import PRLValidationError
from prl.store import PRLStore
from prl.swarm import (
    SwarmRun,
    from_swarm_entry,
    project_run,
    swarm_shard_name,
    to_swarm_entry,
)
from prl.swarm.types import ACTION_TO_MODEL

CASES = {c.case_id: c for c in load_cases()}
NOMINAL = CASES["c01-nominal"]


def _store(tmp_path, sub) -> PRLStore:
    return PRLStore(Storage(data_dir=str(tmp_path / sub)))


def _decoded_records(store: PRLStore, shard: str):
    entries = list(reversed(store._storage.read(shard, limit=1000)))
    return [from_swarm_entry(e) for e in entries]


# --- interface parity --------------------------------------------------------


def test_three_recorders_share_one_interface(tmp_path):
    a = NoOpRecorder()
    bp = OrchestratorEmitter(_store(tmp_path, "bp"))
    b = SwarmRecorder(_store(tmp_path, "b"))
    assert all(isinstance(r, BaseRecorder) for r in (a, bp, b))
    assert (a.condition, bp.condition, b.condition) == ("A", "Bprime", "B")
    # identical call site: same method, same signature, same receipt type
    for r in (a, bp, b):
        receipt = walk_case(NOMINAL, r)[1][0]
        assert isinstance(receipt, RecorderReceipt)


# --- G1: trace(B') \ recorder_events == trace(A), for EVERY case -------------


def test_g1_bprime_trace_equals_a_trace_all_cases(tmp_path):
    for i, case in enumerate(CASES.values()):
        log_a, _ = walk_case(case, NoOpRecorder())
        log_bp, _ = walk_case(case, OrchestratorEmitter(_store(tmp_path, f"bp{i}")))
        assert log_bp.trace() == log_a.trace(), case.case_id
        assert log_bp.trace_hash() == log_a.trace_hash(), case.case_id
        # and B too, in the pre-prompt deterministic regime
        log_b, _ = walk_case(case, SwarmRecorder(_store(tmp_path, f"b{i}")))
        assert log_b.trace_hash() == log_a.trace_hash(), case.case_id


def test_recorder_events_are_journaled_by_walk_and_flagged(tmp_path):
    log_bp, receipts = walk_case(NOMINAL, OrchestratorEmitter(_store(tmp_path, "bp")))
    flagged = [e for e in log_bp.events if e.recorder_event]
    assert len(flagged) == sum(1 for r in receipts if r.recorded) > 0
    # the A log has zero flagged entries but the SAME non-recorder journal
    log_a, _ = walk_case(NOMINAL, NoOpRecorder())
    assert not any(e.recorder_event for e in log_a.events)
    assert [e.payload for e in log_a.events] == [
        e.payload for e in log_bp.events if not e.recorder_event
    ]


# --- G3: determinism ---------------------------------------------------------


def test_g3_same_condition_same_trace_and_projection(tmp_path):
    logs, projections = [], []
    for run in ("r1", "r2"):
        store = _store(tmp_path, f"g3-{run}")
        log, _ = walk_case(NOMINAL, OrchestratorEmitter(store))
        shard = swarm_shard_name(NOMINAL.swarm_run_id)
        proj = project_run(_decoded_records(store, shard), swarm_run_id=NOMINAL.swarm_run_id)
        logs.append(log)
        projections.append(proj)
    assert logs[0].trace_hash() == logs[1].trace_hash()
    assert projections[0] == projections[1]


# --- condition semantics -----------------------------------------------------


def test_noop_records_nothing():
    log, receipts = walk_case(NOMINAL, NoOpRecorder())
    assert all(not r.recorded for r in receipts)
    assert all(r.condition == "A" for r in receipts)
    assert not any(e.recorder_event for e in log.events)


def test_swarm_recorder_writes_only_through_bounded_writer(tmp_path):
    store = _store(tmp_path, "b")
    _, receipts = walk_case(NOMINAL, SwarmRecorder(store))
    shard = swarm_shard_name(NOMINAL.swarm_run_id)
    assert all(r.recorded and r.shard == shard and r.tip_hash for r in receipts)
    report = verify_shard(store._storage, shard)
    assert report["status"] == VerifyStatus.OK
    # a refused record propagates the bounded-writer error, appends nothing
    bad = to_swarm_entry(
        SwarmRun(swarm_run_id="swarm_run_other", subject_id="s",
                 orchestrator_id="o", objective="x")
    ).model_copy(update={"source": "prl"})
    n_before = len(store._storage.read(shard, limit=1000))
    with pytest.raises(PRLValidationError):
        store.commit_swarm_entry(bad)
    assert len(store._storage.read(shard, limit=1000)) == n_before


def test_emitter_serializes_verbatim_and_cannot_invent(tmp_path):
    store = _store(tmp_path, "bp")
    emitter = OrchestratorEmitter(store)
    # an event with no emit yields recorded=False — no synthesis possible
    silent = next(e for e in NOMINAL.events if e.emit is None)
    receipt = emitter.emit_from_event(silent)
    assert receipt.recorded is False and receipt.action_name == ""
    # verbatim: the stored record decodes back EQUAL to the declared payload
    emitting = next(e for e in NOMINAL.events if e.emit is not None)
    emitter.emit_from_event(emitting)
    [decoded] = _decoded_records(store, swarm_shard_name(NOMINAL.swarm_run_id))
    assert decoded == ACTION_TO_MODEL[emitting.emit.action_name](**emitting.emit.payload)


def test_bprime_and_b_record_sets_identical(tmp_path):
    store_bp = _store(tmp_path, "bp")
    store_b = _store(tmp_path, "b")
    walk_case(NOMINAL, OrchestratorEmitter(store_bp))
    walk_case(NOMINAL, SwarmRecorder(store_b))
    shard = swarm_shard_name(NOMINAL.swarm_run_id)
    assert _decoded_records(store_bp, shard) == _decoded_records(store_b, shard)


def test_recorders_never_mutate_walk_inputs(tmp_path):
    before = NOMINAL.model_dump()
    log, _ = walk_case(NOMINAL, SwarmRecorder(_store(tmp_path, "b")))
    assert NOMINAL.model_dump() == before  # case untouched
    events_snapshot = log.events
    # emitting again on a fresh store must not touch the previous log
    walk_case(NOMINAL, SwarmRecorder(_store(tmp_path, "b2")))
    assert log.events == events_snapshot
