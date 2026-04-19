# ADR 0001 — Phase 7a.5 Verdict Report

- **Date:** 2026-04-19
- **Parent ADR:** `docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md`
- **Status of parent ADR:** Proposed (unchanged; acceptance gate point 8 = **unsatisfied**)
- **Prototype branch:** `proto/phase-7a-rr-action-name-index` (SHA at benchmark run: `5af3d5f1833a22f4b27cd69128a47b1e59bf18a6`; branch delta vs Phase 7a = harness extension + results + this report, no prototype code change)
- **Prototype code SHA:** `58d7789` (unchanged since Phase 7a — verified by `git diff 58d7789..HEAD -- src/dsm/rr/` returning empty on `2026-04-19`)
- **Verdict:** **FAIL**
- **Measurement host:** `macOS-26.3.1-arm64-arm-64bit`, Python 3.10.20 (`benchmarks/results/phase_7a_5_action_index_100k_20260419.json:platform,python`)

---

## Fixture description

Same generator as Phase 7a (`benchmarks/bench_phase_7a_action_index.py:97–186`), scaled from 10 000 to 100 000 entries per dataset via the new `--fixture-size` CLI argument introduced in this phase. Generator output is deterministic and bit-identical to the Phase 7a path at default parameters (verified by SHA-256 digest of dataset entries).

- **Size.** 100 000 entries per dataset (`benchmarks/bench_phase_7a_action_index.py:620` default overridden by `--fixture-size 100000`).
- **Sessions.** 5 000 — scaled linearly from Phase 7a's 500 to maintain the ~20-entries-per-session target (`benchmarks/bench_phase_7a_action_index.py:625`, `ENTRIES_PER_SESSION_TARGET = 20` at line 59).
- **Action_names.** 30 on Dataset A (Zipf s=1.1), 1 000 on Dataset B (quasi-uniform) — unchanged from Phase 7a.
- **Seeds.** 42 / 43 — unchanged from Phase 7a.
- **Time span.** 30 days — unchanged from Phase 7a.
- **Event-type mix.** 70 % `tool_call`, 15 % `note`, 5 % each of `session_start`, `snapshot`, `session_end` — unchanged.
- **Generator reference.** `benchmarks/bench_phase_7a_action_index.py:119` (session_ids), `:116` (per-entry loop), `:150` (timestamp sort).

---

## Measured thresholds — Dataset A (low cardinality, 30 action_names Zipf)

All raw values cited from `benchmarks/results/phase_7a_5_action_index_100k_20260419.json:datasets[0]`. Reference Phase 7a values cited from `benchmarks/results/phase_7a_action_index_20260419.json:datasets[0]`.

| Metric | 7a (10k) | 7a.5 (100k) | 7a.5 ratio | Gate | Pass? |
|---|---:|---:|---:|---|---|
| SessionIndex_build | 85.45 ms | 1 121.47 ms | — | — | — |
| RR_baseline_build | 483.03 ms | 13 739.94 ms | — | — | — |
| RR_with_action_build | 550.53 ms | 15 120.19 ms | — | — | — |
| **delta_build = Z − Y** | 67.50 ms | 1 380.25 ms | **1.23×** | ≤ 1× | **❌** |
| **absolute_ratio = Z / X** | 6.44× | **13.48×** | — | ≤ 10× | **❌** |
| Query top — ratio | 0.69× | **2.27×** | — | ≤ 1.5× | **❌** |
| Query rare — ratio | 0.02× | 0.02× | — | ≤ 1.5× | ✅ |
| Query C1 (action+session) — ratio | 0.23× | 0.57× | — | ≤ 1.5× | ✅ |
| Query C2 (action+time) — ratio | 0.40× | 0.23× | — | ≤ 1.5× | ✅ |

Row counts (`datasets[0].query_row_counts` in JSON): top = 100/100, rare = 100/100, C1 = 14/14, C2 = 100/100 — SessionIndex and RR return identical cardinality on every variant. Per-query p95 / max (`datasets[0].queries.*`): RR top median 0.0622 ms, p95 0.0818 ms, max 0.2032 ms ; RR C1 median 6.98 ms, max 9.22 ms.

**Dataset A verdict: FAIL on three gates — (i), (ii) top, (iii).**

---

## Measured thresholds — Dataset B (high cardinality, 1 000 action_names uniform)

All raw values cited from `benchmarks/results/phase_7a_5_action_index_100k_20260419.json:datasets[1]`.

