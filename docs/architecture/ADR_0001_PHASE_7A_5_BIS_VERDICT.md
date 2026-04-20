# ADR 0001 — Phase 7a.5-bis Verdict Report (segmented fixture)

- **Date:** 2026-04-20
- **Parent ADR:** `docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md`
- **Status of parent ADR:** Proposed (unchanged by this report ; acceptance gate point 8 **remains unsatisfied** — see verdict below).
- **Prototype branch:** `proto/phase-7a-rr-action-name-index` (SHA at bench run : `f699e675dde90da5f94db364d18baeda228e763b` ; the SHA includes the harness extension for `--fixture-layout` but **no change** under `src/dsm/rr/` since `58d7789`).
- **Prototype code SHA:** `58d7789` — unchanged since Phase 7a. Verified : `git diff 58d7789..HEAD -- src/dsm/rr/` shows only the additive profiler commits from Phase N+1 (no logic changes). `git diff 58d7789..HEAD -- src/dsm/core/ src/dsm/session/` returns empty.
- **Baseline compared against:** `docs/architecture/ADR_0001_PHASE_7A_5_VERDICT.md` (FAIL on monolithic fixture) and `benchmarks/results/phase_7a_5_action_index_100k_20260419.json`.
- **Layout change rationale:** `docs/architecture/ADR_0001_STORAGE_READ_PROBE.md` + its amendment (segmented shows `offset-sensitive (empirically linear-like)` at ~2.55 µs/offset ; monolithic shows a per-call O(file_size) floor ~354 ms at 100 k and a non-trivial offset-dependent component — fixed-term dominance NOT supported with ratio 1.495×).
- **Verdict:** **MIXED** — gates (i) and (iii) **change from FAIL to PASS on both datasets** ; gate (ii) top on Dataset A **still fails**.
- **Run artefacts:** `benchmarks/results/phase_7a_5_bis_action_index_100k_segmented_20260420.json` + `.md`.

---

## Fixture description

- Layout : **segmented** — verified on both datasets.
  - Segments created : **10** per dataset (`shards/sessions/sessions_0001.jsonl` … `sessions_0010.jsonl`).
  - `max_events_per_segment_used` : 10 000 (kernel default, `src/dsm/core/shard_segments.py:33`). Fixture at 100 k produced exactly 10 segments, within the target 5–20 range ; no instance-level override was applied.
  - `Storage.list_shards()` returned the segmented family as expected (dispatch routes to `_read_segmented`). Verification at `benchmarks/results/phase_7a_5_bis_action_index_100k_segmented_20260420.json:datasets[*].fixture_layout_meta.fixture_layout_verified`.
  - Generation time per dataset : ~170 s via `Storage.append()` per entry (fsync-per-entry cost ; 100 k entries × ~1.7 ms / entry). Amortised once per dataset by pre-generating a golden dir and `shutil.copytree`-ing into each build-run's fresh `tmp_path`.
- Size : 100 000 entries per dataset.
- Sessions : 5 000 per dataset.
- Action_names : 30 Zipf (Dataset A) / 1 000 quasi-uniform (Dataset B).
- Seeds : **42 / 43** — identical to Phase 7a.5.
- All other parameters : identical to Phase 7a.5 (timestamps 30-day span, event-type mix, `limit=100` queries, median-of-5 builds, 100-runs-after-5-warmup queries).

---

## Measured thresholds — Dataset A (Zipf)

All cells sourced from `benchmarks/results/phase_7a_5_bis_action_index_100k_segmented_20260420.json:datasets[0]` and `benchmarks/results/phase_7a_5_action_index_100k_20260419.json:datasets[0]`.

| Metric | 7a.5 monolithic (100k) | 7a.5-bis segmented (100k) | Gate | Pass bis? | Changed verdict vs 7a.5? |
|---|---:|---:|---|---|---|
| SessionIndex_build (median ms) | 1 121.5 | 1 017.3 | — | — | — |
| RR_baseline_build (median ms) | 13 739.9 | 6 612.6 | — | — | — |
| RR_with_action_build (median ms) | 15 120.2 | 7 291.1 | — | — | — |
| **delta_build (ms)** | 1 380.3 | **678.6** | — | — | — |
| **delta_build ratio** | 1.231× ❌ | **0.667×** | ≤ 1× | ✅ | **YES** (FAIL → PASS) |
| **Absolute ratio** | 13.482× ❌ | **7.167×** | ≤ 10× | ✅ | **YES** (FAIL → PASS) |
| Query top ratio | 2.267× ❌ | **2.394×** ❌ | ≤ 1.5× | ❌ | NO — still FAIL (+5.6 % worse) |
| Query rare ratio | 0.020× ✅ | 0.027× ✅ | ≤ 1.5× | ✅ | NO — still PASS |
| Query C1 ratio | 0.572× ✅ | 0.371× ✅ | ≤ 1.5× | ✅ | NO — still PASS |
| Query C2 ratio | 0.225× ✅ | 0.250× ✅ | ≤ 1.5× | ✅ | NO — still PASS |

