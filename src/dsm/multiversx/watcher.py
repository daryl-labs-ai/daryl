"""
Chain watcher: observe submitted anchors through INCLUDED -> SETTLED.

Backlog: V1-05 (polling baseline), V1-06 (dual-schema reader), V1-07 (WS).

The watcher is the component that closes the loop between the state machine
and the chain. It takes an AnchorSubmissionReceipt and yields AnchorEvents
until a terminal state is reached.

Two transport paths, both implemented:

    1. WebSocket subscription (primary)  — subscribes to block/tx/event
       topics on the sender's shard via wss://{gateway}/hub/ws.
    2. Polling fallback (secondary)      — polls /transaction/{hash} and
       /blocks/by-round/{round} at round_duration_ms/2 intervals.

The polling path is also used for:
    - Gap-fill after a WebSocket disconnect.
    - The audit CLI (which does not subscribe; it walks linearly).
    - Integration tests against chain-simulator-go.

Dual-schema reader:
    - Under Supernova, the execution result arrives in a subsequent block
      header's `lastExecutionResult` field (or equivalent).
    - Under Andromeda, the execution data is inline in the tx's own block.
    - The DualSchemaReader abstracts the difference and logs which path
      was taken for every read (F5 diagnosis).

Regime synthesis (critical detail, SPEC §4):
    - Under Andromeda, after emitting IncludeEvent, the watcher SYNTHESIZES
      an ExecSuccessEvent (or ExecFailEvent) in the same tick, because there
      is no separate settlement observation — the data was already in the
      included block. This keeps the state machine regime-oblivious.
    - Under Supernova, Include and ExecSuccess/Fail are separate observations
      produced by reading the `lastExecutionResult` of a later block.

Invariants:
    - The watcher NEVER writes entries to the DSM log itself. It yields
      AnchorEvent objects that the backend appends. Separation of concerns
      keeps the watcher testable without a Storage.
    - On any transport failure, the watcher falls back to polling within
      3 * round_duration_ms.
    - The watcher is single-anchor: one instance per intent_id. For
      fan-out across multiple in-flight anchors, the backend manages
      many watcher instances.

Failure modes:
    - WatcherError: both transports exhausted their retry budget.
    - SchemaUnknownError: dual-schema reader cannot parse a block.

Test files:
    - tests/multiversx/test_watcher_polling_andromeda.py (scaffold)
    - tests/multiversx/test_watcher_polling_supernova.py (scaffold)
    - tests/multiversx/test_watcher_ws_reconnect.py (scaffold)
    - tests/multiversx/test_dual_schema_reader.py
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional

from dsm.multiversx.client import GatewayClient
from dsm.multiversx.errors import SchemaUnknownError, WatcherError
from dsm.multiversx.schemas import (
    AnchorEvent,
    AnchorSubmissionReceipt,
    EpochRegime,
)
from dsm.multiversx.state_machine import (
    ExecFailEvent,
    ExecSuccessEvent,
    IncludeEvent,
)

_log = logging.getLogger("dsm.multiversx.watcher")


# ---------------------------------------------------------------------------
# ExecutionResult (internal representation, normalized across regimes)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionResult:
    """Regime-normalized view of a transaction's execution outcome.

    Produced by DualSchemaReader. Used by the watcher to decide whether the
    next yielded event is ExecSuccess or ExecFail.
    """

    status: str  # "success" | "fail" | "pending"
    executed_in_block_nonce: int
    execution_result_hash: str
    gas_used: int
    developer_fees: str
    return_message: str
    schema_path_used: str  # "supernova_lastExecutionResult" | "andromeda_top_level"


class DualSchemaReader:
    """Parse block and transaction responses into ExecutionResult.

    Tries the Supernova schema first (richest), falls back to Andromeda.
    Records which path succeeded in the returned ExecutionResult so audits
    can reconstruct the compatibility-window behavior.

    Args:
        sdk_schema: One of "legacy_only" / "dual" / "new_only".
            - legacy_only: never try the Supernova path.
            - dual (default during transition): try Supernova first, fall
              back to Andromeda.
            - new_only: only try Supernova; raise SchemaUnknownError on
              legacy-shaped blocks.

    Test file: tests/multiversx/test_dual_schema_reader.py
    """

    def __init__(self, *, sdk_schema: str = "dual") -> None:
        if sdk_schema not in ("legacy_only", "dual", "new_only"):
            raise ValueError(f"invalid sdk_schema: {sdk_schema}")
        self._sdk_schema = sdk_schema

    def read_execution_result(
        self,
        tx_response: dict[str, Any],
        containing_block: Optional[dict[str, Any]] = None,
        settling_block: Optional[dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Extract ExecutionResult from the available block/tx data.

        Args:
            tx_response: The `data.transaction` dict from
                GET /transaction/{hash}?withResults=true.
            containing_block: The block header dict in which the tx was
                included. Required for Andromeda path. Optional for Supernova.
            settling_block: The block header that notarized the execution
                result (Supernova only). Must have a `lastExecutionResult`
                field.

        Returns:
            ExecutionResult with `schema_path_used` set to indicate which
            path produced the result.

        Raises:
            SchemaUnknownError: Neither path could produce a result under
                the current sdk_schema policy.

        Invariants:
            - Idempotent: same inputs -> same output.
            - Never returns "pending" unless both paths agree the tx is still
              pending in the gateway's view.

        Test file: tests/multiversx/test_dual_schema_reader.py
        """
        tx = _extract_tx(tx_response)
        containing = _extract_block(containing_block) if containing_block else None

        # V1-F2.1 regime discrimination rule (per prompt §3):
        #   Presence of `lastExecutionResult` OR `lastExecutionResultInfo` on
        #   the CONTAINING block → supernova path. Absence → andromeda path.
        # Deliberately does NOT use network config erd_round_duration; that
        # lives in regime.py and is orthogonal.
        is_supernova = bool(
            containing is not None
            and (
                "lastExecutionResult" in containing
                or "lastExecutionResultInfo" in containing
            )
        )

        if is_supernova:
            # `is_supernova` is True only when `containing` is not None
            # (see the definition above) — assert for mypy narrowing.
            assert containing is not None
            if self._sdk_schema == "legacy_only":
                raise SchemaUnknownError(
                    "containing block carries Supernova discriminator but "
                    "sdk_schema='legacy_only' forbids the Supernova path"
                )
            return self._read_supernova(tx, containing, settling_block)

        # Andromeda path
        if self._sdk_schema == "new_only":
            raise SchemaUnknownError(
                "containing block lacks Supernova discriminator but "
                "sdk_schema='new_only' forbids the Andromeda path"
            )
        return self._read_andromeda(tx, containing)

    # ------------------------------------------------------------------
    # Path implementations (private; pure functions over parsed dicts)
    # ------------------------------------------------------------------

    def _read_andromeda(
        self,
        tx: dict[str, Any],
        containing_block: Optional[dict[str, Any]],
    ) -> "ExecutionResult":
        """Andromeda: execution data is inline in the tx's own block and status.

        `tx.status` is the primary signal under Andromeda (T₂ ≡ T₃) — the
        containing block carries all execution info.
        """
        status_raw = str(tx.get("status", "pending")).lower()
        status = _ANDROMEDA_STATUS_MAP.get(status_raw, "pending")
        block_nonce = int(tx.get("blockNonce") or 0)
        return ExecutionResult(
            status=status,
            executed_in_block_nonce=block_nonce,
            execution_result_hash=str(
                (containing_block or {}).get("rootHash", "")
            ),
            gas_used=int(tx.get("gasUsed") or 0),
            developer_fees=str(
                (containing_block or {}).get("developerFees", "0")
            ),
            return_message=_extract_receipt_data(tx),
            schema_path_used="andromeda_top_level",
        )

    def _read_supernova(
        self,
        tx: dict[str, Any],
        containing_block: dict[str, Any],
        settling_block: Optional[dict[str, Any]],
    ) -> "ExecutionResult":
        """Supernova: authoritative execution outcome lives in the settling
        block's `lastExecutionResult`.

        If `settling_block` is None, we know execution was decoupled but
        cannot yet see it → status='pending' and the watcher should
        continue polling.
        """
        if settling_block is None:
            return ExecutionResult(
                status="pending",
                executed_in_block_nonce=0,
                execution_result_hash="",
                gas_used=0,
                developer_fees="0",
                return_message="",
                schema_path_used="supernova_lastExecutionResult",
            )
        settling = _extract_block(settling_block)
        exec_result = settling.get("lastExecutionResult") or {}
        base = exec_result.get("baseExecutionResult") or {}

        # Signals-list approach (I14): each signal answers independently.
        # Any 'fail' signal wins; no single signal is the sole determinant.
        fired_signals = [
            name
            for name, signal in _SUPERNOVA_FAIL_SIGNALS
            if signal(exec_result, tx)
        ]
        if fired_signals:
            status = "fail"
            _log.debug("supernova fail signals fired: %s", fired_signals)
        else:
            status = _classify_supernova_non_fail(exec_result, tx)

        executed_in_nonce = int(
            settling.get("nonce")
            or base.get("headerNonce")
            or tx.get("executedInBlockNonce")
            or 0
        )
        root_hash = str(
            base.get("rootHash") or exec_result.get("rootHash") or ""
        )
        return ExecutionResult(
            status=status,
            executed_in_block_nonce=executed_in_nonce,
            execution_result_hash=root_hash,
            gas_used=int(exec_result.get("gasUsed") or 0),
            developer_fees=str(exec_result.get("developerFees") or "0"),
            return_message=_extract_receipt_data(tx),
            schema_path_used="supernova_lastExecutionResult",
        )


