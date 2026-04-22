# ADR 0001 — Phase 7a.5 Root Cause Decomposition

- **Date:** 2026-04-20
- **Parent ADR:** `docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md`
- **Parent verdict:** `docs/architecture/ADR_0001_PHASE_7A_5_VERDICT.md` (FAIL)
- **Status of parent ADR:** Proposed (unchanged ; acceptance gate point 8 remains unsatisfied pending optimization decisions).
- **Prototype code SHA:** `58d7789` + additive profiler commits (`d6bcb0d`, `aff1797`). Verified `git diff 58d7789..HEAD -- src/dsm/rr/` shows only new instrumentation (+5 `with _prof.Timed(...)` blocks, 1 new module `_profiler.py`, no logic change : the bucket population, sort, and write semantics are identical to `58d7789`).
- **Purpose:** quantify the contribution of each root cause identified by Phase 7a.5, to inform the optimization plan (Phase N+1, separate prompt).
- **This phase proposes no optimization.**
- **Run artefacts:** `benchmarks/results/phase_7a_5_action_index_100k_profiled_20260419.json` + `.md`. Activation : `DSM_RR_PROFILE=1 python3 benchmarks/bench_phase_7a_action_index.py --fixture-size 100000 --output-suffix _100k_profiled`.

---

## A. Build decomposition

### A.1 Dataset A (low cardinality, 30 action_names Zipf s=1.1)

Median of 5 runs, profiler active. Source : `benchmarks/results/phase_7a_5_action_index_100k_profiled_20260419.json:datasets[0].profile_decomposition.build_sections`.

| Section | Time (ms) | % of total | Notes |
|---|---:|---:|---|
| build:clear | 0.00 | 0.0 % | five `dict.clear()` calls |
| build:list_shards | 0.17 | 0.0 % | 1 monolithic JSONL shard |
| build:scan_and_populate (total) | 10 593.80 | 71.3 % | outer shard loop |
| — build:storage_read_batch | 10 342.68 | **69.6 %** | 21 batches / run (3 batches × N pages, includes final empty batch that triggers break) |
| — build:populate_indexes | 244.42 | 1.6 % | 20 batches × inner for-loop populates 5 indexes |
| build:timeline_sort | 10.96 | 0.1 % | single O(N log N) sort on 100k records |
| build:bucket_sort_actions | 19.17 | 0.1 % | 30 bucket-local sorts ; dominated by top Zipf bucket (~15 k records) |
| build:write_files (total) | 4 209.73 | **28.3 %** | 5 index files, decomposition in § B.1 |
| **Total measured** | 14 833.83 | **99.8 %** | sum of macro sections |
| **Total (wall clock)** | 14 864.80 | 100 % | — |
| **Coverage** | | **99.8 %** | gap 0.2 % = profiler context-manager residual |

### A.2 Dataset B (high cardinality, 1 000 action_names quasi-uniform)

Source : `benchmarks/results/phase_7a_5_action_index_100k_profiled_20260419.json:datasets[1].profile_decomposition.build_sections`.

| Section | Time (ms) | % of total | Notes |
|---|---:|---:|---|
| build:clear | 0.00 | 0.0 % | |
| build:list_shards | 0.18 | 0.0 % | |
| build:scan_and_populate (total) | 10 419.14 | 72.0 % | |
| — build:storage_read_batch | 10 176.52 | **70.3 %** | 21 batches / run |
| — build:populate_indexes | 250.02 | 1.7 % | 20 batches |
| build:timeline_sort | 12.03 | 0.1 % | |
| build:bucket_sort_actions | 22.68 | 0.2 % | 1 000 bucket-local sorts (~70 records each ; per-bucket cost negligible) |
| build:write_files (total) | 4 024.17 | 27.8 % | |
| **Total measured** | 14 478.21 | **100.0 %** | |
| **Total (wall clock)** | 14 476.69 | 100 % | — |
| **Coverage** | | **100.0 %** | slight over from timer overhead being counted both inside `build:total` and inside each sub-section |

### A.3 Normalized cost (scale vs distribution separation)

Normalized metrics allow separating effects that scale with total entries (same work per entry regardless of distribution) from effects that depend on action-name distribution.