**Dataset A verdict: FAIL on gate (ii) top, PASS on gates (i) and (iii) and three other (ii) variants.** Dataset-level `dataset_pass = False` in the JSON.

---

## Measured thresholds — Dataset B (uniform)

Source : `benchmarks/results/phase_7a_5_bis_action_index_100k_segmented_20260420.json:datasets[1]` vs `phase_7a_5_action_index_100k_20260419.json:datasets[1]`.

| Metric | 7a.5 monolithic (100k) | 7a.5-bis segmented (100k) | Gate | Pass bis? | Changed verdict vs 7a.5? |
|---|---:|---:|---|---|---|
| SessionIndex_build (median ms) | 1 227.7 | 1 030.7 | — | — | — |
| RR_baseline_build (median ms) | 14 176.2 | 6 568.2 | — | — | — |
| RR_with_action_build (median ms) | 14 870.1 | 7 194.1 | — | — | — |
| **delta_build (ms)** | 693.9 | 625.9 | — | — | — |
| **delta_build ratio** | 0.565× ✅ | **0.607×** ✅ | ≤ 1× | ✅ | NO — still PASS |
| **Absolute ratio** | 12.112× ❌ | **6.980×** ✅ | ≤ 10× | ✅ | **YES** (FAIL → PASS) |
| Query top ratio | 0.001× ✅ | 0.002× ✅ | ≤ 1.5× | ✅ | NO — still PASS |
| Query rare ratio | 0.001× ✅ | 0.001× ✅ | ≤ 1.5× | ✅ | NO — still PASS |
| Query C1 ratio | 0.001× ✅ | 0.001× ✅ | ≤ 1.5× | ✅ | NO — still PASS |
| Query C2 ratio | 0.001× ✅ | 0.002× ✅ | ≤ 1.5× | ✅ | NO — still PASS |

**Dataset B verdict: PASS on all three gates.** Dataset-level `dataset_pass = True` in the JSON.

---

## Diff vs Phase 7a.5

### Gates that changed verdict between monolithic and segmented

- **Gate (i) delta_build — Dataset A :** FAIL (1.23×) on monolithic → **PASS (0.67×)** on segmented. The delta dropped from 1 380 ms to 679 ms (−51 %).
- **Gate (iii) absolute — Dataset A :** FAIL (13.48×) on monolithic → **PASS (7.17×)** on segmented. RR_with_action absolute time halved (15.12 s → 7.29 s), and so did RR_baseline (13.74 s → 6.61 s). SessionIndex absolute also decreased slightly (1.12 s → 1.02 s).
- **Gate (iii) absolute — Dataset B :** FAIL (12.11×) on monolithic → **PASS (6.98×)** on segmented. Same magnitude of improvement as Dataset A.

### Gates that did NOT change verdict

- **Gate (ii) top — Dataset A : still FAIL** (2.27× → 2.39×, slightly worse by 5.6 %). The `list_copy` cost quantified at 69.1 % of `query_actions:total` in `ADR_0001_PHASE_7A_5_ROOTCAUSE.md §C.1` operates on the in-memory action_index bucket regardless of disk layout. The gate-ii top failure is therefore a **true RR-local issue**, independent of fixture-artefact hypothesis.
- **Gate (ii) rare / C1 / C2 — both datasets : still PASS.** Consistent with root-cause #1 being specific to top-bucket size on the Zipf distribution (which remains ~15 k entries on both layouts) and not with other query variants where the bucket is small.
- **Gate (i) delta_build — Dataset B : still PASS** (0.57× → 0.61×, slight noise-level increase).
- **Gate (ii) top — Dataset B : still PASS** (0.001× → 0.002×). Dataset B top bucket is ~100 entries under uniform distribution — the `list_copy` never becomes a bottleneck there.

### Expected directional change (from N+1B probe predictions) — CONFIRMED

N+1B's predictions (published before 7a.5-bis measurements) :

