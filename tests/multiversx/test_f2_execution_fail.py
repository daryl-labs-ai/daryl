"""
F2 — Execution-fail detection under Andromeda and Supernova.

Backlog: V1-F2.1/.2/.3. Failure matrix row F2.

This is the single most important correctness test of the Supernova
integration. If this test file passes, the three-stage design is doing
its job. If it fails, the adapter is silently letting execution failures
pass as successes — exactly the failure mode that justifies the whole
T₂/T₃ decoupling.

Test chain (I17):

    raw fixture JSON
      → httpx.MockTransport
      → MinimalPollingWatcher (which internally calls DualSchemaReader)
      → state machine (next_state)
      → list of AnchorLogEntry objects
      → audit.verify_anchor_chain()
      → VerifyResult

The ONLY mock permitted in this chain is the HTTP transport (I17).
Reader, state machine, and audit are exercised end-to-end.
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Any, Iterable

import httpx
import pytest

from dsm.multiversx.audit import verify_anchor_chain
from dsm.multiversx.schemas import (
    AnchorFailedEntry,
    AnchorIncludedEntry,
    AnchorSettledEntry,
    AnchorState,
    AnchorSubmissionReceipt,
)
from dsm.multiversx.state_machine import next_state
from dsm.multiversx.watcher import MinimalPollingWatcher

# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Deterministic values shared across fixtures (from fixtures/README.md).
INTENT_ID = uuid.UUID("01234567-89ab-7cde-8123-456789abcdef")
# Supernova fixtures are still derived_from_mip27 (pending Supernova mainnet activation);
# they keep the original deterministic hash and nonces.
TX_HASH = "d9ed0f70fc2326adb8f02c1cc44e4a531c5d1808bb6aa8558a396f03694a554a"
SUPERNOVA_CONTAINING_NONCE = 10000000
SUPERNOVA_SETTLING_NONCE = 10000001
# Andromeda fixtures are observed_on_mainnet (2026-04-17). Two independent
# capture scenarios, each with its own tx hash and block nonce.
ANDROMEDA_SUCCESS_TX_HASH = "c07636310ed94a4b169019666384283f0eb411733617da75179aef1b45685146"
ANDROMEDA_SUCCESS_NONCE = 30024315
ANDROMEDA_INVALID_TX_HASH = "95235d257505512d39f98dc60765cdebfc19fe90f39bea4b05661c10874ae8be"
ANDROMEDA_INVALID_NONCE = 30023889


def _load(relpath: str) -> dict[str, Any]:
    """Load a fixture JSON file by path relative to fixtures/."""
    return json.loads((FIXTURES_DIR / relpath).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# HTTP transport scripting — the ONLY mock in the chain
# ---------------------------------------------------------------------------


def _make_transport(
    *,
    tx_sequence: list[dict[str, Any]],
    block_by_nonce: dict[int, dict[str, Any]],
) -> httpx.MockTransport:
    """Script the tx-endpoint sequence and the block-by-nonce mapping.

    - `tx_sequence`: responses served in order on each GET /transaction/{hash}.
      After the last is served, the last response continues to be returned
      (simulates a persistent tail state).
    - `block_by_nonce`: maps {nonce: response} for GET /block/{shard}/by-nonce/{nonce}.
    """
    tx_iter = iter(tx_sequence)
    state = {"last_tx": None}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/transaction/"):
            try:
                state["last_tx"] = next(tx_iter)
            except StopIteration:
                pass  # keep returning the last tx response
            return httpx.Response(200, json=state["last_tx"])
        if path.startswith("/block/"):
            parts = path.strip("/").split("/")
            # /block/{shard}/by-nonce/{nonce}
            try:
                nonce = int(parts[3])
            except (IndexError, ValueError):
                return httpx.Response(400, json={"error": "bad block path"})
            payload = block_by_nonce.get(nonce)
            if payload is None:
                return httpx.Response(404, json={"error": f"no block for nonce {nonce}"})
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": f"no route for {path}"})

    return httpx.MockTransport(handler)


def _receipt(regime: str, tx_hash: str = TX_HASH) -> AnchorSubmissionReceipt:
    return AnchorSubmissionReceipt(
        intent_id=INTENT_ID,
        tx_hash=tx_hash,
        submitted_at_ms=0,
        nonce=42,
        sender_shard=0,
        regime=regime,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Driver: run watcher → state machine → entry list
# ---------------------------------------------------------------------------


def _drive_to_entries(
    watcher: MinimalPollingWatcher,
    receipt: AnchorSubmissionReceipt,
    regime: str,
) -> list[Any]:
    """Pipe watcher events through next_state to produce the entry chain.

    The anchor is assumed to be in SUBMITTED at watcher start (we already
    have a submission receipt). Each yielded event advances the state
    machine and contributes exactly one entry.
    """
    entries: list[Any] = []
    state = AnchorState.SUBMITTED
    for event in watcher.watch(receipt):
        result = next_state(state, event, regime)  # type: ignore[arg-type]
        state = result.new_state
        entries.append(result.entry_to_emit)
    return entries


def _assert_no_settled_entry(entries: Iterable[Any]) -> None:
    """I18 / sign-off criterion #5: fail-path chains MUST NOT contain an
    AnchorSettledEntry at any position."""
    for idx, entry in enumerate(entries):
        assert not isinstance(entry, AnchorSettledEntry), (
            f"AnchorSettledEntry found at position {idx} in fail-path chain; "
            f"this is a sign-off blocker"
        )


# ---------------------------------------------------------------------------
# F2a — Supernova execution fail
# ---------------------------------------------------------------------------


class TestF2aSupernovaExecutionFail:
    """Supernova: tx included at T₂; settling block's lastExecutionResult
    carries an InvalidBlock miniblock → chain resolves to FAILED."""

    def _run(self) -> list[Any]:
        transport = _make_transport(
            tx_sequence=[
                _load("supernova/tx_included_pending.json"),
                _load("supernova/tx_settled_fail.json"),
            ],
            block_by_nonce={
                SUPERNOVA_CONTAINING_NONCE: _load("supernova/block_containing_tx.json"),
                SUPERNOVA_SETTLING_NONCE: _load("supernova/block_settling_fail.json"),
            },
        )
        http = httpx.Client(base_url="http://stub.invalid", transport=transport)
        watcher = MinimalPollingWatcher(http=http, regime="supernova")
        return _drive_to_entries(watcher, _receipt("supernova"), "supernova")

    def test_exactly_included_then_failed(self) -> None:
        entries = self._run()
        assert len(entries) == 2, f"expected 2 entries, got {len(entries)}: {entries!r}"
        assert isinstance(entries[0], AnchorIncludedEntry)
        assert isinstance(entries[1], AnchorFailedEntry)

    def test_no_settled_entry_anywhere(self) -> None:
        """Sign-off criterion #5."""
        _assert_no_settled_entry(self._run())

    def test_failed_entry_references_settling_block_nonce(self) -> None:
        entries = self._run()
        failed = entries[1]
        assert isinstance(failed, AnchorFailedEntry)
        assert failed.failed_in_block_nonce == SUPERNOVA_SETTLING_NONCE

    def test_audit_verdict_is_execution_failed(self) -> None:
        result = verify_anchor_chain(self._run())
        assert result.verdict == "execution_failed"


