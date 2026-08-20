# DSM Verify — Boundary Statement

**Doctrine locked:** 2026-08-20  
**Author:** Azizi Mohamed (founder)  
**See also:** [DSM_KERNEL_FREEZE_2026_03.md](./DSM_KERNEL_FREEZE_2026_03.md)

---

## Core principle

**DSM proves properties of the record, not reality itself.**

---

## Four levels of integrity

### Level 1: Hash-chain integrity (shipped)

Modification or reordering of an entry is detectable because each hash is
`SHA-256(content + prev_hash)`.

Note: this describes the case where an attacker alters the log WITHOUT
rebuilding everything that follows. An attacker who recomputes the entire chain
can produce a new coherent chain — but it will have a different tip, so the
integrity pin detects it.

### Level 2: Expected-state integrity (shipped)

`dsm verify` recomputes the hash chain from the raw entries, then compares the
tip to the expected integrity pin. Clean truncation of the tail does NOT break
the remaining chain by itself; it fails only because the recomputed tip no
longer matches the pin.

**Verification is:** raw entries + chain + expected integrity state.

### Level 3: Truth (explicitly not claimed)

A factually false entry can be cryptographically intact. Integrity is not truth.
**DSM does not prove that an event happened in the world.**

### Level 4: External tamper resistance (not shipped)

If an attacker rewrites both the shard AND the local integrity pin in the same
step, they can reconstruct a new coherent history. Defeating that needs an
external witness / transparency log / timestamp authority / anchor the local
attacker cannot rewrite retrospectively.

That is a future evolution, not a current property.

---

## What you get now

A trail you can replay, and a check that fails if the trail was quietly edited.

---

## Verification workflow

```bash
dsm verify --shard sessions
```

Returns:

| Field | Meaning |
|-------|---------|
| `status` | `OK`, `TAMPERED`, or `CHAIN_BROKEN` |
| `pin_status` | `PINNED_OK`, `UNPINNED`, `TIP_MISMATCH`, or `AHEAD_OF_PIN` |
| `truncation_detected` | `true` if entry count < pinned count |
| `chain_breaks` | count of `prev_hash` mismatches |
| `tampered` | count of entries with hash mismatch |

A shard with no integrity pin is reported as `UNPINNED` rather than a silent
`OK`. Unpinned shards cannot be verified for completeness.

---

## Terminology note

Daryl is **off-chain**. Blockchain anchoring is not shipped. If external
anchoring is added in the future, it would prove existence, timestamp, and
integrity of selected hashes — not factual truth, semantic correctness, or
business decision validity.

---

## Related documentation

- [README.md — Threat model & limitations](../../README.md#threat-model--limitations)
- [P0_REMEDIATION.md](../security/P0_REMEDIATION.md) — security hardening report
- [DSM_KERNEL_FREEZE_2026_03.md](./DSM_KERNEL_FREEZE_2026_03.md) — kernel stability doctrine
