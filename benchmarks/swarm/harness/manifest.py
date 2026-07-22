"""Run-manifest contract (B1) — pydantic replacement of the candidate's
RUN_MANIFEST.schema.json (no `jsonschema` dependency; the repo already speaks
pydantic). One manifest per run; a matched pair shares `pair_id`, seed and
starting commit. Updated against the merged core: three conditions (A/Bprime/B,
PARITY_SPEC §2), real `VerifyStatus` values, real kernel version "1.0" (never
"unknown"), and the behavioral-parity section (family E).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from prl.types import Carrier

from .parity import DEFAULT_THRESHOLDS, BehavioralParity, ParityThresholds

MANIFEST_VERSION = "swarm-bench.v0.2"

Condition = Literal["A", "Bprime", "B"]
Termination = Literal["success", "budget_exhausted", "no_progress", "error"]


class InstanceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    instance_ref: str                      # path to the pinned instance dir / case file
    acceptance_suite_ref: str | None = None
    regression_suite_ref: str | None = None


class Models(BaseModel):
    """Execution carriers by role (reuses the canonical prl Carrier)."""

    model_config = ConfigDict(extra="forbid")

    planner: Carrier
    workers: tuple[Carrier, ...] = Field(min_length=1)
    reviewers: tuple[Carrier, ...] = Field(min_length=1)
    reconciler: Carrier | None = None


class PriceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_usd_per_mtok: float = Field(ge=0)
    output_usd_per_mtok: float = Field(ge=0)


class Budget(BaseModel):
    """Hard caps — no default-unlimited mode exists."""

    model_config = ConfigDict(extra="forbid")

    max_total_tokens: int = Field(ge=1)
    max_usd: float = Field(ge=0)
    max_wall_seconds: int = Field(ge=1)


class Topology(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planners: int = Field(ge=1)
    workers: int = Field(ge=1)
    reviewers: int = Field(ge=0)
    reconcilers: int = Field(ge=0, default=0)


class Grounding(BaseModel):
    """Present for Bprime/B only. Records HOW records were written and the
    integrity verdicts, by their REAL contracts (VerifyStatus values;
    DSM_KERNEL_VERSION stamped by the bounded writer)."""

    model_config = ConfigDict(extra="forbid")

    emitter: Literal["orchestrator_emitter", "swarm_recorder"]
    kernel_version: Literal["1.0"] = "1.0"
    shard: str
    verify_status: Literal["OK", "TAMPERED", "CHAIN_BROKEN"] | None = None
    replay_success: bool | None = None


class Deviation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    what: str
    why: str


class Outcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    termination: Termination
    tests_passed: float | None = Field(default=None, ge=0, le=1)
    requirements_satisfied: float | None = Field(default=None, ge=0, le=1)
    regressions: int | None = Field(default=None, ge=0)
    diff_ref: str | None = None
    test_report_ref: str | None = None


class RunManifest(BaseModel):
    """One benchmark run. Everything needed to reproduce and fairly compare."""

    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal["swarm-bench.v0.2"] = MANIFEST_VERSION
    run_id: str = Field(min_length=1)
    pair_id: str = Field(min_length=1)
    condition: Condition
    instance: InstanceRef
    starting_commit: str = Field(min_length=7)
    orchestrator_id: str = Field(min_length=1)
    models: Models
    price_table: dict[str, PriceEntry] = Field(default_factory=dict)
    budget: Budget
    seed: int | str
    topology: Topology
    tool_permissions: tuple[str, ...] = ()
    # Prompt parity evidence: hash of every prompt template, plus the single
    # declared grounding block (text + hash). Block text/hash empty for A and
    # Bprime (their prompts are byte-identical, PARITY_SPEC §2).
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    grounding_block_text: str = ""
    grounding_block_hash: str = ""
    parity_thresholds: ParityThresholds = Field(default_factory=lambda: DEFAULT_THRESHOLDS)
    behavioral_parity: BehavioralParity | None = None  # filled by the pair evaluator
    grounding: Grounding | None = None
    preregistration_ref: str | None = None
    deviations: tuple[Deviation, ...] = ()
    outcome: Outcome | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    started_at: str = Field(min_length=1)   # ISO-8601 UTC
    ended_at: str | None = None

    @model_validator(mode="after")
    def _condition_coherence(self) -> "RunManifest":
        if self.condition == "A":
            if self.grounding is not None:
                raise ValueError("condition A must not carry a grounding section")
            if self.grounding_block_text or self.grounding_block_hash:
                raise ValueError("condition A must not carry a grounding block")
        else:
            if self.grounding is None:
                raise ValueError(f"condition {self.condition} requires a grounding section")
            if self.condition == "Bprime":
                if self.grounding.emitter != "orchestrator_emitter":
                    raise ValueError("Bprime records are emitted by the orchestrator only")
                if self.grounding_block_text or self.grounding_block_hash:
                    raise ValueError(
                        "Bprime prompts are byte-identical to A: no grounding block"
                    )
            if self.condition == "B" and self.grounding.emitter != "swarm_recorder":
                raise ValueError("condition B records go through the swarm recorder")
        return self
