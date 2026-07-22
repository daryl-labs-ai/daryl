"""Benchmark case contract + loader (B1).

A BenchmarkCase is a **condition-agnostic deterministic script**: an ordered
list of logical events, each tagged at source with the functional step
identity (PARITY_SPEC §3.1). The future runner (B3) executes the same script
under every condition; in Bprime/B, events carrying an `emit` payload become
swarm records through the bounded writer. The planted faults are the
deterministic oracle (protocol §4, tier 1).

Cross-validation against the canonical core happens at LOAD time:
- every `emit.action_name` must be in the closed `SWARM_ACTIONS` set and its
  payload must validate against the corresponding `prl.swarm` model;
- every expected mechanical diagnostic must be a known replay diagnostic kind;
- step uids must be unique within a case (functional matching requirement).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from prl.swarm.replay import DIAGNOSTIC_KINDS
from prl.swarm.types import ACTION_TO_MODEL, SWARM_ACTIONS

from .parity import STEP_KINDS, BenchRole, StepKind, StepUid

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"

# Harness-level flags for expectations the CORE does not diagnose (they are
# computed by the harness metrics or by annotation). Closed set.
HARNESS_FLAGS: frozenset[str] = frozenset(
    {
        "claimed_vs_observable_gap",     # claimed checks without actual results
        "unrequested_checks",            # claimed but never required
        "coverage_undefined",            # no required checks -> ratio None
        "outcome_failure_with_coherent_trace",  # case 07 dissociation
        "annotation_required",           # cases needing human judgment (06, 12)
        "limitation_dropped_from_report",  # declared limitation absent at report
    }
)

DetectionTier = Literal["mechanical", "harness", "annotation", "none"]


class Emit(BaseModel):
    """A swarm record this event produces in conditions Bprime/B."""

    model_config = ConfigDict(extra="forbid")

    action_name: str
    payload: dict[str, Any]

    @model_validator(mode="after")
    def _payload_validates(self) -> "Emit":
        if self.action_name not in SWARM_ACTIONS:
            raise ValueError(
                f"action {self.action_name!r} outside the closed set {sorted(SWARM_ACTIONS)}"
            )
        ACTION_TO_MODEL[self.action_name](**self.payload)  # raises if invalid
        return self


class CaseEvent(BaseModel):
    """One logical step of the script, tagged at source (never inferred)."""

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=1)                 # script order (NOT a matching key)
    role: BenchRole
    step_kind: StepKind
    task_ref: str = ""
    attempt: int = Field(ge=1, default=1)
    log_note: str = ""                     # what the common event log records
    emit: Emit | None = None               # None => no record in any condition

    @property
    def uid(self) -> StepUid:
        return StepUid(self.role, self.step_kind, self.task_ref, self.attempt)


class PlantedFault(BaseModel):
    """One deliberately planted incoherence — the deterministic oracle."""

    model_config = ConfigDict(extra="forbid")

    fault_id: str
    description: str
    refs: tuple[str, ...] = ()
    detection_tier: DetectionTier
    expected_diagnostics: tuple[str, ...] = ()   # replay kinds (mechanical tier)
    expected_harness_flags: tuple[str, ...] = ()  # HARNESS_FLAGS members

    @field_validator("expected_diagnostics")
    @classmethod
    def _known_diagnostics(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        unknown = set(v) - DIAGNOSTIC_KINDS
        if unknown:
            raise ValueError(f"unknown replay diagnostic kinds: {sorted(unknown)}")
        return v

    @field_validator("expected_harness_flags")
    @classmethod
    def _known_flags(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        unknown = set(v) - HARNESS_FLAGS
        if unknown:
            raise ValueError(f"unknown harness flags: {sorted(unknown)}")
        return v

    @model_validator(mode="after")
    def _tier_coherence(self) -> "PlantedFault":
        if self.detection_tier == "mechanical" and not self.expected_diagnostics:
            raise ValueError("mechanical fault must name >=1 expected replay diagnostic")
        if self.detection_tier == "harness" and not self.expected_harness_flags:
            raise ValueError("harness fault must name >=1 expected harness flag")
        return self


class BenchmarkCase(BaseModel):
    """One deterministic scenario: script + planted-fault oracle."""

    model_config = ConfigDict(extra="forbid")

    case_version: Literal["swarm-bench-case.v0.1"] = "swarm-bench-case.v0.1"
    case_id: str = Field(min_length=1)
    title: str
    objective: str
    swarm_run_id: str
    seed: int = 0
    events: tuple[CaseEvent, ...] = Field(min_length=1)
    planted_faults: tuple[PlantedFault, ...] = ()
    expected_a_detection: str = ""   # how (if at all) the rubric can catch it in A
    notes: str = ""

    @model_validator(mode="after")
    def _script_coherence(self) -> "BenchmarkCase":
        # 1) functional uids unique (matching requirement, PARITY_SPEC §3)
        uids = [e.uid for e in self.events]
        dupes = {u for u in uids if uids.count(u) > 1}
        if dupes:
            raise ValueError(f"duplicate step uids (matching would be ambiguous): {sorted(dupes)}")
        # 2) seq strictly increasing (deterministic script order)
        seqs = [e.seq for e in self.events]
        if seqs != sorted(seqs) or len(set(seqs)) != len(seqs):
            raise ValueError("event seq must be strictly increasing")
        # 3) every emitted record belongs to this case's run
        for e in self.events:
            if e.emit is not None:
                rid = e.emit.payload.get("swarm_run_id")
                if rid != self.swarm_run_id:
                    raise ValueError(
                        f"event seq={e.seq} emits swarm_run_id={rid!r} "
                        f"!= case run {self.swarm_run_id!r}"
                    )
        return self


def load_case(path: Path) -> BenchmarkCase:
    return BenchmarkCase(**json.loads(path.read_text()))


def load_cases(directory: Path = CASES_DIR) -> list[BenchmarkCase]:
    """Load and validate every case fixture, sorted by filename (deterministic)."""
    cases = [load_case(p) for p in sorted(directory.glob("*.json"))]
    ids = [c.case_id for c in cases]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate case ids: {sorted(i for i in ids if ids.count(i) > 1)}")
    return cases


__all__ = [
    "CASES_DIR",
    "HARNESS_FLAGS",
    "STEP_KINDS",
    "BenchmarkCase",
    "CaseEvent",
    "Emit",
    "PlantedFault",
    "load_case",
    "load_cases",
]
