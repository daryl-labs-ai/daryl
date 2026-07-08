# 2026-OrchestratedMemory — Program Status

**Program:** Limits, guarantees, and costs of the current orchestrated DSM
**Opened:** 2026-07-04
**State:** **OPEN** (per `research/PROGRAM_LIFECYCLE.md`)
**Independence:** This program does not cite, reuse, or seek to confirm any
prior program. It is treated as the first.
**Kernel modified:** No.
**Push / PR / canonical contact:** None.

---

## Research question

> Jusqu'où le DSM orchestré actuel tient-il quand plusieurs agents/processus
> produisent, relisent, reprennent et audient une mémoire collective via
> l'orchestrateur central ?

## Hypothesis

> Le DSM orchestré actuel peut supporter un workload multi-agents de
> développement logiciel tant que l'orchestrateur reste le point unique
> d'admission.

---

## Findings (level P — measured properties of the current system)

### P1 — The orchestrator is GIL-bound, not parallelism-friendly

Multi-threaded writes provide **no speedup** (1.00x) regardless of worker
count (2, 5, 10). Root cause confirmed by Axe 1b: same-shard vs distinct-shard
writes are identically slow (ratio 1.00x), proving the bottleneck is the
Python GIL, not FileLock contention.

- Raw `Storage.append()`: ~0.69 ms median (~1444 writes/sec single-writer ceiling)
- Orchestrated `lanes.push()`: ~1.8 ms/entry (~558 writes/sec)
- Threaded (any worker count): identical to sequential

**Implication:** true multi-agent concurrency in single-process DSM is
illusory. The "parallel lanes" design does not deliver parallel writes within
one process; it delivers *isolation*, which is a different (weaker) property.

### P2 — Handoff works; B reconstructs A's full work from DSM

After A pushes 5 decisions and "dies" (process killed), a fresh B process
rebuilds the complete work from collective memory:

- 5/5 decisions recovered
- Attribution to agent_A: correct (100%)
- Completeness (summary + detail + key_findings): 100%
- Reconstruction time: 0.1 ms

**Implication:** the collective projection model delivers on its core
promise — cross-agent handoff without side channels. Ordering is
newest-first (documented), consistent, not a defect.

### P3 — Replay-after-restart works for collective memory; private memory is not stored by DSM

After kill+restart, 150/150 collective entries are recovered across 3 agents
in 0.9 ms. **However**, the original private entries are NOT in any shard
managed by `lanes.push()` — only projections are stored. The caller is
responsible for its own private storage.

**Implication:** DSM collective memory is a projection layer, not a full
memory store. "Replay the original work" requires the caller to have kept
the private entries; DSM alone replays projections, not source entries.

### P4 — Original timestamps are lost on collective projection

The collective entry's `contributed_at` is the time of `push()`, not the
entry's original `timestamp`. A workload spread over 8 hours collapses to
a single-second window in the collective view.

**Implication:** temporal reconstruction of "when did the work actually
happen" is not possible from collective memory alone. The orchestrator
audit shard preserves decision time, but not original work time.

### P5 — Write throughput degrades super-linearly with volume; admission stays flat

| Volume | writes/sec | admit latency (median) |
|--------|------------|------------------------|
| 100 | 565 | 0.73 ms |
| 1000 | 120 | 0.74 ms |
| 5000 | 26 | 0.72 ms |

The orchestrator's `admit()` is **flat** across all cache sizes (0.72–0.74 ms)
— it does not saturate. The throughput collapse (565 → 26, 22× slower) is
**downstream of admission**, in the projection+storage write path.

**Implication:** the orchestrator is NOT the bottleneck at scale. The
storage write path (segment growth + projection construction per entry)
is. Optimising the orchestrator would not help; optimising the storage
write path would.

### P6 — Retry is not idempotent; crash window between admit and write produces audit/collective inconsistency

Two failure properties measured:

