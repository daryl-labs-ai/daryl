"""Swarm v0.1 minimal-slice tests — the REAL kernel write-path proof (Phase 5).

Requires the real DSM kernel (dsm.core.storage / dsm.rr / dsm.verify) and
dsm_primitives. Proves, against a real temporary DSM store:

* bounded append through the registered PRL writer (``commit_swarm_entry`` in
  ``prl/store/dsm_commit.py`` — no new ``LEGITIMATE_WRITERS`` entry);
* real hash + prev_hash chain across two swarm records;
* RR indexing of ``swarm.*`` actions, authoritative order via
  ``navigate_action`` + join record→entry by ``entry_id`` (never trusting
  ``resolve_entries`` order);
* canonical round-trip, ``agent_id != carrier.model``, real
  ``kernel_version = "1.0"`` stamped at the write boundary;
* ``verify_shard`` green by its REAL contract (``status == VerifyStatus.OK``)
  and deliberate tamper detected as ``VerifyStatus.TAMPERED``;
* every bounded-writer refusal happens BEFORE any append.
"""

from __future__ import annotations

import json

import pytest

from dsm.core.storage import Storage
from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator
from dsm.status import VerifyStatus
from dsm.verify import verify_shard

from prl._canonical import canonical_bytes
from prl.exceptions import PRLEntryMappingError, PRLValidationError
from prl.store import PRLStore, SwarmActResult
from prl.swarm import (
    SCHEMA_VERSION,
    SWARM_ACTIONS,
    SwarmRun,
    TaskNode,
    from_swarm_entry,
    swarm_shard_name,
    to_swarm_entry,
)
from prl.types import Carrier, EntryDraft

RUN_ID = "swarm_run_t0001"
SHARD = swarm_shard_name(RUN_ID)


def _run(**over) -> SwarmRun:
    base = dict(
        swarm_run_id=RUN_ID,
        subject_id="subject:t",
        orchestrator_id="agent:orchestrator",
        objective="minimal vertical slice",
        started_at="2026-07-21T10:00:00.000Z",
    )
    base.update(over)
    return SwarmRun(**base)


def _task(**over) -> TaskNode:
    base = dict(
        task_node_id="task:t-1",
        swarm_run_id=RUN_ID,
        role="worker",
        objective="prove the chain",
        status="delegated",
        assigned_agent_id="agent:worker-alpha",
        assigned_carrier=Carrier(provider="anthropic", model="claude-fable-5"),
        created_at="2026-07-21T10:00:01.000Z",
    )
    base.update(over)
    return TaskNode(**base)


def _store(tmp_path) -> PRLStore:
    return PRLStore(Storage(data_dir=str(tmp_path)))


def _shard_count(store: PRLStore, shard: str = SHARD) -> int:
    return len(store._storage.read(shard, limit=1000))


# --- pure models & envelope (no kernel) -------------------------------------


def test_models_forbid_unknown_fields():
    with pytest.raises(Exception):
        SwarmRun(**{**_run().model_dump(), "truth": True})
    with pytest.raises(Exception):
        TaskNode(**{**_task().model_dump(), "extra_field": 1})


def test_models_reject_invalid_status():
    with pytest.raises(Exception):
        _run(status="conflicted")  # not a RunStatus
    with pytest.raises(Exception):
        _task(status="done")  # not a TaskStatus


def test_shard_name_is_fs_safe():
    assert SHARD == "swarm_swarmrunt0001"
    assert ":" not in SHARD and "/" not in SHARD
    with pytest.raises(PRLValidationError):
        swarm_shard_name(":::")


def test_to_swarm_entry_envelope_shape():
    draft = to_swarm_entry(_run())
    assert draft.source == "swarm"
    assert draft.version == SCHEMA_VERSION
    assert draft.session_id == RUN_ID
    assert draft.shard == SHARD
    assert draft.metadata["action_name"] == "swarm.run"
    assert draft.metadata["schema_version"] == SCHEMA_VERSION
    # kernel_version is a write-boundary stamp, not a pure-model concern
    assert "kernel_version" not in draft.metadata


