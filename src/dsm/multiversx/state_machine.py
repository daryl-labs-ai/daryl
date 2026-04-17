"""
Three-stage anchor state machine.

Backlog: V0-03.

Pure, side-effect-free state machine mapping (current_state, event, regime)
to (new_state, entry_to_emit). No I/O, no time reads, no randomness. All
time/nonce/hash context arrives through the event payload.

States (from schemas.AnchorState):

    INTENT_LOGGED ──[Submit]──▶ SUBMITTED
         ▲                        │
         │                        ├─[Include]──▶ INCLUDED
         │                        │                │
         │                        │                ├─[ExecSuccess]──▶ SETTLED (terminal)
         │                        │                ├─[ExecFail]─────▶ FAILED  (terminal)
         │                        │                ├─[StuckTimeout]─▶ STUCK
         │                        │                └─[T3Timeout]────▶ TIMED_OUT
         │                        │
         │                        ├─[Reject]───▶ REJECTED (terminal)
         │                        ├─[T1Timeout]▶ TIMED_OUT
         │                        └─[StuckTimeout]▶ STUCK
         │
         └─[Retry (from TIMED_OUT, with new tx)]─▶ SUBMITTED

Regime collapse rule (SPEC §4):
    - Under `supernova`, INCLUDED and SETTLED are distinct: SETTLED is emitted
      only when `ExecSuccess` is observed.
    - Under `andromeda`, INCLUDED is still a distinct transition and entry.
      An additional synthetic `ExecSuccess` event must be emitted by the
      watcher simultaneously (or immediately after) the `Include` event,
      so the state machine is regime-agnostic.

This design keeps the state machine regime-oblivious. The watcher, not this
module, is responsible for synthesizing `ExecSuccess` under andromeda.

Invariants:
    - `next_state(state, event, regime)` is a pure function.
    - Every valid transition returns exactly one entry (AnchorLogEntry).
    - Every invalid (state, event) pair raises InvalidTransition.
    - The function never inspects real wall-clock time; timestamps MUST be
      provided via the event object.
    - **The state machine NEVER interprets blockchain semantics.** It does
      not decode blocks, parse execution results, compare hashes, or reason
      about the chain. It only advances state based on events that the
      watcher has already normalized. Any future change that introduces
      chain-awareness at this layer defeats the regime-agnostic design and
      must be rejected at review.

Failure modes:
    - InvalidTransition: the transition is not defined for (state, event).
    - PayloadError: event fields fail schema validation (delegated to pydantic).

Test file: tests/multiversx/test_state_machine.py
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, Optional, Union

from dsm.multiversx.errors import InvalidTransition
from dsm.multiversx.schemas import (
    AnchorFailedEntry,
    AnchorIncludedEntry,
    AnchorLogEntry,
    AnchorRejectedEntry,
    AnchorSettledEntry,
    AnchorState,
    AnchorStuckEntry,
    AnchorSubmittedEntry,
    AnchorTimedOutEntry,
    EpochRegime,
)

# ---------------------------------------------------------------------------
# Event types — inputs to next_state()
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubmitEvent:
    """Application is about to submit the tx. Carries submission metadata."""

    intent_id: uuid.UUID
    tx_hash: str
    submitted_at_ms: int
    sender_nonce: int
    gas_limit: int
    gas_price: int


@dataclass(frozen=True)
class IncludeEvent:
    """Watcher observed the tx in a finalized block (T₂)."""

    intent_id: uuid.UUID
    tx_hash: str
    block_nonce: int
    block_hash: str
    shard: int
    header_time_ms: int
    consensus_proof_observed_at_ms: int


@dataclass(frozen=True)
class ExecSuccessEvent:
    """Watcher observed the ExecutionResult for the included block (T₃).

    Under andromeda, the watcher synthesizes this alongside IncludeEvent.
    Under supernova, it arrives one or more blocks later.
    """

    intent_id: uuid.UUID
    executed_in_block_nonce: int
    execution_result_hash: str
    gas_used: int
    developer_fees: str
    settled_at_ms: int
    schema_path_used: str


@dataclass(frozen=True)
class ExecFailEvent:
    """Watcher observed ExecutionResult.status == fail."""

    intent_id: uuid.UUID
    reason: str
    gas_used: int
    return_message: str
    failed_in_block_nonce: int


@dataclass(frozen=True)
class RejectEvent:
    """Gateway rejected the submission before inclusion."""

    intent_id: uuid.UUID
    http_status: int
    proxy_error_message: str
    retry_eligible: bool


@dataclass(frozen=True)
class T1TimeoutEvent:
    """t1_timeout_ms elapsed without observing inclusion."""

    intent_id: uuid.UUID
    tx_hash: str
    elapsed_ms: int
    last_observed_block_nonce: Optional[int]


@dataclass(frozen=True)
class T3TimeoutEvent:
    """t3_timeout_ms elapsed after inclusion without observing settlement."""

    intent_id: uuid.UUID
    tx_hash: str
    elapsed_ms: int
    last_observed_block_nonce: Optional[int]


@dataclass(frozen=True)
class StuckTimeoutEvent:
    """stuck_threshold_ms elapsed; operator intervention required."""

    intent_id: uuid.UUID
    tx_hash: Optional[str]
    elapsed_ms: int


AnchorTransitionEvent = Union[
    SubmitEvent,
    IncludeEvent,
    ExecSuccessEvent,
    ExecFailEvent,
    RejectEvent,
    T1TimeoutEvent,
    T3TimeoutEvent,
    StuckTimeoutEvent,
]
"""Union of all events the state machine accepts."""


# ---------------------------------------------------------------------------
# Transition result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransitionResult:
    """Result of a single state machine step.

    `entry_to_emit` must be appended to the DSM log by the caller. The state
    machine itself does not perform I/O.
    """

    new_state: AnchorState
    entry_to_emit: AnchorLogEntry


# ---------------------------------------------------------------------------
# Transition function
# ---------------------------------------------------------------------------


def next_state(
    current: AnchorState,
    event: AnchorTransitionEvent,
    regime: EpochRegime,
) -> TransitionResult:
    """Compute the next state and the entry to emit for a single event.

    Args:
        current: The current state of the anchor round-trip.
        event: The observed event.
        regime: The current network regime. Used only to validate transitions;
            event types themselves are regime-agnostic (the watcher normalizes
            them before calling into this function).

    Returns:
        TransitionResult with the new state and the entry to append to the
        DSM log.

    Raises:
        InvalidTransition: If `event` is not a valid transition from `current`.

    Invariants:
        - Pure function. No I/O. No time reads.
        - **Never interprets blockchain semantics.** The state machine is
          regime-agnostic. Regime-specific normalization (e.g. synthesizing
          ExecSuccessEvent from an Andromeda-style inclusion) happens in
          the watcher, not here.
        - Terminal states (SETTLED, FAILED, REJECTED) MUST NOT accept any
          further events; any call with these as `current` raises
          InvalidTransition.
        - `event.intent_id` is carried into the emitted entry unchanged.

    Test file: tests/multiversx/test_state_machine.py
    """
    handler = _DISPATCH.get((current, type(event)))
    if handler is None:
        raise InvalidTransition(
            f"no transition defined for "
            f"(state={current.name}, event={type(event).__name__})"
        )
    return handler(event, regime)


def _from_intent_logged_submit(
    event: SubmitEvent, regime: EpochRegime
) -> TransitionResult:
    return TransitionResult(
        new_state=AnchorState.SUBMITTED,
        entry_to_emit=AnchorSubmittedEntry(
            intent_id=event.intent_id,
            tx_hash=event.tx_hash,
            submitted_at_ms=event.submitted_at_ms,
            sender_nonce=event.sender_nonce,
            gas_limit=event.gas_limit,
            gas_price=event.gas_price,
        ),
    )


def _from_submitted_include(
    event: IncludeEvent, regime: EpochRegime
) -> TransitionResult:
    return TransitionResult(
        new_state=AnchorState.INCLUDED,
        entry_to_emit=AnchorIncludedEntry(
            intent_id=event.intent_id,
            tx_hash=event.tx_hash,
            block_nonce=event.block_nonce,
            block_hash=event.block_hash,
            shard=event.shard,
            header_time_ms=event.header_time_ms,
            consensus_proof_observed_at_ms=event.consensus_proof_observed_at_ms,
        ),
    )


def _from_submitted_reject(
    event: RejectEvent, regime: EpochRegime
) -> TransitionResult:
    return TransitionResult(
        new_state=AnchorState.REJECTED,
        entry_to_emit=AnchorRejectedEntry(
            intent_id=event.intent_id,
            http_status=event.http_status,
            proxy_error_message=event.proxy_error_message,
            retry_eligible=event.retry_eligible,
        ),
    )


def _from_submitted_t1_timeout(
    event: T1TimeoutEvent, regime: EpochRegime
) -> TransitionResult:
    return TransitionResult(
        new_state=AnchorState.TIMED_OUT,
        entry_to_emit=AnchorTimedOutEntry(
            intent_id=event.intent_id,
            tx_hash=event.tx_hash,
            elapsed_ms=event.elapsed_ms,
            last_observed_block_nonce=event.last_observed_block_nonce,
            timeout_phase="t1_inclusion",
        ),
    )


def _from_submitted_stuck(
    event: StuckTimeoutEvent, regime: EpochRegime
) -> TransitionResult:
    return TransitionResult(
        new_state=AnchorState.STUCK,
        entry_to_emit=AnchorStuckEntry(
            intent_id=event.intent_id,
            tx_hash=event.tx_hash,
            elapsed_ms=event.elapsed_ms,
        ),
    )


def _from_included_exec_success(
    event: ExecSuccessEvent, regime: EpochRegime
) -> TransitionResult:
    return TransitionResult(
        new_state=AnchorState.SETTLED,
        entry_to_emit=AnchorSettledEntry(
            intent_id=event.intent_id,
            executed_in_block_nonce=event.executed_in_block_nonce,
            execution_result_hash=event.execution_result_hash,
            gas_used=event.gas_used,
            developer_fees=event.developer_fees,
            settled_at_ms=event.settled_at_ms,
            schema_path_used=event.schema_path_used,  # type: ignore[arg-type]
        ),
    )


def _from_included_exec_fail(
    event: ExecFailEvent, regime: EpochRegime
) -> TransitionResult:
    return TransitionResult(
        new_state=AnchorState.FAILED,
        entry_to_emit=AnchorFailedEntry(
            intent_id=event.intent_id,
            reason=event.reason,
            gas_used=event.gas_used,
            return_message=event.return_message,
            failed_in_block_nonce=event.failed_in_block_nonce,
        ),
    )


def _from_included_t3_timeout(
    event: T3TimeoutEvent, regime: EpochRegime
) -> TransitionResult:
    # Under andromeda, T₂ ≡ T₃ and the watcher synthesizes settlement
    # alongside inclusion; a T3 timeout from INCLUDED is a watcher bug.
    if regime == "andromeda":
        raise InvalidTransition(
            "T3TimeoutEvent is not expected from INCLUDED under regime=andromeda "
            "(T₂ ≡ T₃; watcher should synthesize ExecSuccessEvent with inclusion)"
        )
    return TransitionResult(
        new_state=AnchorState.TIMED_OUT,
        entry_to_emit=AnchorTimedOutEntry(
            intent_id=event.intent_id,
            tx_hash=event.tx_hash,
            elapsed_ms=event.elapsed_ms,
            last_observed_block_nonce=event.last_observed_block_nonce,
            timeout_phase="t3_settlement",
        ),
    )


def _from_included_stuck(
    event: StuckTimeoutEvent, regime: EpochRegime
) -> TransitionResult:
    return TransitionResult(
        new_state=AnchorState.STUCK,
        entry_to_emit=AnchorStuckEntry(
            intent_id=event.intent_id,
            tx_hash=event.tx_hash,
            elapsed_ms=event.elapsed_ms,
        ),
    )


def _from_timed_out_submit(
    event: SubmitEvent, regime: EpochRegime
) -> TransitionResult:
    # Retry with a new tx_hash (same intent_id).
    return TransitionResult(
        new_state=AnchorState.SUBMITTED,
        entry_to_emit=AnchorSubmittedEntry(
            intent_id=event.intent_id,
            tx_hash=event.tx_hash,
            submitted_at_ms=event.submitted_at_ms,
            sender_nonce=event.sender_nonce,
            gas_limit=event.gas_limit,
            gas_price=event.gas_price,
        ),
    )


# Dispatch table — declared after the handlers. Terminal states
# (SETTLED, FAILED, REJECTED) are intentionally absent: any event from those
# states falls through to the InvalidTransition raise in next_state().
#
# Each handler is typed `Callable[[SpecificEvent, EpochRegime], ...]` but the
# dispatch wants a single value type. Python's Callable is contravariant in
# its parameters, so a `Callable[[SubmitEvent, ...], ...]` is NOT a subtype
# of `Callable[[AnchorTransitionEvent, ...], ...]`. We use `Callable[..., ...]`
# (any-args) at the dict level; each handler is only ever invoked with an
# event of the type its signature declares, because the dispatch key
# includes `type(event)`.
_Handler = Callable[..., TransitionResult]
_DISPATCH: dict[tuple[AnchorState, type], _Handler] = {
    (AnchorState.INTENT_LOGGED, SubmitEvent): _from_intent_logged_submit,
    (AnchorState.SUBMITTED, IncludeEvent): _from_submitted_include,
    (AnchorState.SUBMITTED, RejectEvent): _from_submitted_reject,
    (AnchorState.SUBMITTED, T1TimeoutEvent): _from_submitted_t1_timeout,
    (AnchorState.SUBMITTED, StuckTimeoutEvent): _from_submitted_stuck,
    (AnchorState.INCLUDED, ExecSuccessEvent): _from_included_exec_success,
    (AnchorState.INCLUDED, ExecFailEvent): _from_included_exec_fail,
    (AnchorState.INCLUDED, T3TimeoutEvent): _from_included_t3_timeout,
    (AnchorState.INCLUDED, StuckTimeoutEvent): _from_included_stuck,
    (AnchorState.TIMED_OUT, SubmitEvent): _from_timed_out_submit,
}


def is_terminal(state: AnchorState) -> bool:
    """True iff `state` is a terminal state (no further events accepted).

    Terminal: SETTLED, FAILED, REJECTED.
    Non-terminal: everything else, including STUCK and TIMED_OUT.

    Test file: tests/multiversx/test_state_machine.py
    """
    return state in (AnchorState.SETTLED, AnchorState.FAILED, AnchorState.REJECTED)


def initial_state() -> AnchorState:
    """Return the initial state for a new anchor round-trip.

    The anchor flow begins with INTENT_LOGGED after the AnchorIntent has been
    written and fsynced locally (and before any network call per F12).
    """
    return AnchorState.INTENT_LOGGED
