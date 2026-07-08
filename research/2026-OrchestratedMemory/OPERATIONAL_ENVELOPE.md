# Operational Envelope of DSM

**What this is:** a measured profile of what DSM *is*, not what it aspires
to become. Every row is falsifiable, measured, and tied to a specific
experiment. No marketing, no promises, no roadmap.

**Derived from:** 2026-OrchestratedMemory (7 P-level findings), commit `a5e56dc`.
**Living document:** re-measure when the architecture changes. A row that
no longer reproduces means the envelope moved — update the row and the
experiment it cites.

---

## How to read this

- **✓** — DSM delivers this guarantee, measured.
- **partial** — DSM delivers a weaker form than the name suggests; the
  gap is named.
- **✗** — DSM does not provide this; the consequence is named.
- **Confidence** — the strength of the evidence behind the row:
  - **High** — measured across enough cases that the next measurement is
    very likely to agree; or a structural property unlikely to change
    without an architecture rewrite.
  - **Medium** — measured on a small sample or a narrow scenario; the
    *direction* is reliable, the *number* may shift under wider workload.
  - **Low** — not present in this envelope; if introduced, it would mark
    a row worth re-measuring before relying on it.
- Each row cites the experiment that produced it and the scope it holds in.

This is not a feature list. It is a contract description. If you rely on
DSM for something marked ✗, you are relying on a property the system does
not have. If you rely on a Medium-confidence row for a critical decision,
re-measure it under your own workload first.

---

## Operational profile

### Admission control

| Property | Status | Confidence | Measurement | Scope |
|----------|--------|------------|-------------|-------|
| Central admission gate | ✓ | High | `NeutralOrchestrator.admit()`, 0.73 ms median, flat to 5000 cached entries | Single process, current `orchestrator.py` |
| Sovereignty enforcement | ✓ | High | Fail-closed by default (100% reject without `policy.set()`); configurable per-owner | Current `sovereignty.py` |
| Admission audit trail | ✓ | High | Every decision logged to `orchestrator_audit` shard with verdict + reason | Current orchestrator |

### Memory and recall

| Property | Status | Confidence | Measurement | Scope |
|----------|--------|------------|-------------|-------|
| Cross-agent handoff | ✓ | **Medium** | Fresh process fully reconstructs prior agent's work (5/5 decisions, correct attribution, <1 ms) | `LaneGroup.recent()` |
| Collective projection storage | ✓ | High | Summary + detail + key_findings preserved per pushed entry | `ShardSyncEngine.push()` |
| Private execution reconstruction | **partial** | High | DSM stores projections, not source entries; full replay of original work requires caller-managed private storage | Current push path |
| Temporal fidelity of original work | **partial** | High | Collective `contributed_at` is push-time; multi-hour work collapses to the push window. The original `entry.timestamp` is not carried into the projection. | Current projection |
| Replay across long durations | **partial** | **Medium** | Collective entries survive restart; private entries do so only if the caller stored them. Temporal ordering of original work is not reconstructable from collective memory alone. | Current collective layer |

### Concurrency and scaling

| Property | Status | Confidence | Measurement | Scope |
|----------|--------|------------|-------------|-------|
| Parallel write scaling (threads) | **✗** | High | 1.00× speedup at 2/5/10 workers; root cause is Python GIL, not FileLock (same-shard vs distinct-shard identical) | CPython single-process |
| Write throughput vs volume | **degrades** | High | 565 writes/sec (100 entries) → 26 writes/sec (5000 entries), 22× slowdown | Projection + storage path |
| Admission saturation under load | ✓ (non-bottleneck) | High | `admit()` flat at ~0.73 ms from 100 to 5000 entries; the bottleneck is downstream | Current orchestrator |
| Distributed operation | **✗** | High | Single `Storage`, single `data_dir`, single process; no federation/peer/network adapter | Current architecture |

### Reliability under failure

