# Skill Retrieval v0

Skill Retrieval v0 is a deterministic, pure-data proof that Daryl can consume
Skill-as-data metadata before any training path exists.

It retrieves skill context from `datasets/dsm_reasoning_v0/records.jsonl` using
only static fields:

- `record_kind`
- `user_id`
- `domain`
- `skill_id`
- `task_type`
- `entry_type`
- `epistemic_status`
- `required_checks`

## Scope

Retrieval v0 is intentionally small:

- no model call
- no vector DB
- no embeddings
- no registry service
- no index server
- no shard router
- no physical sharding
- no Evidence V2
- no dashboard
- no benchmark
- no witness/MMR/STH/anchoring

The implementation does not import DSM internals. Callers provide records as
plain dictionaries, and the retriever returns a deterministic context object.

## User Scope

User isolation is a first-class invariant:

- `user_id="mohamed"` can only retrieve records with `user_id="mohamed"`;
- records for `other_user` are excluded even when `domain` and `skill_id`
  match;
- records without `user_id` are excluded by default from user-scoped retrieval.

Global/template records may be modeled later, but v0 keeps them out of
user-scoped retrieval unless a future contract explicitly opts in.

## Metadata-First, Shard-Later

The retriever proves the `metadata-first, shard-later` policy. Domain, skill,
task, and user boundaries are enforced through metadata filters only. No
physical domain shard, skill shard, registry, or router is introduced.
