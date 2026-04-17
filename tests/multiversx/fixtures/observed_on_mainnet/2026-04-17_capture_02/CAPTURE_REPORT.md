# Mainnet Andromeda Capture — 2026-04-17 #02 (correction)

## Purpose
Correction of capture_01 success-side. The tx chosen in capture_01
(5a0b7169...) was cross-shard to metachain, which broke the
tx.blockHash / block.hash consistency invariant for intra-shard scope.
This capture replaces only the success_tx pair with an intra-shard
equivalent. The invalid_* files in capture_01 remain the authoritative
invalid-side observation.

## Source
- gateway: https://gateway.multiversx.com
- network: mainnet, regime: Andromeda
- capture date: 2026-04-17

## Files saved
- success_tx.json
- success_block_containing.json

## Transaction details
- hash: c07636310ed94a4b169019666384283f0eb411733617da75179aef1b45685146
- status: success
- miniblockType: TxBlock
- blockNonce: 30024315
- sourceShard == destinationShard: 1 (intra-shard ✓)
- tx.blockHash == block.hash: verified true (`0cb39a6f7f75655d984af32caed9762f7b359ca467b0ce8032c72b95015b0a8c`)
- value: 3000000000000000000 (3 EGLD, non-zero)
- data: present (closer to DSM shape than a plain transfer)
- sender == receiver: False (not a self-transfer; acceptable per capture methodology — shape parity with DSM use-case is sufficient)

## Supersedes
- capture_01/success_tx.json
- capture_01/success_block_containing.json

capture_01/* remain on disk as historical observations. V1.B-01 should
reference capture_02/success_* and capture_01/invalid_*.
