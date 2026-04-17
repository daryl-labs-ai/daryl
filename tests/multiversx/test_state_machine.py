"""
Tests for the three-stage anchor state machine.

Backlog: V0-03.

Acceptance criteria (from BACKLOG.md):
    - Every valid transition in SPEC §4 has an explicit test.
    - Every invalid (state, event) pair raises InvalidTransition.
    - The state machine is a pure function (no I/O, no time reads).
"""
from __future__ import annotations

import uuid

import pytest

from dsm.multiversx.errors import InvalidTransition
from dsm.multiversx.schemas import (
    AnchorFailedEntry,
    AnchorIncludedEntry,
    AnchorRejectedEntry,
    AnchorSettledEntry,
    AnchorState,
    AnchorStuckEntry,
    AnchorSubmittedEntry,
    AnchorTimedOutEntry,
)
from dsm.multiversx.state_machine import (
    ExecFailEvent,
    ExecSuccessEvent,
    IncludeEvent,
    RejectEvent,
    StuckTimeoutEvent,
    SubmitEvent,
    T1TimeoutEvent,
    T3TimeoutEvent,
    next_state,
)

INTENT_A = uuid.UUID("00000000-0000-4000-8000-000000000001")
INTENT_B = uuid.UUID("00000000-0000-4000-8000-000000000002")


def _submit(tx_hash: str = "0xtx1") -> SubmitEvent:
    return SubmitEvent(
        intent_id=INTENT_A,
        tx_hash=tx_hash,
        submitted_at_ms=1_000,
        sender_nonce=5,
        gas_limit=300_000,
        gas_price=1_000_000_000,
    )


def _include(tx_hash: str = "0xtx1") -> IncludeEvent:
    return IncludeEvent(
        intent_id=INTENT_A,
        tx_hash=tx_hash,
        block_nonce=100,
        block_hash="0xblock",
        shard=0,
        header_time_ms=2_000,
        consensus_proof_observed_at_ms=2_100,
    )


def _exec_success() -> ExecSuccessEvent:
    return ExecSuccessEvent(
        intent_id=INTENT_A,
        executed_in_block_nonce=101,
        execution_result_hash="0xexec",
        gas_used=50_000,
        developer_fees="0",
        settled_at_ms=3_000,
        schema_path_used="supernova_lastExecutionResult",
    )


def _exec_fail() -> ExecFailEvent:
    return ExecFailEvent(
        intent_id=INTENT_A,
        reason="out-of-gas",
        gas_used=49_999,
        return_message="oog",
        failed_in_block_nonce=101,
    )


def _reject() -> RejectEvent:
    return RejectEvent(
        intent_id=INTENT_A,
        http_status=400,
        proxy_error_message="invalid signature",
        retry_eligible=False,
    )


def _t1() -> T1TimeoutEvent:
    return T1TimeoutEvent(
        intent_id=INTENT_A, tx_hash="0xtx1", elapsed_ms=60_000, last_observed_block_nonce=99
    )


def _t3() -> T3TimeoutEvent:
    return T3TimeoutEvent(
        intent_id=INTENT_A, tx_hash="0xtx1", elapsed_ms=120_000, last_observed_block_nonce=100
    )


def _stuck() -> StuckTimeoutEvent:
    return StuckTimeoutEvent(intent_id=INTENT_A, tx_hash="0xtx1", elapsed_ms=600_000)


# ---------------------------------------------------------------------------


class TestHappyPathSupernova:
    def test_intent_to_submitted(self) -> None:
        result = next_state(AnchorState.INTENT_LOGGED, _submit(), "supernova")
        assert result.new_state == AnchorState.SUBMITTED
        assert isinstance(result.entry_to_emit, AnchorSubmittedEntry)
        assert result.entry_to_emit.tx_hash == "0xtx1"
        assert result.entry_to_emit.intent_id == INTENT_A

    def test_submitted_to_included(self) -> None:
        result = next_state(AnchorState.SUBMITTED, _include(), "supernova")
        assert result.new_state == AnchorState.INCLUDED
        assert isinstance(result.entry_to_emit, AnchorIncludedEntry)
        assert result.entry_to_emit.block_nonce == 100

    def test_included_to_settled(self) -> None:
        result = next_state(AnchorState.INCLUDED, _exec_success(), "supernova")
        assert result.new_state == AnchorState.SETTLED
        assert isinstance(result.entry_to_emit, AnchorSettledEntry)
        assert result.entry_to_emit.executed_in_block_nonce == 101

    def test_settled_is_terminal(self) -> None:
        with pytest.raises(InvalidTransition):
            next_state(AnchorState.SETTLED, _submit(), "supernova")
        with pytest.raises(InvalidTransition):
            next_state(AnchorState.SETTLED, _include(), "supernova")


class TestHappyPathAndromeda:
    def test_intent_submitted_included_settled(self) -> None:
        # INTENT_LOGGED -> SUBMITTED
        r1 = next_state(AnchorState.INTENT_LOGGED, _submit(), "andromeda")
        assert r1.new_state == AnchorState.SUBMITTED
        # SUBMITTED -> INCLUDED
        r2 = next_state(r1.new_state, _include(), "andromeda")
        assert r2.new_state == AnchorState.INCLUDED
        # INCLUDED -> SETTLED (watcher synthesized ExecSuccessEvent alongside)
        r3 = next_state(r2.new_state, _exec_success(), "andromeda")
        assert r3.new_state == AnchorState.SETTLED