# ---------------------------------------------------------------------------
# F2b — Andromeda execution fail
# ---------------------------------------------------------------------------


class TestF2bAndromedaExecutionFail:
    """Andromeda: execution-fail is visible in the same block as inclusion
    (T₂ ≡ T₃). Watcher synthesizes Include + ExecFail co-terminous."""

    def _run(self) -> list[Any]:
        # Mainnet-observed (2026-04-17): tx.status='invalid', miniblockType='InvalidBlock'.
        # The block has miniBlocks[2].type == 'InvalidBlock' as the block-side signal.
        transport = _make_transport(
            tx_sequence=[_load("andromeda/tx_invalid.json")],
            block_by_nonce={
                ANDROMEDA_INVALID_NONCE: _load("andromeda/block_invalid.json"),
            },
        )
        http = httpx.Client(base_url="http://stub.invalid", transport=transport)
        watcher = MinimalPollingWatcher(http=http, regime="andromeda")
        return _drive_to_entries(
            watcher, _receipt("andromeda", tx_hash=ANDROMEDA_INVALID_TX_HASH), "andromeda"
        )

    def test_exactly_included_then_failed(self) -> None:
        entries = self._run()
        assert len(entries) == 2
        assert isinstance(entries[0], AnchorIncludedEntry)
        assert isinstance(entries[1], AnchorFailedEntry)

    def test_no_settled_entry_anywhere(self) -> None:
        _assert_no_settled_entry(self._run())

    def test_audit_verdict_is_execution_failed(self) -> None:
        result = verify_anchor_chain(self._run())
        assert result.verdict == "execution_failed"


# ---------------------------------------------------------------------------
# F2a-lag — Supernova execution fail with a lagging tx endpoint
# ---------------------------------------------------------------------------


class TestF2aLagSupernovaTxEndpointLags:
    """F2a variant: tx_settled_fail.json is mutated at runtime so its
    `status` reads 'pending' while the settling block already shows an
    InvalidBlock miniblock. The reader MUST derive failure from the
    block-side signal alone (I14)."""

    def _run(self) -> list[Any]:
        # Runtime mutation of a copy — the fixture file on disk stays
        # unchanged (I: "Do NOT modify provided fixtures in place").
        lagging_tx = copy.deepcopy(_load("supernova/tx_settled_fail.json"))
        assert lagging_tx["data"]["transaction"]["status"] == "fail"
        lagging_tx["data"]["transaction"]["status"] = "pending"
        transport = _make_transport(
            tx_sequence=[
                _load("supernova/tx_included_pending.json"),
                lagging_tx,
            ],
            block_by_nonce={
                SUPERNOVA_CONTAINING_NONCE: _load("supernova/block_containing_tx.json"),
                SUPERNOVA_SETTLING_NONCE: _load("supernova/block_settling_fail.json"),
            },
        )
        http = httpx.Client(base_url="http://stub.invalid", transport=transport)
        watcher = MinimalPollingWatcher(http=http, regime="supernova")
        return _drive_to_entries(watcher, _receipt("supernova"), "supernova")

    def test_exactly_included_then_failed_despite_tx_lag(self) -> None:
        entries = self._run()
        assert len(entries) == 2
        assert isinstance(entries[0], AnchorIncludedEntry)
        assert isinstance(entries[1], AnchorFailedEntry)

    def test_no_settled_entry_anywhere(self) -> None:
        _assert_no_settled_entry(self._run())

    def test_audit_verdict_is_execution_failed(self) -> None:
        result = verify_anchor_chain(self._run())
        assert result.verdict == "execution_failed"

    def test_fixture_file_on_disk_unchanged(self) -> None:
        """Regression guard: the mutation must be on an in-memory copy."""
        on_disk = _load("supernova/tx_settled_fail.json")
        assert on_disk["data"]["transaction"]["status"] == "fail"


