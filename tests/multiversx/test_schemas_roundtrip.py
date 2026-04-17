"""
Round-trip tests for every AnchorLogEntry subclass.

Backlog: V0-01.

Contract:
    - construct → model_dump() → parse_anchor_log_entry() → equal to original
    - missing/unknown entry_type raises PayloadError
    - pydantic.ValidationError is translated to PayloadError at the boundary
    - optional contextual fields may be absent (I5 / I6 regression guard)
"""
from __future__ import annotations

import uuid

import pytest

from dsm.multiversx.errors import PayloadError
from dsm.multiversx.schemas import (
    AnchorFailedEntry,
    AnchorIncludedEntry,
    AnchorIntent,
    AnchorReconciledEntry,
    AnchorRejectedEntry,
    AnchorSettledEntry,
    AnchorStuckEntry,
    AnchorSubmittedEntry,
    AnchorTimedOutEntry,
    parse_anchor_log_entry,
)

INTENT = uuid.UUID("00000000-0000-4000-8000-0000000000aa")
LAST_HASH = "0x" + "ab" * 32


def _roundtrip(entry) -> None:
    """Dump, re-parse, and assert equality."""
    dumped = entry.model_dump(mode="json")
    parsed = parse_anchor_log_entry(dumped)
    assert parsed == entry


class TestRoundTrip:
    def test_anchor_intent(self) -> None:
        entry = AnchorIntent(
            intent_id=INTENT,
            shard_id="sessions",
            last_hash=LAST_HASH,
            entry_nonce=1,
            epoch_regime="supernova",
        )
        _roundtrip(entry)

    def test_anchor_submitted(self) -> None:
        entry = AnchorSubmittedEntry(
            intent_id=INTENT,
            tx_hash="0xtx",
            submitted_at_ms=1,
            sender_nonce=1,
            gas_limit=300_000,
            gas_price=1_000_000_000,
        )
        _roundtrip(entry)

    def test_anchor_included(self) -> None:
        entry = AnchorIncludedEntry(
            intent_id=INTENT,
            tx_hash="0xtx",
            block_nonce=10,
            block_hash="0xblk",
            shard=0,
            header_time_ms=2,
            consensus_proof_observed_at_ms=3,
        )
        _roundtrip(entry)

    def test_anchor_settled(self) -> None:
        entry = AnchorSettledEntry(
            intent_id=INTENT,
            executed_in_block_nonce=11,
            execution_result_hash="0xexec",
            gas_used=50_000,
            developer_fees="0",
            settled_at_ms=4,
            schema_path_used="supernova_lastExecutionResult",
        )
        _roundtrip(entry)

    def test_anchor_failed(self) -> None:
        entry = AnchorFailedEntry(
            intent_id=INTENT,
            reason="out-of-gas",
            gas_used=49_999,
            return_message="oog",
            failed_in_block_nonce=12,
        )
        _roundtrip(entry)

    def test_anchor_rejected(self) -> None:
        entry = AnchorRejectedEntry(
            intent_id=INTENT,
            http_status=400,
            proxy_error_message="invalid signature",
            retry_eligible=False,
        )
        _roundtrip(entry)

    def test_anchor_timed_out(self) -> None:
        entry = AnchorTimedOutEntry(
            intent_id=INTENT,
            tx_hash="0xtx",
            elapsed_ms=60_000,
            last_observed_block_nonce=9,
            timeout_phase="t1_inclusion",
        )
        _roundtrip(entry)

    def test_anchor_stuck(self) -> None:
        entry = AnchorStuckEntry(
            intent_id=INTENT, tx_hash="0xtx", elapsed_ms=600_000
        )
        _roundtrip(entry)

    def test_anchor_reconciled(self) -> None:
        entry = AnchorReconciledEntry(
            intent_id=INTENT,
            shard_id="sessions",
            local_tail_last_hash=LAST_HASH,
            on_chain_last_hash=LAST_HASH,
            reconciled_at_ms=5,
            reconciliation_verdict="match",
        )
        _roundtrip(entry)


