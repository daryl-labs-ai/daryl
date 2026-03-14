# DSM Stabilization Roadmap

Post-audit plan for correcting critical and important issues without breaking kernel guarantees. **No code changes until each fix is explicitly scheduled and applied one by one.**

---

## Kernel-critical modules (invariants)

| Module | Invariants |
|--------|------------|
| `memory/dsm/core/storage.py` | Deterministic, append-only, replay-compatible. Never break existing hash chains. |
| `memory/dsm/core/shard_segments.py` | Segment layout and naming unchanged; rotation semantics preserved. |
| `memory/dsm/core/models.py` | Entry / ShardMeta schema: no breaking changes. |

All changes in these modules must remain **deterministic**, **append-only**, and **replay compatible**.

---

## Critical issues (blockers)

| ID | Issue | File | Risk |
|----|-------|------|------|
| **C1** | Non-atomic write in `_set_last_hash()` | `storage.py` | Crash during write can corrupt hash chain state permanently. |
| **C2** | Missing `import sys` in replay CLI | `replay.py` | `sys.exit()` used without import → `NameError` at runtime. |
| **C3** | O(N) cost per append in `get_active_segment()` | `shard_segments.py` | Line count on every append → O(N²) writes per segment. |
| **C4** | O(N²) in `_read_segmented()` | `storage.py` | Two full passes per paginated read. |

---

## Important issues

| ID | Issue | Notes |
|----|-------|------|
| **I1** | Segment rotation race | Two processes may create the same new segment. |
| **I2** | entry_count race | `_update_shard_metadata()` runs outside the file lock. |
| **I3** | Security module path mismatch | `security.py` references `dsm_v2` instead of `memory/dsm`. |
| **I4** | Context builder empty content_preview | Default `resolve=False` → content_preview always "". |
| **I5** | `Signing.chain_entry()` hashing | Uses content-only hash, not canonical. |
| **I6** | `verify_chain()` skips first entry | First entry not verified. |

---

## Phase 1 — Integrity and crash safety

**Goal:** Eliminate crash-induced corruption and runtime crashes. No change to hash formula or append path semantics.

| # | Task | Affected files | Risk level | Expected change |
|---|------|----------------|------------|-----------------|
| 1.1 | **C2** Add missing `import sys` in replay CLI | `memory/dsm/core/replay.py` | Low | Add `import sys` at top. No behavior change. |
| 1.2 | **C1** Make `_set_last_hash()` atomic | `memory/dsm/core/storage.py` | Medium | Write to temp file in same dir, `fsync`, then `os.replace` to final path. Preserve exact JSON content. |
| 1.3 | **C1** Make `_update_shard_metadata()` atomic | `memory/dsm/core/storage.py` | Medium | Same pattern: temp file + fsync + `os.replace`. |

**Order:** 1.1 → 1.2 → 1.3.  
**Rationale:** C2 is the safest (single import, no kernel logic). Then C1 for both hash and metadata files to prevent corruption on crash.

**Kernel rules:** No change to Entry schema, hash formula, or append order. Replay and existing chains remain valid.

---

## Phase 2 — Storage performance

**Goal:** Remove O(N) and O(N²) costs from append and read paths. Preserve semantics and replay.

| # | Task | Affected files | Risk level | Expected change |
|---|------|----------------|------------|-----------------|
| 2.1 | **C3** Segment metadata (event_count) | `memory/dsm/core/shard_segments.py` | Medium | Introduce `segment_XXXX.meta` (or similar) with `event_count`, `first_timestamp`, `last_timestamp`. Update on append; read in `_get_active_segment_path()` instead of counting lines. Backfill or lazy migration for existing segments. |
| 2.2 | **C4** Cursor/stream-based read for segmented shards | `memory/dsm/core/storage.py` | Medium | Replace two-pass offset pagination in `_read_segmented()` with single-pass stream: e.g. iterator that yields (entry, position) and stop when offset/limit satisfied. Or use segment metadata to compute skip count without full count pass. |

**Order:** 2.1 → 2.2.  
**Rationale:** Segment metadata (2.1) reduces append cost and can support a smarter read path (2.2).

**Kernel rules:** Append remains append-only. Read API (`read(shard_id, offset=0, limit=N)`) and return order (newest-first) unchanged. No change to hash chain or segment file format for existing data.

---

## Phase 3 — Concurrency safety

**Goal:** Fix races in metadata and segment rotation without breaking single-process behavior.

