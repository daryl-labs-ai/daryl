"""
Error hierarchy for the MultiversX anchor adapter.

Backlog: V0-05.

All errors inherit from MultiversXAnchorError. No error in this adapter
should leak as a bare Exception to the caller — the facade in anchor.py
expects a coherent hierarchy it can translate to DSM-level error codes.

Hierarchy:

    MultiversXAnchorError
        RegimeError              - regime detection or epoch handling
        PayloadError             - DSM01 codec, schema validation at boundary
        InvalidTransition        - state machine rejected the (state, event) pair
        SchemaUnknownError       - dual-schema reader cannot parse block
        SubmissionError          - submission-time failure
            RejectedByGateway    - explicit non-2xx from gateway
        NetworkError             - transport-level failure
        WatcherError             - watcher lifecycle failure
        AuditError               - audit CLI / verify() failure

Invariants:
    - Every error carries a human-readable `message`.
    - Errors that classify as retryable set `retry_eligible` truthy.
    - Never raise `Exception` directly; always pick a subclass.

Test file: tests/multiversx/test_errors.py
"""
from __future__ import annotations

from typing import Optional


class MultiversXAnchorError(Exception):
    """Base class for all errors raised by the MultiversX adapter."""

    retry_eligible: bool = False

    def __init__(self, message: str, *, retry_eligible: Optional[bool] = None) -> None:
        super().__init__(message)
        self.message = message
        if retry_eligible is not None:
            self.retry_eligible = retry_eligible


class RegimeError(MultiversXAnchorError):
    """Regime detection failed, or epoch handling produced an inconsistency.

    Raised only when the caller opted into strict refresh. Non-strict
    detection never raises this; it returns a fail-closed verdict instead.
    """


class PayloadError(MultiversXAnchorError):
    """DSM01 codec failure, or pydantic validation failure at the adapter boundary.

    Test file: tests/multiversx/test_payload_codec.py
    """


class InvalidTransition(MultiversXAnchorError):
    """State machine rejected the (current_state, event) pair.

    This is always a bug — either in the watcher (producing impossible
    events) or in the caller driving the state machine directly.
    """


class SchemaUnknownError(MultiversXAnchorError):
    """Dual-schema reader cannot identify which schema a block uses.

    Raised when neither the Supernova path (`lastExecutionResult`) nor the
    legacy path (top-level `rootHash` / `stateRootHash`) produces a valid
    ExecutionResult. Likely a third-party indexer lag (F5) or a new schema
    revision past the compatibility window.

    Test file: tests/multiversx/test_dual_schema_reader.py
    """


class SubmissionError(MultiversXAnchorError):
    """Raised when `submit()` cannot complete.

    Subclasses distinguish gateway-level rejection from transport-level failure.
    """


class RejectedByGateway(SubmissionError):
    """Explicit non-2xx response from the gateway, with a parsed error message.

    Carries the proxy error message verbatim for audit entry construction.
    See F1 in SPEC §6 for the rejection-reason table and retry eligibility.
    """

    def __init__(
        self,
        message: str,
        *,
        http_status: int,
        proxy_error_message: str,
        retry_eligible: bool,
    ) -> None:
        super().__init__(message, retry_eligible=retry_eligible)
        self.http_status = http_status
        self.proxy_error_message = proxy_error_message


class NetworkError(MultiversXAnchorError):
    """Transport-level failure (timeout, connection refused, 5xx).

    retry_eligible defaults to True; callers backoff and retry.
    """

    retry_eligible = True


class WatcherError(MultiversXAnchorError):
    """Watcher lifecycle failure: stream closed permanently, gap-fill unrecoverable,
    or both WebSocket and polling fallbacks have exhausted their retry budgets.
    """


class AuditError(MultiversXAnchorError):
    """Audit CLI or verify() failed in a way distinct from a mismatch verdict.

    A mismatch is reported as VerifyResult.verdict="mismatch", not an error.
    AuditError is reserved for "cannot compute a verdict" situations (e.g.
    the gateway is unreachable and no replica is configured).

    Test file: tests/multiversx/test_audit_cli.py
    """


# ---------------------------------------------------------------------------
# Rejection reason classification (F1 table from SPEC §6)
# ---------------------------------------------------------------------------


def classify_rejection_reason(proxy_error_message: str) -> bool:
    """Return retry_eligible flag for a given gateway rejection message.

    Args:
        proxy_error_message: The raw `error` field from a non-2xx gateway
            response. Case-insensitive substring match.

    Returns:
        True iff the rejection is eligible for automatic retry.

    Matching (substring, case-insensitive):
        - "lower nonce in transaction"      -> True  (refresh nonce)
        - "higher nonce in transaction"     -> True  (wait for mempool)
        - "insufficient funds"              -> False (operator refund)
        - "invalid signature"               -> False (halt)
        - "gas limit too low"               -> True  (raise gas)
        - "chain id mismatch"               -> False (misconfig)
        - "transaction size too big"        -> False (payload format bug)
        - anything else                     -> True  (unknown; backoff)

    Test file: tests/multiversx/test_errors.py
    """
    normalized = (proxy_error_message or "").lower()
    # Permanent rejections (operator intervention required).
    _NON_RETRYABLE_SUBSTRINGS = (
        "insufficient funds",
        "invalid signature",
        "chain id mismatch",
        "transaction size too big",
    )
    # Transient rejections (adapter may retry after adjustment).
    _RETRYABLE_SUBSTRINGS = (
        "lower nonce in transaction",
        "higher nonce in transaction",
        "gas limit too low",
    )
    for marker in _NON_RETRYABLE_SUBSTRINGS:
        if marker in normalized:
            return False
    for marker in _RETRYABLE_SUBSTRINGS:
        if marker in normalized:
            return True
    # Unknown / empty message: back off and retry with a caution log.
    return True
