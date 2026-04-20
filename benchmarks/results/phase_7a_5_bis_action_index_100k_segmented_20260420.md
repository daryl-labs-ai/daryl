# Phase 7a.5-bis benchmark — RR action_name index vs SessionIndex

- Run timestamp (UTC): 2026-04-20T16:22:55.639635+00:00
- Prototype branch: proto/phase-7a-rr-action-name-index
- Commit SHA: 0017894090c5014b5450f95ec958142187cb57f7
- Python: 3.10.20
- Platform: macOS-26.3.1-arm64-arm-64bit
- Fixture size per dataset: 100,000 entries
- Comparison baseline: `phase_7a_5_action_index_100k_20260419.json`

**Overall verdict: FAIL**

## Dataset A_low_card_zipf

- 100,000 entries, 5,000 sessions, 30 action_names Zipf s=1.1
- Distribution: zipf; seed: 42
- Distinct action_names observed: 30
- Top action: `action_0000`  ·  Rare action: `action_0027`

### Build

| Metric | median (ms) | p95 (ms) | max (ms) | vs SessionIndex | Gate | Pass |
|---|---:|---:|---:|---|---|---|
| SessionIndex_build | 1017.30 | 1054.90 | 1054.90 | 1.00× | — | — |
| RR_baseline_build | 6612.58 | 6663.65 | 6663.65 | 6.50× | — | — |
| RR_with_action_build | 7291.13 | 8741.91 | 8741.91 | 7.17× | — | — |
| **delta_build = RR_with - RR_baseline** | 678.56 | — | — | 0.67× | ≤ 1× | ✅ |
| RR_with_action absolute | — | — | — | 7.17× | ≤ 3× (info) | operational flag (>3×) |

### Queries

| Variant | SI median (ms) | RR median (ms) | RR p95 (ms) | RR max (ms) | ratio | Gate | Pass | SI rows | RR rows |
|---|---:|---:|---:|---:|---|---|---|---:|---:|
| top | 0.0245 | 0.0586 | 0.0753 | 0.1070 | 2.39× | ≤ 1.5× | ❌ | 100 | 100 |
| rare | 0.4984 | 0.0137 | 0.0138 | 0.0168 | 0.03× | ≤ 1.5× | ✅ | 100 | 100 |
| C1 (action+session) | 9.9933 | 3.7056 | 5.6322 | 6.1475 | 0.37× | ≤ 1.5× | ✅ | 14 | 14 |
| C2 (action+time) | 2.1096 | 0.5266 | 1.0535 | 2.7952 | 0.25× | ≤ 1.5× | ✅ | 100 | 100 |

**Dataset A_low_card_zipf verdict: FAIL**

## Dataset B_high_card_uniform

- 100,000 entries, 5,000 sessions, 1000 action_names quasi-uniform
- Distribution: uniform; seed: 43
- Distinct action_names observed: 1000
- Top action: `action_0060`  ·  Rare action: `action_0615`

### Build

| Metric | median (ms) | p95 (ms) | max (ms) | vs SessionIndex | Gate | Pass |
|---|---:|---:|---:|---|---|---|
| SessionIndex_build | 1030.75 | 1080.80 | 1080.80 | 1.00× | — | — |
| RR_baseline_build | 6568.17 | 6604.10 | 6604.10 | 6.37× | — | — |
| RR_with_action_build | 7194.10 | 7362.30 | 7362.30 | 6.98× | — | — |
| **delta_build = RR_with - RR_baseline** | 625.93 | — | — | 0.61× | ≤ 1× | ✅ |
| RR_with_action absolute | — | — | — | 6.98× | ≤ 3× (info) | operational flag (>3×) |

### Queries

| Variant | SI median (ms) | RR median (ms) | RR p95 (ms) | RR max (ms) | ratio | Gate | Pass | SI rows | RR rows |
|---|---:|---:|---:|---:|---|---|---|---:|---:|
| top | 8.3556 | 0.0126 | 0.0129 | 0.0162 | 0.00× | ≤ 1.5× | ✅ | 97 | 97 |
| rare | 8.3069 | 0.0083 | 0.0085 | 0.0179 | 0.00× | ≤ 1.5× | ✅ | 60 | 60 |
| C1 (action+session) | 8.3138 | 0.0068 | 0.0072 | 0.0395 | 0.00× | ≤ 1.5× | ✅ | 2 | 2 |
| C2 (action+time) | 8.3214 | 0.0131 | 0.0132 | 0.0135 | 0.00× | ≤ 1.5× | ✅ | 35 | 35 |

**Dataset B_high_card_uniform verdict: PASS**