| # | Task | Affected files | Risk level | Expected change |
|---|------|----------------|------------|-----------------|
| 3.1 | **I2** entry_count under lock | `memory/dsm/core/storage.py` | Medium | Move `_update_shard_metadata(shard, entry)` inside the same lock that protects append (segment file lock), or use a dedicated lock for the integrity file used by both `_set_last_hash` and `_update_shard_metadata`. |
| 3.2 | **I1** Segment rotation race | `memory/dsm/core/shard_segments.py` (+ optionally storage) | Medium | Before creating a new segment, take a lock (e.g. on a `shard_family.lock` file or on the last segment file) so only one process creates the next segment. Creation = create file + write segment metadata. |

**Order:** 3.1 → 3.2.  
**Rationale:** entry_count correctness (3.1) is simpler and reduces observable races; then segment creation (3.2).

**Kernel rules:** Lock scope and ordering must avoid deadlocks. Append and replay semantics unchanged.

---

## Phase 4 — Agent usability improvements

**Goal:** Improve context quality and signing/verification consistency. No kernel storage/shard changes.

| # | Task | Affected files | Risk level | Expected change |
|---|------|----------------|------------|-----------------|
| 4.1 | **I4** Context builder default content_preview | `memory/dsm/rr/context/rr_context_builder.py` | Low | Document that `resolve=True` is required for non-empty content_preview; or add a small default (e.g. first batch resolved when limit is small) with a cap to keep context size bounded. |
| 4.2 | **I5** Align `Signing.chain_entry()` with canonical hash | `memory/dsm/core/signing.py` | Low | Deprecate or extend `chain_entry()` to use the same canonical hash as storage (or document it as legacy content-only). Callers must be audited. |
| 4.3 | **I6** Verify first entry in `verify_chain()` | `memory/dsm/core/signing.py` | Low | Include first entry in verification (recompute its hash; no prev_hash to check). |
| 4.4 | **I3** Security module path | `memory/dsm/security.py` (and/or core) | Low | Replace `dsm_v2` references with `memory.dsm` or relative imports so paths match the repository layout. |

**Order:** 4.1 → 4.2 → 4.3 → 4.4 (or 4.2/4.3 together).  
**Rationale:** Phase 4 is outside the kernel write path; changes are documentation, signing consistency, and import paths.

**Kernel rules:** No change to `storage.py`, `shard_segments.py`, or `models.py` in this phase.

---

## Ordered list of fixes (execution order)

1. **C2** — Add `import sys` in `replay.py` (safest; no kernel logic).
2. **C1** — Atomic `_set_last_hash()` in `storage.py` (temp file + fsync + replace).
3. **C1** — Atomic `_update_shard_metadata()` in `storage.py`.
4. **C3** — Segment metadata in `shard_segments.py` (event_count, no line count).
5. **C4** — Cursor/stream-based read in `storage._read_segmented()`.
6. **I2** — entry_count update under lock in `storage.py`.
7. **I1** — Segment rotation lock in `shard_segments.py`.
8. **I4** — Context builder content_preview behavior or docs.
9. **I5** — `Signing.chain_entry()` vs canonical hash.
10. **I6** — First-entry verification in `verify_chain()`.
11. **I3** — Security module path fix.

---

## Application rule

- **One fix at a time:** Each item above is implemented, tested (pytest + sanity checks), and committed (or merged) before starting the next.
- **Regression checks:** After each change: run `pytest -q`, verify append + read + `verify_chain()`, and that existing replay/traces still validate.
- **Kernel changes:** For storage/shard_segments, ensure no hash formula change, no schema change, and no non-append write to existing segment or integrity files (except atomic replace of integrity file).

---

## Safest starting fix

**Recommended first fix: C2 — Add `import sys` in `memory/dsm/core/replay.py`.**

- **Why:** Single line, no kernel logic, no hash or storage behavior change. Removes a clear runtime bug (`NameError` when replay CLI hits an exit path).
- **Risk:** Minimal (import only).
- **Next:** Then proceed to C1 (atomic writes) for integrity and crash safety.

---

## Reference

- Audit TODO: `docs/architecture/DSM_AUDIT_TODO.md`
- This roadmap: `docs/architecture/DSM_STABILIZATION_ROADMAP.md`
- **Kernel audit results (post C1–C4):** [DSM_KERNEL_AUDIT_RESULTS.md](DSM_KERNEL_AUDIT_RESULTS.md) — CR-1, CR-2, CR-3, M-1, M-3 and implementation order.