class TestFailurePaths:
    def test_submitted_to_rejected(self) -> None:
        result = next_state(AnchorState.SUBMITTED, _reject(), "supernova")
        assert result.new_state == AnchorState.REJECTED
        assert isinstance(result.entry_to_emit, AnchorRejectedEntry)
        assert result.entry_to_emit.proxy_error_message == "invalid signature"

    def test_submitted_to_timed_out_t1(self) -> None:
        result = next_state(AnchorState.SUBMITTED, _t1(), "supernova")
        assert result.new_state == AnchorState.TIMED_OUT
        assert isinstance(result.entry_to_emit, AnchorTimedOutEntry)
        assert result.entry_to_emit.timeout_phase == "t1_inclusion"

    def test_included_to_failed(self) -> None:
        result = next_state(AnchorState.INCLUDED, _exec_fail(), "supernova")
        assert result.new_state == AnchorState.FAILED
        assert isinstance(result.entry_to_emit, AnchorFailedEntry)
        assert result.entry_to_emit.reason == "out-of-gas"

    def test_included_to_timed_out_t3(self) -> None:
        result = next_state(AnchorState.INCLUDED, _t3(), "supernova")
        assert result.new_state == AnchorState.TIMED_OUT
        assert isinstance(result.entry_to_emit, AnchorTimedOutEntry)
        assert result.entry_to_emit.timeout_phase == "t3_settlement"

    def test_any_state_to_stuck(self) -> None:
        for state in (AnchorState.SUBMITTED, AnchorState.INCLUDED):
            result = next_state(state, _stuck(), "supernova")
            assert result.new_state == AnchorState.STUCK
            assert isinstance(result.entry_to_emit, AnchorStuckEntry)


class TestAndromedaT3TimeoutIsBug:
    """Review note: T3 timeout from INCLUDED under andromeda is a watcher bug."""

    def test_t3_from_included_andromeda_raises(self) -> None:
        with pytest.raises(InvalidTransition, match="andromeda"):
            next_state(AnchorState.INCLUDED, _t3(), "andromeda")


class TestRetryFromTimedOut:
    def test_timed_out_to_submitted_on_retry(self) -> None:
        retry = SubmitEvent(
            intent_id=INTENT_A,
            tx_hash="0xtx2",
            submitted_at_ms=5_000,
            sender_nonce=6,
            gas_limit=320_000,
            gas_price=1_000_000_000,
        )
        result = next_state(AnchorState.TIMED_OUT, retry, "supernova")
        assert result.new_state == AnchorState.SUBMITTED
        assert isinstance(result.entry_to_emit, AnchorSubmittedEntry)
        assert result.entry_to_emit.tx_hash == "0xtx2"

    def test_same_intent_id_across_retries(self) -> None:
        first = next_state(AnchorState.INTENT_LOGGED, _submit("0xtx1"), "supernova")
        retry = SubmitEvent(
            intent_id=INTENT_A,
            tx_hash="0xtx2",
            submitted_at_ms=5_000,
            sender_nonce=6,
            gas_limit=320_000,
            gas_price=1_000_000_000,
        )
        second = next_state(AnchorState.TIMED_OUT, retry, "supernova")
        assert first.entry_to_emit.intent_id == second.entry_to_emit.intent_id == INTENT_A


class TestInvalidTransitions:
    def test_submit_from_submitted_raises(self) -> None:
        with pytest.raises(InvalidTransition):
            next_state(AnchorState.SUBMITTED, _submit(), "supernova")

    def test_include_from_intent_logged_raises(self) -> None:
        with pytest.raises(InvalidTransition):
            next_state(AnchorState.INTENT_LOGGED, _include(), "supernova")

    def test_exec_success_from_submitted_raises(self) -> None:
        with pytest.raises(InvalidTransition):
            next_state(AnchorState.SUBMITTED, _exec_success(), "supernova")

    def test_events_from_terminal_states_all_raise(self) -> None:
        terminals = (AnchorState.SETTLED, AnchorState.FAILED, AnchorState.REJECTED)
        events = (
            _submit(),
            _include(),
            _exec_success(),
            _exec_fail(),
            _reject(),
            _t1(),
            _t3(),
            _stuck(),
        )
        for state in terminals:
            for event in events:
                with pytest.raises(InvalidTransition):
                    next_state(state, event, "supernova")


class TestPurity:
    def test_no_time_reads(self) -> None:
        """Two identical calls produce structurally equal results."""
        submit = _submit()
        r1 = next_state(AnchorState.INTENT_LOGGED, submit, "supernova")
        r2 = next_state(AnchorState.INTENT_LOGGED, submit, "supernova")
        assert r1 == r2

    def test_no_randomness(self) -> None:
        """Identical inputs always produce identical outputs (100 iterations)."""
        event = _include()
        expected = next_state(AnchorState.SUBMITTED, event, "supernova")
        for _ in range(100):
            assert next_state(AnchorState.SUBMITTED, event, "supernova") == expected
