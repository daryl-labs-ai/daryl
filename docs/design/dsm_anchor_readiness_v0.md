# DSM Anchor Readiness v0

## Status

Design-only, plus one no-network payload contract test. No anchoring is built.

This follows the strategic decision recorded in the known-answer replay
(`tests/test_known_answer_decision_replay_v0.py`): DSM stays off-chain as a
preparation / pre-commit trust layer. This note only crystallizes the *shape* of
a safe export that could later be anchored — it does not anchor anything.

## Purpose

Define a canonical hash-only DSM receipt export that may later be anchored
externally.

This is not anchoring.
This is not blockchain integration.
This is not a smart contract.
This is not a chain adapter.

## What it prepares

A stable, privacy-preserving payload derived from an existing DSM receipt (the
hashes the gateway already produces: `decision_hash`, `input_context_hash`,
`raw_output_hash`, and an `audit_hash`). The payload carries only hashes and
coarse status labels — never content.

## Payload v0

Fields:

- `schema_version`: `dsm_anchor_payload.v0`
- `privacy`: `hash_only`
- `decision_hash`
- `input_context_hash`
- `raw_output_hash`
- `audit_hash`
- `validation_status`
- `decision_kind`
- `agent_id_hash`
- `created_at`
- `chain_target`: `unspecified`

The `agent_id` is never exported raw; only its canonical hash
(`agent_id_hash`) appears. The payload is built from an allowlist of fields, so
any extra fields present on the source receipt are dropped by construction.

## Privacy invariants

The payload MUST NOT contain:

- raw provider output
- full prompt
- full reasoning text
- markdown audit body
- explain JSON body
- personal data / PII
- API credentials
- authorization tokens
- file contents
- external documents

## Trust model

The payload can prove local receipt integrity and can be verified locally: its
canonical hash (via the existing `hash_canonical`, prefix `v1:`) binds the field
set, so any tampering changes the hash.

If anchored externally in the future, anchoring would prove existence /
timestamp / integrity of selected hashes.

It would NOT prove:

- factual truth
- semantic correctness
- business decision validity
- reasoning validity
- external verification
- provider authority

## Non-goals

- no chain selection
- no smart contract
- no wallet
- no transaction
- no chain adapter (MultiversX / EVM / Base / Sui / XRPL / …)
- no witness / MMR / STH
- no external anchoring
- no network calls
- no registry / dashboard / API / MCP / Custom GPT
- no kernel changes
- no validation changes
- no status assignment changes
- no provider runtime changes

## Stop condition

v0 ends after this design note and one no-network payload test. No chain is
chosen, no adapter is built, no transaction is sent, and no v1 payload is
created without a separate decision.