| Metric | 7a (10k) | 7a.5 (100k) | 7a.5 ratio | Gate | Pass? |
|---|---:|---:|---:|---|---|
| SessionIndex_build | 85.34 ms | 1 227.71 ms | — | — | — |
| RR_baseline_build | 480.57 ms | 14 176.17 ms | — | — | — |
| RR_with_action_build | 547.23 ms | 14 870.08 ms | — | — | — |
| **delta_build = Z − Y** | 66.65 ms | 693.90 ms | **0.57×** | ≤ 1× | ✅ |
| **absolute_ratio = Z / X** | 6.41× | **12.11×** | — | ≤ 10× | **❌** |
| Query top — ratio | 0.01× | 0.001× | — | ≤ 1.5× | ✅ |
| Query rare — ratio | 0.00× | 0.001× | — | ≤ 1.5× | ✅ |
| Query C1 — ratio | 0.01× | 0.001× | — | ≤ 1.5× | ✅ |
| Query C2 — ratio | 0.01× | 0.001× | — | ≤ 1.5× | ✅ |

Row counts : top = 100/100 (RR rows matches SI rows: top bucket at 100k with 1 000 uniform actions holds ~100 entries, same limit reached on both sides), rare = 100/100, C1 / C2 return small sets. Per-query p95 / max all bounded within 0.02 ms.

**Dataset B verdict: FAIL on gate (iii) only.** Delta and query gates pass.

---

## Scaling observations

Facts measured between Phase 7a (10 k) and Phase 7a.5 (100 k), data volume multiplier = 10×. Scaling factor = 100k-value / 10k-value on the same metric. A scaling factor of ~10 indicates linear scaling ; above 11 is super-linear ; below 9 is sub-linear.

- **RR_baseline_build scales super-linearly at factor 28–30×** for 10× data (Dataset A: `483.03 → 13 739.94 ms`, factor 28.45 ; Dataset B: `480.57 → 14 176.17 ms`, factor 29.50 — `benchmarks/results/phase_7a_5_action_index_100k_20260419.json:datasets[*].builds.RR_baseline_build.median_ms` over Phase 7a references). RR's four cross-cutting indexes do **not** amortise favourably ; the fixed overhead hypothesis that motivated the ≤ 10× gate in ADR 0001 Phase 7a.5 is **falsified by this measurement**.
- **SessionIndex_build also scales super-linearly, but less: factor 13–14×** for 10× data (`85.45 → 1 121.47`, factor 13.12 on A ; `85.34 → 1 227.71`, factor 14.39 on B). The ~2.1× super-linearity excess of RR over SessionIndex explains the absolute-ratio drift from 6.44× (10k) to 12.11–13.48× (100k).
- **RR_with_action_build scales at factor 27× on both datasets** (`550.53 → 15 120.19` = 27.46 on A ; `547.23 → 14 870.08` = 27.17 on B), i.e. it tracks RR_baseline's super-linearity closely — the `action_name` extension is not the dominant scaling factor. The extension's incremental cost (`delta_build`) scaled 20.45× on Dataset A and 10.41× on Dataset B. The Dataset A delta inflation is why gate (i) fails there ; Dataset B's delta remains linear and passes gate (i).
- **Absolute ratio moves from 6.44× (10k) to 13.48× (A) / 12.11× (B) at 100k.** This is the headline result of Phase 7a.5 : the 6.44× figure published in `ADR_0001_PHASE_7A_VERDICT.md` Amendments was explicitly annotated as 10k-only, and it does not transfer to production-representative scale. A drift above the 10× gate defined before measurement in `docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md > Migration plan > Phase 7a.5` means the operational-acceptability hypothesis is rejected.
- **Query top regresses structurally on Dataset A** : `0.69× (10k) → 2.27× (100k)`, a 3.3× relative degradation. Dataset B's query top ratio improved (`0.01× → 0.001×`) because the Dataset B top bucket remains small (~100 entries at 100k under uniform distribution over 1 000 action_names), whereas Dataset A's top bucket grows roughly 10× (from ~2 000 to ~15 000 entries under Zipf concentration).

---

## Root cause analysis (FAIL)

Three gates missed across the two datasets. Root causes identifiable from measurement alone are listed below ; where measurement alone is insufficient, that is stated explicitly.

### Gate (ii) top — Dataset A — RR 2.27× slower than SessionIndex on top query

**Root cause identified.** `src/dsm/rr/navigator/rr_navigator.py:140–141` — `navigate_action` does `list(records)` where `records = index.get(action_name, [])`. This is a shallow copy of the **entire bucket** before returning. At Dataset A 100 k, the top-Zipf bucket for `action_0000` holds ~15 000 records (compare Dataset A top at 10 k : ~2 000 records, where the copy cost was negligible). The copy is O(bucket_size) per query call ; `RRQueryEngine.query_actions` then iterates with early-exit at `limit=100`, but the copy overhead has already been paid in full.