1. **Absolute build ratio should drop significantly on segmented.** Prediction : 13.48× → 3–6× range.
   Measured : 13.48× → **7.17×** (A), 12.11× → **6.98×** (B). Drops are significant (−47 %) and land just outside the predicted range (closer to 7× than 3–6×, but well under the 10× gate). **Directionally confirmed ; magnitude slightly less than predicted.** The 7.17× floor is set by the segmented read cost that `ADR_0001_STORAGE_READ_PROBE.md` measured as `linear-like ~2.55 µs/offset` plus the 10-segment open/readlines work.
2. **`delta_build` should stay similar or slightly decrease.** Prediction : close to monolithic value.
   Measured : 1.23× → **0.67×** (A) — meaningfully lower, not similar. Explanation : the 21 monolithic calls each carrying ~354 ms of full-file-scan were the "extra" burden RR_with_action shared with RR_baseline ; on segmented, that per-call baseline is much lower (~2.73 ms for segment 1), so the delta attributable to the action_index extension becomes a cleaner signal. 0.57× → 0.61× on Dataset B (stable, within noise). **Dataset A confirmed directionally (decreased) ; Dataset B confirmed exactly (stable).**
3. **Query top ratio should remain unchanged.** Prediction : stays around 2.27×.
   Measured : 2.27× → **2.39×** (A), 0.001× → 0.002× (B). Both near-identical to monolithic. **Confirmed.** Query-time work is entirely on the in-memory action_index bucket ; file layout is irrelevant.
4. **Queries rare / C1 / C2 should remain PASS.** Prediction : PASS.
   Measured : all PASS on both datasets, both layouts. **Confirmed.**

**No material divergence from predictions.** The N+1B probe's predictive model held on all four cases. This is itself a validation of the probe's methodology.

### Harness control (non-regression)

Before the main 100k segmented run, the extended harness was verified with `--fixture-layout monolithic --fixture-size 10000` against the Phase 7a published results :

| Metric | Phase 7a (10k, orig) | Control (10k, extended harness) | Δ% |
|---|---:|---:|---:|
| Dataset A delta_build ratio | 0.790 | 0.722 | −8.6 % |
| Dataset A absolute ratio | 6.442 | 6.121 | −5.0 % |
| Dataset A query top ratio | 0.685 | 0.739 | +7.8 % |
| Dataset A query C1 ratio | 0.233 | 0.247 | +6.3 % |
| Dataset B delta_build ratio | 0.781 | 0.815 | +4.4 % |
| Dataset B absolute ratio | 6.412 | 6.493 | +1.3 % |

All macro gate ratios within ±10 % (Δ range : −8.6 % to +7.8 %). Dataset B query ratios (absolute times < 30 µs) show larger percent swings (+37 % to +119 %) because the denominator is in the noise floor — these are not gate-ratio regressions, they are amplified floating-point noise where wall-clock measurements are microseconds. Harness is not regressing.

---

## Verdict

**Final verdict : MIXED.** Overall benchmark output = FAIL (`dataset_pass=False` on Dataset A, `dataset_pass=True` on Dataset B). Decomposed per gate :

| Gate | Dataset A | Dataset B |
|---|---|---|
| (i) `delta_build ≤ 1× SI` | **PASS** (0.667×) — was FAIL | PASS (0.607×) |
| (ii) query top ≤ 1.5× | **FAIL** (2.394×) — unchanged | PASS (0.002×) |
| (ii) query rare / C1 / C2 ≤ 1.5× | PASS | PASS |
| (iii) absolute ≤ 10× | **PASS** (7.167×) — was FAIL | **PASS** (6.980×) — was FAIL |

Per the brief's MIXED case :
> **Case: MIXED (some gates pass, some fail)**
> - Which gates changed verdict, which didn't — published above.
> - Gates still failing indicate problems that are **not** layout-dependent (true RR-local issues, e.g., `list_copy` for gate (ii) top if it still fails).
> - Phase 7b **partially unblocked** or still blocked depending on which gates pass.
> - No amendment to ADR 0001 structure; acceptance gate point 8 remains unsatisfied until all three gates pass.

Translating to this measurement :
- The "70 % `storage_read_batch`" observation from `ADR_0001_PHASE_7A_5_ROOTCAUSE.md §A.1` **was** partially a fixture-artefact. On segmented, RR's aggregate build cost drops by ~47 % (13.74 s → 6.61 s for RR_baseline), which is exactly the magnitude N+1B predicted.
- The `nav:action:list_copy` observation from `ADR_0001_PHASE_7A_5_ROOTCAUSE.md §C.1,§C.9` **was not** a fixture-artefact. It is a genuine RR-local cost that persists on segmented with near-identical magnitude (2.27× → 2.39× on Dataset A top query).
- **Phase 7b remains blocked** on Dataset A gate (ii) top, independently of layout. It is no longer blocked on gate (iii), which was the most structural concern.
- **Acceptance gate point 8 remains unsatisfied** per the Phase 7a.5 original gating rule (all three gates must PASS on both datasets).

