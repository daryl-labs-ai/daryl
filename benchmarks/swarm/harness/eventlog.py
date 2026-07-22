"""Common benchmark event log (B2) — identical for A, B′ and B.

This is the harness's OWN journal, strictly separate from DSM Swarm records:

```
orchestrator
   ├── common benchmark event log     # A, B′, B   (this module)
   └── recorder protocol              # per-condition Swarm representation
```

The log is produced by the orchestrator/harness walk for EVERY condition —
recorders never write it and never become its producers (otherwise condition A
would lose symmetric evaluation instrumentation and the comparison would be
biased). Recorder activity is journaled BY THE WALK as entries flagged
``recorder_event=True``; the parity trace excludes them mechanically, which is
exactly the ``trace(B′) \\ recorder_events == trace(A)`` subtraction of gate G1
(PARITY_SPEC §4).

Pure module: no kernel, no provider, no I/O beyond explicit (de)serialization.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from prl._canonical import canonical_bytes

from .parity import BenchRole, StepKind, StepUid


class LogEvent(BaseModel):
    """One journal entry, tagged at source with the functional step identity."""

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=1)
    role: BenchRole
    step_kind: StepKind
    task_ref: str = ""
    attempt: int = Field(ge=1, default=1)
    note: str = ""
    prompt_hash: str = ""                 # hash of the prompt used, "" if none
    tool_calls: tuple[str, ...] = ()      # declared tool invocations of the step
    payload: dict[str, Any] = Field(default_factory=dict)  # declared fields (rubric input)
    recorder_event: bool = False          # True = journaled recorder activity

    @property
    def uid(self) -> StepUid:
        return StepUid(self.role, self.step_kind, self.task_ref, self.attempt)


class EventLog:
    """Append-only in-memory journal with a deterministic parity trace."""

    def __init__(self) -> None:
        self._events: list[LogEvent] = []

    def append(self, event: LogEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> tuple[LogEvent, ...]:
        return tuple(self._events)

    def trace(self) -> tuple[tuple[str, str, str, int, str, tuple[str, ...]], ...]:
        """The parity trace (PARITY_SPEC §4): ordered functional steps with
        their prompt hash and tool calls, EXCLUDING recorder events."""
        return tuple(
            (e.role, e.step_kind, e.task_ref, e.attempt, e.prompt_hash, e.tool_calls)
            for e in self._events
            if not e.recorder_event
        )

    def trace_hash(self) -> str:
        """Deterministic sha256 of the parity trace (gate G1/G3 comparator)."""
        payload = [list(entry[:5]) + [list(entry[5])] for entry in self.trace()]
        return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()

    def step_kind_sequence(self) -> list[str]:
        """Input of `parity.sequence_divergence` (non-recorder steps only)."""
        return [e.step_kind for e in self._events if not e.recorder_event]

    # -- explicit (de)serialization for run artifacts -------------------------

    def to_jsonl(self) -> str:
        return "\n".join(e.model_dump_json() for e in self._events) + ("\n" if self._events else "")

    @classmethod
    def from_jsonl(cls, text: str) -> "EventLog":
        log = cls()
        for line in text.splitlines():
            if line.strip():
                log.append(LogEvent.model_validate_json(line))
        return log
