"""
MultiversXAnchorBackend — the concrete AnchorBackend implementation.

Backlog: V0-06 (skeleton), V1-03 (submit implementation), V1-21 (reconcile).

Glues together:
    - RegimeDetector  (regime.py)
    - GatewayClient   (client.py)
    - PayloadAnchorBuilder (payload.py)
    - AnchorStateMachine  (state_machine.py)
    - ChainWatcher    (watcher.py)
    - DualSchemaReader (watcher.py)

Implements the AnchorBackend ABC from anchor_backend.py (which is imported
into the existing src/dsm/anchor.py by a minimal 2-line addition; see
anchor_backend.py docstring).

Ordering invariant (F12, SPEC §6):
    submit() MUST ensure the AnchorIntent entry is durably fsynced to the
    DSM log BEFORE any network call is made. This is the single most
    important correctness property of this backend. V1-04 tests it explicitly.

Test files:
    - tests/multiversx/test_backend_contract.py  (scaffold)
    - tests/multiversx/test_submit_intent_to_included.py (scaffold)
    - tests/multiversx/test_fsync_ordering_f12.py (scaffold)
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Iterator, Literal, Optional

from dsm.anchor_backend import AnchorBackend
from dsm.multiversx.client import GatewayClient, TransactionSigner
from dsm.multiversx.config import AdapterConfig
from dsm.multiversx.errors import (
    AuditError,
    MultiversXAnchorError,
    NetworkError,
    RejectedByGateway,
)
from dsm.multiversx.payload import encode_payload
from dsm.multiversx.regime import RegimeDetector, build_snapshot
from dsm.multiversx.schemas import (
    AnchorEvent,
    AnchorIntent,
    AnchorSubmissionReceipt,
    BackendCapabilities,
    EpochRegime,
    ReconcileReport,
    VerifyResult,
)
from dsm.multiversx.state_machine import (
    AnchorState,
    initial_state,
    next_state,
)
from dsm.multiversx.watcher import ChainWatcher, DualSchemaReader, WatcherConfig


class MultiversXAnchorBackend(AnchorBackend):
    """Payload-anchor backend for MultiversX, spanning Andromeda and Supernova.

    Args:
        gateway_url: Gateway base URL.
        signer: An object implementing TransactionSigner.
        account_address: The sender address (should match signer.address()).
        storage: The DSM Storage instance to append entries to. Type is
            intentionally `Any` here to avoid depending on dsm.core at
            scaffold time; runtime duck-types on .append().
        config: AdapterConfig instance; provides flags, retry, watcher params.
        regime_detector: Optional RegimeDetector override (test injection).
        client: Optional GatewayClient override (test injection).

    Test file: tests/multiversx/test_backend_contract.py (scaffold)
    """

    backend_name = "multiversx"
    backend_version = "0.1.0"

    def __init__(
        self,
        gateway_url: str,
        signer: TransactionSigner,
        account_address: str,
        storage: Any,  # dsm.core.Storage — not imported to respect the freeze
        *,
        config: Optional[AdapterConfig] = None,
        regime_detector: Optional[RegimeDetector] = None,
        client: Optional[GatewayClient] = None,
    ) -> None:
        from dsm.multiversx.config import load_config
        from dsm.multiversx.regime import RegimeCache, default_cache_path

        self._gateway_url = gateway_url
        self._signer = signer
        self._account_address = account_address
        self._storage = storage
        self._config = config if config is not None else load_config(None)
        self._client = client if client is not None else GatewayClient(gateway_url)
        if regime_detector is not None:
            self._regime_detector = regime_detector
        else:
            self._regime_detector = RegimeDetector(
                self._client, RegimeCache(default_cache_path())
            )
        # Cached per-anchor account shard; resolved on first submit via client.
        self._account_shard: Optional[int] = None

    # ------------------------------------------------------------------
    # AnchorBackend ABC surface
    # ------------------------------------------------------------------

    def capabilities(self) -> BackendCapabilities:
        """Report backend capabilities for the current regime.

        Returns:
            BackendCapabilities with:
                - supports_settlement_stage: True (always, even under
                  andromeda; the SETTLED stage is regime-agnostic at the
                  DSM log level — see SPEC §4).
                - regime: from regime_detector.current().regime
                - estimated_t1_ms / estimated_t3_ms: from retry config
                  multiplied by round_duration_ms.

        Test file: tests/multiversx/test_backend_contract.py (scaffold)
        """
        verdict = self._regime_detector.current()
        round_ms = verdict.round_duration_ms
        t1_blocks = self._config.retry.t1_timeout_blocks
        t3_blocks = self._config.retry.t3_timeout_blocks
        return BackendCapabilities(
            backend_name=self.backend_name,
            backend_version=self.backend_version,
            regime=verdict.regime,
            supports_settlement_stage=True,
            estimated_t1_ms=t1_blocks * round_ms,
            estimated_t3_ms=(t1_blocks + t3_blocks) * round_ms,
        )

    def submit(self, intent: AnchorIntent) -> AnchorSubmissionReceipt:
        """Submit a payload anchor transaction for `intent`.

        Responsibility split (F12 ordering rule):
            - PRIMARY enforcement of the fsync-before-submit ordering lives
              in the Anchor facade (src/dsm/anchor.py), which controls the
              full lifecycle intent_write -> fsync -> submit.
            - This backend performs only a DEFENSIVE CHECK on entry: it
              asserts that the intent has been durably appended to storage.
              That assertion is a belt-and-suspenders guard against facade
              regressions and future callers who bypass the facade.

        Rationale: keeping the backend thin in terms of storage coupling
        makes it easier to add other backends (Ethereum, Solana, Bitcoin-
        OpenTimestamps) that reuse the same state machine and watcher
        pattern. The facade owns orchestration; the backend owns transport
        and on-chain semantics.

        Flow:

            0. DEFENSIVE CHECK: verify intent has been durably appended to
               DSM storage (F12 defensive; primary enforcement in anchor.py).
            1. Verify `intent.network_config_snapshot`, if present, is
               consistent with the currently detected regime. If the
               snapshot is absent (legacy / replay), proceed without the
               consistency check and log an INFO-level note.
            2. encode_payload(intent) to get DSM01 bytes.
            3. Fetch nonce from gateway.
            4. Build the tx: self-addressed, value=0, data=payload, gas=300000.
            5. Sign.
            6. POST /transaction/send.
            7. Emit AnchorSubmittedEntry to storage.
            8. Return AnchorSubmissionReceipt.

        Args:
            intent: The AnchorIntent entry, already appended and fsynced
                to the log by the caller (anchor.py facade).

        Returns:
            AnchorSubmissionReceipt.

        Raises:
            RejectedByGateway: F1 family; classify_rejection_reason() sets
                retry_eligible per SPEC §6.
            NetworkError: Transport-level failure.
            MultiversXAnchorError: Any other adapter failure (including
                the defensive-check failure if the caller bypassed the facade
                and submitted an intent that was not persisted).

        Invariants:
            - If this method raises after step 6 completed, storage state is
              inconsistent (tx submitted, no entry). Callers must treat this
              as operator-intervention territory. The caller pattern that
              avoids this is: subscribe the watcher before calling submit().

        Test file: tests/multiversx/test_submit_intent_to_included.py (scaffold)
                  tests/multiversx/test_fsync_ordering_f12.py (scaffold)
        """
        # TODO[V1-03]: implement per the flow above. Remember:
        #   - Defensive check only on entry; do NOT reimplement facade-level
        #     ordering guarantees. Raise MultiversXAnchorError with a clear
        #     message if the defensive check fails.
        #   - Consistency check against network_config_snapshot is CONDITIONAL
        #     on its presence (it is Optional since the schema softening).
        raise NotImplementedError("V1-03 scaffold: submit")

    def watch(self, receipt: AnchorSubmissionReceipt) -> Iterator[AnchorEvent]:
        """Yield AnchorEvents as the anchor progresses INCLUDED → SETTLED.

        Delegates to ChainWatcher. Events yielded must be appended to the
        DSM log by the caller (anchor.py facade does this), and fed to the
        state machine via next_state().

        Args:
            receipt: From submit().

        Yields:
            AnchorEvent objects in causal order. Terminal events (settled,
            failed) are always the last yielded on the happy path.

        Raises:
            WatcherError, SchemaUnknownError, NetworkError: As per watcher.

        Test files: the watcher integration tests cover this.
        """
        # TODO[V0-06]: construct ChainWatcher from self._config + regime,
        # delegate.
        raise NotImplementedError("V0-06 scaffold: watch")

    def verify(self, intent_entry_id: str, on_chain_ref: dict) -> VerifyResult:
        """Verify that a local anchor intent matches on-chain data.

        This is the audit primitive. It reads the local log for the
        AnchorIntent at `intent_entry_id`, fetches the corresponding tx
        from the gateway, and runs the checks in SPEC §7.2.

        Args:
            intent_entry_id: Local DSM entry ID for the AnchorIntent.
            on_chain_ref: Dict with at least `tx_hash`. May include
                `block_nonce` for faster lookup.

        Returns:
            VerifyResult with per-check booleans and an overall verdict.

        Raises:
            AuditError: Cannot compute a verdict (network down, etc.).
            NetworkError: Transport-level failure.

        Test file: tests/multiversx/test_audit_cli.py
        """
        # TODO[V1-20]: implement the §7.2 check list:
        #   C1: payload in tx.data matches intent's last_hash / entry_nonce
        #   C2: tx's block header_time_ms within skew of intent's captured_at_ms
        #   C3: ExecutionResult.status == success
        #   C4: settling block is a valid successor of included block
        raise NotImplementedError("V1-20 scaffold: verify")

    def reconcile(self, shard_id: str) -> ReconcileReport:
        """Reconcile the local DSM tail against the last on-chain anchor.

        Used after a crash in the kernel micro-window (F11, SPEC §6).
        Reads the last on-chain anchor for `shard_id` (by walking the
        sender's recent transactions via Elasticsearch-backed endpoints)
        and compares to the local tail.

        Args:
            shard_id: DSM shard to reconcile.

        Returns:
            ReconcileReport with verdict and optional emitted entry id.

        Emits:
            AnchorReconciledEntry iff verdict is "match" or "local_ahead".
            For "diverged", does not emit — the operator must investigate.

        Test file: tests/multiversx/test_reconcile.py (scaffold)
        """
        # TODO[V1-21]: implement.
        raise NotImplementedError("V1-21 scaffold: reconcile")

    # ------------------------------------------------------------------
    # Utilities exposed on the backend for diagnostics
    # ------------------------------------------------------------------

    def current_regime(self) -> EpochRegime:
        """Return the current detected regime.

        Convenience for tests and dashboards. Not part of the ABC.
        """
        return self._regime_detector.current().regime


# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------


def build_backend_from_config(
    config_path: Optional[Path],
    signer: TransactionSigner,
    storage: Any,
) -> MultiversXAnchorBackend:
    """Convenience factory: load config and wire a backend.

    Args:
        config_path: Path to the adapter TOML config; None uses default.
        signer: Signing provider.
        storage: DSM Storage.

    Returns:
        A ready-to-use MultiversXAnchorBackend with GatewayClient and
        RegimeDetector constructed from config.

    Test file: tests/multiversx/test_backend_contract.py (scaffold)
    """
    from dsm.multiversx.config import load_config
    from dsm.multiversx.regime import RegimeCache, default_cache_path

    config = load_config(config_path)
    client = GatewayClient(config.gateway_url)
    cache = RegimeCache(default_cache_path())
    detector = RegimeDetector(client, cache)
    return MultiversXAnchorBackend(
        gateway_url=config.gateway_url,
        signer=signer,
        account_address=config.account_address,
        storage=storage,
        config=config,
        regime_detector=detector,
        client=client,
    )
