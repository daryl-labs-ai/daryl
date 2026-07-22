"""Deterministic case walk (B2) — the minimal, condition-symmetric execution
of a BenchmarkCase script. This is the parity-load-bearing core the B3 runner
will extend (FakeProvider, prompts, manifests); the walk itself defines WHO
writes the common event log and HOW recorder activity is journaled, so it
lives in the harness, not in tests.

Contract:
* the walk — never the recorder — writes the common event log, identically in
  every condition (symmetric evaluation instrumentation);
* for an event carrying ``emit``:
  - condition A: the NoOp recorder is invoked at the SAME call site (parity),
    records nothing;
  - condition B′: the OrchestratorEmitter serializes the event verbatim;
  - condition B: the SwarmRecorder emits the record built from the event
    (in B3+ the record may be produced by agents; in the deterministic walk it
    is the same declared payload — byte-parity by construction);
* every ACTUAL recorder append is journaled BY THE WALK as a
  ``recorder_event=True`` entry (excluded from the parity trace, PARITY_SPEC
  §3.5/§4) — G1's subtraction is therefore mechanical.
"""

from __future__ import annotations

from collections.abc import Callable

from prl.swarm.types import ACTION_TO_MODEL

from .cases import BenchmarkCase, CaseEvent
from .eventlog import EventLog, LogEvent
from .recorder import BaseRecorder, OrchestratorEmitter, RecorderReceipt


def walk_case(
    case: BenchmarkCase,
    recorder: BaseRecorder,
    *,
    prompt_hash_fn: Callable[[CaseEvent], str] | None = None,
) -> tuple[EventLog, list[RecorderReceipt]]:
    """Execute the case script under one condition. Returns the common event
    log (walk-owned) and the recorder receipts (condition-owned).

    ``prompt_hash_fn`` (B3 runner) supplies the EFFECTIVE prompt hash journaled
    for a step (``""`` = no provider interaction for that step). The walk stays
    the single definition of journaling semantics; the runner only injects the
    prompt/provider concern through this hook.
    """
    log = EventLog()
    receipts: list[RecorderReceipt] = []
    for event in case.events:
        log.append(
            LogEvent(
                seq=event.seq,
                role=event.role,
                step_kind=event.step_kind,
                task_ref=event.task_ref,
                attempt=event.attempt,
                note=event.log_note,
                prompt_hash=prompt_hash_fn(event) if prompt_hash_fn else "",
                payload=dict(event.emit.payload) if event.emit else {},
            )
        )
        if event.emit is None:
            continue
        if isinstance(recorder, OrchestratorEmitter):
            receipt = recorder.emit_from_event(event)
        else:
            record = ACTION_TO_MODEL[event.emit.action_name](**event.emit.payload)
            receipt = recorder.emit(record)
        receipts.append(receipt)
        if receipt.recorded:
            # journaled BY THE WALK, flagged, excluded from the parity trace
            log.append(
                LogEvent(
                    seq=event.seq,
                    role=event.role,
                    step_kind=event.step_kind,
                    task_ref=event.task_ref,
                    attempt=event.attempt,
                    note=f"recorder append {receipt.action_name}",
                    recorder_event=True,
                )
            )
    return log, receipts
