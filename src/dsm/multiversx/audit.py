"""
Audit CLI for MultiversX-anchored DSM logs.

Backlog: V1-20.

Implements `dsm verify --mvx`:
    Walks a DSM shard, finds every AnchorIntent, fetches the corresponding
    tx from the MultiversX gateway, runs the SPEC §7.2 check list, and
    reports ok / mismatch / pending / error verdicts.

Regime-aware semantics:
    - For each intent, reads `epoch_regime` from the intent entry.
    - For regime=supernova, REQUIRES a terminal `anchor_settled` or
      `anchor_failed` entry to exist. An intent in state INCLUDED is
      treated as `pending` (not a failure).
    - For regime=andromeda, accepts `anchor_settled` (which the backend
      always emits even under andromeda for regime-agnostic audit).
    - Anchors that predate the adapter's regime-tagging (legacy DSM logs
      from before this adapter) are flagged as `unknown_regime` and
      treated as andromeda by default — this is a conservative compromise
      for backfill compatibility.

Exit codes:
    0 — all anchors verify
    1 — one or more mismatches (actionable)
    2 — cannot compute a verdict (gateway unreachable, etc.)

Invariants:
    - Audit never writes to the DSM log; it is strictly read-only over
      local storage and gateway.
    - The audit tool MUST refuse to validate an intent whose terminal
      state has not been reached under its own regime rule. Reporting
      `pending` is the honest outcome; reporting `ok` on an INCLUDED
      supernova anchor would silently mask execution failures.

Failure modes:
    - AuditError: structural issue (log unreadable, gateway missing).
    - NetworkError: transport failure.

Test file: tests/multiversx/test_audit_cli.py
"""
from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Optional

from dsm.multiversx.backend import MultiversXAnchorBackend
from dsm.multiversx.errors import AuditError
from dsm.multiversx.schemas import (
    AnchorFailedEntry,
    AnchorIncludedEntry,
    AnchorIntent,
    AnchorRejectedEntry,
    AnchorSettledEntry,
    AnchorStuckEntry,
    AnchorSubmittedEntry,
    AnchorTimedOutEntry,
    VerifyResult,
)


def verify_anchor_chain(entries: Iterable[Any]) -> VerifyResult:
    """Audit a single anchor's DSM log entry chain and return a VerifyResult.

    This is the V1-F2 audit primitive: given the sequence of entries
    produced by the state machine for one `intent_id`, classify the
    overall verdict.

    Semantics (regime-agnostic; the watcher already normalized regime-
    specific details into the entry sequence):

        - Presence of an AnchorFailedEntry  → verdict='execution_failed'
        - Presence of an AnchorRejectedEntry → verdict='execution_failed'
          (classified here as a chain-level failure; callers that need to
          distinguish pre-inclusion rejection from post-inclusion failure
          can inspect the entries directly)
        - Presence of an AnchorSettledEntry (and no failure) → verdict='ok'
        - Otherwise (e.g. only an AnchorIncludedEntry)       → verdict='pending'

    A chain that contains BOTH an AnchorSettledEntry and an
    AnchorFailedEntry is a state-machine bug; this function reports
    'execution_failed' in that case and adds a diagnostic note, since
    the most audit-safe interpretation is to surface the failure.

    Args:
        entries: Iterable of AnchorLogEntry objects for one intent, in
            emission order. Consumed once.

    Returns:
        VerifyResult with verdict and per-check booleans.

    Test file: tests/multiversx/test_f2_execution_fail.py
    """
    entries_list = list(entries)
    has_included = any(isinstance(e, AnchorIncludedEntry) for e in entries_list)
    has_settled = any(isinstance(e, AnchorSettledEntry) for e in entries_list)
    has_failed = any(isinstance(e, AnchorFailedEntry) for e in entries_list)
    has_rejected = any(isinstance(e, AnchorRejectedEntry) for e in entries_list)
    has_timed_out = any(isinstance(e, AnchorTimedOutEntry) for e in entries_list)
    has_stuck = any(isinstance(e, AnchorStuckEntry) for e in entries_list)

    intent_id = _chain_intent_id(entries_list)
    notes: list[str] = []

    checks = {
        "included_observed": has_included,
        "settled_observed": has_settled,
        "failed_observed": has_failed,
        "rejected_observed": has_rejected,
        "timed_out_observed": has_timed_out,
        "stuck_observed": has_stuck,
    }

    if has_failed and has_settled:
        notes.append(
            "chain contains BOTH AnchorSettledEntry and AnchorFailedEntry; "
            "reporting execution_failed (most audit-safe interpretation)"
        )
        return VerifyResult(
            intent_id=intent_id,
            verdict="execution_failed",
            checks=checks,
            notes=notes,
        )
    if has_failed or has_rejected:
        return VerifyResult(
            intent_id=intent_id,
            verdict="execution_failed",
            checks=checks,
            notes=notes,
        )
    if has_settled:
        return VerifyResult(
            intent_id=intent_id, verdict="ok", checks=checks, notes=notes
        )
    if has_included or has_timed_out or has_stuck:
        return VerifyResult(
            intent_id=intent_id, verdict="pending", checks=checks, notes=notes
        )
    return VerifyResult(
        intent_id=intent_id, verdict="not_found", checks=checks, notes=notes
    )


