# V1-F2 Fixtures — Epistemic Status and Usage

These fixtures drive the V1-F2 test. They are the ONLY inputs that V1-F2 tests
are allowed to consume. If any V1 test constructs a wire-format input by
hand rather than loading from this directory, that test does not count
toward F2 sign-off.

## File inventory

```
fixtures/
├── README.md                           (this file)
├── andromeda/                          (V1.B-01: observed_on_mainnet 2026-04-17)
│   ├── tx_success.json                 F0 baseline — status='success', miniblockType='TxBlock'
│   ├── tx_success.meta.json            sidecar metadata (source provenance)
│   ├── tx_invalid.json                 F2b CRITICAL — status='invalid', miniblockType='InvalidBlock'
│   ├── tx_invalid.meta.json            sidecar metadata
│   ├── block_containing_tx.json        block containing the success tx (shard 1, nonce 30024315)
│   ├── block_containing_tx.meta.json   sidecar metadata
│   ├── block_invalid.json              block containing the invalid tx (shard 1, nonce 30023889); miniBlocks[2].type == 'InvalidBlock'
│   └── block_invalid.meta.json         sidecar metadata
├── supernova/                          (still derived_from_mip27; mainnet activation pending)
│   ├── tx_included_pending.json        T₂ intermediate observation
│   ├── tx_settled_success.json         T₃ baseline — status='success'
│   ├── tx_settled_fail.json            F2a CRITICAL tx-side — status='fail'
│   ├── block_containing_tx.json        block N (tx included, no ExecResult)
│   ├── block_settling_success.json     block N+1 with successful lastExecutionResult
│   └── block_settling_fail.json        F2a CRITICAL block-side — InvalidBlock miniblock
└── observed_on_mainnet/                (append-only capture archive — read-only for the reader)
    ├── 2026-04-17_capture_01/          invalid-side authoritative source + superseded cross-shard success
    └── 2026-04-17_capture_02/          intra-shard success-side correction of capture_01
```

## Epistemic status of each fixture

Each fixture's source is now recorded in a **sidecar `*.meta.json` file**
next to the fixture, not inline. Observed fixtures are byte-exact vs their
source capture (I23): the payload JSON itself is never modified for
metadata. Sidecar `source` values:

- **`observed_on_mainnet_YYYY-MM-DD`** — copied byte-exact from a real
  mainnet gateway response captured under `observed_on_mainnet/`. The
  source_ref field points to the specific capture file + commit hash.
  This is ground truth.
- **`documented`** — legacy status for pre-V1.B-01 Andromeda fixtures
  (superseded; all Andromeda entries are now observed).
- **`derived_from_mip27`** — shape reconstructed from MIP-27 (the Supernova
  specification draft). The STRUCTURE is what MIP-27 guarantees
  (decoupled execution notarized in later block headers,
  `lastExecutionResult` on `ApiBlock`, ExecutionResult struct in
  Appendix B). The exact JSON field NAMES and CASING are best-effort
  Go-JSON conventions. Supernova fixtures MUST be recalibrated against
  a real mainnet capture once Supernova activates.

Summary:

| Fixture | Source | Confidence |
|---|---|---|
| andromeda/tx_success.json | observed_on_mainnet_2026-04-17 | high |
| andromeda/tx_invalid.json | observed_on_mainnet_2026-04-17 | high |
| andromeda/block_containing_tx.json | observed_on_mainnet_2026-04-17 | high |
| andromeda/block_invalid.json | observed_on_mainnet_2026-04-17 | high |
| supernova/tx_included_pending.json | derived_from_mip27 | medium |
| supernova/tx_settled_success.json | derived_from_mip27 | medium |
| supernova/tx_settled_fail.json | derived_from_mip27 | medium |
| supernova/block_containing_tx.json | derived_from_mip27 | medium |
| supernova/block_settling_success.json | derived_from_mip27 | medium |
| supernova/block_settling_fail.json | derived_from_mip27 | medium-low |

The `block_settling_fail.json` fixture carries the weakest confidence because
MIP-27 does not explicitly specify how per-tx failure status is surfaced in
the block-level `lastExecutionResult`. It MAY be an `InvalidBlock` miniblock
header, it MAY be a dedicated failed-tx array, or it MAY be encoded purely
through receipts that live at a separate endpoint. The fixture models the
InvalidBlock-miniblock hypothesis; the test plan accounts for this by
requiring the dual-schema reader to accept AT LEAST ONE of: InvalidBlock
miniblock header, failure SCR, tx endpoint status='fail'.

## Deterministic values — reusable across fixtures

All fixtures share these values so each fixture can be substituted for its
variant without recomputing hashes:

**Supernova** (still derived_from_mip27; deterministic):