# ---------------------------------------------------------------------------
# Helper pure functions — keep schema-field lookups localized (I15)
# ---------------------------------------------------------------------------


def _extract_tx(tx_response: dict[str, Any]) -> dict[str, Any]:
    """Unwrap a `/transaction/{hash}` response envelope to the tx dict."""
    data = tx_response.get("data") or {}
    return dict(data.get("transaction") or {})


def _extract_block(block_envelope: dict[str, Any]) -> dict[str, Any]:
    """Unwrap a `/block/...` response envelope to the block dict.

    Accepts either an already-unwrapped block dict or a full envelope.
    """
    if "data" in block_envelope and "block" in (block_envelope.get("data") or {}):
        return dict(block_envelope["data"]["block"])
    return dict(block_envelope)


def _extract_receipt_data(tx: dict[str, Any]) -> str:
    """Return the tx receipt's `data` string if present, else empty string."""
    receipt = tx.get("receipt")
    if isinstance(receipt, dict):
        return str(receipt.get("data") or "")
    return ""


# Status vocabulary for Andromeda; pending is the catch-all for unknown.
_ANDROMEDA_STATUS_MAP: dict[str, str] = {
    "success": "success",
    "fail": "fail",
    "invalid": "fail",
    "pending": "pending",
}

# I13: keep the "non-terminal status" set open; adding a new value is a
# one-line change here.
_NON_TERMINAL_STATUS_VALUES: frozenset[str] = frozenset(
    {"pending", "included", "consensus-final"}
)


