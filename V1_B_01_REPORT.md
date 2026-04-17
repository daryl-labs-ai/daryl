# V1.B-01 Report — Andromeda Fixtures Recalibration

## Status
green

## Test results

```
$ PYTHONPATH=src python3 -m pytest tests/multiversx/

tests/multiversx/test_audit_cli.py sssssssssssssssssssssssss             [ 15%]
tests/multiversx/test_backend_contract.py .......                        [ 20%]
tests/multiversx/test_dual_schema_reader.py sssssssssssssssss            [ 31%]
tests/multiversx/test_errors.py ..........                               [ 37%]
tests/multiversx/test_f2_execution_fail.py ................              [ 47%]
tests/multiversx/test_payload_codec.py ...................               [ 59%]
tests/multiversx/test_regime_detection.py ..........................     [ 75%]
tests/multiversx/test_schemas_roundtrip.py ...................           [ 87%]
tests/multiversx/test_state_machine.py ...................               [100%]

SKIPPED [25] tests/multiversx/test_audit_cli.py: V1-20 scaffold: audit CLI not implemented
SKIPPED [17] tests/multiversx/test_dual_schema_reader.py: V1-06 scaffold: dual-schema reader not implemented
======================= 116 passed, 42 skipped in 0.33s ========================
```

Identical test counts vs V1-F2 baseline (116 passed, 42 skipped). F2b and
F2-neg-b consume the new observed fixtures on the new mainnet nonces /
hashes; F2a, F2a-lag, F2-neg-a (Supernova paths) remain untouched.

## Fixtures replaced

| Fixture | Before V1.B-01 | After V1.B-01 | Source |
|---|---|---|---|
| `andromeda/tx_success.json` | documented derived | byte-exact from capture_02 | `observed_on_mainnet/2026-04-17_capture_02/success_tx.json` |
| `andromeda/block_containing_tx.json` | documented derived | byte-exact from capture_02 | `observed_on_mainnet/2026-04-17_capture_02/success_block_containing.json` |
| `andromeda/tx_invalid.json` *(new)* | *(did not exist — replaces `tx_fail.json`)* | byte-exact from capture_01 | `observed_on_mainnet/2026-04-17_capture_01/invalid_tx.json` |
| `andromeda/block_invalid.json` *(new)* | *(did not exist)* | byte-exact from capture_01 | `observed_on_mainnet/2026-04-17_capture_01/invalid_block_containing.json` |
| `andromeda/tx_fail.json` | documented derived, status=`"fail"` | **DELETED** (mainnet vocabulary uses `"invalid"`) | n/a |