class TestDispatchErrors:
    def test_missing_entry_type_raises(self) -> None:
        with pytest.raises(PayloadError, match="entry_type is missing"):
            parse_anchor_log_entry({"intent_id": str(INTENT)})

    def test_unknown_entry_type_raises(self) -> None:
        with pytest.raises(PayloadError, match="unknown entry_type"):
            parse_anchor_log_entry(
                {"entry_type": "anchor_banana", "intent_id": str(INTENT)}
            )

    def test_non_dict_input_raises(self) -> None:
        with pytest.raises(PayloadError, match="expects a dict"):
            parse_anchor_log_entry("not a dict")  # type: ignore[arg-type]


class TestValidationErrorTranslation:
    """pydantic.ValidationError is translated to PayloadError at the boundary."""

    def test_missing_required_core_field(self) -> None:
        # Missing entry_nonce from anchor_intent.
        payload = {
            "entry_type": "anchor_intent",
            "intent_id": str(INTENT),
            "shard_id": "sessions",
            "last_hash": LAST_HASH,
            "epoch_regime": "supernova",
        }
        with pytest.raises(PayloadError, match="validation failed"):
            parse_anchor_log_entry(payload)

    def test_invalid_last_hash_pattern(self) -> None:
        payload = {
            "entry_type": "anchor_intent",
            "intent_id": str(INTENT),
            "shard_id": "sessions",
            "last_hash": "not-a-hash",
            "entry_nonce": 1,
            "epoch_regime": "supernova",
        }
        with pytest.raises(PayloadError):
            parse_anchor_log_entry(payload)

    def test_negative_entry_nonce(self) -> None:
        payload = {
            "entry_type": "anchor_intent",
            "intent_id": str(INTENT),
            "shard_id": "sessions",
            "last_hash": LAST_HASH,
            "entry_nonce": -1,
            "epoch_regime": "supernova",
        }
        with pytest.raises(PayloadError):
            parse_anchor_log_entry(payload)

    def test_validation_error_chained_as_cause(self) -> None:
        payload = {
            "entry_type": "anchor_intent",
            "intent_id": str(INTENT),
            "shard_id": "sessions",
            "last_hash": "bad",
            "entry_nonce": 1,
            "epoch_regime": "supernova",
        }
        try:
            parse_anchor_log_entry(payload)
        except PayloadError as exc:
            assert exc.__cause__ is not None
            from pydantic import ValidationError

            assert isinstance(exc.__cause__, ValidationError)
        else:
            pytest.fail("expected PayloadError")


class TestOptionalFieldsAbsent:
    """I5 / I6: optional contextual fields may be absent without error."""

    def test_anchor_intent_without_network_config_snapshot(self) -> None:
        """AnchorIntent: only the 4 core fields required; snapshot absent OK."""
        payload = {
            "entry_type": "anchor_intent",
            "intent_id": str(INTENT),
            "shard_id": "sessions",
            "last_hash": LAST_HASH,
            "entry_nonce": 1,
            "epoch_regime": "supernova",
        }
        entry = parse_anchor_log_entry(payload)
        assert isinstance(entry, AnchorIntent)
        assert entry.network_config_snapshot is None
        assert entry.adapter_version is None
        assert entry.signature_ed25519 is None

    def test_anchor_settled_without_schema_path_used(self) -> None:
        payload = {
            "entry_type": "anchor_settled",
            "intent_id": str(INTENT),
            "executed_in_block_nonce": 11,
            "gas_used": 50_000,
            "settled_at_ms": 4,
        }
        entry = parse_anchor_log_entry(payload)
        assert isinstance(entry, AnchorSettledEntry)
        assert entry.schema_path_used is None
        assert entry.execution_result_hash is None

    def test_anchor_failed_with_only_required_fields(self) -> None:
        payload = {
            "entry_type": "anchor_failed",
            "intent_id": str(INTENT),
            "reason": "out-of-gas",
        }
        entry = parse_anchor_log_entry(payload)
        assert isinstance(entry, AnchorFailedEntry)
        assert entry.gas_used is None
        assert entry.failed_in_block_nonce is None
