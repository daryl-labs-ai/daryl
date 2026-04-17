# V1-F2 Report — Execution-Fail Detection Under Andromeda and Supernova

**Status:** green. F2a, F2b, F2a-lag, F2-neg-a, F2-neg-b are all passing. V0's
100 tests remain green; no kernel file was touched.

## 1. Status

green

## 2. Test results

```
$ PYTHONPATH=src python3 -m pytest tests/multiversx/test_f2_execution_fail.py -v

tests/multiversx/test_f2_execution_fail.py::TestF2aSupernovaExecutionFail::test_exactly_included_then_failed PASSED                 [  6%]
tests/multiversx/test_f2_execution_fail.py::TestF2aSupernovaExecutionFail::test_no_settled_entry_anywhere PASSED                    [ 12%]
tests/multiversx/test_f2_execution_fail.py::TestF2aSupernovaExecutionFail::test_failed_entry_references_settling_block_nonce PASSED [ 18%]
tests/multiversx/test_f2_execution_fail.py::TestF2aSupernovaExecutionFail::test_audit_verdict_is_execution_failed PASSED            [ 25%]
tests/multiversx/test_f2_execution_fail.py::TestF2bAndromedaExecutionFail::test_exactly_included_then_failed PASSED                 [ 31%]
tests/multiversx/test_f2_execution_fail.py::TestF2bAndromedaExecutionFail::test_no_settled_entry_anywhere PASSED                    [ 37%]
tests/multiversx/test_f2_execution_fail.py::TestF2bAndromedaExecutionFail::test_audit_verdict_is_execution_failed PASSED            [ 43%]
tests/multiversx/test_f2_execution_fail.py::TestF2aLagSupernovaTxEndpointLags::test_exactly_included_then_failed_despite_tx_lag PASSED [ 50%]
tests/multiversx/test_f2_execution_fail.py::TestF2aLagSupernovaTxEndpointLags::test_no_settled_entry_anywhere PASSED                [ 56%]
tests/multiversx/test_f2_execution_fail.py::TestF2aLagSupernovaTxEndpointLags::test_audit_verdict_is_execution_failed PASSED        [ 62%]
tests/multiversx/test_f2_execution_fail.py::TestF2aLagSupernovaTxEndpointLags::test_fixture_file_on_disk_unchanged PASSED           [ 68%]
tests/multiversx/test_f2_execution_fail.py::TestF2NegASupernovaExecutionSuccess::test_emits_included_then_settled PASSED            [ 75%]
tests/multiversx/test_f2_execution_fail.py::TestF2NegASupernovaExecutionSuccess::test_audit_verdict_is_ok PASSED                    [ 81%]
tests/multiversx/test_f2_execution_fail.py::TestF2NegBAndromedaExecutionSuccess::test_emits_included_then_settled PASSED            [ 87%]
tests/multiversx/test_f2_execution_fail.py::TestF2NegBAndromedaExecutionSuccess::test_audit_verdict_is_ok PASSED                    [ 93%]
tests/multiversx/test_f2_execution_fail.py::TestF2ReaderIsOnCriticalPath::test_replacing_reader_breaks_f2a PASSED                   [100%]

============================== 16 passed in 0.27s ==============================
```

Full suite: `116 passed, 42 skipped` (42 skips = 25 V1-20 audit CLI + 17 V1-06
dual-schema-reader scaffold stubs; F2 was 10 of the previous 52 skips, now all
active).

## 3. Fixture divergences

None. All 9 fixtures parsed cleanly on first read; the reader produced the
expected `(status, schema_path_used)` for every combination in the README's
truth table including F2a-lag (tx.status mutated to `"pending"` while the
settling block still shows the `InvalidBlock` miniblock).

The `supernova/block_settling_fail.json` fixture carries three independent
failure signals (`miniBlockHeaders[].type == "InvalidBlock"`, `failedTxCount > 0`,
`executedTxCount == 0`). The reader's signal list wires the first two per I14;
the third is left unused to keep the rule-set orthogonal. On Battle Net
confirmation, pruning to the authoritative signal is a one-line change inside
`_SUPERNOVA_FAIL_SIGNALS`.

## 4. Scope deviations

None against I13–I20. In detail:

- **I13** — `_NON_TERMINAL_STATUS_VALUES` is a frozenset; adding a new value
  is one character.