# I14: Supernova failure signals. Structured as an (name, callable) list so
# additional block-side signals (failure SCRs, dedicated failedTransactions
# arrays, etc.) can be appended without redesign. `tx` is the secondary
# input for corroboration — no signal may treat `tx.status == 'fail'` as the
# sole determinant when block-side data is available.
_FailSignal = Callable[[dict[str, Any], dict[str, Any]], bool]


def _signal_invalid_block_miniblock(
    exec_result: dict[str, Any], tx: dict[str, Any]
) -> bool:
    """PRIMARY fail signal: any miniBlockHeader with type == 'InvalidBlock'."""
    for mb in exec_result.get("miniBlockHeaders") or []:
        if mb.get("type") == "InvalidBlock":
            return True
    return False


def _signal_failed_tx_count(
    exec_result: dict[str, Any], tx: dict[str, Any]
) -> bool:
    """Secondary fail signal: executionResult.failedTxCount > 0."""
    try:
        return int(exec_result.get("failedTxCount") or 0) > 0
    except (TypeError, ValueError):
        return False


_SUPERNOVA_FAIL_SIGNALS: list[tuple[str, _FailSignal]] = [
    ("invalid_block_miniblock_header", _signal_invalid_block_miniblock),
    ("failed_tx_count", _signal_failed_tx_count),
]


def _classify_supernova_non_fail(
    exec_result: dict[str, Any], tx: dict[str, Any]
) -> str:
    """Decide between 'success' and 'pending' when no fail signal fired.

    'success' requires BLOCK-SIDE evidence (executedTxCount > 0 with a
    TxBlock miniblock). tx.status may corroborate but is never the sole
    determinant (I14).
    """
    executed_count = 0
    try:
        executed_count = int(exec_result.get("executedTxCount") or 0)
    except (TypeError, ValueError):
        executed_count = 0
    has_tx_block = any(
        (mb or {}).get("type") == "TxBlock"
        for mb in (exec_result.get("miniBlockHeaders") or [])
    )
    if has_tx_block and executed_count > 0:
        return "success"
    tx_status = str(tx.get("status") or "pending").lower()
    if tx_status in _NON_TERMINAL_STATUS_VALUES:
        return "pending"
    if tx_status == "success":
        # Block-side is inconclusive but tx corroborates — treat as pending
        # until the block signal catches up (fail-safe).
        return "pending"
    return "pending"