def _chain_intent_id(entries: list[Any]) -> uuid.UUID:
    """Return the first non-null intent_id found in the chain, else UUID(int=0)."""
    for entry in entries:
        iid = getattr(entry, "intent_id", None)
        if iid is not None:
            return iid
    return uuid.UUID(int=0)


@dataclass
class AuditReport:
    """Aggregate audit result over a DSM shard.

    Fields:
        shard_id: Inspected shard.
        total_intents: Number of AnchorIntent entries found.
        ok: Intents that passed all checks.
        mismatches: Intents whose on-chain data diverged.
        pending: Intents that have not reached terminal state per regime.
        not_found: Intents whose tx_hash is not visible on the gateway.
        execution_failed: Intents whose on-chain execution failed.
        errors: Intents where verification itself could not complete.
        per_intent: Per-intent VerifyResult in iteration order.
    """

    shard_id: str
    total_intents: int = 0
    ok: int = 0
    mismatches: int = 0
    pending: int = 0
    not_found: int = 0
    execution_failed: int = 0
    errors: int = 0
    per_intent: list[VerifyResult] = field(default_factory=list)

    def exit_code(self) -> int:
        """Compute the process exit code per the module docstring rules."""
        if self.errors > 0:
            return 2
        if self.mismatches > 0 or self.not_found > 0:
            return 1
        return 0


def audit_shard(
    storage: Any,  # dsm.core.Storage (duck-typed; kernel is frozen)
    shard_id: str,
    backend: MultiversXAnchorBackend,
    *,
    max_clock_skew_ms: int = 60_000,
) -> AuditReport:
    """Run a full audit of `shard_id` against the MultiversX gateway.

    Args:
        storage: DSM Storage. Accessed read-only.
        shard_id: Name of the shard to audit.
        backend: The MultiversXAnchorBackend whose verify() is called for
            each intent.
        max_clock_skew_ms: Allowed skew between local intent timestamp
            and on-chain block timestamp.

    Returns:
        AuditReport with per-intent and aggregate results.

    Raises:
        AuditError: Storage is unreadable or structurally corrupt.

    Test file: tests/multiversx/test_audit_cli.py
    """
    # TODO[V1-20]: implement:
    #   1. Iterate AnchorIntent entries from storage.read(shard_id).
    #   2. For each, find the latest terminal-state entry (settled /
    #      failed / rejected / stuck) with matching intent_id.
    #   3. Build the on_chain_ref dict (tx_hash and optional block_nonce).
    #   4. Call backend.verify(intent_entry_id, on_chain_ref).
    #   5. Tally into AuditReport.
    raise NotImplementedError("V1-20 scaffold: audit_shard")


def iter_intents_with_terminal_states(
    storage: Any, shard_id: str
) -> Iterator[tuple[dict[str, Any], Optional[dict[str, Any]]]]:
    """Iterate (intent_entry, terminal_entry_or_none) pairs in order.

    Pure over storage's read interface. Useful for testing without a full
    backend. If no terminal entry exists for an intent, the second element
    is None (intent is pending or stuck).

    Test file: tests/multiversx/test_audit_cli.py
    """
    # TODO[V1-20]: implement using storage.read() only; do not mutate.
    raise NotImplementedError("V1-20 scaffold: iter_intents_with_terminal_states")


# ---------------------------------------------------------------------------
# CLI entry point — wired via pyproject.toml console_script or `dsm verify`
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    """Argument parser for `dsm verify --mvx`.

    Exposed separately for tests that want to invoke the CLI with custom
    argv without involving sys.exit.
    """
    parser = argparse.ArgumentParser(
        prog="dsm verify --mvx",
        description="Verify MultiversX anchors in a DSM shard.",
    )
    parser.add_argument("--shard", required=True, help="DSM shard name to audit")
    parser.add_argument("--data-dir", default="memory", help="DSM storage data dir")
    parser.add_argument("--config", default=None, help="Adapter TOML config path")
    parser.add_argument(
        "--max-clock-skew-ms",
        type=int,
        default=60_000,
        help="Allowed skew between local intent and on-chain block timestamps",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Report output format",
    )
    return parser


def cli_main(argv: Optional[list[str]] = None) -> int:
    """Entry point for `dsm verify --mvx`.

    Returns the process exit code (0/1/2 per module docstring).

    Test file: tests/multiversx/test_audit_cli.py
    """
    # TODO[V1-20]: implement:
    #   1. parse args
    #   2. load Storage from data-dir
    #   3. build backend via build_backend_from_config(config_path)
    #   4. call audit_shard()
    #   5. render report (text or JSON)
    #   6. return report.exit_code()
    raise NotImplementedError("V1-20 scaffold: cli_main")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli_main())