- **I14** — fail detection is a signals list (`_SUPERNOVA_FAIL_SIGNALS`). When
  a settling block is present, block-side signals are evaluated first; `tx.status`
  is used for success/pending corroboration only, never as the sole fail
  determinant. F2a-lag proves this: tx.status mutated to `"pending"` still
  produces the correct `fail` verdict.
- **I15** — all field lookups live in `_extract_tx`, `_extract_block`,
  `_extract_receipt_data`, and the two `_signal_*` helpers.
- **I16** — `MinimalPollingWatcher` has no WebSocket, no reconnect, no timeouts,
  no gap-fill. The legacy `ChainWatcher` remains a V1.B scaffold (unchanged).
- **I17** — the ONLY mock in the F2a/F2b/F2a-lag chains is `httpx.MockTransport`.
  `TestF2ReaderIsOnCriticalPath` uses `monkeypatch` to prove the reader is
  load-bearing — that is the reviewer's own sign-off #3 check encoded as a
  test, and it does not touch the F2a/F2b/F2a-lag chains.
- **I18** — all three required tests are green.
- **I20** — no V1.B work started.

**One supporting implementation** outside V1-F2.1/.2/.3: `verify_anchor_chain()`
was added to `audit.py` because V1-F2.3 requires `audit.verify_anchor_chain(...)`
but only `audit_shard` / `iter_intents_with_terminal_states` existed in the
scaffold. The new function is ≈50 lines, pure over the entry list, and does not
touch kernel or network.

**`mypy`** (sign-off #6): clean after 4 mechanical fixes — pydantic v2 stubs
unify `Field(default_factory=Model)` return to `Never` (wrapped in `lambda`
and annotated `# type: ignore[call-arg]` with a comment, `config.py`);
`Callable` is contravariant in its parameters so the per-event-type handler
dispatch cannot fit a `Callable[[AnchorTransitionEvent, ...], ...]` slot
(handler type loosened to `Callable[..., TransitionResult]`; safety preserved
by the dispatch key which embeds `type(event)`, `state_machine.py`); added
missing `Callable` import; added an `assert containing is not None` in
`DualSchemaReader.read_execution_result` with a comment to narrow the
`Optional[dict]` inherited from the discriminator (`watcher.py`). Two
`# type: ignore` introduced, both commented per sign-off criterion #6. Final
output: `Success: no issues found in 11 source files`.

## 5. V1.B readiness

F2 being green validates the three-stage design end-to-end: the reader correctly
derives failure from block-side signals under both regimes, the watcher
emits exactly the two state-machine events required (no `ExecSuccessEvent` ever
leaks onto a fail path), and the audit chain returns `execution_failed` on
every failure scenario including the lagging-tx-endpoint edge case. The
Supernova-aware design is not silently letting execution failures pass as
successes. V1.B (watcher expansion: WebSocket, timeouts, reconnect, gap-fill)
can proceed.

## 6. Open questions for human review

1. The reader accepts the fixture's `baseExecutionResult.headerNonce` as the
   source of truth for `executed_in_block_nonce`, falling back to the settling
   block's top-level `nonce` and then `tx.executedInBlockNonce`. On Battle Net,
   if the canonical field is elsewhere, one line in `_read_supernova` changes —
   please confirm the precedence order against the first real capture.
2. `AnchorFailedEntry.reason` is populated from the tx receipt's `data` string
   (base64-ish). MIP-27 does not document a canonical human-readable failure
   reason under Supernova; the current value is operator-useful but not
   intended for user-facing audit output. Should V1.C expand this with SCR
   decoding?
3. `_ts_to_ms` uses a `< 10**12` magnitude heuristic to discriminate
   seconds-vs-ms timestamps. The fixtures deliberately mix both (Andromeda
   seconds, Supernova ms). Battle Net may expose a dedicated `timestampMs`
   field; if so, the heuristic should give way to explicit field lookup.
4. The `_FailSignal = Callable[[dict[str, Any], dict[str, Any]], bool]`
   signature means the signals operate on raw dicts, not on the pydantic
   models in `schemas.py`. Two readings are possible — (a) deliberate
   decoupling from provisional `derived_from_mip27` shapes per I15, letting
   field-name churn touch only `_signal_*` without crossing into validation;
   (b) incidental sidestepping of pydantic's stricter typing. Both produce
   working code today; the difference will show at Battle Net calibration.
   To decide for (a) on purpose: promote `exec_result` to a pydantic
   model in `schemas.py` once the shape stabilises, and retype signals
   against that model. To be tracked for V1.B.