| Name | Value |
|---|---|
| DSM01 payload (base64) | `RFNNMDEIc2Vzc2lvbnOrq6urq6urq6urq6urq6urq6urq6urq6urq6urq6urqwAAAAAAAABCASNFZ4mrfN6BI0VniavN7w==` |
| DSM01 payload bytes | 70 |
| intent_id | `01234567-89ab-7cde-8123-456789abcdef` |
| entry_nonce (DSM) | 66 |
| last_hash (DSM, 0x+hex) | `0x` + `ab` × 32 |
| shard_id | `sessions` |
| tx_hash (Supernova) | `d9ed0f70fc2326adb8f02c1cc44e4a531c5d1808bb6aa8558a396f03694a554a` |
| tx nonce (sender) | 42 |
| sender = receiver | `erd1qyu5wthldzr8wx5c9ucg8kjagg0jfs53s8nr3zpz3hypefsdd8ssycr6th` |
| containing block nonce (Supernova) | 10000000 |
| settling block nonce (Supernova) | 10000001 |
| containing block hash (Supernova) | `3c5e9d60cdd02cbfeba896f6cef6b9a3de1d92e351c08d659cdb0d2a5557812c` |
| settling block hash (Supernova) | `02954ba529ce93d0a77e127c2f8a4e31cd89373a2c8c1c5f377b225dc7b62fac` |
| miniblock hash (Supernova) | `72c5ec7d924ee15b2f0496d030e22bc5cee0b1b4485b7dc9542779152956ea70` |
| timestamp (Supernova, ms) | 1776376800000 / 250 / 600 |

**Andromeda** (observed_on_mainnet 2026-04-17; NOT deterministic — real mainnet values):

| Name | Value |
|---|---|
| success tx hash | `c07636310ed94a4b169019666384283f0eb411733617da75179aef1b45685146` |
| success block nonce | 30024315 |
| success block hash | `0cb39a6f7f75655d984af32caed9762f7b359ca467b0ce8032c72b95015b0a8c` |
| success shard | 1 (intra-shard, `tx.blockHash == block.hash` verified) |
| invalid tx hash | `95235d257505512d39f98dc60765cdebfc19fe90f39bea4b05661c10874ae8be` |
| invalid block nonce | 30023889 |
| invalid block hash | `f806c9690d4c8fc74bc8a72ab85607e9c0fa0255bebbbff0b7da3dc23d1fb81d` |
| invalid miniblock hash (InvalidBlock) | `5959721f63a0d30ddeeccd2b7ea089b27aa51f524cb8b24a52bf58d07b24dfae` |
| invalid shard | 1 (intra-shard) |
| timestamp (Andromeda, seconds + ms) | per-fixture; real mainnet values; `timestamp` and `timestampMs` coexist |

Supernova values were generated deterministically. Andromeda values are
the real mainnet transactions/blocks observed on 2026-04-17; changing any
Andromeda constant requires a new capture and a new commit under
`observed_on_mainnet/`.

## How the dual-schema reader must use these

The reader is a pure function of up to three inputs:

1. `tx_response`: parsed JSON from GET /transaction/{hash}?withResults=true
2. `containing_block`: parsed JSON from GET /block/{shard}/by-nonce/{nonce}
   — the block the tx was included in
3. `settling_block`: parsed JSON from GET /block/{shard}/by-nonce/{nonce}
   — under Supernova, typically containing_block.nonce + 1

Expected decisions per fixture combination:

| tx response | containing block | settling block | Expected output |
|---|---|---|---|
| `andromeda/tx_success.json` | `andromeda/block_containing_tx.json` | None | ExecutionResult(status='success', schema_path_used='andromeda_top_level') |
| `andromeda/tx_invalid.json` | `andromeda/block_invalid.json` | None | ExecutionResult(status='fail', schema_path_used='andromeda_top_level') — mainnet emits `status='invalid'`, `_ANDROMEDA_STATUS_MAP` translates to `'fail'` |
| `supernova/tx_included_pending.json` | `supernova/block_containing_tx.json` | None | ExecutionResult(status='pending', schema_path_used='supernova_lastExecutionResult') — because the settling block has not yet been observed |
| `supernova/tx_settled_success.json` | `supernova/block_containing_tx.json` | `supernova/block_settling_success.json` | ExecutionResult(status='success', schema_path_used='supernova_lastExecutionResult') |
| `supernova/tx_settled_fail.json` | `supernova/block_containing_tx.json` | `supernova/block_settling_fail.json` | ExecutionResult(status='fail', schema_path_used='supernova_lastExecutionResult') |

Note the last row — that's F2a. Failure MUST be detected even though the
tx endpoint itself merely says 'fail' without the authoritative failure
payload. The dual-schema reader derives its verdict from the settling
block's `lastExecutionResult.miniBlockHeaders[].type == "InvalidBlock"`
signal. This is what distinguishes a "real" F2 test from a superficial one.

