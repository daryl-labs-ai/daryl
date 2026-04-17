"""
Schemas for anchor entries written to the DSM log.

Backlog: V0-01.

Each entry type corresponds to a state transition in the three-stage anchor
state machine (see state_machine.py and SPEC §4). Entries are JSON-serialized
by the DSM kernel; pydantic models here provide validated Python access.

Design principles:
    - All entry types carry `entry_type` as a string discriminator so the
      audit CLI can dispatch on it without depending on class inheritance.
    - `intent_id` (UUIDv7) is the correlation key across all entries that
      belong to a single anchor round-trip.
    - **Core fields are required; contextual fields are optional.** The
      "core" fields identify the anchor round-trip and are never silently
      omittable: `intent_id`, `last_hash`, `entry_nonce`, `epoch_regime`.
      Everything else is optional or has a documented default, to support
      replay, mocks, legacy log entries from before newer fields existed,
      and V2 schema evolutions. The audit tool is **context-aware**, not
      schema-rigid: absence of an optional field is reported as a note or
      downgrade, never as a hard rejection.
    - Pydantic v2 style. `ConfigDict(frozen=True, extra="forbid")` on every
      model to make entries tamper-evident at the pydantic layer.

Invariants enforced at validation time:
    - `intent_id` is a valid UUIDv7 (first 48 bits = ms timestamp).
    - `last_hash` is 32 bytes (SHA-256); represented as 0x-prefixed hex.
    - `entry_nonce` is non-negative.
    - Timestamps are integer ms since epoch; no naive datetimes.

Failure modes:
    - Validation errors are raised as `pydantic.ValidationError`. Callers
      should translate to `dsm.multiversx.errors.PayloadError` at the
      adapter boundary.

Test file: tests/multiversx/test_schemas_roundtrip.py
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from dsm.multiversx.errors import PayloadError

# ---------------------------------------------------------------------------
# Regime and capabilities
# ---------------------------------------------------------------------------

EpochRegime = Literal["andromeda", "supernova"]
"""The two possible MultiversX execution regimes the adapter handles.

`andromeda` means pre-Supernova mainnet (coupled inclusion/execution, 6 s
rounds). `supernova` means post-Supernova (decoupled, 600 ms rounds, execution
results notarized in a subsequent header). See SPEC §2–§3.
"""


class AnchorState(str, Enum):
    """State of a single anchor round-trip in the three-stage state machine.

    See state_machine.py and SPEC §4 for transitions. `INTENT_LOGGED` is the
    initial state; `SETTLED`, `FAILED`, and `REJECTED` are terminal success/
    failure states. `STUCK` is a non-terminal alarm state requiring operator
    action.
    """

    INTENT_LOGGED = "intent_logged"
    SUBMITTED = "submitted"
    INCLUDED = "included"
    SETTLED = "settled"
    FAILED = "failed"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    STUCK = "stuck"


class NetworkConfigSnapshot(BaseModel):
    """Captured /network/config fields at anchor intent time.

    Every `AnchorIntent` carries this snapshot so post-hoc audits can
    reconstruct the regime and chain parameters without re-querying the
    network. See SPEC §2 for how it is produced.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    chain_id: str
    round_duration_ms: int = Field(..., ge=1)
    protocol_version: str
    captured_at_ms: int = Field(..., ge=0)

    @field_validator("chain_id")
    @classmethod
    def _chain_id_nonempty(cls, v: str) -> str:
        if not v:
            raise ValueError("chain_id must be non-empty")
        return v