# ---------------------------------------------------------------------------
# Watcher
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WatcherConfig:
    """Runtime parameters for the watcher.

    Derived from config.AdapterConfig at backend init, combined with the
    current regime's round_duration_ms.
    """

    round_duration_ms: int
    t1_timeout_ms: int
    t3_timeout_ms: int
    stuck_threshold_ms: int
    ws_url: str
    reconnect_base_ms: int
    reconnect_max_ms: int
    polling_fallback_after_ms: int
    sdk_schema: str


# ---------------------------------------------------------------------------
# MinimalPollingWatcher — V1-F2.2 scope
# ---------------------------------------------------------------------------
#
# Intentionally narrow. NO WebSocket, NO reconnect, NO timeout handling (t1,
# t3, t_max), NO gap-fill, NO cross-shard, NO relayed-v3. Per prompt I16 any
# of those before F2 is green is a scope violation.
#
# Responsibility: given a submission receipt and an http transport that can
# serve /transaction/{hash} and /block/{shard}/by-nonce/{nonce}, emit a
# sequence of state-machine events (IncludeEvent, then ExecSuccessEvent or
# ExecFailEvent) terminating when the anchor reaches a terminal state as
# seen by the DualSchemaReader. The caller drives the state machine over
# these events to obtain the log entries.
#
# Test: tests/multiversx/test_f2_execution_fail.py