def test_round_trip_is_canonical_stable():
    run = _run()
    draft = to_swarm_entry(run)
    decoded = from_swarm_entry(draft)
    assert decoded == run
    assert canonical_bytes(
        decoded.model_dump(mode="json", exclude_none=True)
    ) == draft.content.encode("utf-8")


def test_from_swarm_entry_rejects_unknown_action():
    draft = to_swarm_entry(_run())
    bad = draft.model_copy(update={"metadata": {"action_name": "swarm.nope"}})
    with pytest.raises(PRLEntryMappingError):
        from_swarm_entry(bad)


def test_from_swarm_entry_rejects_non_json_content():
    draft = to_swarm_entry(_run())
    bad = draft.model_copy(update={"content": "not-json{"})
    with pytest.raises(PRLEntryMappingError):
        from_swarm_entry(bad)


def test_from_swarm_entry_rejects_payload_model_mismatch():
    draft = to_swarm_entry(_run())
    # run payload under the task action: decodes as JSON, fails the model
    bad = draft.model_copy(
        update={"metadata": {**draft.metadata, "action_name": "swarm.task"}}
    )
    with pytest.raises(PRLValidationError):
        from_swarm_entry(bad)


# --- bounded writer: real kernel append (Phase 5 points 1–7, 14) ------------


def test_commit_swarm_entries_chain_on_real_kernel(tmp_path):
    store = _store(tmp_path)

    r1 = store.commit_swarm_entry(to_swarm_entry(_run()))
    assert isinstance(r1, SwarmActResult)
    assert r1.action_name == "swarm.run"
    assert r1.shard == SHARD and r1.swarm_run_id == RUN_ID
    assert r1.tip_hash and r1.entry_id  # real Entry receipt

    r2 = store.commit_swarm_entry(to_swarm_entry(_task()))
    assert r2.action_name == "swarm.task"

    # Storage.read returns newest-first (documented contract) — restore
    # chronological order for the chain assertion.
    entries = list(reversed(store._storage.read(SHARD, limit=10)))
    assert len(entries) == 2
    e1, e2 = entries
    assert e1.hash == r1.tip_hash and e2.hash == r2.tip_hash
    assert e1.prev_hash is None
    assert e2.prev_hash == e1.hash  # exact chain
    # real kernel version stamped at the write boundary
    assert e1.metadata["kernel_version"] == "1.0"
    assert e2.metadata["kernel_version"] == "1.0"


# --- RR replay: authoritative order + join by id (points 8–13) --------------


def test_rr_replay_authoritative_order_and_identity(tmp_path):
    store = _store(tmp_path)
    run = _run()
    task = _task()
    task_done = _task(status="claimed_done", created_at="2026-07-21T10:00:02.000Z")
    for record in (run, task, task_done):
        store.commit_swarm_entry(to_swarm_entry(record))

    builder = RRIndexBuilder(storage=store._storage, index_dir=str(store._storage.data_dir / "rr_index"))
    builder.build()
    nav = RRNavigator(builder, store._storage)

    recs = nav.navigate_action("swarm.run") + nav.navigate_action("swarm.task")
    assert len(recs) == 3
    ts = [r["timestamp"] for r in nav.navigate_action("swarm.task")]
    assert ts == sorted(ts)  # authoritative order: ascending

    # resolve by JOIN on entry_id — never trust resolve_entries order
    entries = nav.resolve_entries(list(reversed(recs)))
    by_id = {e.id: e for e in entries}
    joined = [by_id[r["entry_id"]] for r in recs]
    decoded = [from_swarm_entry(e) for e in joined]

    assert [type(d).__name__ for d in decoded] == ["SwarmRun", "TaskNode", "TaskNode"]
    assert decoded[0] == run
    # latest-wins readable in authoritative order
    assert [d.status for d in decoded[1:]] == ["delegated", "claimed_done"]
    # identity separation survives the round-trip
    d_task = decoded[1]
    assert d_task.assigned_agent_id == "agent:worker-alpha"
    assert d_task.assigned_carrier.model == "claude-fable-5"
    assert d_task.assigned_agent_id != d_task.assigned_carrier.model
    # canonical stability against the stored content
    assert canonical_bytes(
        decoded[0].model_dump(mode="json", exclude_none=True)
    ).decode("utf-8") == joined[0].content


