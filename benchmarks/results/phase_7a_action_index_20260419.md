# Phase 7a benchmark — RR action_name index vs SessionIndex

- Run timestamp (UTC): 2026-04-19T20:04:41.020424+00:00
- Prototype branch: proto/phase-7a-rr-action-name-index
- Commit SHA: a693429e9dcdaded07a55e854d59efc9b7eecbcb
- Python: 3.10.20
- Platform: macOS-26.3.1-arm64-arm-64bit

**Overall verdict: PASS**

## Dataset A_low_card_zipf

- 10 000 entries, 500 sessions, 30 action_names Zipf s=1.1
- Distribution: zipf; seed: 42
- Distinct action_names observed: 30
- Top action: `action_0000`  ·  Rare action: `action_0025`

### Build

| Metric | median (ms) | p95 (ms) | max (ms) | vs SessionIndex | Gate | Pass |
|---|---:|---:|---:|---|---|---|
| SessionIndex_build | 85.45 | 97.04 | 97.04 | 1.00× | — | — |
| RR_baseline_build | 483.03 | 488.41 | 488.41 | 5.65× | — | — |
| RR_with_action_build | 550.53 | 556.11 | 556.11 | 6.44× | — | — |
| **delta_build = RR_with - RR_baseline** | 67.50 | — | — | 0.79× | ≤ 1× | ✅ |
| RR_with_action absolute | — | — | — | 6.44× | ≤ 3× (info) | operational flag (>3×) |

### Queries

| Variant | SI median (ms) | RR median (ms) | RR p95 (ms) | RR max (ms) | ratio | Gate | Pass | SI rows | RR rows |
|---|---:|---:|---:|---:|---|---|---|---:|---:|
| top | 0.0237 | 0.0162 | 0.0164 | 0.0170 | 0.69× | ≤ 1.5× | ✅ | 100 | 100 |
| rare | 0.2873 | 0.0066 | 0.0069 | 0.0079 | 0.02× | ≤ 1.5× | ✅ | 56 | 56 |
| C1 (action+session) | 0.4103 | 0.0955 | 0.1082 | 0.8100 | 0.23× | ≤ 1.5× | ✅ | 15 | 15 |
| C2 (action+time) | 0.1638 | 0.0649 | 0.0858 | 0.2926 | 0.40× | ≤ 1.5× | ✅ | 100 | 100 |

**Dataset A_low_card_zipf verdict: PASS**

## Dataset B_high_card_uniform

- 10 000 entries, 500 sessions, 1 000 action_names quasi-uniform
- Distribution: uniform; seed: 43
- Distinct action_names observed: 997
- Top action: `action_0649`  ·  Rare action: `action_0316`

### Build

| Metric | median (ms) | p95 (ms) | max (ms) | vs SessionIndex | Gate | Pass |
|---|---:|---:|---:|---|---|---|
| SessionIndex_build | 85.34 | 96.25 | 96.25 | 1.00× | — | — |
| RR_baseline_build | 480.57 | 485.81 | 485.81 | 5.63× | — | — |
| RR_with_action_build | 547.23 | 554.09 | 554.09 | 6.41× | — | — |
| **delta_build = RR_with - RR_baseline** | 66.65 | — | — | 0.78× | ≤ 1× | ✅ |
| RR_with_action absolute | — | — | — | 6.41× | ≤ 3× (info) | operational flag (>3×) |

### Queries

| Variant | SI median (ms) | RR median (ms) | RR p95 (ms) | RR max (ms) | ratio | Gate | Pass | SI rows | RR rows |
|---|---:|---:|---:|---:|---|---|---|---:|---:|
| top | 0.2813 | 0.0027 | 0.0030 | 0.0030 | 0.01× | ≤ 1.5× | ✅ | 19 | 19 |
| rare | 0.2788 | 0.0010 | 0.0010 | 0.0012 | 0.00× | ≤ 1.5× | ✅ | 4 | 4 |
| C1 (action+session) | 0.2803 | 0.0015 | 0.0016 | 0.0017 | 0.01× | ≤ 1.5× | ✅ | 1 | 1 |
| C2 (action+time) | 0.2879 | 0.0036 | 0.0037 | 0.0039 | 0.01× | ≤ 1.5× | ✅ | 7 | 7 |

**Dataset B_high_card_uniform verdict: PASS**
