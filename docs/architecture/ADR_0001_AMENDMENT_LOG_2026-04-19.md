# ADR 0001 — Amendment Log 2026-04-19

- **Status of ADR 0001:** Proposed (unchanged)
- **Trigger:** Critical reading of Phase 7a verdict — two blind spots identified.
  1. The 10 000-entry fixture is not representative of production scale ; the 6.44× absolute-build ratio at 10 k is not a bounded prediction of what happens at 100 k+.
  2. The "Phase 7b unblocked" language in the Phase 7a `Consequences` section blurred the distinction between architectural feasibility (what Phase 7a measured) and operational acceptability (what Phase 7b will inherit). The fix is to make the distinction load-bearing in the document structure, not to re-benchmark.

## Changes applied in-place

1. **`docs/architecture/ADR_0001_PHASE_7A_VERDICT.md`** — four amendments, all in-place, no new top-level sections outside the existing document structure :
   - **Amendment A** — new section `Bucket sorting: build-time vs query-time`, inserted between `## Measured thresholds` and `## Verdict`. Cites `src/dsm/rr/index/rr_index_builder.py:201, 208–210` and `src/dsm/rr/query/rr_query_engine.py:137–180` to establish the verdict : **build-time sort, stable ordering by timestamp**, with insertion-order tiebreaker via Timsort stability. No query-time sort.
   - **Amendment B** — new sub-section `### Interpretation of Dataset B query ratios` appended to `## Measured thresholds`. Names the 0.00×–0.01× ratios for what they are : a bucket-size dividend (~7 entries/bucket, `limit=100` never reached), not a 100× algorithmic advantage. Forbids "100× faster" / "order of magnitude speedup" framings in future writing ; replaces with "RR benefits from action-bucketed partitioning ; the observed ratio is dominated by bucket size, not by algorithmic improvement".
   - **Amendment C** — new `#### Debt transfer to former SessionIndex consumers` sub-section under `### Operational concerns`. Names the 1× → 6.44× transfer for the 8 SessionIndex consumers enumerated in the classification report. Explains why this doesn't block Phase 7a (incremental cost is the gated metric) and why it requires Phase 7a.5 (absolute cost at production scale).
   - **Amendment D** — `## Verdict` opening reformulated as **"PASS (architectural gates)"**, with an explicit "transition to Phase 7b is conditioned on Phase 7a.5" clause. The existing `### Consequences of this verdict` bullet "Phase 7b is unblocked" was edited in-place to "architecturally unblocked, operationally conditioned on Phase 7a.5".
2. **`docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md`** — Phase 7a.5 inserted into the existing migration plan between 7a and 7b. Three gates (i/ii/iii) with explicit PASS/FAIL consequences. Anchored edits elsewhere in the same document :
   - `Consequences > Négatives` — migration estimate bumped from "~12–16 engineer-days" to "~13–17 engineer-days" (+1 j for the 7a.5 re-benchmark, 0 new prototype code).
   - `Success criteria` — item `8` added : Phase 7a.5 verdict document required for `Accepted`.
   - `Open questions before Accepted` — new `### Q2 — Phase 7a.5 scalability verdict` opened, marked `Open`.
   - Migration plan `Total` line updated to reflect 7a / 7a.5 / 7b as three sub-phases of Phase 7.

## What is NOT changed

- Phase 7a verdict : remains **PASS** on the architectural gates defined before measurement. No post-hoc gate reshuffling.
- `docs/architecture/ADR_0001_SESSIONINDEX_CLASSIFICATION.md` : **not touched**. The `duplicative` verdict stands. A Phase 7a.5 FAIL would not reopen classification — a scaling failure on RR's pre-existing 4 indexes is an optimisation requirement, not grounds for reclassification.
- Prototype branch and SHA : `proto/phase-7a-rr-action-name-index` @ `58d7789` — unchanged. No new code commits on the prototype in this phase.
- Benchmark results : `benchmarks/results/phase_7a_action_index_20260419.{json,md}` — unchanged.
- Canonical layering model section of ADR 0001 : unchanged.
- ADR 0001 status : remains **Proposed**. No transition toward `Accepted` in this phase.
- Kernel (`src/dsm/core/`) : untouched, frozen.

## Separation of concerns enforced by these amendments

| Question | Phase that answers it | Verdict so far |
|---|---|---|
| Can RR structurally absorb `action_name` without violating its existing invariants ? | Phase 7a (architectural feasibility) | **PASS** on 10 000-entry fixture |
| Does that structural absorption remain operationally tolerable at production scale ? | Phase 7a.5 (operational acceptability) | **Open** — awaits execution on 100 000-entry fixture |
| Can the 8 SessionIndex consumers be rebranched onto RR without regression ? | Phase 7b (execution) | Blocked until 7a.5 PASSes |
| Should ADR 0001 transition from `Proposed` to `Accepted` ? | Separate acceptance-review phase | Requires items 1–8 of `Success criteria`, including the 7a.5 verdict |

## Next step

Execute Phase 7a.5 benchmark. See `docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md > Migration plan > Phase 7 > 7a.5` for the scope, gates, and artefact requirements.

---

*This amendment log is trace-only. It introduces no normative rule not already present in ADR 0001 or the Phase 7a verdict report — it only records how those existing rules were refactored to make the feasibility / operability distinction structural rather than rhetorical. If a new rule or decision needs to be recorded in the future, it belongs in the ADR itself, not here.*
