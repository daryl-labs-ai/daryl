# Phase 7a.5-bis benchmark — RR action_name index vs SessionIndex

- Run timestamp (UTC): 2026-04-20T17:01:55.006501+00:00
- Prototype branch: proto/phase-7a-rr-action-name-index
- Commit SHA: fb5343c4a36853dc23d418b520a727200d6b493a
- Python: 3.10.20
- Platform: macOS-26.3.1-arm64-arm-64bit
- Fixture size per dataset: 100,000 entries
- Comparison baseline: `phase_7a_5_action_index_100k_20260419.json`

**Overall verdict: PASS**

## Dataset A_low_card_zipf

- 100,000 entries, 5,000 sessions, 30 action_names Zipf s=1.1
- Distribution: zipf; seed: 42
- Distinct action_names observed: 30
- Top action: `action_0000`  ·  Rare action: `action_0027`

### Build

| Metric | median (ms) | p95 (ms) | max (ms) | vs SessionIndex | Gate | Pass |
|---|---:|---:|---:|---|---|---|
| SessionIndex_build | 1278.02 | 1333.36 | 1333.36 | 1.00× | — | — |
| RR_baseline_build | 7453.79 | 7724.96 | 7724.96 | 5.83× | — | — |
| RR_with_action_build | 7581.31 | 7658.09 | 7658.09 | 5.93× | — | — |
| **delta_build = RR_with - RR_baseline** | 127.53 | — | — | 0.10× | ≤ 1× | ✅ |
| RR_with_action absolute | — | — | — | 5.93× | ≤ 3× (info) | operational flag (>3×) |

### Queries

| Variant | SI median (ms) | RR median (ms) | RR p95 (ms) | RR max (ms) | ratio | Gate | Pass | SI rows | RR rows |
|---|---:|---:|---:|---:|---|---|---|---:|---:|
| top | 0.0241 | 0.0131 | 0.0173 | 0.0311 | 0.54× | ≤ 1.5× | ✅ | 100 | 100 |
| rare | 0.5884 | 0.0132 | 0.0136 | 0.0241 | 0.02× | ≤ 1.5× | ✅ | 100 | 100 |
| C1 (action+session) | 11.5291 | 5.6302 | 7.8054 | 8.0388 | 0.49× | ≤ 1.5× | ✅ | 14 | 14 |
| C2 (action+time) | 3.1300 | 0.5720 | 2.1522 | 3.6940 | 0.18× | ≤ 1.5× | ✅ | 100 | 100 |

**Dataset A_low_card_zipf verdict: PASS**

## Dataset B_high_card_uniform

- 100,000 entries, 5,000 sessions, 1000 action_names quasi-uniform
- Distribution: uniform; seed: 43
- Distinct action_names observed: 1000
- Top action: `action_0060`  ·  Rare action: `action_0615`

### Build

| Metric | median (ms) | p95 (ms) | max (ms) | vs SessionIndex | Gate | Pass |
|---|---:|---:|---:|---|---|---|
| SessionIndex_build | 1091.97 | 1190.55 | 1190.55 | 1.00× | — | — |
| RR_baseline_build | 6664.69 | 6785.85 | 6785.85 | 6.10× | — | — |
| RR_with_action_build | 7413.19 | 7570.35 | 7570.35 | 6.79× | — | — |
| **delta_build = RR_with - RR_baseline** | 748.49 | — | — | 0.69× | ≤ 1× | ✅ |
| RR_with_action absolute | — | — | — | 6.79× | ≤ 3× (info) | operational flag (>3×) |

### Queries

| Variant | SI median (ms) | RR median (ms) | RR p95 (ms) | RR max (ms) | ratio | Gate | Pass | SI rows | RR rows |
|---|---:|---:|---:|---:|---|---|---|---:|---:|
| top | 8.8478 | 0.0129 | 0.0134 | 0.0139 | 0.00× | ≤ 1.5× | ✅ | 97 | 97 |
| rare | 8.2907 | 0.0085 | 0.0086 | 0.0088 | 0.00× | ≤ 1.5× | ✅ | 60 | 60 |
| C1 (action+session) | 8.1532 | 0.0066 | 0.0067 | 0.0068 | 0.00× | ≤ 1.5× | ✅ | 2 | 2 |
| C2 (action+time) | 8.2562 | 0.0132 | 0.0133 | 0.0135 | 0.00× | ≤ 1.5× | ✅ | 35 | 35 |

**Dataset B_high_card_uniform verdict: PASS**