class BackendCapabilities(BaseModel):
    """Advertised capabilities of an AnchorBackend.

    The facade in `anchor.py` reads these to decide whether to require
    `anchor_settled` as terminal (Supernova) or accept `anchor_included`
    (Andromeda). See SPEC §1.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend_name: str
    backend_version: str
    regime: EpochRegime
    supports_settlement_stage: bool
    estimated_t1_ms: int = Field(..., ge=0)
    estimated_t3_ms: int = Field(..., ge=0)


# ---------------------------------------------------------------------------
# Anchor entries (written to the DSM log)
# ---------------------------------------------------------------------------


class _EntryBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_type: str
    intent_id: uuid.UUID


class AnchorIntent(_EntryBase):
    """Local pre-commit entry. Written BEFORE any network call.

    Invariants:
        - MUST be fsynced to disk and committed to the shard's last-hash
          integrity file BEFORE `submit()` is invoked (see F12 in SPEC §6).
        - `last_hash` MUST equal the shard's tail at `entry_nonce`.
        - `epoch_regime` and `network_config_snapshot` MUST be populated
          from a RegimeDetector query at intent time, not a cached default.

    Test file: tests/multiversx/test_schemas_roundtrip.py
    """

    entry_type: Literal["anchor_intent"] = "anchor_intent"
    # Core identity — never silently omittable.
    shard_id: str = Field(..., min_length=1, max_length=64)
    last_hash: str = Field(..., pattern=r"^0x[0-9a-fA-F]{64}$")
    entry_nonce: int = Field(..., ge=0)
    epoch_regime: EpochRegime
    # Contextual / conditional — optional to preserve backward compatibility
    # with replay, mocks, and future V2 schema evolutions. Audit is context-
    # aware: if `network_config_snapshot` is absent and epoch_regime is
    # "supernova", the audit tool emits a downgrade note but does not refuse
    # to verify. See SPEC §7.2 and audit.py.
    network_config_snapshot: Optional[NetworkConfigSnapshot] = None
    adapter_version: Optional[str] = None
    signature_ed25519: Optional[str] = None
    # ^ Ed25519 signature over a canonical encoding of the other fields.
    # Optional until P9 (signing.py) integration is wired. See SPEC §8.


class AnchorSubmittedEntry(_EntryBase):
    """Emitted after the gateway ACKs the submission but before inclusion.

    Invariants:
        - MUST be preceded in the DSM log by an `AnchorIntent` with the same
          `intent_id`.
        - `tx_hash` MUST match the hash returned by the gateway.
    """

    entry_type: Literal["anchor_submitted"] = "anchor_submitted"
    tx_hash: str = Field(..., min_length=1)
    submitted_at_ms: int = Field(..., ge=0)
    sender_nonce: int = Field(..., ge=0)
    gas_limit: int = Field(..., ge=0)
    gas_price: int = Field(..., ge=0)


class AnchorIncludedEntry(_EntryBase):
    """Emitted when the tx is observed in a finalized block (T₂).

    Under Andromeda, inclusion coincides with execution. Under Supernova,
    inclusion means consensus-final but NOT yet executed — the `AnchorSettled`
    entry must follow before the anchor can be treated as audit-valid.

    Invariants:
        - `block_nonce` > 0
        - `header_time_ms` MUST be taken from the block header, not local
          wall clock.
    """

    entry_type: Literal["anchor_included"] = "anchor_included"
    tx_hash: str
    block_nonce: int = Field(..., ge=0)
    block_hash: str
    shard: int = Field(..., ge=0)
    header_time_ms: int = Field(..., ge=0)
    consensus_proof_observed_at_ms: int = Field(..., ge=0)


class AnchorSettledEntry(_EntryBase):
    """Terminal success. Emitted when the ExecutionResult is notarized.

    Under Andromeda, settled block is the same as the included block; this
    entry is still emitted for regime-agnostic audit replay (SPEC §4).
    Under Supernova, the settled block is typically the successor of the
    included block.

    Invariants:
        - Either preceded by an `AnchorIncludedEntry` with same `intent_id`,
          OR (in regime=andromeda compatibility mode) co-emitted with it.
        - `executed_in_block_nonce` >= included block_nonce.
        - `schema_path_used` records whether the dual-schema reader used the
          Supernova path (`supernova_lastExecutionResult`) or the legacy path
          (`andromeda_top_level`). This is the diagnostic field for F5.
    """

    entry_type: Literal["anchor_settled"] = "anchor_settled"
    executed_in_block_nonce: int = Field(..., ge=0)
    # Optional: may be missing if the indexer did not expose it. Audit
    # treats absence as "cannot verify execution_result_hash" but not as
    # a failure.
    execution_result_hash: Optional[str] = None
    gas_used: int = Field(..., ge=0)
    developer_fees: str = "0"
    settled_at_ms: int = Field(..., ge=0)
    # Optional: legacy entries from before the dual-schema reader existed
    # will not have this. Audit interprets absence as "path unknown" and
    # logs a WARNING rather than rejecting the entry.
    schema_path_used: Optional[
        Literal["supernova_lastExecutionResult", "andromeda_top_level"]
    ] = None


class AnchorFailedEntry(_EntryBase):
    """Terminal failure. Emitted when ExecutionResult.status == "fail".

    Distinct from `AnchorRejectedEntry` (pre-inclusion rejection) and
    `AnchorTimedOutEntry` (no observation within threshold). This entry
    represents an execution failure after the tx was accepted by the chain.
    """

    entry_type: Literal["anchor_failed"] = "anchor_failed"
    # `reason` remains required — it is why the entry exists.
    reason: str
    # Optional: may be unavailable from a minimal indexer or if execution
    # fell over before gas accounting completed.
    gas_used: Optional[int] = Field(default=None, ge=0)
    return_message: str = ""
    failed_in_block_nonce: Optional[int] = Field(default=None, ge=0)


class AnchorRejectedEntry(_EntryBase):
    """Emitted when the gateway rejects the submission at mempool level.

    See F1 in SPEC §6 for the rejection-reason table.

    Invariants:
        - `retry_eligible` MUST match the rejection-reason table in SPEC §6.
        - `http_status` and `proxy_error_message` come from the gateway
          response; do not paraphrase.
    """

    entry_type: Literal["anchor_rejected"] = "anchor_rejected"
    http_status: int = Field(..., ge=100, le=599)
    proxy_error_message: str
    retry_eligible: bool


class AnchorTimedOutEntry(_EntryBase):
    """Emitted when the tx has not been observed within the t1/t3 threshold.

    Non-terminal: adapter may retry with a new submission. If retry succeeds,
    a new `AnchorSubmittedEntry` is emitted with a new `tx_hash`; `intent_id`
    remains the same. See SPEC §4.
    """

    entry_type: Literal["anchor_timed_out"] = "anchor_timed_out"
    tx_hash: str
    elapsed_ms: int = Field(..., ge=0)
    last_observed_block_nonce: Optional[int] = None
    timeout_phase: Literal["t1_inclusion", "t3_settlement"]


class AnchorStuckEntry(_EntryBase):
    """Operator alarm. Anchor has exceeded stuck_threshold_ms.

    Non-terminal but requires operator intervention (likely chain halt or
    prolonged backpressure).
    """

    entry_type: Literal["anchor_stuck"] = "anchor_stuck"
    tx_hash: Optional[str] = None
    elapsed_ms: int = Field(..., ge=0)


class AnchorReconciledEntry(_EntryBase):
    """Emitted after `reconcile()` matches the local tail to an on-chain anchor.

    Used for F11 recovery. See SPEC §6, backend.reconcile(), and V1-21.
    """

    entry_type: Literal["anchor_reconciled"] = "anchor_reconciled"
    shard_id: str
    local_tail_last_hash: str
    on_chain_last_hash: str
    reconciled_at_ms: int
    reconciliation_verdict: Literal["match", "local_ahead", "diverged"]


# ---------------------------------------------------------------------------
# Runtime-only types (not persisted as entries, passed between components)
# ---------------------------------------------------------------------------


class AnchorSubmissionReceipt(BaseModel):
    """Returned by `MultiversXAnchorBackend.submit()`; input to `watch()`.

    This is a runtime handle, not an entry. It is NOT written to the DSM log.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent_id: uuid.UUID
    tx_hash: str
    submitted_at_ms: int
    nonce: int
    sender_shard: int
    regime: EpochRegime