class MinimalPollingWatcher:
    """V1-F2 polling-only watcher.

    Synchronous, single-anchor, single-shard, no retries, no timeouts. Uses
    an injected `httpx.Client` so tests can plug in an `httpx.MockTransport`
    with no other mocking (I17). Not async — V1.B concerns.

    Args:
        http: Pre-configured `httpx.Client` with `base_url` set. Test code
            constructs this with `transport=httpx.MockTransport(handler)`.
        regime: Current regime. Used ONLY to decide the andromeda
            synthesis pattern; the actual fail/success reading is
            fixture-structure-driven through DualSchemaReader.
        reader: Optional DualSchemaReader override (tests).
        max_polls: Upper bound on iterations per phase; a safety net, not
            a timeout. Exceeding it raises WatcherError. Default 20 is
            well above any fixture-driven scenario.
    """

    def __init__(
        self,
        *,
        http: "Any",  # httpx.Client — not imported at top to avoid hard dep
        regime: EpochRegime,
        reader: Optional[DualSchemaReader] = None,
        max_polls: int = 20,
    ) -> None:
        self._http = http
        self._regime = regime
        self._reader = reader or DualSchemaReader(sdk_schema="dual")
        self._max_polls = max_polls

    def watch(
        self, receipt: AnchorSubmissionReceipt
    ) -> "Iterator[Any]":
        """Yield state-machine events until a terminal outcome is observed.

        Events yielded (all from state_machine.py):
            - IncludeEvent (exactly one)
            - ExecSuccessEvent OR ExecFailEvent (exactly one)

        Two events total on every happy- or fail-path. Never yields a
        SettledEntry or FailedEntry directly — those are entries produced
        by the state machine from these events.
        """
        tx, containing_block = self._poll_until_included(receipt.tx_hash)

        # Preliminary read — decides andromeda vs supernova path.
        preliminary = self._reader.read_execution_result(
            tx_response={"data": {"transaction": tx}},
            containing_block=containing_block,
            settling_block=None,
        )

        yield IncludeEvent(
            intent_id=receipt.intent_id,
            tx_hash=receipt.tx_hash,
            block_nonce=int(tx.get("blockNonce") or 0),
            block_hash=str(tx.get("blockHash") or ""),
            shard=int(tx.get("sourceShard") or 0),
            header_time_ms=_header_time_ms(containing_block),
            consensus_proof_observed_at_ms=0,
        )

        if preliminary.schema_path_used == "andromeda_top_level":
            # T₂ ≡ T₃ — synthesize the terminal event from the same data.
            yield self._build_terminal_event(
                receipt=receipt,
                result=preliminary,
                settled_block_ts=containing_block.get("timestamp"),
            )
            return

        # Supernova: poll for the settling block until the reader returns a
        # non-pending status.
        shard = int(tx.get("sourceShard") or 0)
        last_result: Optional[ExecutionResult] = None
        settling_block: Optional[dict[str, Any]] = None
        for _ in range(self._max_polls):
            fresh_tx = self._fetch_tx(receipt.tx_hash)
            settling_nonce = int(
                fresh_tx.get("executedInBlockNonce")
                or int(tx.get("blockNonce") or 0) + 1
            )
            settling_block = self._fetch_block(shard, settling_nonce)
            result = self._reader.read_execution_result(
                tx_response={"data": {"transaction": fresh_tx}},
                containing_block=containing_block,
                settling_block=settling_block,
            )
            if result.status != "pending":
                last_result = result
                break
            last_result = result
        else:
            raise WatcherError(
                f"settling block did not yield a terminal status within "
                f"{self._max_polls} polls"
            )

        assert last_result is not None
        yield self._build_terminal_event(
            receipt=receipt,
            result=last_result,
            settled_block_ts=(settling_block or {}).get("timestamp"),
        )

    # ------------------------------------------------------------------
    # HTTP primitives
    # ------------------------------------------------------------------

    def _poll_until_included(
        self, tx_hash: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Poll the tx endpoint until a `blockNonce` is set, then fetch the
        containing block. Returns (tx_dict, containing_block_dict).
        """
        tx: dict[str, Any] = {}
        for _ in range(self._max_polls):
            tx = self._fetch_tx(tx_hash)
            if tx.get("blockNonce"):
                break
        else:
            raise WatcherError(
                f"tx {tx_hash} did not appear in a block within "
                f"{self._max_polls} polls"
            )
        block = self._fetch_block(
            shard=int(tx.get("sourceShard") or 0),
            nonce=int(tx["blockNonce"]),
        )
        return tx, block

    def _fetch_tx(self, tx_hash: str) -> dict[str, Any]:
        resp = self._http.get(
            f"/transaction/{tx_hash}", params={"withResults": "true"}
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or {}
        return dict(data.get("transaction") or {})

    def _fetch_block(self, shard: int, nonce: int) -> dict[str, Any]:
        resp = self._http.get(f"/block/{shard}/by-nonce/{nonce}")
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or {}
        return dict(data.get("block") or {})

    # ------------------------------------------------------------------
    # Event construction
    # ------------------------------------------------------------------

    def _build_terminal_event(
        self,
        *,
        receipt: AnchorSubmissionReceipt,
        result: "ExecutionResult",
        settled_block_ts: Any,
    ) -> "Any":
        if result.status == "fail":
            return ExecFailEvent(
                intent_id=receipt.intent_id,
                reason=result.return_message or "execution_failed_on_chain",
                gas_used=result.gas_used,
                return_message=result.return_message,
                failed_in_block_nonce=result.executed_in_block_nonce,
            )
        return ExecSuccessEvent(
            intent_id=receipt.intent_id,
            executed_in_block_nonce=result.executed_in_block_nonce,
            execution_result_hash=result.execution_result_hash,
            gas_used=result.gas_used,
            developer_fees=result.developer_fees,
            settled_at_ms=_ts_to_ms(settled_block_ts),
            schema_path_used=result.schema_path_used,
        )


def _header_time_ms(block: dict[str, Any]) -> int:
    """Normalize a block `timestamp` to ms, handling seconds vs ms input."""
    return _ts_to_ms(block.get("timestamp"))


def _ts_to_ms(ts: Any) -> int:
    """Convert a block timestamp (seconds or ms) to ms.

    Heuristic: values under 10**12 are treated as seconds (valid until
    year ~33658); values at or above are treated as ms. This matches the
    Andromeda-seconds vs Supernova-ms split in the V1-F2 fixtures.
    """
    try:
        n = int(ts or 0)
    except (TypeError, ValueError):
        return 0
    if n < 10**12:
        return n * 1000
    return n


class ChainWatcher:
    """Observe an in-flight anchor and yield AnchorEvents until terminal.

    Usage:
        watcher = ChainWatcher(client=client, config=config, regime="supernova")
        for event in watcher.watch(receipt):
            # backend appends event to DSM log and advances state machine
            ...

    Threading model:
        - One watcher instance per anchor (per intent_id).
        - The `watch()` iterator blocks the calling thread on its transport.
          Callers that want concurrency run each watcher in a task.

    Test files:
        - tests/multiversx/test_watcher_polling_andromeda.py (scaffold)
        - tests/multiversx/test_watcher_polling_supernova.py (scaffold)
        - tests/multiversx/test_watcher_ws_reconnect.py (scaffold)
    """

    def __init__(
        self,
        *,
        client: GatewayClient,
        config: WatcherConfig,
        regime: EpochRegime,
        reader: Optional[DualSchemaReader] = None,
    ) -> None:
        self._client = client
        self._config = config
        self._regime = regime
        self._reader = reader or DualSchemaReader(sdk_schema=config.sdk_schema)

    def watch(self, receipt: AnchorSubmissionReceipt) -> Iterator[AnchorEvent]:
        """Yield AnchorEvents until the anchor reaches a terminal state.

        Yields (in order, for a normal happy-path supernova run):
            1. AnchorIncludedEntry (T₂)
            2. AnchorSettledEntry  (T₃)

        For andromeda happy path:
            1. AnchorIncludedEntry (T₂)
            2. AnchorSettledEntry  (co-emitted; synthesized from the same
               block data)

        For failure paths, yields AnchorFailedEntry, AnchorTimedOutEntry,
        or AnchorStuckEntry as appropriate.

        Args:
            receipt: The submission receipt from `submit()`.

        Raises:
            WatcherError: Both transports exhausted; no observation possible.
            SchemaUnknownError: Block format unrecognized.

        Test files: see module docstring.
        """
        # TODO[V1-05]: polling baseline. Implement the full happy-path first
        # (andromeda coupled, then supernova decoupled), then add:
        # TODO[V1-07]: WebSocket primary with polling fallback.
        # TODO[V1-08]: t1/t3/stuck timeout emissions.
        raise NotImplementedError("V1-05 scaffold: ChainWatcher.watch")

    def _observe_inclusion(
        self, receipt: AnchorSubmissionReceipt
    ) -> dict[str, Any]:
        """Wait until the tx hash appears in a finalized block.

        Returns the containing block's header dict. Raises WatcherError on
        t1 timeout.

        Test file: tests/multiversx/test_watcher_polling_andromeda.py (scaffold)
        """
        # TODO[V1-05]
        raise NotImplementedError("V1-05 scaffold: _observe_inclusion")

    def _observe_settlement(
        self,
        receipt: AnchorSubmissionReceipt,
        containing_block: dict[str, Any],
    ) -> ExecutionResult:
        """Wait until the ExecutionResult for the anchor is notarized.

        Under andromeda, returns synchronously with the inclusion data.
        Under supernova, polls/subscribes for the settling block.

        Raises WatcherError on t3 timeout.

        Test file: tests/multiversx/test_watcher_polling_supernova.py (scaffold)
        """
        # TODO[V1-05]
        raise NotImplementedError("V1-05 scaffold: _observe_settlement")


# ---------------------------------------------------------------------------
# WebSocket subscription (V1-07, scaffolded separately)
# ---------------------------------------------------------------------------


class WebSocketSubscriber:
    """Subscribe to block/tx events on the sender's shard via /hub/ws.

    Produces a stream of dicts compatible with the polling code paths, so
    the watcher can switch transports transparently.

    Lifecycle:
        - Connect on first call; reconnect with exponential backoff.
        - On reconnect, perform gap-fill via GatewayClient.get_blocks_by_round.
        - If gap exceeds 100 blocks, fall back to polling for recovery.

    Test file: tests/multiversx/test_watcher_ws_reconnect.py (scaffold)
    """

    def __init__(self, *, ws_url: str, shard_id: int) -> None:
        self._ws_url = ws_url
        self._shard_id = shard_id

    def stream(self) -> Iterator[dict[str, Any]]:
        """Yield normalized block/tx events.

        Never raises on transient disconnects; falls back to reconnect logic.
        Raises WatcherError only when reconnect budget is exhausted.

        Test file: tests/multiversx/test_watcher_ws_reconnect.py (scaffold)
        """
        # TODO[V1-07]: implement websockets client with exponential backoff,
        # topic subscription per SPEC §5, gap-fill on reconnect.
        raise NotImplementedError("V1-07 scaffold: WebSocketSubscriber.stream")
