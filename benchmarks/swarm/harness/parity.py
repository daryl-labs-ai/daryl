"""Behavioral parity primitives (B1) — the FROZEN homologous-step contract.

Implements `PARITY_SPEC_V0_1.md`: functional step identity assigned at
emission, functional (never positional) matching, sequence divergence as a
metric, and the pre-registered v0.1 thresholds. Pure module: no I/O, no
kernel, no provider.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Closed sets (PARITY_SPEC_V0_1.md §3.1). Single definition point.
BenchRole = Literal["orchestrator", "planner", "worker", "reviewer", "reconciler"]
StepKind = Literal[
    "run_setup", "plan", "delegate", "implement", "self_check", "submit_work",
    "review", "decide", "reconcile", "emit_conflict", "report",
]
STEP_KINDS: frozenset[str] = frozenset(
    {
        "run_setup", "plan", "delegate", "implement", "self_check",
        "submit_work", "review", "decide", "reconcile", "emit_conflict",
        "report",
    }
)


class StepUid(NamedTuple):
    """The functional step identity: (role, step_kind, task_ref, attempt).

    Homology across conditions is EQUALITY of this tuple (PARITY_SPEC §3.2).
    Sequence position is never a matching key.
    """

    role: str
    step_kind: str
    task_ref: str
    attempt: int


def step_uid(role: str, step_kind: str, task_ref: str = "", attempt: int = 1) -> StepUid:
    """Build a validated StepUid. Raises ValueError outside the closed sets."""
    if step_kind not in STEP_KINDS:
        raise ValueError(f"unknown step_kind {step_kind!r} (closed set: {sorted(STEP_KINDS)})")
    if attempt < 1:
        raise ValueError(f"attempt must be >= 1, got {attempt}")
    return StepUid(role=role, step_kind=step_kind, task_ref=task_ref, attempt=attempt)


def match_steps(
    a: list[StepUid], b: list[StepUid]
) -> tuple[list[StepUid], list[StepUid], list[StepUid]]:
    """Functional matching (PARITY_SPEC §3.2/§3.5).

    Returns ``(homologous, only_in_a, only_in_b)`` — homologous = uids present
    in both lists (each uid is unique per condition by construction; the
    contract validator enforces it). Order of the returned lists follows the
    first argument's order for determinism.
    """
    set_a, set_b = set(a), set(b)
    homologous = [u for u in a if u in set_b]
    only_a = [u for u in a if u not in set_b]
    only_b = [u for u in b if u not in set_a]
    return homologous, only_a, only_b


def sequence_divergence(a: list[str], b: list[str]) -> float:
    """Normalized Levenshtein distance between two step_kind sequences.

    `call_sequence_divergence` in PARITY_SPEC §5: distance ÷ max(len).
    Returns 0.0 for two empty sequences. Pure DP, deterministic.
    """
    if not a and not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, y in enumerate(b, start=1):
            curr[j] = min(
                prev[j] + 1,          # deletion
                curr[j - 1] + 1,      # insertion
                prev[j - 1] + (x != y),  # substitution
            )
        prev = curr
    return prev[-1] / max(len(a), len(b))


class ParityThresholds(BaseModel):
    """Pre-registered v0.1 thresholds (PARITY_SPEC §5). Changing any value is
    a dated protocol revision, never a silent edit."""

    model_config = ConfigDict(extra="forbid")

    spec_version: Literal["parity.v0.1"] = "parity.v0.1"
    # hard gate: prompts outside the declared block must hash-match
    prompt_hash_verification_required: bool = True
    # deterministic regime: trace equality is mandatory (G1-G3)
    deterministic_trace_equality_required: bool = True
    # live regime: confounded-stratum thresholds
    max_call_count_delta_abs: int = 2
    max_call_count_delta_ratio: float = 0.10
    max_call_sequence_divergence: float = 0.15
    max_retries_delta: int = 2
    max_decision_outcome_divergence: float = 0.20

    @field_validator(
        "max_call_count_delta_ratio",
        "max_call_sequence_divergence",
        "max_decision_outcome_divergence",
    )
    @classmethod
    def _ratio_bounds(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"ratio threshold must be within [0, 1], got {v!r}")
        return v


DEFAULT_THRESHOLDS = ParityThresholds()


class BehavioralParity(BaseModel):
    """Measured parity of one matched pair (family E). All values computed by
    the harness; `confounded` is DERIVED from thresholds, never hand-set."""

    model_config = ConfigDict(extra="forbid")

    prompt_hash_verification: bool
    call_count_delta: dict[str, int] = Field(default_factory=dict)  # role -> B-A
    call_count_a: dict[str, int] = Field(default_factory=dict)      # role -> A count
    call_sequence_divergence: float = 0.0
    retries_delta: int = 0
    decision_outcome_divergence: float | None = None
    tool_selection_distance: float | None = None       # descriptive in v0.1
    reasoning_length_delta: dict[str, int] | None = None  # descriptive in v0.1
    unmatched_steps: tuple[str, ...] = ()               # rendered StepUids
    notes: tuple[str, ...] = ()


def is_confounded(
    parity: BehavioralParity, thresholds: ParityThresholds = DEFAULT_THRESHOLDS
) -> tuple[bool, tuple[str, ...]]:
    """Apply PARITY_SPEC §5 to one pair. Returns (confounded, reasons).

    `prompt_hash_verification=False` is NOT a confounded verdict — it is a
    hard-gate violation the caller must treat as pair-invalid (excluded with
    reason); it is still reported here as a reason for visibility.
    """
    reasons: list[str] = []
    if thresholds.prompt_hash_verification_required and not parity.prompt_hash_verification:
        reasons.append("prompt_hash_verification failed (HARD GATE: pair invalid)")
    for role, delta in sorted(parity.call_count_delta.items()):
        base = parity.call_count_a.get(role, 0)
        allowed = max(
            thresholds.max_call_count_delta_abs,
            int(base * thresholds.max_call_count_delta_ratio),
        )
        if abs(delta) > allowed:
            reasons.append(f"call_count_delta[{role}]={delta} exceeds ±{allowed}")
    if parity.call_sequence_divergence > thresholds.max_call_sequence_divergence:
        reasons.append(
            f"call_sequence_divergence={parity.call_sequence_divergence:.3f} "
            f"> {thresholds.max_call_sequence_divergence}"
        )
    if abs(parity.retries_delta) > thresholds.max_retries_delta:
        reasons.append(f"retries_delta={parity.retries_delta} exceeds ±{thresholds.max_retries_delta}")
    if (
        parity.decision_outcome_divergence is not None
        and parity.decision_outcome_divergence > thresholds.max_decision_outcome_divergence
    ):
        reasons.append(
            f"decision_outcome_divergence={parity.decision_outcome_divergence:.3f} "
            f"> {thresholds.max_decision_outcome_divergence}"
        )
    return (bool(reasons), tuple(reasons))