# --- verify_shard real contract + tamper (points 15–16) ---------------------


def test_verify_shard_ok_then_tamper_detected(tmp_path):
    store = _store(tmp_path)
    store.commit_swarm_entry(to_swarm_entry(_run()))
    store.commit_swarm_entry(to_swarm_entry(_task()))

    report = verify_shard(store._storage, SHARD)
    assert report["status"] == VerifyStatus.OK  # REAL contract
    assert report["verified"] == report["total_entries"] == 2
    assert report["pin_status"] == "PINNED_OK"

    # deliberate tamper: flip payload bytes inside the shard segment file
    seg_files = [
        p
        for p in store._storage.data_dir.rglob(f"*{SHARD}*")
        if p.is_file() and "integrity" not in str(p)
    ]
    assert seg_files
    target = seg_files[0]
    raw = target.read_bytes()
    assert b"prove the chain" in raw
    target.write_bytes(raw.replace(b"prove the chain", b"PROVE THE CHAIN", 1))

    report2 = verify_shard(store._storage, SHARD)
    assert report2["status"] == VerifyStatus.TAMPERED
    assert report2["tampered"] >= 1


# --- bounded writer refusals, all BEFORE append (points 17–18) --------------


def test_writer_refuses_non_swarm_source(tmp_path):
    store = _store(tmp_path)
    draft = to_swarm_entry(_run()).model_copy(update={"source": "prl"})
    with pytest.raises(PRLValidationError, match="source"):
        store.commit_swarm_entry(draft)
    assert _shard_count(store) == 0  # refused before append


def test_writer_refuses_wrong_version(tmp_path):
    store = _store(tmp_path)
    draft = to_swarm_entry(_run()).model_copy(update={"version": "prl.v1"})
    with pytest.raises(PRLValidationError, match="version"):
        store.commit_swarm_entry(draft)
    assert _shard_count(store) == 0


def test_writer_refuses_prl_and_unknown_actions(tmp_path):
    store = _store(tmp_path)
    base = to_swarm_entry(_run())
    for action in ("prl.consultation", "prl.project", "swarm.memory_candidate", "anything"):
        bad = base.model_copy(
            update={"metadata": {**base.metadata, "action_name": action}}
        )
        with pytest.raises(PRLValidationError, match="closed"):
            store.commit_swarm_entry(bad)
    assert _shard_count(store) == 0
    # closed set, v0.1 semantic core: memory_candidate / context_grant deferred
    assert SWARM_ACTIONS == {
        "swarm.run", "swarm.task", "swarm.work", "swarm.review",
        "swarm.decision", "swarm.conflict",
    }


def test_writer_refuses_wrong_schema_version_metadata(tmp_path):
    store = _store(tmp_path)
    base = to_swarm_entry(_run())
    bad = base.model_copy(
        update={"metadata": {**base.metadata, "schema_version": "swarm.v9"}}
    )
    with pytest.raises(PRLValidationError, match="schema_version"):
        store.commit_swarm_entry(bad)
    assert _shard_count(store) == 0


def test_writer_refuses_invalid_payload_before_append(tmp_path):
    store = _store(tmp_path)
    base = to_swarm_entry(_run())
    payload = json.loads(base.content)
    payload["status"] = "conflicted"  # invalid RunStatus — refused by the model
    bad = base.model_copy(
        update={"content": canonical_bytes(payload).decode("utf-8")}
    )
    with pytest.raises(PRLValidationError):
        store.commit_swarm_entry(bad)
    assert _shard_count(store) == 0


