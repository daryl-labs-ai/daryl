# DSM Kernel Audit Results and Correction Plan

**Date:** Post-stabilization audit (C1–C4 implemented).  
**Scope:** `memory/dsm/core/` (storage, shard_segments, models, signing, replay, security).  
**No code is modified in this step — documentation only.**

---

## 1. Audit context

A full technical audit of the DSM kernel was completed. The following modules were audited:

| File | Role |
|------|------|
| `memory/dsm/core/storage.py` | Append/read, integrity files, shard metadata |
| `memory/dsm/core/shard_segments.py` | Segment layout, active segment, rotation |
| `memory/dsm/core/models.py` | Entry, ShardMeta |
| `memory/dsm/core/signing.py` | Hash chain verification |
| `memory/dsm/core/replay.py` | Trace replay, step hash verification |
| `memory/dsm/core/security.py` | Integrity monitor, paths |

Stabilization fixes **C1–C4** are confirmed as implemented:

- **C1** — Atomic integrity writes (`_set_last_hash()`: temp → fsync → `os.replace`).
- **C2** — Replay CLI: missing `import sys` added.
- **C3** — Segment metadata (`segment_meta.json`) for O(1) append; no line counting.
- **C4** — Streaming segmented reads; O(limit) instead of double-pass.

Despite this, the audit identified **remaining issues**. The kernel is **not yet ready for freeze**.

---

## 2. Critical issues (must fix before kernel freeze)

| ID | Issue | File | Required action |
|----|-------|------|-----------------|
| **CR-1** | Non-atomic overwrite in `_update_shard_metadata()` | `memory/dsm/core/storage.py` | Same integrity file as `_set_last_hash()` is overwritten with a non-atomic write, undoing C1’s crash-safety. **Make write atomic:** tmp → flush → fsync → `os.replace`. |
| **CR-2** | `_get_last_hash()` has no corruption handling | `memory/dsm/core/storage.py` | `json.load()` is used without try/except. Corrupted integrity file causes `JSONDecodeError` on every append. **Add** try/except and safe fallback or explicit integrity error. |
| **CR-3** | Replay step hash verification is self-referential | `memory/dsm/core/replay.py` | Verifier hashes the full record **including** the stored `step_hash` field, so the hash input contains the hash. **Compute hash on record excluding `step_hash`.** |

---

## 3. Medium issues (should fix before freeze)

| ID | Issue | File | Required action |
|----|-------|------|-----------------|
| **M-1** | Incorrect `verified_records` in replay report | `memory/dsm/core/replay.py` | Formula subtracts `corrupt_count` even though corrupt records are not in the parsed list. Correct the statistics. |
| **M-3** | Security integrity monitor uses wrong paths | `memory/dsm/core/security.py` | Monitor references `dsm_v2/core/*` instead of actual kernel path `memory/dsm/core/*`. Security layer monitors non-existent files. **Fix path references.** |

---

## 4. Affected files

| File | Issues |
|------|--------|
| `memory/dsm/core/storage.py` | CR-1, CR-2 |
| `memory/dsm/core/replay.py` | CR-3, M-1 |
| `memory/dsm/core/security.py` | M-3 |

No changes to: `shard_segments.py`, `models.py`, `signing.py` in this correction plan.

---

## 5. Kernel readiness

**Audit result:** Kernel readiness ≈ **62 / 100**.

Architecture is sound; **critical fixes (CR-1, CR-2, CR-3) are required** before declaring the kernel frozen.

---

## 6. Proposed implementation order

Fixes will be applied **one at a time**, each with implementation and tests before the next:

| Order | ID | Description |
|-------|----|-------------|
| 1 | **CR-1** | Atomic write for `_update_shard_metadata()` in `storage.py` |
| 2 | **CR-2** | Integrity file corruption handling in `_get_last_hash()` in `storage.py` |
| 3 | **CR-3** | Replay step hash computed excluding `step_hash` in `replay.py` |
| 4 | **M-3** | Security monitor paths corrected in `security.py` |
| 5 | **M-1** | Replay report `verified_records` (and related stats) corrected in `replay.py` |

**Rationale:**  
- CR-1 restores full crash-safety for the same integrity file used by C1.  
- CR-2 prevents appends from failing on corrupted integrity files.  
- CR-3 makes replay verification semantically correct.  
- M-3 fixes real monitoring targets.  
- M-1 improves replay report accuracy without changing verification logic.

---

## 7. References

- Stabilization roadmap: [DSM_STABILIZATION_ROADMAP.md](DSM_STABILIZATION_ROADMAP.md)
- Audit TODO: [DSM_AUDIT_TODO.md](DSM_AUDIT_TODO.md)
