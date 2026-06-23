# Daryl-for-ChatGPT v0 — Design Note

## Status

Design-only. No implementation yet.

This note defines how ChatGPT can interact with Daryl/DSM without confusing
provider integration with client integration. It follows the closure of
provider-live v0 (see `docs/milestones/provider_live_v0.md`).

## Problem

"Working with Daryl in ChatGPT" can mean two different things:

1. ChatGPT/OpenAI as a provider proposing into DSM.
2. ChatGPT as a client calling DSM as a tool.

These are different trust directions and must not be mixed.

## Direction A — OpenAI as provider

In this direction, OpenAI is just another untrusted provider.

It proposes into the existing Agent Proposal Gateway.

DSM remains the authority over:

- validation status;
- accepted/rejected/review classification;
- audit persistence;
- Agent Memory explanation.

This direction may be smoke-tested manually through the existing
OpenAI-compatible provider path.

Non-goals:

- no special ChatGPT integration;
- no status authority for OpenAI;
- no provider-as-truth;
- no validation loosening.

## Direction B — ChatGPT as client

In this direction, ChatGPT calls DSM as an external tool.

This is the real "Daryl inside ChatGPT" path.

It requires a minimal DSM API before any Custom GPT Action, MCP server, or
connector.

## Minimal API shape

Daryl-for-ChatGPT v0 should be a thin wrapper over existing DSM/gateway
behavior. It introduces no new validation, status, or trust semantics.

Candidate actions:

### `retrieve_context`

Input:

- `scope`
- optional `domain`
- optional `skill_id`
- optional `query`

Output:

- context summary
- context hash
- source references where available

### `submit_proposal`

Input:

- `scope`
- `provider`
- `structured_output`
- optional raw output hash

Output:

- DSM-assigned `validation_status`
- warnings
- rejections
- model_proposed flag
- audit reference
- input context hash
- raw output hash

### `explain_decision`

Input:

- audit reference or decision hash

Output:

- explain JSON
- markdown audit
- verification hint

## Trust boundary

ChatGPT is never trusted as the authority.

Whether ChatGPT acts as provider or client:

- ChatGPT proposes.
- DSM validates.
- DSM assigns status.
- DSM persists audit.
- DSM explains.
- Provider/client supplied status is ignored or rejected according to existing
  gateway rules.

`accepted_for_audit` means auditable and honest enough to persist.

It does not mean:

- factual truth;
- business decision approval;
- external verification;
- external anchoring;
- repeatability;
- reliability.

## Non-goals for v0

Do not implement in this phase:

- Custom GPT Actions;
- MCP server;
- public network deployment;
- auth and multi-tenant isolation;
- dashboard;
- vector database;
- embeddings;
- training/fine-tuning;
- Evidence V2;
- witness/MMR/STH/anchoring;
- registry;
- new provider runtime;
- product CLI.

## Recommended sequence

1. Keep using ChatGPT as project copilote today.
2. Optionally smoke-test OpenAI as provider through the existing gateway path.
3. Define and test a local/mock-first minimal API wrapper.
4. Only after that, decide whether to expose DSM through Custom GPT Actions or
   MCP.

## Stop condition

This note does not authorize implementation.

Any implementation must be opened as a separate decision with:

- concrete use case;
- API contract;
- auth/isolation decision if networked;
- explicit non-goals.
