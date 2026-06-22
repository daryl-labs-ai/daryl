# Skill Execution Loop v0

Skill Execution Loop v0 closes the deterministic Skill-as-data loop:

```text
retrieval output -> deterministic skill trace -> eval scoring
```

It consumes the output of `retrieve_skill_context(...)` and produces a
`skill_execution_trace.v0` scaffold. The trace is meant to show what a later
reasoner must verify and apply. It does not produce the business answer.

## Scope

Skill Execution v0 is:

- deterministic
- pure-data
- metadata-scoped
- auditable by a static scorer

It does not introduce:

- training
- fine-tuning
- distillation
- adapters
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
- DSM kernel changes

## Trace Rules

The composer preserves retrieval scope:

- `user_id`
- `domain`
- `skill_id`
- `task_type`

Candidate rules remain candidates. Validated rules are listed separately from
candidate rules, and candidate rules are never applied as truth.

Every required check becomes a verification item. Checks not covered by
`known_inputs` are surfaced in `missing_checks` and `warnings`.

The trust model is mandatory. It states that the output is a deterministic
scaffold, that no business decision has been produced, and that the trace does
not prove factual truth or reasoning validity.

## Limits

Skill Execution v0 does not replace a reasoner. It only prepares deterministic
context for one. It does not read DSM internals, create evidence records, or
persist execution state.