| Property | Status | Confidence | Measurement | Scope |
|----------|--------|------------|-------------|-------|
| Durability of committed writes | ✓ | **Medium** | 50/50 entries survived kill+restart | Current segment storage |
| Localised corruption containment | ✓ | **Medium** | 1 corrupted JSONL line skipped cleanly; 19/20 entries survive | `iter_shard_events` reader |
| Idempotent retries | **✗** | High | Re-pushing same entries creates doubles (50→100); no hash dedup on collective push | Current `ShardSyncEngine.push()` |
| Admit→write atomicity | **✗** | High | Crash between `admit()` and `push()` leaves an orphan audit decision ("allow" logged, no collective entry) | Current push path |

---

## At-a-glance

```
                       DSM operational envelope (commit a5e56dc)
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Admission control          ✓                                        │
  │  Audit trail                ✓                                        │
  │  Cross-agent handoff        ✓                                        │
  │  Durability (committed)     ✓                                        │
  │  Corruption containment     ✓                                        │
  │  Private replay             partial  (projection-only)               │
  │  Temporal fidelity          partial  (push-time, not work-time)      │
  │  Parallel write scaling     ✗        (GIL-bound)                     │
  │  Distributed operation      ✗        (single-process by design)      │
  │  Idempotent retries         ✗        (at-least-once, not exactly-on) │
  │  Admit→write atomicity      ✗        (crash window exists)           │
  └──────────────────────────────────────────────────────────────────────┘
```

---

## What this envelope means in practice

**For an integrator asking "can DSM do X?":**

- *"Can multiple agents share memory and pick up each other's work?"* — Yes
  (P2). Handoff is the strongest property here.
- *"Can DSM survive crashes without losing committed data?"* — Yes (P1/P6
  durability), with the caveat that retries may duplicate and the audit
  may briefly over-report.
- *"Can DSM scale horizontally across processes or hosts?"* — No. Not today.
  That requires the absent distributed backend.
- *"Can DSM replay exactly what an agent did, byte-for-byte?"* — Not from
  collective memory alone. Only projections survive; the caller owns the
  source entries.
- *"Can DSM tell me *when* an agent actually did the work?"* — Not from
  collective memory. It tells you when the work was *pushed*, which is
  different.
- *"Can DSM handle 5000+ entries per batch efficiently?"* — It can, but
  throughput drops 22×; budget for it or batch smaller.

**For an architect considering where to invest:**

- The orchestrator is *not* the bottleneck. Do not optimise admission.
- The storage write path *is* the bottleneck at volume. That is where
  measurement should focus next.
- Distribution is a missing layer, not a defect of the existing one.
  Adding it is a build, not a fix.

---

## What this envelope is NOT

- It is **not a feature list**. The ✓ rows are guarantees, not
  advertisements; the ✗ rows are honest limits, not apologies.
- It is **not static**. Every row cites an experiment. If the experiment
  no longer reproduces after a change, the row must be re-measured —
  not edited from memory.
- It is **not a roadmap**. It says nothing about what DSM should become.
  It says what DSM *is*, so that future changes can be evaluated against
  a measured baseline rather than against an assumption.
- It is **not canonical documentation**. It is a research artefact. The
  canonical repo may adopt it (or not) via its own review; until then it
  lives here as a reference.

---

## Provenance

Every row traces to a specific experiment in
`research/2026-OrchestratedMemory/experiments/`:

```
Admission / audit / sovereignty   om1_concurrency.py, om34_replay_audit.py
Handoff                           om2_handoff.py
Replay / temporal fidelity        om34_replay_audit.py
Concurrency / scaling             om1_concurrency.py, om1b_parallelism_rootcause.py
Throughput vs volume              om5_stress.py
Durability / retry / crash        om6_failure.py
Corruption containment            om6_failure.py
```

Reproduce with the project venv (Python 3.12). No network. No
canonical-repo access. No kernel modification.