SessionIndex does not copy — `src/dsm/session/session_index.py:169` iterates `self._actions` directly (`for act in self._actions`). At limit=100 with ~15 000 matches available, SessionIndex exits after ~100 iterations without allocating a new list.

This is a prototype design artefact that was invisible at 10 k and dominates at 100 k. It is consistent with the "no modification to prototype code" constraint : the copy pattern is intentional in RR's navigator design (all four navigation methods follow the same pattern, `navigate_session` line 78, `navigate_agent` line 88, `navigate_shard` line 129, `navigate_action` line 141). Addressing it requires either exposing a streaming iterator from the navigator, or letting query_engine work against the bucket reference directly — both are prototype changes, out of scope for Phase 7a.5.

### Gate (iii) — both datasets — RR absolute build scales super-linearly vs SessionIndex

**Root cause partially identified ; full decomposition requires instrumentation.**

- **Measured.** RR_baseline scaling factor ~28–29× vs SessionIndex's ~13–14× for the same 10× data volume. RR's super-linearity excess is the driver of the ≤ 10× gate failure.
- **Candidate causes visible without further instrumentation :**
  - `RRIndexBuilder._write_index_files` at `src/dsm/rr/index/rr_index_builder.py:183–207` serialises each index file via `json.dump(payload, f, ensure_ascii=False, indent=2)`. At 100 k records across four indexes (session / agent / timeline / shard), pretty-printed JSON output is ~3–4× larger on disk than JSONL without indent. SessionIndex at `src/dsm/session/session_index.py:102–108` writes JSONL line-by-line (no indent).
  - `timeline_index.sort(key=lambda x: x["timestamp"])` at `src/dsm/rr/index/rr_index_builder.py:175` runs over 100 k records (O(N log N) ≈ 1.66 M comparisons). SessionIndex's `actions.sort` at `src/dsm/session/session_index.py:97` runs over ~70 k action-only records (~1.15 M comparisons) — smaller base, same complexity class.
  - The agent_index lists (grouped by `agent` at line 60 of rr_index_builder.py) become long at 100 k : with only 3 agents in the fixture, each bucket holds ~33 k records. List-append cost is O(1) amortised, but the serialised output per bucket becomes large and intensifies the indent-JSON overhead.
- **Cannot be decomposed from the median-of-5 benchmark alone.** Distinguishing whether the sort, the JSON indent serialisation, or GC pressure dominates requires a per-phase wall-clock split inside `RRIndexBuilder.build()`, which is a prototype change forbidden by Phase 7a.5 scope. **Root cause for the build super-linearity is therefore not yet fully identified ; requires instrumentation pass on `src/dsm/rr/index/rr_index_builder.py:119–178` (the `build()` method body).**

### Gate (i) — Dataset A only — delta_build exceeds 1× SessionIndex_build

**Root cause identified.** Dataset A's delta inflated from 67.5 ms (10 k) to 1 380.25 ms (100 k) — scaling factor 20.45× for 10× data. On Dataset B the same metric scales 10.41× (near-linear) and gate (i) passes. The asymmetry matches the Dataset A top bucket growth (~2 000 → ~15 000 records under Zipf) : at 100 k, the sort-at-end pass at `src/dsm/rr/index/rr_index_builder.py:208–210` (`for bucket in self.action_index.values(): bucket.sort(...)`) pays O(bucket_size × log bucket_size) per bucket ; under Zipf the dominant bucket is ~2 orders of magnitude larger than the median bucket, driving total sort time super-linearly. Dataset B's uniform distribution keeps buckets small (~100 each), so the same sort pass scales linearly.

This is consistent with the prototype's design choice to sort each bucket at build (`proto(rr)` commit `a693429`) rather than at insert ; the choice was correct at 10 k but the Zipf-tail cost becomes visible only at 100 k.

---

## Consequences

### Immediate

- **Phase 7b is blocked.** ADR 0001 `Migration plan > Phase 7 > 7b` precondition "Phase 7a.5 verdict is PASS" is not met.
- **ADR 0001 acceptance gate point 8 is unsatisfied.** `docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md > Success criteria > 8` requires PASS on all three gates on both datasets. We have 3× FAIL on Dataset A and 1× FAIL on Dataset B.
- **ADR 0001 remains `Proposed`.** Status was already Proposed ; Phase 7a.5 FAIL does not move it backward. It simply refuses to clear the acceptance gate.
- **Phase 7a's PASS verdict stands.** `docs/architecture/ADR_0001_PHASE_7A_VERDICT.md` verdict is unaffected. Phase 7a measured architectural feasibility at 10 k and that result remains valid. Phase 7a.5 measured operational acceptability at 100 k and rejects the null hypothesis. The two verdicts coexist as designed in `docs/architecture/ADR_0001_AMENDMENT_LOG_2026-04-19.md`.