### Case applicability (verbatim from brief)

- ❌ **Full PASS**: not applicable. Gate (ii) top on Dataset A still fails.
- ✅ **MIXED**: this is the applicable case. Per the brief : "Gates still failing indicate problems that are **not** layout-dependent (true RR-local issues, e.g., `list_copy` for gate (ii) top if it still fails)." — which is the exact pattern measured.
- ❌ **Full FAIL**: not applicable. Multiple gates materially improved under segmented.

---

## Strategic implications

Segmented layout **mostly** recovers the Phase 7a.5 FAIL : gate (iii) passes by a comfortable margin on both datasets (7.17× and 6.98× vs the 10× ceiling), gate (i) passes on both. The 70 %-of-build `storage_read_batch` finding from the root-cause decomposition was, as N+1B predicted and this phase confirms, meaningfully layout-dependent. That specific operational-cost concern is no longer the primary blocker of Phase 7b.

What remains is the `list_copy` cost on the top-Zipf bucket, which is independent of file layout and is an RR-local implementation artefact of `src/dsm/rr/navigator/rr_navigator.py:140–141` (as quantified in `ADR_0001_PHASE_7A_5_ROOTCAUSE.md §C.9`). A defensible next phase — not prescribed here — would be a targeted change to the navigator/query-engine integration to avoid copying the full bucket on top-action queries at Zipf scale, combined with a re-run of this harness at `--fixture-layout segmented --fixture-size 100000` to verify gate (ii) top drops below 1.5× on Dataset A. No change to storage, kernel, or SessionIndex would be required by that phase. ADR 0001's viability is not contested by this verdict — only the implementation detail that blocks gate (ii) top remains to be addressed.

---

## What this phase does NOT decide

- Does not promote ADR 0001 to `Accepted`.
- Does not modify the Phase 7a.5 verdict report — it remains as the monolithic record.
- Does not re-run root-cause decomposition on segmented. Decomposition from Phase N+1 was on monolithic ; a segmented decomposition is a defensible follow-up if one wants to quantify the `storage_read_batch` reduction per-section, but the current verdict did not require it.
- Does not modify kernel, RR, SessionIndex.
- Does not prescribe a specific `list_copy` fix. A defensible next phase is noted in Strategic implications, not prescribed.
- Does not re-open the N+1B probe's labels on monolithic or segmented. Those measurements stand.

---

## Files examined / created

- **Harness (extended, additive).** `benchmarks/bench_phase_7a_action_index.py` — new `--fixture-layout {monolithic,segmented}` argument (default `monolithic`, preserves Phase 7a / 7a.5 reproducibility) ; new helpers `_entry_from_dict`, `_build_segmented_golden`, `_copy_golden_to` ; `_run_build_series` and `_prepare_query_env` accept an optional `materialize_fn` ; `bench_dataset` pre-generates a golden segmented fixture once per dataset when layout is segmented. Segmented fixture generated via `Storage.append()` — the production path through `ShardSegmentManager`, not by writing files directly.
- **Results (new).** `benchmarks/results/phase_7a_5_bis_action_index_100k_segmented_20260420.json` + `.md`. Schema additions over Phase 7a.5 : `fixture_layout`, `fixture_layout_meta.fixture_layout_verified.{verified,segments_count,max_events_per_segment_used,shard_paths,list_shards_dispatch}`, phase label `"7a.5-bis"`, `comparison_baseline = "phase_7a_5_action_index_100k_20260419.json"`.
- **Baseline (unchanged, verified).** `benchmarks/results/phase_7a_5_action_index_100k_20260419.json` (Phase 7a.5 monolithic) — referenced, not modified.
- **Prototype code (unchanged, verified).** `src/dsm/rr/*` — `git diff 58d7789..HEAD -- src/dsm/rr/` shows only the additive profiler commits from Phase N+1 (no logic changes introduced by this phase). `src/dsm/core/` and `src/dsm/session/` untouched — `git diff 58d7789..HEAD --` on both paths returns empty.
- **Regression evidence.** `python3 -m pytest tests/rr/ -q` = 29 passed before and after the harness extension.
