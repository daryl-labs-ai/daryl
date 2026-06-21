# Skill-as-data Eval v0.2 Contract

Status: proposed implementation contract

This document defines a deterministic, model-agnostic evaluation contract for
`datasets/dsm_reasoning_v0/`. It aligns with issue #30 and extends the scoring
surface to the Skill-as-data v0.1 fields merged in PR #32.

## Non-goals

Eval v0.2 does not introduce:

- training
- fine-tuning
- distillation
- adapters
- model calls
- Claude/Codex comparison
- registry service
- Evidence V2
- physical sharding
- dashboard
- witness/MMR/STH/anchoring
- DSM kernel changes

The evaluator consumes static dataset records and candidate outputs. It does
not call LLMs and does not compare agents.

## Inputs

Input A: one record from `datasets/dsm_reasoning_v0/records.jsonl`.

Input B: one candidate output:

- for `reasoning_trace`, candidate JSON shaped as `agent_memory.explain.v1`
  plus optional Markdown audit report;
- for `skill_memory_entry`, candidate skill-memory metadata and payload.

## Output

The scorer returns:

```json
{
  "record_id": "...",
  "record_kind": "reasoning_trace",
  "score": 100.0,
  "max_score": 100.0,
  "penalties": [
    {
      "code": "...",
      "message": "...",
      "severity": "low"
    }
  ]
}
```

Scores are deterministic. A penalty reduces the score according to its severity:

- low: 5 points
- medium: 15 points
- high: 30 points

The exact weighting is intentionally small-scope and reversible.

## Record kinds

`reasoning_trace` records are full reasoning examples:

```text
question -> facts -> hypotheses -> inferences -> decision
```

They are scored against candidate `agent_memory.explain.v1` JSON and Markdown.

`skill_memory_entry` records are skill memory items:

```text
feedback -> correction -> candidate rule -> skill_rule_updates
```

They are not scored as full explain reports and do not require fake
`expected_json` or `expected_markdown`.

## Scoring dimensions

### agent_memory.explain.v1 structure

For `reasoning_trace`, penalize:

- missing JSON;
- wrong `schema_version`;
- wrong `status`;
- missing decision when expected;
- malformed or missing `supporting_chain`;
- missing expected warning codes.

### Trust Model / Limitations

Markdown should include a clear `Trust Model / Limitations` section.

The candidate must not imply that DSM proves factual truth or reasoning
validity. It must preserve the local-trust boundary.

### Over-promise wording

Strongly penalize wording such as:

- proven true
- verified truth
- guaranteed
- tamper-proof
- cryptographic proof of truth
- factual truth verified

DSM must not be represented as proving truth.

### Fact / hypothesis / rule / preference separation

Reasoning traces should preserve distinct facts, hypotheses, inferences, and
decisions.

Skill memory must keep corrections, preferences, candidate rules, validated
rules, and outcomes typed. A speculative correction must not silently become a
validated rule.

### Required checks

For `skill_memory_entry`, required checks are scored as first-class structure.
Missing checks are penalized and reported as itemized penalties.

### Expected warnings

Negative reasoning records may expect warning codes such as:

- `missing_dependency`
- `cycle_detected`
- `depth_limit_reached`
- `taxonomy_confusion`

The scorer checks that expected warning codes are surfaced.

### Hash normalization

The dataset uses placeholders such as:

```text
<HASH_FACT_1>
<HASH_DECISION>
```

Raw runtime `v1:` hashes in candidate targets are penalized because they are
environment-specific and not semantic targets.

### Candidate rule preservation

Skill corrections must remain `candidate_rule` until explicitly validated.
The scorer penalizes:

- correction promoted to `validated_rule`;
- skill rule update status other than `candidate`;
- missing promotion policy;
- fake explain JSON/Markdown attached to a skill memory entry.

### User isolation

User isolation is a first-class criterion. A user-scoped retrieval for user A
must never return user B entries.

Records with `user_id = null` or absent `user_id` are global/template material
and must be excluded from user-scoped retrieval by default unless explicitly
requested.

## Expansion gate

The harness can run now on the 7 current records.

No public or meaningful model-level conclusions should be drawn until the
corpus reaches approximately 15-30 diverse records across multiple domains and
negative cases.

Do not expand the dataset further until this harness is running and reviewed.

## Placement

Eval v0.2 tooling lives outside `src/dsm/`, under:

```text
eval/dsm_reasoning_eval_v0_2/
```

It must not import DSM kernel internals and must not touch Storage.
