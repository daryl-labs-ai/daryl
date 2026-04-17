"""
Gateway HTTP client and signing adapters.

Backlog: V1-01 (HTTP client), V1-02 (signing and submission).

Wraps the Gateway Proxy REST API endpoints the adapter needs. This module is
the sole surface through which the rest of the adapter talks to MultiversX.
Keeping it isolated means tests can replace `GatewayClient` with a fake for
failure-injection without reaching into the watcher or backend.

Endpoints wrapped (all Gateway Proxy paths):

    GET  /network/config
    GET  /network/status/{shardId}
    GET  /address/{address}
    GET  /address/{address}/nonce
    POST /transaction/send
    GET  /transaction/{hash}?withResults=true
    GET  /block/{shardId}/by-nonce/{nonce}
    GET  /blocks/by-round/{round}

Invariants:
    - Every method translates 2xx into typed data, non-2xx into
      RejectedByGateway or NetworkError per the rules in errors.py.
    - Retries on 5xx with exponential backoff (capped per config).
    - Does NOT implement idempotency; callers drive tx nonce.
    - All timeouts are configurable; defaults are conservative.

Failure modes:
    - NetworkError on transport failure.
    - RejectedByGateway on non-2xx with a parsed error message.
    - PayloadError on malformed JSON.

Test file: tests/multiversx/test_client_gateway.py  (not in the mandatory
skeleton list; mark scaffold when created).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

from dsm.multiversx.errors import (
    NetworkError,
    PayloadError,
    RejectedByGateway,
)


@dataclass(frozen=True)
class SignedTransaction:
    """A MultiversX transaction after signing.

    The `body` is the canonical JSON payload expected by POST /transaction/send.
    The `tx_hash` is the locally-computed hash (SHA-256 of the canonical
    bytes). The client verifies the returned hash matches.
    """

    body: dict[str, Any]
    tx_hash: str


class TransactionSigner(Protocol):
    """Minimal signer interface. An adapter wraps multiversx-sdk's signer."""

    def address(self) -> str: ...
    def sign(self, tx_body: dict[str, Any]) -> SignedTransaction: ...


