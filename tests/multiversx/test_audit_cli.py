"""
Tests for the audit CLI (`dsm verify --mvx`).

Backlog: V1-20.

Acceptance criteria (from BACKLOG.md):
    - Log with 10 intents across both regimes; audit passes iff all 10
      match on-chain.
    - Exit code 0 / 1 / 2 for ok / mismatch / error.
    - Regime-specific rules enforced: supernova anchors require anchor_settled
      (not just anchor_included) before being considered valid.

Structured into:
    - unit tests on audit_shard() with a fake storage and fake backend
    - tests on iter_intents_with_terminal_states()
    - end-to-end CLI tests invoking cli_main() with custom argv

These tests require the backend's verify() and the DSM storage interface.
They are skipped at scaffold stage; remove pytest.skip once V1-20 is
implemented.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="V1-20 scaffold: audit CLI not implemented"
)


class TestAuditShardHappyPath:
    """All intents pass every check."""

    def test_10_settled_intents_all_ok(self) -> None:
        """10 AnchorIntent + 10 AnchorSettled entries, all matching on-chain → 10 ok."""
        raise NotImplementedError

    def test_exit_code_zero(self) -> None:
        """AuditReport.exit_code() returns 0 when no mismatches or errors."""
        raise NotImplementedError


class TestAuditShardMismatch:
    """Some intents diverge from on-chain data."""

    def test_wrong_last_hash_reports_mismatch(self) -> None:
        """
        Intent has last_hash=X. On-chain payload decodes to last_hash=Y.
        Report should count this as mismatch, not ok.
        """
        raise NotImplementedError

    def test_timestamp_skew_exceeds_threshold_reports_mismatch(self) -> None:
        """
        Intent.network_config_snapshot.captured_at_ms and the block's
        header_time_ms differ by more than max_clock_skew_ms → mismatch.
        """
        raise NotImplementedError

    def test_exit_code_one_on_mismatch(self) -> None:
        """Any mismatch → exit code 1."""
        raise NotImplementedError


class TestAuditShardRegimeSemantics:
    """SPEC §7.2: supernova requires anchor_settled; incomplete → pending."""

    def test_supernova_included_but_not_settled_is_pending(self) -> None:
        """
        Most important regime-specific test.
        Intent has epoch_regime='supernova'. Log has AnchorIncludedEntry
        but no AnchorSettledEntry. verify() returns verdict='pending',
        NOT 'ok'.
        """
        raise NotImplementedError

    def test_andromeda_settled_required_for_ok(self) -> None:
        """
        Even under andromeda, adapter emits anchor_settled for regime-
        agnostic audit. Absence of settled → pending, not ok.
        """
        raise NotImplementedError

    def test_mixed_regime_log_audit(self) -> None:
        """
        Log contains both andromeda and supernova anchors (transition-window
        case). Audit handles each by its own epoch_regime tag.
        """
        raise NotImplementedError


class TestAuditShardExecutionFailure:
    """Anchors whose on-chain execution failed are reported correctly."""

    def test_failed_entry_reports_execution_failed(self) -> None:
        """
        Log has AnchorIntent + AnchorFailedEntry. verify() returns
        verdict='execution_failed'. NOT 'mismatch'; they are distinct.
        """
        raise NotImplementedError


class TestAuditShardNotFound:
    """Anchors whose tx_hash doesn't exist on the gateway."""

    def test_missing_tx_reports_not_found(self) -> None:
        """
        Log has AnchorIntent + AnchorSubmittedEntry but gateway returns
        404 on the tx. verify() returns verdict='not_found'.
        """
        raise NotImplementedError

    def test_exit_code_one_on_not_found(self) -> None:
        """not_found is actionable — exit 1."""
        raise NotImplementedError


class TestAuditShardErrors:
    """Gateway unreachable, storage corrupt, etc."""

    def test_gateway_unreachable_reports_error(self) -> None:
        """NetworkError during verify → AuditReport.errors incremented."""
        raise NotImplementedError

    def test_exit_code_two_on_error(self) -> None:
        """Any error → exit 2."""
        raise NotImplementedError

    def test_storage_unreadable_raises_audit_error(self) -> None:
        """audit_shard() raises AuditError if storage.read() raises."""
        raise NotImplementedError


class TestIterIntentsWithTerminalStates:
    """The iterator that pairs intents with their terminal entries."""

    def test_pairs_intent_with_settled(self) -> None:
        """Each AnchorIntent with a matching AnchorSettledEntry → paired."""
        raise NotImplementedError

    def test_pairs_intent_with_failed(self) -> None:
        """Each AnchorIntent with a matching AnchorFailedEntry → paired."""
        raise NotImplementedError

    def test_intent_without_terminal_yields_none(self) -> None:
        """Intents with no terminal entry → second element is None."""
        raise NotImplementedError

    def test_intent_id_matching(self) -> None:
        """
        Entries with the same intent_id are paired; entries with different
        intent_ids are not accidentally paired.
        """
        raise NotImplementedError

    def test_preserves_log_order(self) -> None:
        """Iterator preserves the order in which intents appear in the log."""
        raise NotImplementedError


class TestCliMain:
    """End-to-end CLI behavior via cli_main(argv)."""

    def test_happy_path_exit_zero(self) -> None:
        """Full CLI invocation against a fixture log; exit code 0."""
        raise NotImplementedError

    def test_missing_shard_arg_exit_two(self) -> None:
        """argparse error on missing --shard → exit code 2."""
        raise NotImplementedError

    def test_json_output_format(self) -> None:
        """--format=json emits parseable JSON to stdout."""
        raise NotImplementedError

    def test_text_output_format(self) -> None:
        """--format=text emits human-readable summary."""
        raise NotImplementedError

    def test_custom_clock_skew(self) -> None:
        """--max-clock-skew-ms is honored."""
        raise NotImplementedError

    def test_custom_config_path(self) -> None:
        """--config points at a custom adapter TOML."""
        raise NotImplementedError
