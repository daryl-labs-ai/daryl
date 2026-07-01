# ADR-PRL-0013 — Distributed Certification via per-registry chains

**Status:** Accepted — ratified-by-Mohamed 2026-07-01 · **Version:** v1 · **Date:** 2026-07-01 · **Regime:** `declared`
**Depends on:** ADR-PRL-0001 (Constitution), 0002 (Registry Architecture), 0004 (MEF); builds on the
Identity-across-projections proof (#3, PR #82) and the #5b-A proof (PR #106).
**Axis:** certification / substrate contract. **Nature:** codifies **what #5b-A proved** — the ADR follows
the proof. It fixes a **contract**, not a kernel change (the run touched no core).

> **Certification does not require a single registry. Independent chains — each internally verifiable —
> belong to one proof-space by *attestation and value-identity*, not by a single global tip.**

## Why now
The kernel survey located the single-registry assumption precisely — the per-shard triple **{tip file +
local `FileLock` + `prev_hash` linkage}** — and found the distribution primitives already present above
the core (`lanes`, `exchange`, `witness`). The **#5b-A strong-form run** (PR #106) then **proved**, on two
**independent** DSM registries with **no shared tip**, that Daryl's guarantees survive: identical
`standing`/`governed_standing`/`object_standing` by value-identity, cross-registry portable-receipt
verification, and tip attestation — **without a global tip and without a core change**. This ADR ratifies
that result as law (**option A**).

## Decision (the rule)

> Daryl's **certification may be distributed** across independent registries. Each registry maintains its
> **own verifiable `prev_hash` chain** (its own tip); there is **no single global tip**. Membership of two
> registries in **one proof-space** is established **read/proof-side** by three pillars, each verifiable
> on its own and together:
> 1. **Internal integrity** — each chain is `verify_shard`-valid on its own;
> 2. **Cross-registry verifiability** — an act is verified via a **portable receipt** against its
>    **issuer's** DSM (`exchange`); a tampered act fails (`HASH_MISMATCH`);
> 3. **Proof-space membership** — each registry's tip is **attested** (`witness`).
> Reconciliation of identity and standings across registries **is the value-identity join** already used
> by standing/coherence (#3) — it adds **no new identity or standing rule**.

## The load-bearing invariant

> **A receipt is immutable, verifiable, and non-forgeable *without* a single authoritative chain.**
> Receipts are **substrate-relative** — the *same* act gets a **different** `Entry.hash` in each registry
> (expected, #3); what is invariant is the **semantic layer** (`claim_id`/content and the derived
> standings) and the **cross-registry verifiability** (portable receipt + attestation). Certification is a
> property of **each chain plus the reconciliation layer**, never of a single global order.

## The rules (minimal, contract-level)
1. **Per-registry chains.** Each registry keeps its own `prev_hash` chain + tip; append is serialized
   **locally** (its own `FileLock`); there is **no cross-registry tip, lock, or order**.
2. **No global tip / no consensus.** Membership is **not** a merged log, a quorum, or a Merkle-DAG (that is
   option (b), deferred). It is **attestation + portable receipts + value-identity**.
3. **Reconciliation is read/proof-side** and **is** the #3 value-identity join — **no new rule**;
   `governed_standing` (ADR-0011) and `object_standing` (ADR-0012) reconcile **identically** across
   registries.
4. **Cross-registry verification is by portable receipt** (`exchange`, against the issuer's DSM); a
   tampered act **fails**.
5. **Receipts differ across registries by design** — the contract asserts semantic identity + portable
   verifiability + attestation, **never receipt-equality**.
6. **No core kernel change.** `Storage.append` / `Entry.hash` / `prev_hash` / `verify_shard` are
   **unchanged**; certification is distributed **above** the core, using existing primitives.

## Non-goals (hard scope fence)
No global/cross-registry tip, no consensus / quorum / Merkle-DAG (**option (b)** — a true distributed
substrate — is a **deferred fallback**, warranted **only** if the invariant fails); no change to the core
append/verify chain; no signatures added to the core path; no write-side chain-merge; no new identity or
standing rule.

## Governance
The certification substrate contract is a **governed decision** — it must be **human-ratified**. (The
proof preceded the law: #5b-A ran and passed before this ADR; the ADR codifies the proven contract.)

## Proof (already executed)
**PR #106** — the #5b-A strong-form run: two independent DSM registries, no shared tip, the 8-point gate
green, CI-reproducible, no credential. Metadata: distinct tips (`R_A v1:ee2d15dd…` ≠ `R_B v1:1aa3d786…`),
same-act receipts differ, portable receipt `CONFIRMED` (tamper → `HASH_MISMATCH`), two witness
attestations. Recorded in `PROOF_LOG.md` (2026-07-01, #5b option A).

## Consequences & sequence
- This **closes #5b** — the last robustness frontier; **all 9 robustness frontiers are now proven**.
- **Ratification** flips the register's Canonical law to include this ADR; the frontier row is already
  🟢 (the proof).
- **Option (b)** (distributed substrate — Merkle-DAG / consensus / multi-signature) remains a **named,
  deferred fallback**, to be revisited only if a future case breaks the invariant (a receipt unverifiable
  cross-registry, or standings that diverge).