| Section | Dataset A (ms) | Dataset A (ms / 1k entries) | Dataset B (ms) | Dataset B (ms / 1k entries) |
|---|---:|---:|---:|---:|
| scan_and_populate | 10 593.80 | 105.94 | 10 419.14 | 104.19 |
| storage_read_batch | 10 342.68 | 103.43 | 10 176.52 | 101.77 |
| populate_indexes | 244.42 | 2.44 | 250.02 | 2.50 |
| timeline_sort | 10.96 | 0.11 | 12.03 | 0.12 |
| bucket_sort_actions | 19.17 | — (see below) | 22.68 | — (see below) |
| write_files (total) | 4 209.73 | 42.10 | 4 024.17 | 40.24 |

Per-bucket cost of `bucket_sort_actions` :

| Dataset | Buckets | ms / bucket (mean) | Observation |
|---|---:|---:|---|
| A (Zipf) | 30 | 0.64 | concentrated work — top bucket ~15 k records dominates the sort pass, other 29 buckets are ~O(100) each |
| B (uniform) | 1 000 | 0.023 | flat — each bucket ~70 records, sort finishes instantly |

### A.4 Cross-dataset observations

Facts from A.1–A.3 only :

- `scan_and_populate` : 105.94 ms / 1k (A) vs 104.19 ms / 1k (B) — **distribution-independent within 2 %**, consistent with per-entry work that does not depend on action-name distribution. This matches the expectation from § A.3 rationale.
- `storage_read_batch` : 103.43 ms / 1k (A) vs 101.77 ms / 1k (B) — **also distribution-independent within 2 %**. Storage reads depend on data volume, not on the semantic content of metadata. Expected.
- `storage_read_batch` absorbs **97.5 %–97.7 %** of `scan_and_populate` on both datasets. `populate_indexes` — the per-entry index-appending work — is only **2.3 %–2.4 %** of its parent. The bottleneck in the scan phase is **reading from storage**, not populating indexes.
- `populate_indexes` : 2.44 ms / 1k (A) vs 2.50 ms / 1k (B). The extra action_name-index work imposed on Dataset A (fewer but larger buckets) is within noise of Dataset B. Per-entry index-population is dominated by the 4 cross-cutting indexes (session / agent / timeline / shard) that both datasets pay in full.
- `bucket_sort_actions` : **concentrated-vs-flat asymmetry is visible** — 0.64 ms/bucket (A) vs 0.023 ms/bucket (B), a ~28× per-bucket ratio. Consistent with Zipf concentration (top bucket ~15k records → O(15k log 15k) ≈ 210k ops ; B's uniform buckets are ~70 records → O(70 log 70) ≈ 430 ops). However the absolute cost on both datasets is negligible (< 0.2 % of build total) so this does not drive gate (iii).
- `write_files` : 42.10 ms / 1k (A) vs 40.24 ms / 1k (B) — **also distribution-independent within 5 %**. Per § B, serialization cost is driven by payload size, not by structure.
- **Timeline_sort is negligible** at 0.1 % of build, despite being the single most-named suspect in classical database literature. It is not a scaling bottleneck here.

**The decomposition locates 99.8 %+ of build time in two macro sections : `scan_and_populate` (71–72 %) and `write_files` (27–28 %). All other instrumented sections combined are < 0.5 %.**

---

## B. Serialization decomposition (`_write_index_files`)

### B.1 Dataset A

Source : `benchmarks/results/phase_7a_5_action_index_100k_profiled_20260419.json:datasets[0].profile_decomposition.build_sections`, keys `write:<name>:*`. `file_io` is derived as `total − json_dump`.

| Index file | json_dump (ms) | file_io (ms, derived) | replace (ms) | total (ms) | % of write_files |
|---|---:|---:|---:|---:|---:|
| sessions.idx | 911.91 | 0.79 | 0.18 | 912.70 | 21.7 % |
| agents.idx | 880.64 | 0.77 | 0.22 | 881.41 | 20.9 % |
| timeline.idx | 812.64 | 0.63 | 0.19 | 813.27 | 19.3 % |
| shards.idx | 876.62 | 0.87 | 0.20 | 877.49 | 20.8 % |
| actions.idx | 643.80 | 1.14 | 0.21 | 644.94 | 15.3 % |
| **Total** | 4 125.61 | 4.20 | 1.00 | 4 129.82 | 98.1 % |

Sum of per-file `total_ms` = 4 129.82 vs outer `write_files.median_ms` = 4 209.73. Discrepancy = **79.91 ms / 1.9 %**, within the ±5 % rule of § 1.2. The 79.91 ms residual is the `mkstemp` + `os.fdopen` context entry/exit overhead plus the per-file Python loop overhead ; it is **not** hidden double-count.

### B.2 Dataset B

Source : same JSON, `datasets[1]`.

| Index file | json_dump (ms) | file_io (ms, derived) | replace (ms) | total (ms) | % of write_files |
|---|---:|---:|---:|---:|---:|
| sessions.idx | 890.35 | 0.83 | 0.22 | 891.18 | 22.1 % |
| agents.idx | 861.22 | 0.72 | 0.21 | 861.94 | 21.4 % |
| timeline.idx | 783.34 | 0.64 | 0.21 | 783.98 | 19.5 % |
| shards.idx | 855.56 | 0.69 | 0.20 | 856.26 | 21.3 % |
| actions.idx | 629.09 | 0.71 | 0.22 | 629.79 | 15.7 % |
| **Total** | 4 019.57 | 3.59 | 1.06 | 4 023.16 | 100.0 % |

Sum of per-file `total_ms` = 4 023.16 vs outer `write_files.median_ms` = 4 024.17. Discrepancy = **1.01 ms / 0.03 %**, well under the ±5 % rule.

### B.3 JSON serialization vs file I/O ratio

Across both datasets :

- `json_dump` represents **99.9 % of per-file total** (4 125.61 / 4 129.82 on A ; 4 019.57 / 4 023.16 on B).
- `file_io` (`mkstemp + fdopen + close + replace`) represents **0.1 % of per-file total** (4.20 ms on A ; 3.59 ms on B).
- `os.replace` alone (atomic rename) represents **0.02 %** (~1 ms total across 5 files).

The dominant cost within `write_files` is **json_dump**. File I/O proper — file creation, descriptor open/close, atomic rename — is negligible.

**Measured fact.** The `indent=2` setting is currently used in `json.dump` at `src/dsm/rr/index/rr_index_builder.py:255`. Removing the `indent=2` argument would only affect `json_dump` time — serialization output size would shrink (~3–4× fewer bytes on disk for structured records), and `json.dump`'s walk of the object graph would be faster. It would not affect `file_io`, which is already negligible.

**Upper bound of `indent=2` removal win** :
- `json_dump` contributes 99.9 % of per-file total ;
- per-file total sums to 98.1 % (A) / 100.0 % (B) of `write_files` ;
- `write_files` contributes 28.3 % (A) / 27.8 % (B) of total build.
- Upper bound of removing `indent=2` entirely = 0.999 × 0.981 × 0.283 = **27.7 % of total build time** (A) ; same calc for B = **27.8 %**.

This is an upper bound because removing `indent=2` does not eliminate `json_dump` — it reduces it. The realized win would be some fraction of 27.7 %, not the full number. Phase 7a.5 measured the absolute ratio at 13.48× (A) / 12.11× (B) ; an optimization that shaves 10–20 % of total build would bring absolute ratio to ~11× (A) / ~10× (B), still above or at the gate (iii) threshold.

**This report does not propose removing `indent=2`.** It bounds the possible win so Phase N+1 can decide whether that optimization alone closes gate (iii) — the answer from the numbers above is **no, not alone**.

---

## C. Query decomposition

Per-variant, 100 samples after 5 warmup, profiler active. Source : `benchmarks/results/phase_7a_5_action_index_100k_profiled_20260419.json:datasets[*].profile_decomposition.query_decompositions.<variant>`.

Denominator for coverage is `query_actions:total` (the inner timer wrapping the whole `query_actions` method body). The wall-clock `query_total_median_ms` at the top of each variant includes additional lambda + function-call + profiler overhead of ~15–25 µs per call ; the decomposition below is relative to the inner `query_actions:total` to remain internally consistent.

### C.1 Dataset A — Query top

| Step | median (µs) | p95 (µs) | max (µs) | % of query_actions:total |
|---|---:|---:|---:|---:|
| nav:action:bucket_lookup | 0.208 | 0.250 | 1.250 | 0.5 % |
| nav:action:list_copy | 30.021 | 39.750 | 114.792 | **69.1 %** |
| query_actions:slice_or_filter | 11.334 | 11.959 | 113.250 | 26.1 % |
| **query_actions:total** (inner) | 43.459 | 54.875 | 229.125 | — |
| Sum of steps | 41.56 | — | — | **95.6 %** coverage |
| Wall-clock query_total | 67.334 | — | — | — |

Row count match with SessionIndex : 100 / 100 (both reach limit).

### C.2 Dataset A — Query rare

| Step | median (µs) | p95 (µs) | max (µs) | % of query_actions:total |
|---|---:|---:|---:|---:|
| nav:action:bucket_lookup | 0.167 | 0.209 | 0.500 | 1.2 % |
| nav:action:list_copy | 0.541 | 0.542 | 0.750 | 4.0 % |
| query_actions:slice_or_filter | 11.208 | 11.583 | 18.500 | 83.2 % |
| **query_actions:total** | 13.479 | 14.084 | 21.417 | — |
| Sum of steps | 11.92 | — | — | 88.4 % coverage |

Row count match : 100 / 100 (rare bucket still has > 100 records even on Zipf — rare = 90th-percentile rank, not 100th).

### C.3 Dataset A — Query C1 (action + session)

| Step | median (µs) | p95 (µs) | max (µs) | % of query_actions:total |
|---|---:|---:|---:|---:|
| nav:action:bucket_lookup | 0.833 | 1.500 | 92.042 | 0.0 % |
| nav:action:list_copy | 27.083 | 45.333 | 95.167 | 0.4 % |
| query_actions:slice_or_filter | 6 711.833 | 8 953.209 | 10 204.542 | 99.3 % |
| **query_actions:total** | 6 762.124 | 8 983.750 | 10 341.750 | — |
| Sum of steps | 6 739.75 | — | — | 99.7 % coverage |

The session filter on the top Zipf bucket (~15k records) never early-exits at `limit=100` because only 14 matches exist ; the loop scans the full bucket.

### C.4 Dataset A — Query C2 (action + time)

| Step | median (µs) | p95 (µs) | max (µs) | % of query_actions:total |
|---|---:|---:|---:|---:|
| nav:action:bucket_lookup | 0.250 | 0.875 | 8.625 | 0.0 % |
| nav:action:list_copy | 26.938 | 41.667 | 109.417 | 4.5 % |
| query_actions:slice_or_filter | 573.187 | 2 397.958 | 3 252.208 | 95.0 % |
| **query_actions:total** | 603.334 | 2 469.084 | 3 445.917 | — |
| Sum of steps | 600.38 | — | — | 99.5 % coverage |

### C.5 Dataset B — Query top

| Step | median (µs) | p95 (µs) | max (µs) | % of query_actions:total |
|---|---:|---:|---:|---:|
| nav:action:bucket_lookup | 0.167 | 0.209 | 0.459 | 1.3 % |
| nav:action:list_copy | 0.250 | 0.334 | 0.750 | 1.9 % |
| query_actions:slice_or_filter | 10.959 | 11.959 | 18.459 | 83.9 % |
| **query_actions:total** | 13.062 | 14.875 | 21.917 | — |
| Sum of steps | 11.38 | — | — | 87.1 % coverage |

### C.6 Dataset B — Query rare

| Step | median (µs) | p95 (µs) | max (µs) | % of query_actions:total |
|---|---:|---:|---:|---:|
| nav:action:bucket_lookup | 0.167 | 0.209 | 0.250 | 1.9 % |
| nav:action:list_copy | 0.208 | 0.250 | 0.667 | 2.3 % |
| query_actions:slice_or_filter | 7.000 | 7.250 | 8.500 | 78.1 % |
| **query_actions:total** | 8.958 | 10.708 | 14.250 | — |
| Sum of steps | 7.38 | — | — | 82.3 % coverage |

### C.7 Dataset B — Query C1

| Step | median (µs) | p95 (µs) | max (µs) | % of query_actions:total |
|---|---:|---:|---:|---:|
| nav:action:bucket_lookup | 0.167 | 0.250 | 0.375 | 2.4 % |
| nav:action:list_copy | 0.250 | 0.333 | 0.417 | 3.5 % |
| query_actions:slice_or_filter | 5.083 | 5.167 | 6.500 | 72.2 % |
| **query_actions:total** | 7.042 | 9.000 | 10.458 | — |
| Sum of steps | 5.50 | — | — | 78.1 % coverage |

### C.8 Dataset B — Query C2

| Step | median (µs) | p95 (µs) | max (µs) | % of query_actions:total |
|---|---:|---:|---:|---:|
| nav:action:bucket_lookup | 0.167 | 0.209 | 0.292 | 1.2 % |
| nav:action:list_copy | 0.250 | 0.333 | 0.833 | 1.8 % |
| query_actions:slice_or_filter | 10.750 | 11.167 | 14.083 | 79.4 % |
| **query_actions:total** | 13.542 | 14.458 | 17.583 | — |
| Sum of steps | 11.17 | — | — | 82.5 % coverage |

### C.9 Quantification of the root cause #1 (`list(records)`)

Based on § C.1 : **`list_copy` contributes 69.1 % of `query_actions:total`** on Dataset A, top variant.

This is the query variant where Phase 7a.5 measured the worst gate (ii) ratio (2.27× SessionIndex). Applying the decision rule stated in the prompt :

> If `list_copy` > 50 % of query_total : **this is the dominant root cause for the top-query failure.**

The measured 69.1 % exceeds the 50 % threshold. The `navigate_action` copy pattern at `src/dsm/rr/navigator/rr_navigator.py:140–141` (`records = index.get(...)` → `return list(records)`) is the dominant root cause of the Dataset A top-query gate failure. The naming in the Phase 7a.5 verdict is confirmed quantitatively — not just directionally correct, but quantitatively dominant.

Gate (ii) on Dataset A, C1 variant shows `slice_or_filter` at 99.3 % of `query_actions:total` — but **this variant PASSES gate (ii)** (ratio 0.57× ≤ 1.5×), so it is not a gate-failure contributor. Same for C2 (95.0 % in slice_or_filter, passes gate at 0.23×). The slice_or_filter cost on combined queries is structurally driven by bucket scanning on large Zipf buckets ; it is descriptive (§ C.3, § C.4) but does not enter the § D ranking because it is not mapped to a failed gate.

---

## D. Ranked root cause contributors

Ranking rule (from the prompt) :
- a contributor enters the table **only if** (i) its measured contribution is ≥ 10 % of total build or query, OR (ii) it is directly responsible for a failed gate (explicit mapping).
- each ranked contributor must cite at least one failed gate.

Failed gates in Phase 7a.5 :
- **Gate (i)** delta_build ≤ 1× SessionIndex — fails on Dataset A only (1.23× observed).
- **Gate (ii) top variant** latency ≤ 1.5× SessionIndex — fails on Dataset A only (2.27×).
- **Gate (iii)** absolute build ≤ 10× SessionIndex — fails on both datasets (13.48× A / 12.11× B).

| Rank | Root cause | Gate affected | Dataset(s) | Measured contribution | Upper bound of fix win |
|---|---|---|---|---:|---|
| 1 | `storage_read_batch` — paginated `Storage.read(offset=K, limit=batch_size)` calls (21 calls / run) via `src/dsm/rr/index/rr_index_builder.py:164` (`_read_batch`) | (iii) | A, B | **69.6 % (A) / 70.3 % (B)** of total build | up to **~70 %** if storage access were free ; realistic fraction unknown without re-implementation. Kernel-level question : `src/dsm/core/storage.py:128` `Storage.read` behaviour under non-zero `offset`. |
| 2 | `write_files:json_dump` — per-file JSON serialization with `indent=2` at `src/dsm/rr/index/rr_index_builder.py:255` (5 index files per build) | (iii) | A, B | **27.8 % (A) / 27.7 % (B)** of total build | up to **~27.8 %** of build if `json_dump` disappeared entirely (it cannot) ; bounded by removing `indent=2` alone, which is a fraction of that 27.8 % (size reduction ~3–4×, time reduction likely 50–80 % of `json_dump` = ~14–22 % of total build) |
| 3 | `nav:action:list_copy` — `list(records)` copy of full bucket at `src/dsm/rr/navigator/rr_navigator.py:141` | (ii) top | A | **69.1 %** of `query_actions:total` on top variant | up to **~69 %** of query latency on Dataset A top if copy were eliminated ; realistic fraction depends on whether the copy can be replaced by a reference hand-off without breaking the API contract |

Cumulative contribution of top 2 (gate iii contributors) : **97.4 % (A) / 98.0 % (B)** of total build. The gate (iii) FAIL magnitude is almost entirely explained by these two contributors.

Cumulative contribution for gate (ii) top on Dataset A : `list_copy` alone covers 69.1 % of the `query_actions:total` that Phase 7a.5 measured as 2.27× SessionIndex. The remaining 30.9 % is split between `slice_or_filter` (26.1 %) and measurement residual (4.8 %).

**Gate (i) — Dataset A only — is not cleanly explained by a single ranked cause.** Decomposition of the difference `RR_with_action − RR_baseline` across the 5-run medians yields a structural expected delta of ~700 ms (extra actions.idx write 644.94 ms + bucket_sort 19.17 ms + marginal populate_indexes extra ~50 ms for per-entry action_index appending). Observed delta is 1 380.25 ms on Dataset A vs 693.90 ms on Dataset B ; Dataset B matches the ~700 ms structural prediction, Dataset A has an extra ~700 ms not accounted for by any measured section individually. This residual is consistent with run-to-run variance in the subtraction of two large similar-magnitude medians (14 s each). **No single root cause is measured as dominant for gate (i)**, so gate (i) does not have a ranked contributor in this table — it is listed here in narrative form for honesty. The gate is real ; the root cause is not isolated by the current instrumentation.

---

## E. Unmeasured / hypothetical zones

Items named or considered but **not** quantified in this phase :

- **Internal behaviour of `Storage.read(offset=K, limit=N)` at `src/dsm/core/storage.py:128`.** The rank-1 ranked contributor (`storage_read_batch`, 70 % of build) is a single measurement around the `_read_batch` call, not a decomposition of *inside* `Storage.read`. Whether that call seeks O(1), scans the file from offset 0 to `offset`, or caches partial reads — not measured. The kernel is frozen, so instrumenting it is out of scope here. **Status : hypothesis that `Storage.read` has O(offset) cost is consistent with the per-batch scaling observed (65 ms / batch at 10k vs ~492 ms / batch at 100k on same batch_size), but this has not been confirmed by direct instrumentation of `Storage.read`.** Required for future work : a kernel-side measurement phase with its own ADR and its own gate, or a non-paginated read pattern benchmark.
- **Python GC pauses during build.** GC activity at 100 k records × 4 dicts × 70 k list appends is plausibly non-trivial, but not measured. Would require `gc` module instrumentation. Not done.
- **disk flush / fsync contribution.** `os.fdopen(..., "w")` context close flushes to kernel buffer ; `os.replace` triggers directory entry update. Neither is the same as `fsync`. A true fsync would add disk-round-trip time not captured here. The measured `file_io` of ~1 ms per file excludes explicit fsync because the code does not call it. **Status : out of scope ; the prototype does not fsync.**
- **Run-to-run variance on gate (i) Dataset A.** The 700 ms unexplained residual between Dataset A's observed delta (1 380 ms) and structural-prediction delta (~700 ms) is not measured — it is inferred as "run-to-run variance of subtraction of similar-magnitude medians" but not confirmed by distribution analysis. A histogram of the 5 individual build times would help ; 5 samples is too few for a robust distribution claim.
- **`RRIndexBuilder.build()` profiler overhead itself.** The ~0.2–0.4 % coverage excess on total build (sum of macro sections > wall-clock by that amount) is attributable to profiler context-manager overhead being double-counted inside `build:total` and its children. Not individually measured ; accepted as a sub-1 % residual.
- **`query_actions:total` wall-clock overhead.** Wall-clock measured at 67 µs (Dataset A top) vs `query_actions:total` inner timer at 43 µs — the 24 µs gap includes lambda dispatch, the `_time_call` wrapper, and residual profiler overhead. Not individually decomposed ; the § C tables use the inner timer as denominator to keep the decomposition internally consistent.

If the list were empty, I would say "no unmeasured zones". The list is not empty ; the biggest unmeasured item is the internal behaviour of `Storage.read(offset=K)` which is kernel-frozen and would require its own measurement phase.

---

## F. Coverage summary

- Build decomposition coverage :
  - Dataset A : 99.8 % (§ A.1) — no `unattributed` bucket needed (gap ≤ 2 %).
  - Dataset B : 100.0 % (§ A.2) — slight over from timer overhead being counted in both `build:total` and sub-sections ; acceptable residual.
  - Per-file write_files sum vs outer `write_files` timer : 98.1 % (A), 100.0 % (B) — within ±5 % rule.
- Query decomposition coverage (sum of sub-steps / `query_actions:total`) :
  - Dataset A : 95.6 % (top), 88.4 % (rare), 99.7 % (C1), 99.5 % (C2).
  - Dataset B : 87.1 % (top), 82.3 % (rare), 78.1 % (C1), 82.5 % (C2).
  - Queries at the lowest coverage (Dataset B, C1 at 78.1 %) — the 21.9 % unattributed is the `_coerce_to_numeric` ISO-string parsing (not individually timed, § 1.3 rule) + Python method call dispatch + profiler residual. At absolute times of ~5–10 µs per query, the 22 % gap is ~1–2 µs, consistent with per-call dispatch overhead on a very short query path. **No hidden section is suspected.**
- All coverage values are ≥ 78.1 % ; the prompt's target is > 98 %. **Build decomposition meets the target.** Query decomposition falls short for Dataset B variants because the absolute query times are ≤ 15 µs each, where the fixed overhead of profiler context-managers and Python dispatch becomes a measurable fraction. Adding instrumentation to close the remaining 10–22 % would require timing inside the method prologue (`_coerce_to_numeric`, list initialisation), which approaches the forbidden "tight loop" granularity per the § 1.4 rule.

Decision recorded : the query sub-98 % coverage on Dataset B is **accepted as the lower bound of what coarse-grained instrumentation can produce at this query-time scale**. Documented hypothesis for the gap : **Python method-call dispatch + argument coercion + profiler context-manager entry/exit overhead**. The gap is not attributable to any single named subsection.

---

## G. Constraints satisfied

- [x] **No logic change in `src/dsm/rr/`.** Verified by inspection : `git diff 58d7789..HEAD -- src/dsm/rr/` shows only (a) a new file `src/dsm/rr/_profiler.py`, (b) new `with _prof.Timed(...)` context-manager blocks wrapping existing code, and (c) one new kwarg `enable_action_index` in `RRIndexBuilder.__init__` (which was already present in commit `a693429` as part of Phase 7a, and is unchanged in this phase). No bucket population rule, no sort rule, no JSON serialization call, no atomic-rename call was modified.
- [x] **`tests/rr/ -q` remains green with profiling off.** 29 passed.
- [x] **`tests/rr/ -q` remains green with profiling on** (`DSM_RR_PROFILE=1 python3 -m pytest tests/rr/ -q`). 29 passed.
- [x] **No optimization proposed in this document.** Sections D and B.3 bound possible fix wins ; they do not propose fixes. Section E lists unmeasured zones ; it does not propose fixes.
- [x] **No dependency added.** Profiler uses only `os`, `time`, and stdlib types.
- [x] **No kernel modification.** `src/dsm/core/` untouched ; verified by `git diff 58d7789..HEAD -- src/dsm/core/` returning empty.
- [x] **SessionIndex intact.** `git diff 58d7789..HEAD -- src/dsm/session/` returning empty.
- [x] **ADR 0001 still `Proposed`.**
- [x] **SessionIndex classification still `duplicative`.**

---

*This report quantifies the root causes of the Phase 7a.5 FAIL verdict. It proposes no optimization. The optimization plan (Phase N+1) will consume sections D and B.3 as inputs, and must explicitly scope any optimization either to a measured contributor (§ D) or to one of the unmeasured zones (§ E) after quantifying that zone in a separate preceding phase.*
