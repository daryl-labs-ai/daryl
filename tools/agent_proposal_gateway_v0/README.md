# Agent Proposal Gateway v0

Agent Proposal Gateway v0 is a provider-agnostic trust boundary:

```text
DSM context -> untrusted provider proposal -> DSM validation -> Agent Memory audit
```

External providers propose. DSM assigns status. Agent Memory persists an
explainable audit trail.

## Non-goals

This gateway does not introduce:

- training
- fine-tuning
- distillation
- ML adapters
- model calls in CI
- embeddings
- vector DB
- registry service
- index server
- shard router
- Evidence V2
- physical sharding
- dashboard
- benchmark
- witness/MMR/STH/anchoring
- DSM kernel changes

## Providers

Providers implement `propose(context) -> dict` and expose metadata:

```json
{
  "kind": "mock",
  "name": "mock",
  "model": "mock-good",
  "base_url_label": "local-test"
}
```

v0 includes:

- a mock provider for CI and corruption scenarios;
- an OpenAI-compatible provider tested only with mocked HTTP transport.

## Trust Boundary

The provider cannot:

- assign DSM validation status;
- claim DSM truth;
- promote candidate rules;
- turn audit acceptance into business truth.

DSM ignores any agent-supplied status and records a warning. That warning alone
does not cause rejection.

## DSM Statuses

Only three statuses exist:

- `accepted_for_audit`
- `needs_human_review`
- `rejected_by_validator`

Every proposal keeps `model_proposed=true`, including rejected proposals.

## Persistence

All proposals are persisted via public Agent Memory V1 APIs. Rejected and
needs-review proposals are explainable, but retrieval contamination is prevented
by a strict allowlist:

```text
validation_status == accepted_for_audit
```

Never use `status != rejected` as a retrieval filter.
