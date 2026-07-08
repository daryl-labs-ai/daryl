# Knowledge Maturity Hierarchy

**Applies to:** all research programs under `research/`.
**Purpose:** prevent confusing an elegant idea with established knowledge.
**Rule:** every finding, claim, or hypothesis carries exactly one maturity
level. The level determines what the finding may be used for. A finding may
not be cited at a higher level than it has earned.

---

## The six levels

| Level | Name | Meaning | May be used to |
|-------|------|---------|----------------|
| **O** | Observation | A measured fact, no claim of generality | describe what was seen |
| **P** | Property | A demonstrated property of the system, scoped to its architectural contract | reason about the system, justify engineering decisions |
| **H** | Unifying hypothesis | An explanatory model that ties multiple observations together | guide future investigation, name a pattern |
| **F** | Falsification-resistant | A hypothesis that survived active attempts to refute it in the lab | carry weight in design discussion; still not integrable |
| **R** | Real-world validated | Confirmed under real workloads by independent measurement | justify a canonical proposal |
| **C** | Canonical | Accepted by the canonical repository (ADR, merged code, official docs) | be relied upon as part of the system |

**Monotonicity is not assumed.** A finding can lose level. An `R` can be
demoted to `F` if later workloads contradict it. The hierarchy records
current confidence, not permanent truth.

---

## Classification of the 2026-RTM program

### Level O — Observations (measured facts, not generalised)

- `Storage.read(offset=K)` is O(K) on segmented shards (Loop 1)
- monolithic `Storage.read` is O(N) constant ~180ms regardless of offset (Loop 1)
- `RRIndexBuilder.build()` scales with exponent 1.18 vs ideal 1.00 (Loop 1)
- the canonical hash covers exactly 6 entry fields (Loop 2)
- `id`, `shard`, `version` are outside every cryptographic mechanism (Loop 2)
- pre-existing deterministic test failure in
  `test_standing_index_bounded_cost_kernel` on `main` (Loop 1, side-finding)

### Level P — Properties (demonstrated, scoped to architectural contract)

- *Trust boundary:* `shard` is the sole post-write access-control field in
  `audit_shard()`, and is not integrity-protected — mutation bypasses audit
  (Loop 3). **P**, scoped to current `audit.py`.
- *Identity fragility:* `id` is used as a join key by the query engine,
  receipt resolver, and coverage tracker, and is not integrity-protected —
  mutation corrupts all three (Loop 3). **P**, scoped to current RR layer.
- *Receipt/causal decoupling:* `receipt_hash` does not cover `dispatch_hash`
  or `routing_hash` (Loop 4). **P**, scoped to current `exchange.py`.
- *Identity re-registration:* `IdentityRegistry.register()` performs no
  owner-continuity check (Loop 4 IA3). **P**, scoped to current registry.
- *Performance fix candidates:* single-pass build (~9×), reverse-scan
  resolve (6–11×), correctness-proven (Loop 1). **P**, scoped to current
  read path. These are candidate improvements the canonical repo *could*
  adopt via its own process — they are at the boundary of P and C.
- *Minimal independence of {I,V,C/P}:* the four properties are 2-by-2
  independent, with empirical counter-examples for all 6 reductions
  (Loop 6). **P** as a property of the *model*.
- *Non-distribution of current DSM:* multi-agent memory is orchestrated
  (single `NeutralOrchestrator` gates all collective writes) and local
  (single `Storage`, one `data_dir`, one process), not distributed. **P**,
  scoped to current architecture at commit `a5e56dc`
  (2026-DistributedMemory Phase 0).
- *GIL-bound concurrency:* multi-threaded collective writes provide no
  speedup (1.00x at 2/5/10 workers); root cause is Python GIL, not FileLock
  (same-shard vs distinct-shard ratio 1.00x). **P**, scoped to CPython
  single-process (2026-OrchestratedMemory Axe 1).
- *Handoff fidelity:* a fresh process fully reconstructs a prior agent's
  collective work (entries, attribution, projection detail) in <1 ms.
  **P**, scoped to current `LaneGroup.recent()` (2026-OrchestratedMemory
  Axe 2).
- *Projection-only collective storage:* `lanes.push()` stores projections,
  not source entries; full replay of original work is impossible from DSM
  alone. **P**, scoped to current `ShardSyncEngine.push()`
  (2026-OrchestratedMemory Axe 3).
- *Temporal collapse:* collective `contributed_at` is push-time, not the
  entry's original timestamp; multi-hour work collapses to a single-second
  window. **P**, scoped to current projection (2026-OrchestratedMemory
  Axe 4).
- *Orchestrator non-saturation:* `admit()` latency is flat (~0.73 ms) from
  100 to 5000 cached entries; throughput degradation (565→26 writes/sec)
  is downstream, in projection+storage, not in admission. **P**, scoped
  to current write path (2026-OrchestratedMemory Axe 5).
- *At-least-once collective semantics:* retry of the same entries creates
  duplicates (no hash dedup); a crash between `admit()` and `push()` leaves
  an orphan audit decision. **P**, scoped to current push path
  (2026-OrchestratedMemory Axe 6).

### Level H → F — RTM

- The implicit Relation Graph: DSM is structurally a directed graph of 25
  relation types, of which 0 satisfy I ∧ V ∧ C ∧ P (Loop 5). Promoted
  from **H** (Loop 5) to **F** (Loop 6) after resisting falsification.
- Property **A (Authenticity)** identified by falsification as the open
  boundary (Loop 6). **H**, not yet F — its independence from {I,V,C/P}
  has not been proven.

### Level R — none

Nothing in this program has been validated under real workloads.

### Level C — none

Nothing in this program has been accepted by the canonical repository.

---

## What each level permits

- **O / P findings** may inform engineering on the canonical repo through
  the repo's own review process. The performance P-findings (Loop 1) are
  the closest to actionable — they describe a measured defect with a
  measured fix, gated only by integration testing.
- **H / F findings** may *not* be cited to justify a PR. They may name a
  pattern and guide investigation. RTM (F) may not be integrated.
- **R** is the threshold for a canonical proposal. Reached only via the
  protocol in `2026-RTM/05-real-world-protocol/`.
- **C** is the threshold for reliance. Reached only by canonical acceptance.

---

## The discipline this hierarchy enforces

The 2026-RTM program's most important property is not RTM. It is that the
program stopped at F and refused to claim R or C without evidence it could
not manufacture. This hierarchy makes that refusal explicit and reusable:
any future finding can be placed on the same scale, and the same restraint
can be applied without re-deriving it.

A finding may not skip levels. H does not become R by elegance; F does not
become C by repeated citation. The only upward path is evidence gathered
at the level above.
