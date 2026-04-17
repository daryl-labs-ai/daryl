"""
Tests for classify_rejection_reason (F1 table from SPEC §6).

Backlog: V0-05.
"""
from __future__ import annotations

import pytest

from dsm.multiversx.errors import classify_rejection_reason


class TestClassifyRejectionReason:
    """Exact F1 table coverage — one test per row plus unknown + empty."""

    def test_lower_nonce_is_retryable(self) -> None:
        assert classify_rejection_reason("lower nonce in transaction") is True

    def test_higher_nonce_is_retryable(self) -> None:
        assert classify_rejection_reason("higher nonce in transaction") is True

    def test_insufficient_funds_is_not_retryable(self) -> None:
        assert classify_rejection_reason("insufficient funds") is False

    def test_invalid_signature_is_not_retryable(self) -> None:
        assert classify_rejection_reason("invalid signature") is False

    def test_gas_limit_too_low_is_retryable(self) -> None:
        assert classify_rejection_reason("gas limit too low") is True

    def test_chain_id_mismatch_is_not_retryable(self) -> None:
        assert classify_rejection_reason("chain id mismatch") is False

    def test_transaction_size_too_big_is_not_retryable(self) -> None:
        assert classify_rejection_reason("transaction size too big") is False

    def test_unknown_message_is_retryable(self) -> None:
        assert classify_rejection_reason("some brand new gateway error text") is True

    def test_empty_string_is_retryable(self) -> None:
        assert classify_rejection_reason("") is True

    def test_case_insensitive_substring_match(self) -> None:
        # Sentinel substring embedded in mixed-case surrounding text.
        assert classify_rejection_reason("ERROR: Insufficient Funds for tx") is False
        assert classify_rejection_reason("Note: LOWER Nonce In Transaction") is True
