"""Recorder protocol (B2) — the per-condition Swarm representation.

Three implementations behind ONE shared interface so every condition presents
identical call sites (the fairness invariant; only the recorder object
differs, never the surrounding logic):

* :class:`NoOpRecorder` (condition A) — same interface, records nothing, does
  not even encode (zero instrumentation cost).
* :class:`OrchestratorEmitter` (condition B′) — strictly bounded verbatim
  serializer of events the orchestrator already holds. It makes NO decision,
  adds NO check, invents NO limitation, transforms NO prompt, deduces NO
  conflict, enriches NOTHING: its only capability is turning an event's
  already-declared payload into the corresponding swarm record and delegating
  the append. It is not a fourth behavior — it is B-without-the-prompt-channel.
* :class:`SwarmRecorder` (condition B) — encodes agent/orchestrator-produced
  records and delegates the append.

Every real append goes through ``PRLStore.commit_swarm_entry(...)`` — the
bounded writer — and NOTHING else. Recorders never receive or construct a
``Storage``, never touch the common benchmark event log (`eventlog.py`, owned
by the harness walk), and never mutate the records they are given (pydantic
models are immutable-by-convention here; recorders only read them).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict

from prl.store.dsm_commit import PRLStore, SwarmActResult
from prl.swarm.types import ACTION_TO_MODEL, SWARM_ACTION, SwarmRecord, to_swarm_entry

from .cases import CaseEvent


class RecorderReceipt(BaseModel):
    """Outcome of one emit. ``recorded=False`` for the control (nothing was
    appended). ``tip_hash`` is the DSM chain receipt — it certifies storage
    integrity, never content truth."""

    model_config = ConfigDict(extra="forbid")

    recorded: bool
    condition: str
    action_name: str
    swarm_run_id: str
    shard: str | None = None
    entry_id: str | None = None
    tip_hash: str | None = None


class BaseRecorder(ABC):
    """Shared interface. Conditions differ ONLY in which recorder instance is
    wired — call sites are identical."""

    condition: str = "?"

    @abstractmethod
    def emit(self, record: SwarmRecord) -> RecorderReceipt:
        """Record one swarm fact (or not, for the control)."""
        raise NotImplementedError


class NoOpRecorder(BaseRecorder):
    """Condition A: identical call sites, zero recording, zero encoding."""

    condition = "A"

    def emit(self, record: SwarmRecord) -> RecorderReceipt:
        return RecorderReceipt(
            recorded=False,
            condition=self.condition,
            action_name=SWARM_ACTION[record.kind],
            swarm_run_id=getattr(record, "swarm_run_id", "") or "",
        )


class _BoundedWriterRecorder(BaseRecorder):
    """Common append path: encode via the canonical envelope, delegate to the
    bounded writer. Subclasses only fix the condition label and (for B′) the
    verbatim-serialization boundary."""

    def __init__(self, store: PRLStore) -> None:
        # The ONLY write capability a recorder ever holds is the bounded
        # PRLStore facade; Storage is invisible from here.
        self._store = store

    def emit(self, record: SwarmRecord) -> RecorderReceipt:
        result: SwarmActResult = self._store.commit_swarm_entry(to_swarm_entry(record))
        return RecorderReceipt(
            recorded=True,
            condition=self.condition,
            action_name=result.action_name,
            swarm_run_id=result.swarm_run_id,
            shard=result.shard,
            entry_id=result.entry_id,
            tip_hash=result.tip_hash,
        )


class SwarmRecorder(_BoundedWriterRecorder):
    """Condition B: full treatment recorder."""

    condition = "B"


class OrchestratorEmitter(_BoundedWriterRecorder):
    """Condition B′: verbatim serialization of orchestrator-held events ONLY.

    The bounded contract is mechanical, not just documentary:
    :meth:`emit_from_event` accepts a :class:`CaseEvent` and reconstructs the
    record EXACTLY from ``event.emit.payload`` (already validated at case-load
    time). An event without ``emit`` yields ``recorded=False`` — the emitter
    can never invent a receipt for an event that declared nothing.
    """

    condition = "Bprime"

    def emit_from_event(self, event: CaseEvent) -> RecorderReceipt:
        if event.emit is None:
            return RecorderReceipt(
                recorded=False,
                condition=self.condition,
                action_name="",
                swarm_run_id="",
            )
        record = ACTION_TO_MODEL[event.emit.action_name](**event.emit.payload)
        return self.emit(record)
