# Phase 7a.5 benchmark — RR action_name index vs SessionIndex

- Run timestamp (UTC): 2026-04-19T22:12:05.353073+00:00
- Prototype branch: proto/phase-7a-rr-action-name-index
- Commit SHA: d6bcb0d3e37a4cb14a2d4befbd4cc3ba5e31b43a
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
| SessionIndex_build | 1137.63 | 1208.83 | 1208.83 | 1.00× | — | — |
| RR_baseline_build | 13859.57 | 14082.05 | 14082.05 | 12.18× | — | — |
| RR_with_action_build | 14915.68 | 15382.07 | 15382.07 | 13.11× | — | — |
| **delta_build = RR_with - RR_baseline** | 1056.11 | — | — | 0.93× | ≤ 1× | ✅ |
| RR_with_action absolute | — | — | — | 13.11× | ≤ 3× (info) | operational flag (>3×) |

### Queries

| Variant | SI median (ms) | RR median (ms) | RR p95 (ms) | RR max (ms) | ratio | Gate | Pass | SI rows | RR rows |
|---|---:|---:|---:|---:|---|---|---|---:|---:|
| top | 0.0254 | 0.0673 | 0.0786 | 0.1434 | 2.65× | ≤ 1.5× | ❌ | 100 | 100 |
| rare | 0.6169 | 0.0146 | 0.0152 | 0.0156 | 0.02× | ≤ 1.5× | ✅ | 100 | 100 |
| C1 (action+session) | 12.3474 | 6.8954 | 9.1178 | 10.3429 | 0.56× | ≤ 1.5× | ✅ | 14 | 14 |
| C2 (action+time) | 3.7471 | 0.6389 | 2.6699 | 4.0542 | 0.17× | ≤ 1.5× | ✅ | 100 | 100 |

**Dataset A_low_card_zipf verdict: FAIL**

## Dataset B_high_card_uniform

- 100,000 entries, 5,000 sessions, 1000 action_names quasi-uniform
- Distribution: uniform; seed: 43
- Distinct action_names observed: 1000
- Top action: `action_0060`  ·  Rare action: `action_0615`

### Build

| Metric | median (ms) | p95 (ms) | max (ms) | vs SessionIndex | Gate | Pass |
|---|---:|---:|---:|---|---|---|
| SessionIndex_build | 1202.85 | 1378.37 | 1378.37 | 1.00× | — | — |
| RR_baseline_build | 14098.18 | 14347.95 | 14347.95 | 11.72× | — | — |
| RR_with_action_build | 14533.73 | 14614.34 | 14614.34 | 12.08× | — | — |
| **delta_build = RR_with - RR_baseline** | 435.55 | — | — | 0.36× | ≤ 1× | ✅ |
| RR_with_action absolute | — | — | — | 12.08× | ≤ 3× (info) | operational flag (>3×) |

### Queries

| Variant | SI median (ms) | RR median (ms) | RR p95 (ms) | RR max (ms) | ratio | Gate | Pass | SI rows | RR rows |
|---|---:|---:|---:|---:|---|---|---|---:|---:|
| top | 10.8634 | 0.0139 | 0.0163 | 0.0736 | 0.00× | ≤ 1.5× | ✅ | 97 | 97 |
| rare | 10.6206 | 0.0096 | 0.0118 | 0.0448 | 0.00× | ≤ 1.5× | ✅ | 60 | 60 |
| C1 (action+session) | 10.7727 | 0.0078 | 0.0102 | 0.0276 | 0.00× | ≤ 1.5× | ✅ | 2 | 2 |
| C2 (action+time) | 10.6181 | 0.0143 | 0.0155 | 0.0468 | 0.00× | ≤ 1.5× | ✅ | 35 | 35 |

**Dataset B_high_card_uniform verdict: FAIL**