def test_writer_refuses_kind_action_mismatch(tmp_path):
    store = _store(tmp_path)
    # a valid TASK payload smuggled under the swarm.run action
    task_draft = to_swarm_entry(_task())
    bad = task_draft.model_copy(
        update={"metadata": {**task_draft.metadata, "action_name": "swarm.run"}}
    )
    with pytest.raises(PRLValidationError):
        store.commit_swarm_entry(bad)
    assert _shard_count(store) == 0


def test_writer_refuses_session_run_id_mismatch(tmp_path):
    store = _store(tmp_path)
    draft = to_swarm_entry(_run()).model_copy(update={"session_id": "other_run"})
    with pytest.raises(PRLValidationError, match="swarm_run_id"):
        store.commit_swarm_entry(draft)
    assert _shard_count(store) == 0


def test_writer_refuses_handcrafted_arbitrary_draft(tmp_path):
    """A hand-built EntryDraft with an arbitrary payload cannot borrow the path."""
    store = _store(tmp_path)
    draft = EntryDraft(
        session_id="x",
        source="swarm",
        content='{"anything": 1}',
        shard="swarm_x",
        metadata={"action_name": "swarm.run", "schema_version": SCHEMA_VERSION},
        timestamp="2026-07-21T10:00:00.000Z",
        version=SCHEMA_VERSION,
    )
    with pytest.raises(PRLValidationError):
        store.commit_swarm_entry(draft)
    assert len(store._storage.read("swarm_x", limit=10)) == 0


# --- semantic core: every new action through the bounded writer -------------


def test_writer_accepts_all_semantic_core_actions(tmp_path):
    from prl.swarm import ConflictRecord, DecisionReceipt, ReviewReceipt, WorkReceipt

    store = _store(tmp_path)
    records = [
        _run(),
        _task(),
        WorkReceipt(
            work_id="work:t-1",
            swarm_run_id=RUN_ID,
            claimed_actions=("edited file",),
            task_node_id="task:t-1",
            agent_id="agent:worker-alpha",
            created_at="2026-07-21T10:00:03.000Z",
        ),
        ReviewReceipt(
            review_id="review:t-1",
            swarm_run_id=RUN_ID,
            reviewed_ref="work:t-1",
            lens="correctness",
            verdict="approve",
            created_at="2026-07-21T10:00:04.000Z",
        ),
        DecisionReceipt(
            decision_id="dec:t-1",
            swarm_run_id=RUN_ID,
            subject_id="subject:t",
            decision="accept the work",
            status="accepted",
            created_at="2026-07-21T10:00:05.000Z",
        ),
        ConflictRecord(
            conflict_id="conf:t-1",
            swarm_run_id=RUN_ID,
            competing_refs=("dec:t-1", "work:t-1"),
            conflict_type="decision",
            state="open",
            created_at="2026-07-21T10:00:06.000Z",
        ),
    ]
    actions = [store.commit_swarm_entry(to_swarm_entry(r)).action_name for r in records]
    assert actions == [
        "swarm.run", "swarm.task", "swarm.work",
        "swarm.review", "swarm.decision", "swarm.conflict",
    ]
    entries = list(reversed(store._storage.read(SHARD, limit=10)))
    assert len(entries) == 6
    assert all(e.metadata["kernel_version"] == "1.0" for e in entries)
    for e, nxt in zip(entries, entries[1:]):
        assert nxt.prev_hash == e.hash


def test_writer_refuses_new_action_kind_mismatch(tmp_path):
    from prl.swarm import WorkReceipt

    store = _store(tmp_path)
    work = WorkReceipt(
        work_id="work:t-1",
        swarm_run_id=RUN_ID,
        claimed_actions=("x",),
    )
    draft = to_swarm_entry(work)
    bad = draft.model_copy(
        update={"metadata": {**draft.metadata, "action_name": "swarm.review"}}
    )
    with pytest.raises(PRLValidationError):
        store.commit_swarm_entry(bad)
    assert _shard_count(store) == 0


# --- integrated scenario: append -> RR -> projection -> verify -> tamper -----