### SessionIndex classification

- **SessionIndex classification remains `duplicative`.** `docs/architecture/ADR_0001_SESSIONINDEX_CLASSIFICATION.md` is not reopened. The FAIL is an **operational scaling issue on RR's existing indexes**, not an argument that SessionIndex's access pattern is materially orthogonal. SessionIndex's own `SessionIndex_build` is itself super-linear at factor 13–14× over the same 10× data volume — SessionIndex is not "materially better scaling" either, it is less super-linear by a factor of ~2.
- Per `ADR_0001_CANONICAL_CONSUMPTION_PATH.md > Migration plan > Phase 7a.5 > Consequences if 7a.5 FAILS` : "a 6.44×-at-10k-that-drifts-past-10×-at-100k is an optimisation requirement on RR's pre-existing indexes, independent of the `action_name` extension — not grounds for reclassification". That clause applies exactly here.

### Next step is RR optimisation, not reclassification

Options to evaluate (do **not** decide in this report ; a separate prompt / ADR amendment is the proper vehicle) :

- **JSON-lines over pretty-printed JSON** for RR index files — swap `json.dump(..., indent=2)` (`src/dsm/rr/index/rr_index_builder.py:200`) for line-by-line JSONL like `SessionIndex` does. Expected to reduce I/O volume by ~3–4× at 100 k.
- **Navigator iterator vs list-copy** — replace the `list(records)` pattern at `rr_navigator.py:78, 88, 129, 141` with an iterator or a reference hand-off, eliminating the O(bucket_size) copy that dominates Dataset A query top.
- **Incremental rebuild** — index only newly appended entries since the last build, rather than full cold rebuild. Larger change, potentially a dedicated ADR.
- **Lazy index loading** — load only the indexes actually queried by the current call-site. Reduces per-call memory and I/O, but does not reduce build cost.
- **Shard-level index partitioning** — build one index set per shard, rebuild only the touched shard. Structural refactor.

A rebenchmark with each candidate optimisation (keeping the 10× / 10k→100k methodology intact) is the correct path to re-open Phase 7a.5. No gates are relaxed in the re-open.

---

## What this verdict does NOT do

- Does **not** invalidate Phase 7a's PASS verdict on architectural gates.
- Does **not** reopen `docs/architecture/ADR_0001_SESSIONINDEX_CLASSIFICATION.md`. Classification stays `duplicative`.
- Does **not** amend Phase 7a verdict report. The 6.44× figure there remains accurately annotated as 10 k-only.
- Does **not** merge the prototype branch. `proto/phase-7a-rr-action-name-index` stays unmerged.
- Does **not** decide which optimisation path to pursue. That is a separate phase.
- Does **not** re-propose a relaxed gate. The ≤ 10× threshold was fixed before measurement in ADR 0001 v2 and will not be relaxed post-hoc.

---

## Files examined / created

- **Harness (extended, additive).** `benchmarks/bench_phase_7a_action_index.py` — new `--fixture-size` and `--output-suffix` CLI arguments (default behaviour reproduces Phase 7a when invoked without flags), blocking gate (iii) `absolute_gate_pass_under_10x` added to `bench_dataset` (`benchmarks/bench_phase_7a_action_index.py:455–469`). Harness extension committed on `5af3d5f`.
- **Results (new).** `benchmarks/results/phase_7a_5_action_index_100k_20260419.json` and `.md`. Schema additions over Phase 7a output : `phase`, `fixture_size`, `comparison_baseline` (keys at JSON root), `absolute_gate_pass_under_10x` (inside each dataset's `builds`).
- **Prototype (unchanged, verified).** `src/dsm/rr/index/rr_index_builder.py`, `src/dsm/rr/query/rr_query_engine.py`, `src/dsm/rr/navigator/rr_navigator.py`. `git diff 58d7789..HEAD -- src/dsm/rr/` = empty. Prototype code behaviour at 100 k is unmodified from its behaviour at 10 k ; only the input size changed.
- **Baselines (unchanged, verified).** `src/dsm/session/session_index.py` (never touched), `benchmarks/results/phase_7a_action_index_20260419.json` (used as reference baseline at `comparison_baseline` JSON key, content byte-identical to the Phase 7a artefact).
- **Reference for gate definitions.** `docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md > Migration plan > Phase 7a.5` (gates i/ii/iii, thresholds fixed pre-measurement).
- **Reference for Phase 7a results.** `docs/architecture/ADR_0001_PHASE_7A_VERDICT.md` (including Amendments A/B/C/D — the 6.44× figure referenced there is 10 k-only and remains accurate at that scale).
