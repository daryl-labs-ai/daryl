# DSM Swarm Benchmark — Symmetric Scoring Rubric for Condition A (v0.1)

Status: pre-registered, frozen with `PARITY_SPEC_V0_1.md`. This rubric defines
how every mechanical and honesty metric is computed **for condition A from the
common technical event log** using the SAME operational definitions the replay
applies to B — so "B scores better because only B is instrumented" cannot
arise from asymmetric measurement. The scorer is blind to condition: logs are
label-stripped and path-normalized before scoring.

## 1. Source and ground rules

- Input: the common event log (JSONL; one object per logical step, tagged with
  `step_uid = (role, step_kind, task_ref, attempt)` at emission — see
  `PARITY_SPEC_V0_1.md §3`) plus persisted artifacts. Nothing else.
- The scorer applies **mechanical procedures only** (field lookups, id joins,
  set comparisons). No semantic inference, no reading of free text beyond
  extracting declared identifiers. Where a metric requires judgment it is
  annotation-tier (cases 06/12) and is out of this rubric.
- The same procedures run against B's event log too (not only its replay), so
  the A-vs-B comparison of family-A/C metrics is log-vs-log under one rubric;
  B's replay-derived values are reported alongside, labelled as the
  DSM-evidence dimension.

## 2. Operational definitions (identical for A and B)

| Concept | Definition on the event log |
|---|---|
| decision | a `decide` step whose payload declares `decision_id`, `subject_id`, an outcome, and optional `bases` (list of ids) |
| work claim | a `submit_work` step declaring `work_id`, `claimed_actions`, optional `required/claimed/actual checks`, `limitations` |
| review | a `review` step declaring `review_id`, `reviewed_ref`, `lens`, `verdict ∈ {approve, reject, inconclusive}` |
| conflict (explicit) | an `emit_conflict` step declaring `conflict_id`, `competing_refs (≥2)`, `state` |
| reference resolvable | the referenced id appears as the declared id of an earlier step in the same run's log |
| provenance reconstructable (decision) | the decision declares an author (`agent_id`) AND every declared basis is resolvable |
| contradiction surfaced | a mechanical pass (id-join of reviews by `reviewed_ref`, verdict-set inspection; join of decisions by `subject_id`) reports the planted incompatibility |
| check gap | `claimed_checks \ actual_checks` (observable gap) and `required_checks \ claimed_checks` (coverage gap), as set differences on declared names |
| limitation preserved | a limitation string declared at `submit_work`/`review` appears (id-linked) in the terminal `report` step's payload |
| orphan | a receipt-declaring step whose `task_ref` matches no `delegate` step in the log |
| superseded basis | a decision basis id that some later `decide` step declares it `supersedes` |

## 3. Metric computation for A

- `provenance_reconstruction_rate` = reconstructable decisions ÷ decisions.
- `reference_resolution_rate` = resolvable declared refs ÷ declared refs.
- `orphan_rate` = orphans ÷ receipt-declaring steps.
- `required_check_coverage` = mean over work claims of |required ∩ claimed| ÷
  |required| (claims with no required checks: excluded from the mean, counted
  separately — never scored 1.0).
- `divergent_review_detection` = planted review divergences surfaced ÷ planted.
- `missing_reference_count`, `unresolved_conflict_count` = direct counts.
- `unsupported_claim_rate` = claims declaring no resolvable evidence ÷ claims.
- `claimed_vs_observable_check_gap` = mean |claimed \ actual| ÷ |claimed|
  (claims with empty `claimed` excluded, counted).
- `decision_basis_retrievability` = decisions whose every basis is resolvable
  AND not superseded at decision time ÷ decisions.
- `limitation_preservation_rate` = preserved limitations ÷ declared.
- `contradiction_surfacing_rate` = planted contradictions surfaced ÷ planted.

## 4. Honesty of the comparison

- A's log is a **fair champion**: the event log carries the same declared
  fields the records carry in B. What A lacks is the typed, hash-chained,
  replayable *structure* — exactly the treatment under evaluation.
- If a metric is computable for B only via replay (e.g. supersession-cycle
  diagnostics), it is reported in the DSM-evidence dimension, not as an A/B
  family-A comparison.
- Blinding: condition labels, shard names, storage paths and recorder step
  entries are stripped/normalized before the scorer sees the log; suspected
  leakage is recorded per pair with a pre-registered sensitivity analysis.
