# DSM Reasoning Dataset v0

This folder contains a small, schema-checked dataset for evaluating and
structuring DSM Agent Memory reasoning examples. It is not a training-ready
fine-tuning dataset, and no training, distillation, or model update is implied
by these records.

The dataset encodes reasoning chains with:

- `fact`
- `hypothesis`
- `inference`
- `decision`
- `known_limits`
- expected `agent_memory.explain.v1` JSON shape
- expected Markdown audit report fragments

Dataset records have two conceptual kinds:

- `reasoning_trace`: a full question -> facts -> hypotheses -> inferences ->
  decision record with expected JSON/Markdown targets.
- `skill_memory_entry`: a structured skill memory item such as a correction,
  preference, candidate rule, validated rule, or outcome. It is not scored as a
  full Agent Memory explain report and does not require expected JSON/Markdown.

DSM can provide local tamper-evidence for recorded entries. It does not prove
that facts are true, does not prove reasoning validity, and does not provide
external anchoring, witness, MMR, or STH guarantees.

## Skill Metadata

Skill-as-data v0.1 adds optional metadata fields:

- `record_kind`
- `user_id`
- `domain`
- `skill_id`
- `user_skill_id`
- `task_type`
- `required_checks`
- `entry_type`
- `epistemic_status`
- `rule_version`
- `feedback`
- `outcome`
- `correction`
- `skill_rule_updates`

These fields are backward-compatible. Existing records without `record_kind`
are treated as `reasoning_trace` records by the validator.

For v0.1 the sharding policy is:

```text
metadata-first, shard-later
```

There is no physical shard per domain, no physical shard per skill, no shard
router, and no registry service. Logical partitioning uses metadata such as
`user_id`, `domain`, `skill_id`, and `user_skill_id`.

User isolation is a security invariant: user-scoped retrieval for one user must
not return another user's skill memory entries. Records with no `user_id` are
global/template material and must be excluded from user-scoped retrieval by
default unless explicitly requested.

## Hash Policy

DSM hashes are normalized as placeholders such as `<HASH_FACT_1>` and
`<HASH_DECISION>`. Records must not contain real `v1:` DSM hashes in expected
outputs. The goal is to teach structure and expected behavior, not to predict
runtime hashes.

## Records

Positive records:

- `dogfood-01-used-board`
- `dogfood-02-omari-lead-capture`
- `dogfood-03-log-ticket`

Negative records:

- `negative-missing-dependency`
- `negative-cycle`
- `negative-fact-hypothesis-confusion`

Skill memory records:

- `skill-01-omari-lead-capture-correction`

DOGFOOD-03 intentionally includes two external evidence types, `log` and
`ticket`, without implementing V2 evidence. V1 cannot yet reference logs or
tickets as first-class DSM evidence unless those artifacts are imported into
DSM first. That limitation is tracked in issue #27.

## Validation

Run:

```bash
python datasets/dsm_reasoning_v0/validate_dataset.py
```

The validator checks JSONL syntax, required fields, labels, known limits,
Markdown trust wording, hash placeholder shape, and absence of real DSM hashes
in expected JSON/Markdown targets. It uses only the Python standard library and
does not import DSM kernel internals or touch Storage. It treats
`skill_memory_entry` records as skill memory structure, not full reasoning
traces.
