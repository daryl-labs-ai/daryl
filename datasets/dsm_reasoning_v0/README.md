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

DSM can provide local tamper-evidence for recorded entries. It does not prove
that facts are true, does not prove reasoning validity, and does not provide
external anchoring, witness, MMR, or STH guarantees.

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
does not import DSM kernel internals or touch Storage.
