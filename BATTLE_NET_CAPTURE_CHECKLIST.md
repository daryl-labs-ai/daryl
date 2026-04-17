# Battle Net Capture Checklist

## Goal
Capture real MultiversX Battle Net responses to validate Supernova fixture assumptions before V1.B.

## Required captures
- transaction endpoint response for a success case
- transaction endpoint response for a fail case
- containing block response for the transaction
- settling block response for the transaction
- timestamps / nonce relationships across those responses

## What to inspect first
- presence or absence of `lastExecutionResult`
- exact nesting/field names
- whether `baseExecutionResult` exists
- whether failure is signaled by `InvalidBlock`, `failedTxCount`, SCRs, or another field
- whether tx endpoint status lags behind block-level execution result
- whether timestamps are seconds or milliseconds
- exact field names for block nonce / executed block nonce

## Regime coverage requirement
- If V1.B touches only Supernova code paths: at least one observed Battle Net fixture for Supernova is required before merge.
- If V1.B also touches Andromeda fallback paths: at least one observed fixture for Andromeda is also required before merge.

## Output destination
Store captures under:
- `tests/multiversx/fixtures/observed_on_battle_net/`

Do not create this directory now unless it does not already exist.
If you create it, leave it empty.

## Merge gate reminder
No V1.B merge to main until at least one `observed_on_battle_net_*` fixture is green per critical regime touched.
