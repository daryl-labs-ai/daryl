"""B5 live-smoke preparation — typed config, hard caps, no-network dry-run.

Security model (all mechanical, none documentary):

* ``live_execution_authorized = False`` by default. The live transport CANNOT
  be built unless the config carries ``live_execution_authorized=True`` AND an
  explicit ``authorized_budget_usd`` covering the caps AND the API-key env var
  EXISTS (checked by NAME only — its value is read lazily inside the transport
  at call time and never stored, logged, or persisted).
* Every cap is enforced BEFORE the call that would exceed it (``BudgetGuard.
  precheck`` raises; nothing is half-spent), never after.
* The dry-run mode uses a :class:`NoNetworkTransport` that performs zero
  network I/O and marks every result ``network=False`` — it exercises the
  ENTIRE live code path (caps, provenance, redaction, manifests, parity)
  except the socket.
* Secrets: this module never reads a key value outside the live transport
  call; configs, manifests and artifacts carry the env var NAME only.

No kernel import; all Swarm writes still go through the recorders
(``PRLStore.commit_swarm_entry``) — this module adds NO write path.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .manifest import PriceEntry
from .parity import StepUid
from .provider import ProviderCall

# Conservative safety multiplier applied to every token estimate.
EST_SAFETY = 1.5
CHARS_PER_TOKEN = 4


class LiveExecutionNotAuthorized(RuntimeError):
    """Raised whenever a live transport is requested without the full,
    explicit authorization chain (flag + budget + key present)."""


class BudgetExceeded(RuntimeError):
    """Raised BEFORE the call that would cross any hard cap."""


class LiveCallError(RuntimeError):
    """A provider call failed after the configured retries; the run is
    INVALID (a validity matter, never a low score)."""


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(ge=0, default=2)
    backoff_seconds: float = Field(ge=0, default=2.0)


class SmokeCaps(BaseModel):
    """Hard caps — ALL required, no default-unlimited field exists."""

    model_config = ConfigDict(extra="forbid")

    max_usd: float = Field(gt=0)
    max_total_tokens: int = Field(gt=0)
    max_wall_seconds: int = Field(gt=0)
    max_calls: int = Field(gt=0)
    max_output_tokens_per_call: int = Field(gt=0)


class SmokeConfig(BaseModel):
    """Frozen-before-execution smoke configuration (B5)."""

    model_config = ConfigDict(extra="forbid")

    config_version: Literal["swarm-smoke.v0.1"] = "swarm-smoke.v0.1"
    case_id: str
    seed: int = 0
    provider: Literal["openai"] = "openai"     # the repo's declared agents extra
    model: str = Field(min_length=1)
    temperature: float = 0.0
    request_seed: int | None = None            # requested; support recorded per call
    request_timeout_seconds: float = Field(gt=0, default=60.0)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    condition_order: tuple[str, ...] = ("A", "Bprime", "B")
    price: PriceEntry                          # frozen at authorization time
    # The committed price is a conservative PLACEHOLDER ceiling. Live mode is
    # refused until the owner replaces it with the provider's actual published
    # prices AND flips this flag (owner reserve, B5-PREFLIGHT validation): no
    # cost estimate may rely on the placeholder during a live run.
    price_table_confirmed: bool = False
    caps: SmokeCaps
    api_key_env: str = "OPENAI_API_KEY"        # NAME only; value never surfaces
    live_execution_authorized: bool = False    # default: NOTHING live may run
    authorized_budget_usd: float | None = None

    @model_validator(mode="after")
    def _authorization_coherence(self) -> "SmokeConfig":
        if self.live_execution_authorized:
            if not self.price_table_confirmed:
                raise ValueError(
                    "live authorization requires price_table_confirmed=true "
                    "(real published prices frozen, placeholder forbidden)"
                )
            if self.authorized_budget_usd is None:
                raise ValueError(
                    "live authorization requires an explicit authorized_budget_usd"
                )
            if self.caps.max_usd > self.authorized_budget_usd:
                raise ValueError(
                    f"caps.max_usd={self.caps.max_usd} exceeds the authorized "
                    f"budget {self.authorized_budget_usd}"
                )
        if set(self.condition_order) != {"A", "Bprime", "B"}:
            raise ValueError("condition_order must cover exactly A, Bprime, B")
        return self


class CostEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calls: int
    tokens_in_est: int
    tokens_out_est: int
    usd_est: float
    note: str = (
        "conservative: char/4 with x1.5 margin on input; every call assumed to "
        "spend max_output_tokens_per_call on output"
    )


def estimate_smoke_cost(config: SmokeConfig, case) -> CostEstimate:
    """Pre-execution conservative estimate over the exact prompts that would
    be sent (computed locally, zero network)."""
    from .prompts import DEFAULT_GROUNDING_BLOCK, base_prompt, effective_prompt
    from .runner import AGENT_ROLES

    calls = 0
    tokens_in = 0
    for condition in config.condition_order:
        block = DEFAULT_GROUNDING_BLOCK if condition == "B" else None
        for event in case.events:
            if event.role not in AGENT_ROLES:
                continue
            calls += 1
            text = effective_prompt(base_prompt(case, event, config.seed), condition, block)
            tokens_in += int(len(text) / CHARS_PER_TOKEN * EST_SAFETY) + 1
    tokens_out = calls * config.caps.max_output_tokens_per_call
    usd = (
        tokens_in * config.price.input_usd_per_mtok
        + tokens_out * config.price.output_usd_per_mtok
    ) / 1_000_000
    return CostEstimate(
        calls=calls, tokens_in_est=tokens_in, tokens_out_est=tokens_out,
        usd_est=round(usd, 6),
    )


class BudgetGuard:
    """Shared across the whole smoke (all conditions). Refuses BEFORE any cap
    would be crossed. ``clock`` is injectable for tests."""

    def __init__(self, caps: SmokeCaps, price: PriceEntry,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.caps = caps
        self.price = price
        self._clock = clock
        self._t0 = clock()
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0

    @property
    def cost_usd(self) -> float:
        return (
            self.tokens_in * self.price.input_usd_per_mtok
            + self.tokens_out * self.price.output_usd_per_mtok
        ) / 1_000_000

    @property
    def wall_seconds(self) -> float:
        return self._clock() - self._t0

    def precheck(self, est_tokens_in: int) -> None:
        """Raise BudgetExceeded if the NEXT call could cross any cap."""
        est_out = self.caps.max_output_tokens_per_call
        if self.calls + 1 > self.caps.max_calls:
            raise BudgetExceeded(f"max_calls={self.caps.max_calls} would be exceeded")
        projected_tokens = self.tokens_in + est_tokens_in + self.tokens_out + est_out
        if projected_tokens > self.caps.max_total_tokens:
            raise BudgetExceeded(
                f"max_total_tokens={self.caps.max_total_tokens} would be exceeded "
                f"(projected {projected_tokens})"
            )
        projected_cost = self.cost_usd + (
            est_tokens_in * self.price.input_usd_per_mtok
            + est_out * self.price.output_usd_per_mtok
        ) / 1_000_000
        if projected_cost > self.caps.max_usd:
            raise BudgetExceeded(
                f"max_usd={self.caps.max_usd} would be exceeded "
                f"(projected {projected_cost:.4f})"
            )
        if self.wall_seconds > self.caps.max_wall_seconds:
            raise BudgetExceeded(
                f"max_wall_seconds={self.caps.max_wall_seconds} exceeded "
                f"({self.wall_seconds:.0f}s elapsed)"
            )

    def commit(self, tokens_in: int, tokens_out: int) -> None:
        self.calls += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out

    def spend_summary(self) -> dict:
        return {
            "calls": self.calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 6),
            "wall_seconds": round(self.wall_seconds, 3),
        }


class TransportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    tokens_in: int
    tokens_out: int
    network: bool                     # False in every dry-run, always
    provider_seed_honored: bool | None = None


class NoNetworkTransport:
    """Dry-run transport: zero network by construction. Deterministic."""

    network = False

    def __init__(self) -> None:
        self.sends = 0

    def send(self, prompt: str, config: SmokeConfig) -> TransportResult:
        self.sends += 1
        return TransportResult(
            text=f"dry-run-response:{len(prompt)}:{self.sends}",
            tokens_in=len(prompt) // CHARS_PER_TOKEN,
            tokens_out=min(32, config.caps.max_output_tokens_per_call),
            network=False,
            provider_seed_honored=None,
        )


def build_openai_transport(config: SmokeConfig):
    """Build the REAL transport. Only reachable through :func:`build_provider`
    in live mode, i.e. behind the full authorization chain. The key value is
    read from the environment INSIDE each send and never stored."""
    from openai import OpenAI  # lazy: never imported in dry-run/tests

    class _OpenAITransport:
        network = True

        def send(self, prompt: str, cfg: SmokeConfig) -> TransportResult:
            client = OpenAI(  # key read lazily, kept in the SDK client only
                api_key=os.environ[cfg.api_key_env],
                timeout=cfg.request_timeout_seconds,
            )
            response = client.chat.completions.create(
                model=cfg.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=cfg.temperature,
                max_tokens=cfg.caps.max_output_tokens_per_call,
                seed=cfg.request_seed,
            )
            usage = response.usage
            return TransportResult(
                text=response.choices[0].message.content or "",
                tokens_in=usage.prompt_tokens if usage else len(prompt) // CHARS_PER_TOKEN,
                tokens_out=usage.completion_tokens if usage else 0,
                network=True,
                provider_seed_honored=(
                    getattr(response, "system_fingerprint", None) is not None
                    if cfg.request_seed is not None
                    else None
                ),
            )

    return _OpenAITransport()


class LiveProvider:
    """Same duck-typed interface as FakeProvider (``complete``), backed by an
    injected transport and the shared BudgetGuard. Retries per policy; a call
    failing after retries raises LiveCallError (run INVALID, not low-scored)."""

    def __init__(self, config: SmokeConfig, guard: BudgetGuard, transport) -> None:
        self._config = config
        self._guard = guard
        self._transport = transport
        self.results: list[TransportResult] = []
        self.retries_used = 0

    def complete(self, uid: StepUid, effective_prompt: str) -> ProviderCall:
        est_in = int(len(effective_prompt) / CHARS_PER_TOKEN * EST_SAFETY) + 1
        self._guard.precheck(est_in)  # refuse BEFORE, never after
        last_error: Exception | None = None
        for attempt in range(self._config.retry.max_retries + 1):
            try:
                result = self._transport.send(effective_prompt, self._config)
                break
            except Exception as exc:  # provider errors only; guard errors re-raise above
                last_error = exc
                self.retries_used += 1
                if attempt >= self._config.retry.max_retries:
                    raise LiveCallError(
                        f"provider call failed after {attempt + 1} attempt(s): {exc}"
                    ) from exc
                time.sleep(self._config.retry.backoff_seconds)
        self._guard.commit(result.tokens_in, result.tokens_out)
        self.results.append(result)
        import hashlib

        return ProviderCall(
            role=uid.role,
            step_kind=uid.step_kind,
            task_ref=uid.task_ref,
            attempt=uid.attempt,
            effective_prompt_hash="sha256:"
            + hashlib.sha256(effective_prompt.encode("utf-8")).hexdigest(),
            response_text=result.text,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
        )


Mode = Literal["dry_run", "live"]


def build_provider(config: SmokeConfig, guard: BudgetGuard, mode: Mode) -> LiveProvider:
    """The ONLY constructor for smoke providers. Live mode is refused unless
    the full authorization chain holds."""
    if mode == "dry_run":
        return LiveProvider(config, guard, NoNetworkTransport())
    if not config.live_execution_authorized:
        raise LiveExecutionNotAuthorized(
            "live_execution_authorized is False — live smoke refused"
        )
    if config.authorized_budget_usd is None:
        raise LiveExecutionNotAuthorized("no explicit authorized budget — refused")
    if config.api_key_env not in os.environ:
        raise LiveExecutionNotAuthorized(
            f"environment variable {config.api_key_env} not present — refused "
            f"(checked by NAME only)"
        )
    return LiveProvider(config, guard, build_openai_transport(config))
