# Phase 7a.5 benchmark — RR action_name index vs SessionIndex

- Run timestamp (UTC): 2026-04-19T20:40:32.300758+00:00
- Prototype branch: proto/phase-7a-rr-action-name-index
- Commit SHA: 5af3d5f1833a22f4b27cd69128a47b1e59bf18a6
- Python: 3.10.20
- Platform: macOS-26.3.1-arm64-arm-64bit
- Fixture size per dataset: 100,000 entries
- Comparison baseline: `phase_7a_action_index_20260419.json`

**Overall verdict: FAIL**

## Dataset A_low_card_zipf

- 100,000 entries, 5,000 sessions, 30 action_names Zipf s=1.1
- Distribution: zipf; seed: 42
- Distinct action_names observed: 30
- Top action: `action_0000`  ·  Rare action: `action_0027`

### Build

| Metric | median (ms) | p95 (ms) | max (ms) | vs SessionIndex | Gate | Pass |
|---|---:|---:|---:|---|---|---|
| SessionIndex_build | 1121.47 | 1204.09 | 1204.09 | 1.00× | — | — |
| RR_baseline_build | 13739.94 | 13970.80 | 13970.80 | 12.25× | — | — |
| RR_with_action_build | 15120.19 | 17552.21 | 17552.21 | 13.48× | — | — |
| **delta_build = RR_with - RR_baseline** | 1380.25 | — | — | 1.23× | ≤ 1× | ❌ |
| RR_with_action absolute | — | — | — | 13.48× | ≤ 3× (info) | operational flag (>3×) |

### Queries

| Variant | SI median (ms) | RR median (ms) | RR p95 (ms) | RR max (ms) | ratio | Gate | Pass | SI rows | RR rows |
|---|---:|---:|---:|---:|---|---|---|---:|---:|
| top | 0.0275 | 0.0622 | 0.0818 | 0.2032 | 2.27× | ≤ 1.5× | ❌ | 100 | 100 |
| rare | 0.6517 | 0.0128 | 0.0152 | 0.0820 | 0.02× | ≤ 1.5× | ✅ | 100 | 100 |
| C1 (action+session) | 12.1998 | 6.9843 | 8.8703 | 9.2191 | 0.57× | ≤ 1.5× | ✅ | 14 | 14 |
| C2 (action+time) | 4.2029 | 0.9471 | 2.4639 | 4.0406 | 0.23× | ≤ 1.5× | ✅ | 100 | 100 |

**Dataset A_low_card_zipf verdict: FAIL**

## Dataset B_high_card_uniform

- 100,000 entries, 5,000 sessions, 1000 action_names quasi-uniform
- Distribution: uniform; seed: 43
- Distinct action_names observed: 1000
- Top action: `action_0060`  ·  Rare action: `action_0615`

### Build

| Metric | median (ms) | p95 (ms) | max (ms) | vs SessionIndex | Gate | Pass |
|---|---:|---:|---:|---|---|---|
| SessionIndex_build | 1227.71 | 1443.18 | 1443.18 | 1.00× | — | — |
| RR_baseline_build | 14176.17 | 14649.70 | 14649.70 | 11.55× | — | — |
| RR_with_action_build | 14870.08 | 14897.33 | 14897.33 | 12.11× | — | — |
| **delta_build = RR_with - RR_baseline** | 693.90 | — | — | 0.57× | ≤ 1× | ✅ |
| RR_with_action absolute | — | — | — | 12.11× | ≤ 3× (info) | operational flag (>3×) |

### Queries

| Variant | SI median (ms) | RR median (ms) | RR p95 (ms) | RR max (ms) | ratio | Gate | Pass | SI rows | RR rows |
|---|---:|---:|---:|---:|---|---|---|---:|---:|
| top | 11.0697 | 0.0120 | 0.0712 | 0.1932 | 0.00× | ≤ 1.5× | ✅ | 97 | 97 |
| rare | 11.5482 | 0.0075 | 0.0480 | 0.5612 | 0.00× | ≤ 1.5× | ✅ | 60 | 60 |
| C1 (action+session) | 11.2448 | 0.0057 | 0.0274 | 0.0780 | 0.00× | ≤ 1.5× | ✅ | 2 | 2 |
| C2 (action+time) | 11.0793 | 0.0119 | 0.0159 | 0.0171 | 0.00× | ≤ 1.5× | ✅ | 35 | 35 |

**Dataset B_high_card_uniform verdict: FAIL**
