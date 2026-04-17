# Mainnet Andromeda Capture — 2026-04-17 #01

## Source
- gateway: https://gateway.multiversx.com
- network: mainnet
- regime at capture: Andromeda (`erd_round_duration == 6000`, confirmed in `network_config.json`)
- capture date: 2026-04-17

## Files saved
- success_tx.json
- success_block_containing.json
- invalid_tx.json
- invalid_block_containing.json
- network_config.json

## Transaction details

### Success tx
- hash: 5a0b7169618af95328982de00925618e25e98fea9ed256f889b3b08cf3af117e
- status field value observed: `"success"`
- blockNonce: 30016350
- sourceShard: 0
- type: `"normal"`

### Invalid tx
- hash: 95235d257505512d39f98dc60765cdebfc19fe90f39bea4b05661c10874ae8be
- status field value observed: `"invalid"`
- blockNonce: 30023889
- sourceShard: 1
- type: `"invalid"`
- miniblockType reported (if in block response): `InvalidBlock` — present as `miniBlocks[2].type == "InvalidBlock"` in `invalid_block_containing.json` (shard 1, nonce 30023889). Four miniBlocks total in that block: two `TxBlock`, one `InvalidBlock`, one `ReceiptBlock`.

## Key findings vs fixtures

Compare OBSERVED shapes against current derived fixtures
(`tests/multiversx/fixtures/andromeda/*`). Report each discrepancy factually.

### Field presence check (mainnet observed vs andromeda fixtures)

For the success tx response:
- [x] `data.transaction.status`
- [x] `data.transaction.type`
- [x] `data.transaction.hash`
- [x] `data.transaction.blockNonce`
- [x] `data.transaction.blockHash`
- [x] `data.transaction.miniblockHash`
- [x] `data.transaction.gasUsed`
- [x] `data.transaction.timestamp` (seconds)
- [x] `data.transaction.timestampMs` or similar ms variant — present as `timestampMs` (literal field name)

For the containing block response (success_block_containing.json):
- [ ] `data.block.rootHash` — ABSENT. Only `stateRootHash` is present at top level; no standalone `rootHash` key.
- [x] `data.block.stateRootHash`
- [x] `data.block.lastExecutionResult` (should be ABSENT on Andromeda) — ABSENT ✓
- [x] `data.block.lastExecutionResultInfo` (should be ABSENT on Andromeda) — ABSENT ✓
- [x] `data.block.miniBlocks[]` with per-tx entries — miniBlocks array is PRESENT (2 entries for success block, 4 for invalid block), BUT the mainnet miniblock objects do NOT carry a `transactions` array of per-tx metadata. Each miniblock object has `{constructionState, destinationShard, hash, indexOfFirstTxProcessed, indexOfLastTxProcessed, processingType, sourceShard, type}` and the tx-level detail is not inlined. Current andromeda fixture (`tests/multiversx/fixtures/andromeda/block_containing_tx.json`) models `miniBlocks[0].transactions[0]` with per-tx hash/nonce/value — this is a structural divergence.
- [x] `data.block.timestamp` (seconds or ms) — BOTH `timestamp` (seconds) and `timestampMs` (ms) are present as distinct top-level fields.

### Timestamp encoding
- success tx `timestamp` field value: `1776438678` (seconds)
- success block `timestamp` field value: `1776330540` (seconds); `timestampMs`: `1776330540000` (ms)
- is there a separate `timestampMs` field anywhere: **yes** — present on both tx responses and both block responses at the top level alongside `timestamp`. Seconds and ms coexist.

### Status vocabulary observed
- success tx status string: `"success"`
- invalid tx status string: `"invalid"`
- was `fail` observed anywhere: **no** — neither tx endpoint nor block endpoint emitted a `status: "fail"` value in this capture.

## Open questions (do NOT answer, just list)

- is `status=fail` used at all on Andromeda mainnet in April 2026, or is it replaced by `status=invalid` + `InvalidBlock` miniblock for all non-success paths?
- if `lastExecutionResult` appeared on any block response, where and how? (Observation: it did NOT appear on either mainnet block response in this capture; Andromeda hypothesis confirmed.)
- any field present on mainnet that is ABSENT from the current andromeda fixtures? Observed additional top-level tx fields: `NotarizedAtSourceInMetaHash`, `chainID`, `fee`, `function`, `hyperblockHash`, `hyperblockNonce`, `initiallyPaidFee`, `logs`, `miniblockType`, `notarizedAtDestinationInMetaHash`, `notarizedAtDestinationInMetaNonce`, `notarizedAtSourceInMetaNonce`, `operation`, `options`, `processingTypeOnDestination`, `processingTypeOnSource`, `smartContractResults`, `version`, `timestampMs`. Observed additional top-level block fields: `chainID`, `leaderSignature`, `prevRandSeed`, `proof`, `pubKeyBitmap`, `randSeed`, `scheduledData`, `signature`, `softwareVersion`, `status`, `timestampMs`. And each miniblock carries `constructionState`, `indexOfFirstTxProcessed`, `indexOfLastTxProcessed`, `processingType` which the fixture lacks.
- any field present in the current andromeda fixtures that is ABSENT from mainnet? Yes: `data.block.rootHash` is in the fixture but not in the mainnet block response (only `stateRootHash`); `data.block.receiptsHash` is in the fixture AND in mainnet (present on both); fixture miniblock entries inline a `transactions[]` array, mainnet miniblock entries do not.
- the success tx is cross-shard (`sourceShard=0`, `destinationShard=4294967295` metachain). The prompt instructed fetching the containing block via `/block/{sourceShard}/by-nonce/{blockNonce}`; the resulting `success_block_containing.json` has `hash=4151a4a2…` while the tx's own `blockHash` field is `0b2f43ad…`. Hashes differ — the fetched block is the source-shard block at that nonce, not the block whose hash the tx response references (which under cross-shard may be the metachain or destination-shard block). Flagging for capture methodology review before V1.B.

## V1.B readiness note

These observations partially contradict the current `andromeda/*` fixtures: the Andromeda failure status vocabulary in mainnet is `"invalid"` (not `"fail"` as the fixture models), and the mainnet `InvalidBlock`-miniblock signal — currently hypothesized as a Supernova-only feature in our `_SUPERNOVA_FAIL_SIGNALS` list — is already the Andromeda failure carrier on mainnet today.
