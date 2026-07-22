# DSM Swarm Benchmark — Protocol (v0.1, B0-rev1)

Status: pre-registered design, **no run executed**. Adapted under control from
the out-of-repo candidate package's protocol after reconciliation with the
merged Swarm semantic core (PR #130) and the B0-rev1 amendment (falsifiable
parity, A/B′/B, H6). Companion documents: `PARITY_SPEC_V0_1.md` (frozen
matching rules and thresholds), `RUBRIC_A_V0_1.md` (symmetric scoring rubric),
`harness/` (typed contracts), `cases/` (deterministic scenario corpus).

## 1. Question

Does DSM Swarm improve the **observability, traceability, decision
reconstruction and inconsistency detectability** of multi-agent work — without
claiming to improve or prove the truth of the result?

**H1 (primary, falsifiable):** at comparable multi-agent work (same task,
models, prompts outside the declared block, seed), condition B increases the
proportion of claims, verifications, disagreements and decisions whose
provenance and relations can be reconstructed **mechanically** after
execution, by an evaluator with access only to persisted artifacts.

Secondary: **H2** planted-inconsistency detection recall (B replay vs A logs
under the same rubric, comparable precision); **H3** governing-decision
reconstruction success and step count; **H4** declared-limitation preservation
to the final report; **H5** overhead of B is measurable, bounded and separable
(B stays inside the outcome-quality equivalence band); **H6** instrumentation
neutrality (see `PARITY_SPEC_V0_1.md §2`). Null hypotheses: no A/B difference
for H1–H4; overhead non-separable or quality out of band for H5; behavioral
shift beyond thresholds for H6.

DSM Swarm shows **no observable value** if A's ordinary logs, scored under the
same rubric, reach reconstruction/detection rates indistinguishable from B, or
if B runs are frequently non-replayable. The **design is invalid** if prompts
diverge beyond the declared block, the recorder changes agent behavior
(deterministic-regime gate), receipts are synthesized by the harness, or the
planted-fault oracle leaks into prompts.

## 2. Conditions

`A` (control, no records) / `Bprime` (orchestrator-emitted records, prompts
byte-identical to A) / `B` (recorder + single declared grounding block). Full
definition, matching rules and thresholds: `PARITY_SPEC_V0_1.md`. Both
conditions produce the **same common technical event log**; B differs by
*structuring* (typed records via the bounded writer), never by extra
observation. The recorder never: changes a decision, adds a reviewer, resolves
a contradiction, promotes memory, edits a business prompt, invents a receipt,
or turns a log into a truth claim.

## 3. Metric families

- **A. Mechanical** (pure computation; replay for B, `RUBRIC_A_V0_1.md` for
  A): replay_success, provenance_reconstruction_rate,
  reference_resolution_rate, orphan_rate, required_check_coverage,
  missing_reference_count, divergent_review_detection,
  supersession_ambiguity_rate, unresolved_conflict_count,
  deterministic_replay_equality.
- **B. Outcome quality** (gate, never attributed to DSM without a causal
  protocol): task score / acceptance-test pass fraction, regressions,
  completeness.
- **C. Honesty/justification:** unsupported_claim_rate,
  claimed_vs_observable_check_gap, decision_basis_retrievability,
  limitation_preservation_rate, contradiction_surfacing_rate.
- **D. Cost:** tokens (per role/total), provider cost at a frozen price table,
  wall latency, call counts, record count and shard bytes (B), replay time,
  absolute and relative instrumentation overhead (recorder path timed
  separately from inference).
- **E. Behavioral parity** (`PARITY_SPEC_V0_1.md §5`): prompt_hash_verification,
  call_count_delta, call_sequence_divergence, retries_delta,
  decision_outcome_divergence, tool_selection_distance,
  reasoning_length_delta, unmatched steps.

Scoring: paired differences per dimension with bootstrap intervals, no single
composite score, an outcome-quality equivalence band **and** a behavioral
parity band; pairs outside either band go to their labelled stratum
("outcome-quality not comparable" / "confounded — behavioral shift") and never
support H1–H4. Sub-minimum samples are descriptive only.

## 4. Oracles

1. deterministic (planted-fault list of each case — covers 10/12 cases);
2. executable tests (task acceptance/regression suites);
3. human annotation (cases 06 and 12);
4. LLM judge only if annotation cannot scale, and then: anonymized conditions,
   random order, closed rubric, ≥2 judges with agreement measured, raw
   responses kept, result-vs-justification scores separated, **never**
   presented as ground truth;
5. no oracle — assumed for "is the justification true?": out of scope, only
   *retrievability* is measured.

## 5. Phases and spend gates

| Phase | Content | Spend |
|---|---|---|
| B1 | contracts + frozen parity spec + rubric + 12 deterministic cases | 0 |
| B2 | recorders (NoOp / bounded Swarm / orchestrator-emitter) + H6 gate tests | 0 |
| B3 | local runner + deterministic FakeProvider + common event log | 0 |
| B4 | full mechanical campaign (12 cases × A/B′/B), metrics, report | 0 |
| B5 | live smoke: 1 matched pair, 1 instance, caps ≤ 10 USD / 200k tokens / 900 s | **explicit authorization required** |
| B6 | multi-seed campaign (N=8 pairs), hard cap ≤ 100 USD total incl. smoke | **explicit authorization required** |
| B7 | analysis + report | 0 |

No live/paid execution, no provider call, before the explicit authorization of
B5. Out of scope entirely: ContextGrant / context re-serving, MemoryCandidate,
memory promotion, orchestrator product, any truth claim.

## 6. What success may and may not claim

Publishable on success: "On this task family and topology, DSM-instrumented
runs allowed mechanical reconstruction of X% of decision provenance and
detection of Y% of planted inconsistencies, vs X′/Y′% from ordinary logs under
the same rubric, at comparable outcome quality, for a measured overhead of Z."

Never publishable, even on success: that DSM proves content truth, that
declared work actually happened, that hallucinations decrease, that agents get
smarter, or any universal superiority (benchmark score ≠ universal product
proof).