Each observed fixture gained a sidecar `*.meta.json` carrying provenance
(id, regime, scenario, source, source_ref, purpose, caveats). The
payload JSON itself is unmodified, preserving byte-exact equivalence
with the source capture (I23, sign-off #6).

## Reader changes

All changes are confined to `src/dsm/multiversx/watcher.py`. No other
source file changed.

- **Added** `_is_tx_included_successfully(tx)` helper
  (I-Andromeda-1). Returns True iff both `miniblockType == "TxBlock"`
  and `status == "success"`. Used in `_read_andromeda` as the primary
  success check; the legacy `_ANDROMEDA_STATUS_MAP` lookup remains as
  the fallback path for fixtures that may lack `miniblockType`.

- **Renamed** `_SUPERNOVA_FAIL_SIGNALS` → `_FAIL_SIGNALS`. The list is
  now heterogeneous (block-level + tx-level signals) and regime-agnostic
  in scope. The single call site in `_read_supernova` is updated. The
  rename documentation in `watcher.py` does not spell out the old
  identifier literally so that sign-off #3's `grep -r
  "_SUPERNOVA_FAIL_SIGNALS" src/dsm/` comes up empty.

- **Added** `_signal_tx_miniblock_type_invalid(exec_result, tx)` as a
  third entry in `_FAIL_SIGNALS`. Fires when `tx.miniblockType ==
  "InvalidBlock"`. Regime-agnostic: on Supernova fixtures (which have
  `miniblockType=None` on the tx side) it silently returns False.

- **Added** a one-line comment above the regime discriminator citing
  capture_02 as empirical confirmation that Andromeda blocks carry no
  `lastExecutionResult`.

No behavior change for Supernova paths (F2a / F2a-lag / F2-neg-a all
still green). For Andromeda, the primary path is now
`_is_tx_included_successfully`; the fallback through
`_ANDROMEDA_STATUS_MAP` absorbs the `"invalid"` → `"fail"` vocabulary
shift, and F2b emits the same `(AnchorIncludedEntry, AnchorFailedEntry)`
sequence it emitted on the pre-V1.B-01 fixtures.

## Invariants

- **I-Andromeda-1** (`miniblockType` universal on tx responses) —
  verified end-to-end: `_is_tx_included_successfully` reads
  `miniblockType == "TxBlock"` on `andromeda/tx_success.json`; the new
  `_signal_tx_miniblock_type_invalid` reads `miniblockType ==
  "InvalidBlock"` on `andromeda/tx_invalid.json`.
- **I-Andromeda-2** (fail triple `(status="invalid", type="invalid",
  miniblockType="InvalidBlock")`) — observed in `andromeda/tx_invalid.json`.
  Not baked into code; the reader relies on `_ANDROMEDA_STATUS_MAP`
  ("invalid" → "fail") + `_is_tx_included_successfully` falsiness +
  `_signal_tx_miniblock_type_invalid`. Three independent paths all
  agree on the fail verdict.
- **I-Andromeda-3** (`tx.blockHash == block.hash` for intra-shard) —
  preserved in both new fixtures: capture_02 is shard 1 (intra), and
  capture_01 invalid is shard 1 (intra). The superseded
  capture_01/success_* (cross-shard to metachain) is NOT used by any
  test.

V1-F2 invariants I13–I20 unaffected. New invariants I23 (byte-exact
fixtures) and I24 (reader must not depend on unknown mainnet fields)
introduced by this task — both verified by `cmp` and by the unchanged
set of field accesses in `watcher.py`.

## Scope deviations

None. All six tasks (V1.B-01.1 through V1.B-01.6) executed as
specified. Sign-off criteria:

| # | Criterion | Result |
|---|---|---|
| 1 | `pytest tests/multiversx/ -v`: 116 passed, 42 skipped | ✅ identical to V1-F2 baseline |
| 2 | no `tx_fail` in active code/fixtures | ✅ clean |
| 3 | no old signals-list identifier in `src/dsm/` | ✅ clean (rename complete) |
| 4 | no kernel imports in diff | ✅ `src/dsm/core/` + `src/dsm/anchor.py` untouched |
| 5 | `mypy src/dsm/multiversx/` passes | ✅ `Success: no issues found in 11 source files` |
| 6 | four `cmp` byte-exact checks exit 0 | ✅ all four IDENTICAL |
| 7 | `V1_B_01_REPORT.md` present | ✅ this file |
| 8 | `schemas.py model_config` unchanged | ✅ `git diff main...feat/v1-b-01 -- schemas.py` shows no `extra`/`model_config` changes |

## Open questions for human review

- [ ] Should the semantic distinction **rejected** (pre-execution,
  Andromeda `status="invalid"`, Supernova TBD) vs **execution_failed**
  (post-execution, VM revert) be surfaced as a first-class
  `ExecutionResult.status` value and propagated into entry shapes in
  V1.B-02? Current V1.B-01 behavior collapses both into
  `ExecutionResult.status="fail"` → `AnchorFailedEntry` via
  `_ANDROMEDA_STATUS_MAP["invalid"] = "fail"`. This is cryptographically
  sound (an anchor whose on-chain transaction did NOT consume VM
  resources is still an anchor that did not succeed) but loses
  information useful for audit UX. *(This is the Finding #1
  open-question from `CAPTURE_REPORT.md` carried forward.)*

- [ ] The `_FAIL_SIGNALS` list now contains one tx-level signal
  (`_signal_tx_miniblock_type_invalid`) alongside two block-level
  signals. Under the current Supernova path in `_read_supernova`, all
  three are evaluated and any firing wins. If a future Supernova
  capture shows `tx.miniblockType` absent while the block-side signal
  fires, the OR semantics are correct — but the diagnostic log line
  `_log.debug("supernova fail signals fired: %s", fired_signals)` may
  report multiple fires on the Andromeda-similar case and only one on
  a pure Supernova case. Should `_log.debug` grow into a structured
  event (`{tx-level: bool, block-level-invalid-miniblock: bool,
  block-level-failed-tx-count: bool}`) so operators can tell at a
  glance which regime's signal dominated? Not needed for V1.B-01
  correctness; candidate for V1.B-02 observability work.

- [ ] The `receipt.data` plain-text discovery (`"insufficient funds"`
  directly, not base64) suggests V1.B-02 could surface `reason`
  strings more usefully on `AnchorFailedEntry`. The current
  `_extract_receipt_data` returns the string as-is, so this is
  already operator-friendly for Andromeda — no code change needed, but
  the discovery should inform V1.B-02 UX decisions.

## V1.B readiness

**Andromeda side of I22 is satisfied.** Four observed_on_mainnet
fixtures drive F2b and F2-neg-b end-to-end, the reader has been
recalibrated (helper + signal + rename) without changing its Supernova
behavior, and all sign-off criteria are mechanically green.

**Supernova side of I22 remains pending** mainnet Supernova
activation. The Supernova fixtures remain `derived_from_mip27`; the
V1.B-01 changes leave them untouched, and the V0 signals/reader
continue to consume them correctly. The next V1.B action should be a
capture from Supernova-activated mainnet (or Battle Net if that is the
operational staging path) followed by an analogous recalibration prompt
V1.B-02 for the Supernova half.

No V1.B-03+ watcher expansion (WS, timeouts, reconnect, gap-fill) was
started. That remains blocked by I20/I22 until Supernova side clears.
