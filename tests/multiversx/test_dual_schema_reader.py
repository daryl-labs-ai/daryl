"""
Tests for the dual-schema reader.

Backlog: V1-06.

The dual-schema reader is the single riskiest piece of the compatibility
window (F5). It must:
    1. Correctly parse the Supernova `lastExecutionResult` shape.
    2. Correctly parse the Andromeda top-level `rootHash`/`stateRootHash`
       shape.
    3. Log which path was taken for every read (critical for auditing
       the transition window).
    4. Raise SchemaUnknownError when neither path applies, never silently
       guess.

Fixtures use synthetic block/tx dicts shaped after the documented API
responses; they are NOT fetched from a live gateway in scaffolded tests.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="V1-06 scaffold: dual-schema reader not implemented"
)


class TestSupernovaPath:
    """Blocks with `lastExecutionResult` field parse via supernova path."""

    def test_happy_path_success(self) -> None:
        """Settling block with lastExecutionResult.status='success' returns ExecutionResult with status='success' and schema_path_used='supernova_lastExecutionResult'."""
        raise NotImplementedError

    def test_happy_path_fail(self) -> None:
        """Settling block with lastExecutionResult.status='fail' returns ExecutionResult with status='fail'."""
        raise NotImplementedError

    def test_gas_used_extracted(self) -> None:
        """gas_used field in the output matches the settling block's data."""
        raise NotImplementedError

    def test_developer_fees_default_to_zero(self) -> None:
        """Missing developer_fees in the response defaults to '0'."""
        raise NotImplementedError


class TestAndromedaPath:
    """Blocks without `lastExecutionResult` parse via the legacy path."""

    def test_happy_path_from_tx_response(self) -> None:
        """Containing block with top-level rootHash + tx.status='success' parses via andromeda_top_level."""
        raise NotImplementedError

    def test_execution_fail_via_status_field(self) -> None:
        """tx.status='fail' on the andromeda path yields ExecutionResult.status='fail'."""
        raise NotImplementedError


class TestDualMode:
    """sdk_schema='dual' tries supernova first, falls back to andromeda."""

    def test_prefers_supernova_when_both_present(self) -> None:
        """If a settling block has lastExecutionResult, use it even if the tx's block also has top-level rootHash."""
        raise NotImplementedError

    def test_falls_back_to_andromeda_when_no_settling_block(self) -> None:
        """settling_block=None → parse via andromeda path without raising."""
        raise NotImplementedError


class TestLegacyOnlyMode:
    """sdk_schema='legacy_only' never consults lastExecutionResult."""

    def test_ignores_supernova_field(self) -> None:
        """Even if lastExecutionResult is present, legacy_only uses andromeda path."""
        raise NotImplementedError

    def test_raises_on_andromeda_missing(self) -> None:
        """legacy_only + no andromeda fields → SchemaUnknownError."""
        raise NotImplementedError


class TestNewOnlyMode:
    """sdk_schema='new_only' refuses legacy-shaped blocks."""

    def test_happy_path(self) -> None:
        """new_only + supernova-shaped block → parses."""
        raise NotImplementedError

    def test_raises_on_legacy_shape(self) -> None:
        """new_only + legacy-shaped block → SchemaUnknownError."""
        raise NotImplementedError


class TestSchemaUnknownError:
    """When neither path applies, the reader raises, never silently guesses."""

    def test_both_paths_fail_raises(self) -> None:
        """Block with no lastExecutionResult and no rootHash → SchemaUnknownError."""
        raise NotImplementedError

    def test_error_carries_diagnostic_payload(self) -> None:
        """SchemaUnknownError includes the offending block dict for operator diagnosis."""
        raise NotImplementedError


class TestPathLogging:
    """Every successful read records which path was used."""

    def test_supernova_path_logged(self) -> None:
        """ExecutionResult.schema_path_used == 'supernova_lastExecutionResult' after supernova parse."""
        raise NotImplementedError

    def test_andromeda_path_logged(self) -> None:
        """ExecutionResult.schema_path_used == 'andromeda_top_level' after andromeda parse."""
        raise NotImplementedError


class TestF5Disagreement:
    """When both paths are present AND produce different results (should never happen in practice)."""

    def test_prefers_supernova_on_disagreement(self) -> None:
        """Supernova path wins; mismatch is logged at WARNING level.

        TODO[V1-06]: confirm with MultiversX team whether this case is
        possible or whether the gateway guarantees consistency.
        """
        raise NotImplementedError