# ---------------------------------------------------------------------------
# F2-neg-a / F2-neg-b — baseline success controls
# ---------------------------------------------------------------------------
# These are the control tests the prompt requires alongside F2a/F2b/F2a-lag:
# they prove the chain produces `ok` (not `execution_failed`) on valid
# happy-path inputs. A failure here would mean we're returning
# `execution_failed` indiscriminately.


class TestF2NegASupernovaExecutionSuccess:
    def _run(self) -> list[Any]:
        transport = _make_transport(
            tx_sequence=[
                _load("supernova/tx_included_pending.json"),
                _load("supernova/tx_settled_success.json"),
            ],
            block_by_nonce={
                SUPERNOVA_CONTAINING_NONCE: _load("supernova/block_containing_tx.json"),
                SUPERNOVA_SETTLING_NONCE: _load("supernova/block_settling_success.json"),
            },
        )
        http = httpx.Client(base_url="http://stub.invalid", transport=transport)
        watcher = MinimalPollingWatcher(http=http, regime="supernova")
        return _drive_to_entries(watcher, _receipt("supernova"), "supernova")

    def test_emits_included_then_settled(self) -> None:
        entries = self._run()
        assert len(entries) == 2
        assert isinstance(entries[0], AnchorIncludedEntry)
        assert isinstance(entries[1], AnchorSettledEntry)

    def test_audit_verdict_is_ok(self) -> None:
        assert verify_anchor_chain(self._run()).verdict == "ok"


class TestF2NegBAndromedaExecutionSuccess:
    def _run(self) -> list[Any]:
        transport = _make_transport(
            tx_sequence=[_load("andromeda/tx_success.json")],
            block_by_nonce={
                ANDROMEDA_SUCCESS_NONCE: _load("andromeda/block_containing_tx.json"),
            },
        )
        http = httpx.Client(base_url="http://stub.invalid", transport=transport)
        watcher = MinimalPollingWatcher(http=http, regime="andromeda")
        return _drive_to_entries(
            watcher, _receipt("andromeda", tx_hash=ANDROMEDA_SUCCESS_TX_HASH), "andromeda"
        )

    def test_emits_included_then_settled(self) -> None:
        entries = self._run()
        assert len(entries) == 2
        assert isinstance(entries[0], AnchorIncludedEntry)
        assert isinstance(entries[1], AnchorSettledEntry)

    def test_audit_verdict_is_ok(self) -> None:
        assert verify_anchor_chain(self._run()).verdict == "ok"


# ---------------------------------------------------------------------------
# Sign-off criterion #3 — reader is on the critical path
# ---------------------------------------------------------------------------
# A reviewer verifies this by monkey-patching the reader to raise; all F2
# tests must fail. We encode that here as one test so the reviewer need
# not craft the check by hand.


class TestF2ReaderIsOnCriticalPath:
    """Replace DualSchemaReader.read_execution_result with a raiser;
    every F2 test must fail. If any of them don't, the test is bypassing
    the reader — an I17 violation."""

    def test_replacing_reader_breaks_f2a(self, monkeypatch) -> None:
        from dsm.multiversx import watcher as watcher_mod

        def _raiser(*args, **kwargs):  # pragma: no cover — body irrelevant
            raise NotImplementedError("reader short-circuited for critical-path proof")

        monkeypatch.setattr(
            watcher_mod.DualSchemaReader, "read_execution_result", _raiser
        )
        transport = _make_transport(
            tx_sequence=[
                _load("supernova/tx_included_pending.json"),
                _load("supernova/tx_settled_fail.json"),
            ],
            block_by_nonce={
                SUPERNOVA_CONTAINING_NONCE: _load("supernova/block_containing_tx.json"),
                SUPERNOVA_SETTLING_NONCE: _load("supernova/block_settling_fail.json"),
            },
        )
        http = httpx.Client(base_url="http://stub.invalid", transport=transport)
        watcher = MinimalPollingWatcher(http=http, regime="supernova")
        with pytest.raises(NotImplementedError):
            list(watcher.watch(_receipt("supernova")))
