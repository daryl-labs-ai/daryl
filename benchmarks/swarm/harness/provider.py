"""Deterministic FakeProvider (B3) — zero cost, zero network, zero secrets.

The response is a pure function of (seed, functional step identity, effective
prompt): same inputs, same bytes. Token counts are deterministic too, so the
cost/overhead accounting pipeline can be exercised end-to-end without any live
provider. The fake response text is NEVER fed back into the script's behavior
in the deterministic regime — the case script drives the run, which is exactly
what makes G1/G2/G3 provable as equalities.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict

from .parity import StepUid


class ProviderCall(BaseModel):
    """One raw provider interaction (persisted verbatim in run artifacts)."""

    model_config = ConfigDict(extra="forbid")

    role: str
    step_kind: str
    task_ref: str
    attempt: int
    effective_prompt_hash: str
    response_text: str
    tokens_in: int
    tokens_out: int


class FakeProvider:
    """Deterministic stand-in for a model provider."""

    name = "fake"

    def __init__(self, seed: int) -> None:
        self._seed = seed

    def complete(self, uid: StepUid, effective_prompt: str) -> ProviderCall:
        digest = hashlib.sha256(
            f"{self._seed}|{uid.role}|{uid.step_kind}|{uid.task_ref}|{uid.attempt}|"
            f"{effective_prompt}".encode("utf-8")
        ).hexdigest()
        return ProviderCall(
            role=uid.role,
            step_kind=uid.step_kind,
            task_ref=uid.task_ref,
            attempt=uid.attempt,
            effective_prompt_hash="sha256:"
            + hashlib.sha256(effective_prompt.encode("utf-8")).hexdigest(),
            response_text=f"fake-response:{digest[:16]}",
            tokens_in=len(effective_prompt) // 4,
            tokens_out=50 + (int(digest[:4], 16) % 200),
        )