def test_full_semantic_scenario_on_real_kernel(tmp_path):
    from prl.swarm import DecisionReceipt, ReviewReceipt, WorkReceipt, project_run

    store = _store(tmp_path)
    records = [
        _run(),
        _task(),
        WorkReceipt(
            work_id="work:t-1",
            swarm_run_id=RUN_ID,
            claimed_actions=("implemented the slice",),
            task_node_id="task:t-1",
            agent_id="agent:worker-alpha",
            required_checks=("pytest", "ruff"),
            claimed_checks=("pytest",),
            limitations=("no integration test",),
            created_at="2026-07-21T10:00:03.000Z",
        ),
        ReviewReceipt(
            review_id="review:t-1",
            swarm_run_id=RUN_ID,
            reviewed_ref="work:t-1",
            lens="correctness",
            reviewer_agent_id="agent:reviewer-beta",
            verdict="approve",
            limitations=("saw only the diff",),
            created_at="2026-07-21T10:00:04.000Z",
        ),
        DecisionReceipt(
            decision_id="dec:t-1",
            swarm_run_id=RUN_ID,
            subject_id="subject:t",
            decision="ship the slice",
            status="accepted",
            task_node_id="task:t-1",
            evidence_refs=("work:t-1", "review:t-1"),
            agent_id="agent:planner",
            created_at="2026-07-21T10:00:05.000Z",
        ),
    ]
    for r in records:
        store.commit_swarm_entry(to_swarm_entry(r))

    # RR replay: authoritative order = navigate_action, join by entry_id
    builder = RRIndexBuilder(
        storage=store._storage, index_dir=str(store._storage.data_dir / "rr_index")
    )
    builder.build()
    nav = RRNavigator(builder, store._storage)
    recs: list[dict] = []
    for action in sorted(SWARM_ACTIONS):
        recs.extend(nav.navigate_action(action))
    recs.sort(key=lambda r: r["timestamp"])  # global authoritative order
    by_id = {e.id: e for e in nav.resolve_entries(recs)}
    decoded = [from_swarm_entry(by_id[r["entry_id"]]) for r in recs]

    proj = project_run(decoded)
    assert proj.swarm_run_id == RUN_ID and proj.run_status == "open"
    view = proj.tasks["task:t-1"]
    assert view.work_state == "work_reviewed"
    assert view.review_signal == "positive"
    assert view.decision_ids == ("dec:t-1",)
    assert proj.decisions["dec:t-1"].status == "accepted"
    cov = proj.check_coverage["work:t-1"]
    assert cov.missing == ("ruff",) and cov.ratio == 0.5
    assert any(d.kind == "required_checks_uncovered" for d in proj.derived_conflicts)
    assert ("work:t-1", "no integration test") in proj.limitations

    report = verify_shard(store._storage, SHARD)
    assert report["status"] == VerifyStatus.OK
    assert report["verified"] == report["total_entries"] == 5

    seg = [
        p
        for p in store._storage.data_dir.rglob(f"*{SHARD}*")
        if p.is_file() and "integrity" not in str(p)
    ][0]
    raw = seg.read_bytes()
    seg.write_bytes(raw.replace(b"ship the slice", b"SHIP THE SLICE", 1))
    assert verify_shard(store._storage, SHARD)["status"] == VerifyStatus.TAMPERED


# --- PRL coexistence (point 19 spot-check; full suite runs in CI) -----------


def test_swarm_and_prl_writes_coexist(tmp_path):
    from prl.types import ConsultationNode, MEF

    store = _store(tmp_path)
    store.commit_swarm_entry(to_swarm_entry(_run()))
    act = store.commit_act(
        ConsultationNode(
            consultation_id="c-1",
            subject_id="subject:t",
            answer="ok",
            mef=MEF(
                claim_id="claim-1",
                regime="observed.declared",
                confidence=0.9,
                contested=False,
                producer="tester",
                agent_id="agent:tester",
            ),
        )
    )
    assert act.tip_hash
    swarm_report = verify_shard(store._storage, SHARD)
    prl_report = verify_shard(store._storage, act.shard)
    assert swarm_report["status"] == VerifyStatus.OK
    assert prl_report["status"] == VerifyStatus.OK