## F2 test plan — what the watcher must yield

For each scenario, a complete-chain test feeds fixtures into the HTTP
transport mock, lets the watcher poll normally, and asserts the exact
sequence of AnchorEvents yielded:

### F2a (Supernova execution fail)

1. Watcher polls tx endpoint → receives `supernova/tx_included_pending.json`
2. Watcher polls container block → receives `supernova/block_containing_tx.json`
3. Watcher yields `AnchorIncludedEntry`
4. Watcher polls tx endpoint again → receives `supernova/tx_settled_fail.json`
5. Watcher polls settling block → receives `supernova/block_settling_fail.json`
6. Watcher yields `AnchorFailedEntry`
7. Watcher stops (terminal state reached)

Asserted invariants:
- Exactly 2 events yielded (Included, Failed).
- NO `AnchorSettledEntry` anywhere in the yielded sequence.
- The `AnchorFailedEntry.failed_in_block_nonce == 10000001` (settling block).
- Audit tool over the emitted DSM log returns `verdict='execution_failed'`.

### F2b (Andromeda execution fail)

1. Watcher polls tx endpoint → receives `andromeda/tx_invalid.json`
   (mainnet vocabulary: `status="invalid"`, `miniblockType="InvalidBlock"`;
   `_ANDROMEDA_STATUS_MAP["invalid"] = "fail"` translates into the
   reader's internal status).
2. Watcher polls containing block → receives `andromeda/block_invalid.json`
   (contains `miniBlocks[2].type == "InvalidBlock"` as the block-side
   corroborating signal).
3. Watcher synthesizes `IncludeEvent` from the containing block.
4. Watcher yields `AnchorIncludedEntry`.
5. Watcher synthesizes `ExecFailEvent` co-terminous (no separate settling
   block under Andromeda; T₂≡T₃).
6. Watcher yields `AnchorFailedEntry`.
7. Watcher stops.

Asserted invariants:
- Exactly 2 events yielded (Included, Failed), both derived from ONE tx
  observation and ONE block observation.
- NO `AnchorSettledEntry` anywhere.
- Audit tool returns `verdict='execution_failed'`.

### F2a lagging-tx variant (optional but recommended)

Variant of F2a where `supernova/tx_settled_fail.json`'s `status` is
mutated at runtime to `'pending'` to simulate tx-endpoint lag behind
block-endpoint. The watcher MUST still emit `AnchorFailedEntry` based on
the settling block's InvalidBlock miniblock signal alone. This guards
against a fragile dual-schema reader that depends on the tx endpoint
catching up.

## What these fixtures deliberately DO NOT cover

Out of scope for V1-F2, in scope for V1.B and later:

- Cross-shard transactions (sender shard ≠ receiver shard; V1 is intra-shard)
- Relayed v3 transactions (gasless submission via relayer)
- ESDT transfers, smart contract calls (V1 anchors are plain self-addressed
  0-EGLD transfers)
- Epoch transitions mid-anchor
- Stuck / timed-out / rejected paths (V1.C)
- Reconcile / F11 recovery (V1.D)

## Update protocol

When a new real mainnet response is captured (applies to both Andromeda
refreshes and the upcoming Supernova activation):

1. Save the raw capture under `observed_on_mainnet/YYYY-MM-DD_capture_NN/`
   (append-only, never edit captures). Use `curl -o` — never re-serialize
   with `json.dump`.
2. Run `cmp` between the capture and the target fixture before ANY
   replacement. If you are refreshing a fixture, first verify the old
   fixture's source_ref still points at a live capture; replace only
   the payload, byte-exact, via `cp`.
3. Update the sidecar `*.meta.json` with the new `source_ref` (capture
   path + commit hash) and bump the `source` field if provenance tier
   changes (e.g. `derived_from_mip27` → `observed_on_mainnet_YYYY-MM-DD`).
4. Re-run V1-F2 tests. If they now fail, either the dual-schema reader
   needs an update (preferred) or a new fixture variant is needed (flag
   as a new V1.B task).
5. NEVER inline metadata inside the payload — I23 requires byte-exact
   fixtures vs their source capture, enforced by `cmp` in sign-off.

## Provenance log

| Date | Action | By |
|---|---|---|
| 2026-04-17 | Initial fixtures created from docs (Andromeda) + MIP-27 §B (Supernova). | pre-V1-F2 |
| 2026-04-17 | V1.B-01: Andromeda fixtures replaced with observed_on_mainnet byte-exact captures (capture_01 invalid-side + capture_02 success-side). `tx_fail.json` renamed to `tx_invalid.json` to reflect mainnet vocabulary. New `block_invalid.json` added. Sidecar `*.meta.json` introduced per I23. Supernova fixtures unchanged — pending mainnet activation. | V1.B-01 |
