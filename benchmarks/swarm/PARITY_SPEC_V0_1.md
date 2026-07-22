# DSM Swarm Benchmark — Behavioral Parity Specification (v0.1)

Status: **pre-registered, frozen before any implementation or data** (B0-rev1
decision, owner-mandated). Any later change is a dated protocol revision; both
analyses are then reported. This document is the single definition point for
"homologous steps", the A/B′/B matching rules, and the parity thresholds.

---

## 1. The falsifiable parity requirement

Benchmark design requirement (A/B):

- same models
- same prompts
- same providers
- same orchestration, planning and routing
- same task corpus
- same evaluation protocol
- same random seeds whenever supported
- **instrumentation is the only *intended* experimental variable**

Any additional behavioral differences introduced by the instrumentation (extra
prompts, altered routing, additional reasoning steps, retries, tool-selection
changes, etc.) must be identified, measured and reported as potential threats
to validity.

The benchmark distinguishes **instrumentation overhead** from **behavioral
influence**. Measuring runtime cost (latency, storage, tokens) is not
sufficient: the protocol also assesses whether the presence of the recorder
changes the agents' decisions, reasoning paths, or execution strategy. Any
observed behavioral shift is treated as a validity threat and explicitly
documented. Parity is a **target whose attainment is itself measured**, never
an assumed fact.

## 2. Conditions

| Condition | Records written | Prompt grounding block | Purpose |
|---|---|---|---|
| `A` | none | absent | control |
| `Bprime` | emitted by the **orchestrator only**, via the bounded writer | absent (prompts byte-identical to A) | isolates the effect of the recorder's *presence* (overhead + timing/routing) with **zero** prompt channel |
| `B` | emitted via the recorder | the single declared block (hashed in the manifest) | full treatment |

Causal decomposition: `B′ − A` = passive-instrumentation influence (expected
≈ 0 behaviorally; any excess is a validity finding). `B − B′` = grounding-block
influence. Runtime overhead (tokens/latency/bytes) is accounted separately
(metric family D) and never suffices as a parity argument.

**H6 (instrumentation neutrality, falsifiable):** the passive recorder (B′)
does not change the agents' decisions, reasoning paths, or execution strategy
beyond the pre-registered thresholds (§5). If H6 fails, all H1–H4 results are
reported in the *confounded* stratum (§6) — the shift itself becomes the
primary finding. B′ additionally serves as the **permanent behavioral
non-regression suite** for the recorder: every future recorder change must
keep H6 green in the deterministic regime (§4), or the change is known to
influence the agents.

## 3. Homologous steps — frozen definition

**The most fragile notion of the protocol, therefore fixed first** (owner
reservation, B0-rev1). Matching between conditions is **functional, never
positional**.

### 3.1 Step identity is assigned at emission, not inferred post-hoc

The orchestrator (identical code in all three conditions) tags every logical
step **at the moment it executes it** with a condition-independent functional
key:

```
step_uid = (role, step_kind, task_ref, attempt)
```

- `role` ∈ `{orchestrator, planner, worker, reviewer, reconciler}`
- `step_kind` ∈ the CLOSED set:
  `run_setup, plan, delegate, implement, self_check, submit_work, review,
   decide, reconcile, emit_conflict, report`
- `task_ref` = the task id the step serves (`""` for run-level steps)
- `attempt` = 1-based retry counter for that `(role, step_kind, task_ref)`

Because the tag is assigned at source by shared orchestrator code, homology
never depends on reconstructing intent from provider traffic.

### 3.2 Matching rule

Two steps in different conditions are **homologous iff their `step_uid` are
equal**. Sequence position is NEVER a matching key. The step-kind *sequence*
remains a reported metric (`call_sequence_divergence`, §5) but not an
appariement mechanism.

### 3.3 Provider-call fan-out (condensation / splitting)

A logical step may span 1..n provider calls (one provider condenses two
reasonings into one call; another splits one into three). Therefore **all
per-step measures aggregate over the provider calls inside the step**
(tokens, call count, wall time). Provider-implementation fan-out differences
change per-step call counts (measured: `call_count_delta`) but can never break
matching.

### 3.4 Retries

A retry re-enters the same `(role, step_kind, task_ref)` with `attempt + 1`.
Homologous comparison pairs equal attempts; the difference in attempt-set
sizes is the `retries_delta` metric. A retry therefore shifts nothing: later
steps keep their own functional keys.

### 3.5 Unmatched steps

A step present in one condition with no homologue in the other is an
**unmatched step** — counted, listed by `step_uid`, and reported. Recorder
emission steps in B′/B are expected unmatched-by-design and are excluded from
the unmatched count after being verified to be recorder-only (§4).

## 4. Deterministic regime — hard gates (phases B1–B4)

With the deterministic `FakeProvider`, parity is an **invariant, not a
statistic**:

- `trace(A)` = the ordered list of `(step_uid, prompt_hash, tool_calls)` for
  every provider interaction;
- **Gate G1:** `trace(B′) minus recorder-only events == trace(A)` exactly;
- **Gate G2:** `trace(B) minus recorder-only events` differs from `trace(A)`
  **only** by the declared grounding block's hash in the affected prompts;
- **Gate G3:** two runs of the same condition and seed produce identical
  traces and identical projections (`deterministic_replay_equality`).

Any G1–G3 failure in the deterministic regime is a **harness bug** and blocks
the phase — it is not a "threat to validity" to be footnoted.

## 5. Live regime — pre-registered parity thresholds

In live runs parity is distributional. Frozen v0.1 thresholds (violations put
the pair in the *confounded* stratum, §6):

| Check | Threshold | Kind |
|---|---|---|
| `prompt_hash_verification` | all prompts outside the declared block byte-identical (hash-equal) | **hard gate** (pair invalid, excluded with reason) |
| `call_count_delta` (per role) | ≤ max(2 calls, 10% of the role's A count) | confounded if exceeded |
| `call_sequence_divergence` | normalized edit distance over step_kind sequences ≤ 0.15 | confounded |
| `retries_delta` | ≤ 2 per pair | confounded |
| `decision_outcome_divergence` | ≤ 0.20 of homologous `decide` steps with different outcomes | confounded |
| `tool_selection_distance` | reported; no threshold in v0.1 (descriptive) | descriptive |
| `reasoning_length_delta` | reported; no threshold in v0.1 (descriptive) | descriptive |

`call_sequence_divergence` = Levenshtein distance between the two conditions'
step_kind sequences ÷ max(len). Computed by the pure function in
`harness/parity.py`; thresholds live in `ParityThresholds` (manifest) with
these defaults.

## 6. Confounded stratum

A pair exceeding a non-hard threshold is **not excluded**: it is reported in
the *"confounded — behavioral shift"* stratum with its parity metrics, and its
deltas can NEVER support H1–H4. Symmetric to the outcome-quality equivalence
band: one band says "the result is comparable", this one says "the observed
system stayed the same".

## 7. What this spec does not claim

Parity within thresholds does not prove the instrumentation is causally inert
— it bounds the observable behavioral shift under the measured dimensions.
Unmeasured channels (e.g. provider-side state) remain listed as residual
threats in the protocol's validity section.