class GatewayClient:
    """HTTP client for the MultiversX Gateway Proxy.

    Thread-safe for independent calls. Not thread-safe for nonce-dependent
    operations on the same sender (callers must serialize).

    Args:
        base_url: Gateway base URL (e.g. https://gateway.multiversx.com).
        timeout_s: Per-request HTTP timeout in seconds.
        max_retries: Maximum number of retries on 5xx; no retry on 4xx.
        user_agent: Custom user-agent string for support diagnostics.

    Test file: tests/multiversx/test_client_gateway.py (scaffold)
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 30.0,
        max_retries: int = 3,
        user_agent: str = "dsm-mvx/0.1.0",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._user_agent = user_agent

    # ------------------------------------------------------------------
    # Read endpoints
    # ------------------------------------------------------------------

    def get_network_config(self) -> dict[str, Any]:
        """GET /network/config; returns the `data.config` dict.

        Returns:
            Dict with keys including erd_chain_id, erd_round_duration,
            erd_min_gas_price, erd_num_shards_without_meta, etc.

        Raises:
            NetworkError: Transport failure after max_retries.
            PayloadError: Response is not valid JSON or lacks data.config.

        Test file: tests/multiversx/test_client_gateway.py (scaffold)
        """
        # TODO[V1-01]: httpx GET; parse data.config; on error map to typed exc.
        raise NotImplementedError("V1-01 scaffold: get_network_config")

    def get_network_status(self, shard_id: int) -> dict[str, Any]:
        """GET /network/status/{shardId}; returns the `data.status` dict.

        Args:
            shard_id: 0..N-1 for execution shards; 4294967295 for metachain.

        Returns:
            Dict with keys including erd_epoch_number, erd_highest_final_nonce,
            erd_current_round, erd_rounds_per_epoch.

        Test file: tests/multiversx/test_client_gateway.py (scaffold)
        """
        # TODO[V1-01]: same pattern; shard_id embedded in path.
        raise NotImplementedError("V1-01 scaffold: get_network_status")

    def get_account(self, address: str) -> dict[str, Any]:
        """GET /address/{address}; returns `data.account` with balance, nonce, shard.

        Test file: tests/multiversx/test_client_gateway.py (scaffold)
        """
        # TODO[V1-01]
        raise NotImplementedError("V1-01 scaffold: get_account")

    def get_nonce(self, address: str) -> int:
        """GET /address/{address}/nonce; returns the integer nonce.

        Convenience wrapper over get_account for the common case.

        Test file: tests/multiversx/test_client_gateway.py (scaffold)
        """
        # TODO[V1-01]: prefer the dedicated endpoint for lower latency.
        raise NotImplementedError("V1-01 scaffold: get_nonce")

    def get_transaction(
        self, tx_hash: str, *, with_results: bool = True
    ) -> dict[str, Any]:
        """GET /transaction/{hash}?withResults={with_results}; returns `data.transaction`.

        `with_results=True` triggers the gateway to include the processing
        status and SCR (smart-contract results). Required by the watcher to
        detect T₃ under Supernova.

        Test file: tests/multiversx/test_client_gateway.py (scaffold)
        """
        # TODO[V1-01]
        raise NotImplementedError("V1-01 scaffold: get_transaction")

    def get_block_by_nonce(
        self, shard_id: int, nonce: int, *, with_txs: bool = False
    ) -> dict[str, Any]:
        """GET /block/{shardId}/by-nonce/{nonce}; returns the block header + optional txs.

        Test file: tests/multiversx/test_client_gateway.py (scaffold)
        """
        # TODO[V1-01]
        raise NotImplementedError("V1-01 scaffold: get_block_by_nonce")

    def get_blocks_by_round(self, round: int) -> list[dict[str, Any]]:
        """GET /blocks/by-round/{round}; returns all shard blocks for the round.

        Test file: tests/multiversx/test_client_gateway.py (scaffold)
        """
        # TODO[V1-01]
        raise NotImplementedError("V1-01 scaffold: get_blocks_by_round")

    # ------------------------------------------------------------------
    # Write endpoint
    # ------------------------------------------------------------------

    def send_transaction(self, signed: SignedTransaction) -> str:
        """POST /transaction/send; returns the gateway-assigned tx hash.

        Invariants:
            - The returned hash MUST match signed.tx_hash; if not, raises
              PayloadError (this has historically indicated a gateway bug
              or a locally-miscomputed canonical form).

        Raises:
            RejectedByGateway: If the gateway returns a 4xx with an error
                message (F1 family). retry_eligible is set per the
                classify_rejection_reason table in errors.py.
            NetworkError: Transport-level failure after retries.

        Test file: tests/multiversx/test_client_submit.py (scaffold)
        """
        # TODO[V1-02]: implement POST; parse 4xx errors into RejectedByGateway
        # with classify_rejection_reason(msg).
        raise NotImplementedError("V1-02 scaffold: send_transaction")


# ---------------------------------------------------------------------------
# Helpers for parsing gateway envelopes
# ---------------------------------------------------------------------------


def _unwrap_envelope(
    response_json: dict[str, Any], expected_key: Optional[str] = None
) -> Any:
    """Unwrap the standard {data, error, code} response envelope.

    Args:
        response_json: The parsed JSON body of a gateway response.
        expected_key: If set, return `data[expected_key]` instead of `data`.

    Returns:
        The `data` field (or `data[expected_key]`) on success.

    Raises:
        PayloadError: If the envelope is malformed or `code` != "successful".
        RejectedByGateway: If `code` is an error code with a non-empty message.

    Test file: tests/multiversx/test_client_gateway.py (scaffold)
    """
    # TODO[V1-01]: implement per gateway-overview.md envelope spec.
    raise NotImplementedError("V1-01 scaffold: _unwrap_envelope")
