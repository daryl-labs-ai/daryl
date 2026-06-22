# Skill Trace to Agent Memory v0

Skill Trace to Agent Memory v0 bridges deterministic skill execution traces
into Agent Memory V1.

```text
compose_skill_trace output -> Agent Memory V1 -> explain -> Markdown audit
```

This is not a second memory. The adapter writes through the public Agent Memory
V1 API and then uses Agent Memory explanation and Markdown rendering to audit
the stored scaffold.

## Scope

The bridge is:

- deterministic
- pure-data at the mapping layer
- backed by Agent Memory V1 for persistence
- outside the DSM kernel

It does not introduce:

- training
- fine-tuning
- distillation
- adapters for ML
- model calls
- embeddings
- vector DB
- registry service
- index server
- shard router
- physical sharding
- Evidence V2
- dashboard
- benchmark
- witness/MMR/STH/anchoring
- kernel changes

## Mapping

The adapter maps a `skill_execution_trace.v0` scaffold to Agent Memory V1:

- scope, required checks, missing checks, applied validated rules, supporting
  cases, warnings, and trust model become factual support entries;
- candidate rules become hypothesis entries and remain explicitly candidate;
- a scaffold inference links the support entries;
- a scaffold decision entry is recorded only so `explain_decision` can audit
  the chain.

The scaffold decision is not a business decision. It states
`decision_status=not_produced` and `status=requires_reasoner`.

## Dogfood

Tests should use a temporary `data_dir`, then call:

```python
persist_skill_trace_to_agent_memory(trace, data_dir=tmp_path / "data")
```

The result includes the persisted decision hash, the explain JSON contract, and
the Markdown audit report.
