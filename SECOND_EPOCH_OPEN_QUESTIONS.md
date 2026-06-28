# Second-Epoch Open Questions — robustness tests for the demonstrated invariants

**Status:** Open questions (no answers, not a roadmap) · **Date:** 2026-06-28
**Regime:** `declared` · **Supersedable:** yes

These questions did not exist before the MVP. They become meaningful only *because* the base
properties are now demonstrated (see `PROOF_LOG.md`, `MVP_DEMO_SCENARIO.md`). They do **not**
question the foundations — they probe their **limits**.

## The shift that makes this document possible
The first epoch asked: *"what architecture must we invent?"* — and the answer is now demonstrated.
The second epoch asks a different kind of question:

> **Do the invariants we demonstrated survive when the assumptions change?**

The base properties are stable enough to become **design constraints**, not goals. So each entry
below is a **robustness test of an invariant**, not a feature request and not a proposed solution.
The form is deliberate: *demonstrated property → the tension at scale → the invariant under test*.
No entry proposes how to resolve the tension; naming the frontier is the whole job here.

This is a change in the **nature of the proof**, not only its subject. The first epoch proved
**capabilities** — *"can we do X?"* (Retrieval, Consultation, Resolution, Explain — each closed by a
real transcript). The second epoch proves **invariants** — *"does X stay true when the context
changes?"* A capability is shown once; an invariant is shown to *survive*. So every entry below asks
the same underlying question of a property already demonstrated:

> **Is the demonstrated property local (true at scale-one) or universal (true as the system grows)?**

Each entry is, in effect, an attempt to **break** a property we just proved — and a broken property
is a discovery (it was a property of scale-one), not a failure.

---

## 1. Derived standing at scale
- **Demonstrated property.** Standing is a projection: derived by replaying a claim's resolution
  acts, never a stored or authoritative field (Resolution/Standing v1).
- **Tension at scale.** Replay is O(acts per claim). As acts accumulate, deriving standing on every
  read meets a cost frontier.
- **Invariant under test.** Can standing stay **derived and never authoritative** when performance
  pressure pushes toward caching it? (A memoized projection must remain a projection — never a source
  of truth.) The question is whether the property survives optimization, not how to optimize.

## 2. Concurrent resolutions
- **Demonstrated property.** A Resolution is a human/witnessed governance act; standing is the
  latest decision by record order. Supersede/withdraw are new acts, never mutations.
- **Tension at scale.** Multiple humans may issue **incompatible** resolutions on the same claim,
  possibly concurrently, possibly across registries.
- **Invariant under test.** Does "an act, not a mutation" + "latest wins" still yield a *governed*
  outcome when resolutions conflict — or does conflict reveal that governance of competing human
  decisions is a property we have not yet demonstrated?

## 3. Identity across projections
- **Demonstrated property.** The same `claim_id` (`MEF.claim_id` ↔ `target_claim_id`) threads the
  whole chain — Proposal → Resolution → Standing → Explanation — without rupture.
- **Tension at scale.** The manifesto promises the registry is one projection among many (DSM,
  SQLite, Neo4j, a distributed service).
- **Invariant under test.** Does `claim_id` remain **invariant when the registry projection is
  replaced**? Identity continuity across a projection swap is asserted in the manifesto but not yet
  proven by experiment.
- **Why this one is logically prior.** If `claim_id` is not invariant across projections, the other
  four properties lose their referent — standing, explanation, and object identity all assume a
  stable claim identity. If it *is* invariant, the other four become questions about the system's
  **behavior** rather than its **identity**. This is logical priority, not a schedule: it is the
  natural first robustness experiment because everything else is defined relative to it.

## 4. Knowledge compiler (coherent object evolution)
- **Demonstrated property.** A Knowledge Object is a projection of its certified Acts; a single
  `claim_id` accumulates Proposal + Resolution(s) into a derived state.
- **Tension at scale.** When many Acts arrive from many producers (GPT, Claude, a local model, a
  human, a benchmark), how do they become *one coherent evolution* of an Object rather than a pile
  of acts?
- **Invariant under test.** Can "the Object is a projection of its Acts" hold when conflicts,
  supersessions, provenance, and standing must all be reconciled into a single coherent state — the
  parked *knowledge compiler* concept, stated here only as a robustness frontier.

## 5. Distributed Fabric
- **Demonstrated property.** The chain is closed against a single physical registry, read RR-only,
  certified by one DSM.
- **Tension at scale.** At larger scale there may be no single physical registry.
- **Invariant under test.** Which invariants must remain true when there is **no single registry** —
  certification, MEF non-strippability, RR-only reads, derived standing, identity continuity? The
  question is which properties are intrinsic to the protocol and which silently assumed one registry.

---

## How to read this file
Each entry is a **falsifiable frontier**, not a plan. An invariant that cannot survive its test here
is a discovery, not a failure — it tells us where a demonstrated property was actually a property of
*scale-one*. The second epoch's first experiment will not aim to prove Daryl works; it will aim to
**check that a demonstrated property still holds when the system grows.** No entry graduates anywhere
without the same discipline that closed the first epoch: a real transcript, then a Proof Log
movement. Related: `OPEN_QUESTIONS.md` (general register), `MVP_DEMO_SCENARIO.md` (what is proven).