- **Retry creates doubles.** Re-pushing the same 50 entries after a
  simulated crash produces 100 entries in collective memory. There is no
  deduplication by `entry.hash`. An agent that retries after a network
  timeout silently duplicates its contribution.
- **Admit-write crash window.** If the process dies between
  `orchestrator.admit()` (which logs "allow" to `orchestrator_audit`) and
  `lanes.push()` (which writes the projection), the audit shard claims an
  admission occurred with no corresponding collective entry. The audit
  over-reports.

**Implication:** at-least-once semantics, not exactly-once. Consumers of
the collective memory must be tolerant of duplicates; consumers of the
audit shard must be tolerant of orphan admissions.

### P-corollary — Segment corruption is well-contained

Truncating the last line of a segment shard drops exactly that one entry;
19/20 survive. The append-only JSONL reader skips malformed lines cleanly.
This is a robustness property worth keeping.

---

## Conditions where the orchestrated DSM holds

Synthesising the six findings:

- **Single-process, moderate volume** (< ~500 entries per push batch):
  handoff, replay, audit, and attribution all work correctly. The system
  delivers its promised guarantees.
- **Cross-agent handoff via collective memory**: works, with full
  attribution and projection detail.
- **Crash recovery of committed writes**: durable; survived entries are
  recovered on restart.
- **Localised corruption**: contained to the corrupted line.

## Conditions where it breaks or degrades

- **Concurrency**: GIL-bound; threads provide no speedup. Real concurrency
  needs processes, which needs the distributed backend that is absent.
- **Volume**: throughput degrades ~22× from 100 to 5000 entries per batch,
  in the storage path (not the orchestrator).
- **Retry / network failure**: not idempotent; duplicates are created
  silently.
- **Crash between admit and write**: audit and collective become
  inconsistent (audit over-reports).
- **Temporal reconstruction**: original work timestamps are lost in
  collective projection.
- **Full replay of source work**: impossible from DSM alone (only
  projections are stored).

---

## Reproducibility

```
research/2026-OrchestratedMemory/experiments/
├── om1_concurrency.py            — P1: concurrency, no speedup
├── om1b_parallelism_rootcause.py — P1 root cause: GIL vs FileLock
├── om2_handoff.py                — P2: handoff success
├── om34_replay_audit.py          — P3, P4: replay + audit
├── om5_stress.py                 — P5: throughput degradation
└── om6_failure.py                — P6: retry doubles, crash window
```

Run with the project venv (Python 3.12). No network. No canonical-repo
access. No kernel modification.

---

## What this program did NOT do

- It did not test real multi-day workloads with real LLM agents. The
  workloads are *representative* (real DSM writes, real orchestrator
  admissions, real collective projections) but not *real agent work*.
  That distinction matters: the findings describe the *infrastructure's*
  limits, not the *agent coordination* limits.
- It did not compare DSM to other memory systems.
- It did not propose or build any feature. All findings are properties of
  the existing system.

---

## Candidate improvements (proposed for the canonical repo via its own process)

These are **candidate proposals**, not integrations. Each would enter the
canonical repo's own review.

- **C1**: deduplicate collective pushes by `entry.hash` (fixes P6 retry
  doubles). Low risk; the hash is already computed.
- **C2**: preserve original `entry.timestamp` in the collective projection
  (fixes P4 temporal loss). Low risk; one additional field.
- **C3**: make the admit→write path atomic or add a reconcile step that
  detects orphan admissions (fixes P6 crash window). Medium complexity.
- **C4**: investigate the storage write-path degradation at volume (P5).
  The orchestrator is exonerated; the projection+segment path is the
  suspect. This is a measurement, not yet a fix.

None of these are integrated. None are pushed. They are recorded as
candidates for whoever owns the canonical repo's roadmap.

---

## Status

**Program: OPEN.** Six axes tested, seven P-level findings produced. The
hypothesis holds in its qualified form: the orchestrated DSM supports
multi-agent workloads *as long as* the workload is single-process,
moderate-volume, and tolerant of at-least-once semantics. Outside that
envelope, the limits are now measured and named.
