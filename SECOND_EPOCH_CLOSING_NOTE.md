# Second Epoch — Closing Note

**Status:** Historical marker · **Date:** 2026-07-01 · **Closed at:** `main = b50c486` · **Regime:** `declared`

> **The Second Epoch is closed. Its work was to prove the model's robustness — not to add features, but
> to test whether Daryl's guarantees survive when their assumptions change. Nine frontiers were opened;
> nine were proven.**

## What the epoch was
Where the first epoch built the registry, the second asked a single kind of question — *do the proven
invariants survive when the carrier, the scale, the authority, or the substrate changes?* Every movement
followed the same discipline, in this order:

1. **Grounding** — a read-only, factual survey of what the code actually guarantees.
2. **Falsifiable experiment / design** — the sharpest test that could break the claim.
3. **Runtime proof** — a real gate or a measured/CI-reproducible run; the run *is* the proof.
4. **Proof Log** — the movement is recorded only *after* it is real.
5. **Law (ADR)** — only when a rule becomes necessary, and (for the governance rules) only *after* the
   proof, never before.

The inversion is the point: **the proof preceded the law**, not the reverse.

## The tally (at `main = b50c486`)
- **Robustness frontiers: 9 / 9 proven.**
- **Proof Log movements: 16.**
- **Canonical laws (ADR-PRL): 14** (0001–0013 + the RR-binding).
- **Kernel writers: 20 — unchanged, end to end.** The frozen kernel was **never** modified: everything
  was built **above** it — derived, read-only, never stored — except the governance ADRs (0011/0012),
  which add **readings above** the projection, never into it.

## The nine frontiers, by family
- **Identity** — the *referent* survives its carrier: `claim_id` ∉ storage (identity across projections),
  `agent_id` ≠ `model_id` (structured attribution), `org_id` ≠ carrier (organization referent). The
  transversal principle *"identity is never defined by its carrier"* graduated to the manifesto after its
  third referent.
- **Behavior** — the *system* holds under pressure: derived standing at scale (#1), conflict visibility
  (#2), the object referent (#4a), object coherence + object standing (#4b / #4b-S). Governance became
  **homogeneous across scales** — `governed_standing` (claim, ADR-0011) and `object_standing` (subject,
  ADR-0012), the same shape, which **compose**: a contested claim propagates to a contested object.
- **Substrate** — the *proof layer* itself survives distribution: distributed certification by
  per-registry chains (#5b, option A, ADR-0013) — certification survives with **no single registry**,
  reconciled by value-identity, portable receipts, and attestation, with **no global tip and no core
  change**.

## The load-bearing habit
Nothing touched the frozen kernel. Governance was added as **readings above** latest-wins, never as a
mutation of it (`raw_standing` stayed byte-identical throughout). Every index/projection/signal remained
**derived, droppable, never a second source of truth**. That discipline is why the model is *stable*
rather than merely *feature-complete*.

## The transition — from robustness to construction
The conceptual core is settled. The question changes:

> from **"is this property true?"** to **"how does a user exploit it?"**

Most of what follows will **rest on** these foundations rather than redefine them. The remaining work is
**construction, not robustness**:
- **Product surfaces** — turning the proven derivations into things a user manipulates: **Knowledge
  Objects first-class**, maps/navigation, org model & permissions, API / SDK / UI, product search.
- **#4b-C — the content/lineage compiler** — the one remaining *theoretical* chantier: merging an object's
  *content* and tracking *provenance/lineage* across claims. It is likely the **first** movement to break
  the "derived / read-only" pattern (persisted claim↔claim relations, possibly a new act type) — so it
  keeps the epoch's discipline: a heavy grounding first, and the surface may reveal exactly what it must
  compile.

**The Second Epoch proved the model. The next builds on it.**