AnchorEvent = Union[
    AnchorIncludedEntry,
    AnchorSettledEntry,
    AnchorFailedEntry,
    AnchorTimedOutEntry,
    AnchorStuckEntry,
]
"""Union of events yielded by `watch()`. Each one is also the entry written."""


class VerifyResult(BaseModel):
    """Returned by `MultiversXAnchorBackend.verify()`.

    Reports whether a single anchor (by `intent_id`) is valid against the
    on-chain record. See audit.py and SPEC §7.2.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent_id: uuid.UUID
    verdict: Literal["ok", "mismatch", "not_found", "execution_failed", "pending"]
    checks: dict[str, bool]
    notes: list[str] = Field(default_factory=list)


class ReconcileReport(BaseModel):
    """Returned by `MultiversXAnchorBackend.reconcile()`.

    See SPEC §7 for semantics; F11 handling.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    shard_id: str
    local_tail_last_hash: str
    on_chain_last_hash: Optional[str]
    verdict: Literal["match", "local_ahead", "diverged", "no_on_chain_anchor"]
    emitted_entry_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Discriminated union for parsing DSM log entries back into pydantic objects
# ---------------------------------------------------------------------------

AnchorLogEntry = Union[
    AnchorIntent,
    AnchorSubmittedEntry,
    AnchorIncludedEntry,
    AnchorSettledEntry,
    AnchorFailedEntry,
    AnchorRejectedEntry,
    AnchorTimedOutEntry,
    AnchorStuckEntry,
    AnchorReconciledEntry,
]
"""Every possible entry type written by this adapter. Dispatched on `entry_type`."""


def parse_anchor_log_entry(raw: dict[str, Any]) -> AnchorLogEntry:
    """Parse a raw DSM entry payload dict into the appropriate pydantic model.

    Args:
        raw: Dict decoded from the DSM entry's stored JSON payload.

    Returns:
        The appropriate AnchorLogEntry subclass, selected by `entry_type`.

    Raises:
        PayloadError: If `entry_type` is missing or unknown, or if validation
            fails.

    Test file: tests/multiversx/test_schemas_roundtrip.py
    """
    _ENTRY_TYPE_TO_MODEL: dict[str, type[BaseModel]] = {
        "anchor_intent": AnchorIntent,
        "anchor_submitted": AnchorSubmittedEntry,
        "anchor_included": AnchorIncludedEntry,
        "anchor_settled": AnchorSettledEntry,
        "anchor_failed": AnchorFailedEntry,
        "anchor_rejected": AnchorRejectedEntry,
        "anchor_timed_out": AnchorTimedOutEntry,
        "anchor_stuck": AnchorStuckEntry,
        "anchor_reconciled": AnchorReconciledEntry,
    }
    if not isinstance(raw, dict):
        raise PayloadError(
            f"parse_anchor_log_entry expects a dict, got {type(raw).__name__}"
        )
    entry_type = raw.get("entry_type")
    if entry_type is None:
        raise PayloadError("entry_type is missing from log entry payload")
    model_cls = _ENTRY_TYPE_TO_MODEL.get(entry_type)
    if model_cls is None:
        raise PayloadError(f"unknown entry_type: {entry_type!r}")
    try:
        return model_cls.model_validate(raw)  # type: ignore[return-value]
    except ValidationError as exc:
        raise PayloadError(
            f"validation failed for entry_type={entry_type!r}: {exc}"
        ) from exc
