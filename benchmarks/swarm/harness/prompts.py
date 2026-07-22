"""Prompt construction and the THREE-LEVEL hash contract (B3).

Frozen at B2 validation (owner mandate):

1. ``base_prompt_hash``      — the business prompt, common to A, B′ and B;
2. ``grounding_block_hash``  — the declared block, present ONLY in B, hashed
                               separately;
3. ``effective_prompt_hash`` — the prompt actually sent to the provider.

G2 is a RECOMPOSITION check, not a mere difference check:

    effective_prompt(B) == base_prompt + delimited(declared_grounding_block)
    base_prompt_hash(A) == base_prompt_hash(B′) == base_prompt_hash(B)

so a business-prompt change can never hide inside "the declared block".

The grounding block is: canonically delimited, versioned, hashed separately,
absent from A and B′, identical for a given fixture/seed, and STATIC — no
content injected dynamically from prior agent output (v0.1 forbids it; any
future dynamic re-serving must be an explicitly manifested protocol revision).

Pure module: no I/O, no provider, no kernel.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from .cases import BenchmarkCase, CaseEvent
from .manifest import Condition

GROUNDING_OPEN = "<<<DSM-GROUNDING v0.1>>>"
GROUNDING_CLOSE = "<<<END DSM-GROUNDING v0.1>>>"


def prompt_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class GroundingBlock(BaseModel):
    """The single declared A/B prompt difference. Static per fixture/seed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["grounding-block.v0.1"] = "grounding-block.v0.1"
    text: str

    @field_validator("text")
    @classmethod
    def _static_and_undelimited(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("grounding block text must be non-empty")
        if GROUNDING_OPEN in v or GROUNDING_CLOSE in v:
            raise ValueError("block text must not nest the canonical delimiters")
        return v

    def delimited(self) -> str:
        """Canonical delimitation — byte-stable for a given text."""
        return f"\n\n{GROUNDING_OPEN}\n{self.text}\n{GROUNDING_CLOSE}\n"

    def block_hash(self) -> str:
        return prompt_hash(self.delimited())


DEFAULT_GROUNDING_BLOCK = GroundingBlock(
    text=(
        "You may emit typed swarm records (run, task, work, review, decision, "
        "conflict) through the recorder interface. Recording is append-only "
        "evidence of what you claim, decide or observe; it never replaces or "
        "alters your task instructions, and it is never proof your work is "
        "correct."
    )
)


def base_prompt(case: BenchmarkCase, event: CaseEvent, seed: int) -> str:
    """Deterministic business prompt for one agent step — a pure function of
    (case, functional step identity, seed); identical across conditions."""
    return (
        f"[bench:{case.case_id}|seed:{seed}]\n"
        f"role={event.role} step={event.step_kind} task={event.task_ref or '-'} "
        f"attempt={event.attempt}\n"
        f"objective: {case.objective}\n"
        f"instruction: perform the '{event.step_kind}' step for this run."
    )


def effective_prompt(
    base: str, condition: Condition, block: GroundingBlock | None
) -> str:
    """A and B′: the base, byte-identical. B: base + delimited declared block."""
    if condition in ("A", "Bprime"):
        if block is not None:
            raise ValueError(f"condition {condition} must not carry a grounding block")
        return base
    if block is None:
        raise ValueError("condition B requires the declared grounding block")
    return base + block.delimited()


class PromptRecord(BaseModel):
    """The three-level hash evidence for one agent step (manifest artifact)."""

    model_config = ConfigDict(extra="forbid")

    step_key: str                    # "role|step_kind|task_ref|attempt"
    base_prompt_hash: str
    effective_prompt_hash: str
    grounding_block_hash: str = ""   # "" outside condition B
