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

## 6. Agent identity across providers and runs
- **Demonstrated property.** A contribution is attributed via a **flat `producer` string** (e.g.
  `"openai:gpt-4o (consult-adapter v1)"` — provider + model + adapter collapsed into one declared
  identity; ADR-PRL-0007/0008). Enough for v3.
- **Tension at scale.** A logical agent may change model; a model may serve several agents; a provider
  may disappear; runs differ. A flat `producer` cannot express *"the same logical contributor across
  these changes"* — needed for multi-agent collaboration, agent reputation, specialization,
  comparison, "who contributed what", "which agent tends to be reliable", "which agents disagree".
- **Invariant under test.** Are contributions attributable to the **same logical intelligence** when
  the provider, model, adapter, or session changes? The load-bearing rule: **`agent_id` must not be
  `model_id`** — a logical agent can change model, a model can serve many agents, a provider can vanish;
  contribution identity must survive all of that. (Likely future structure: `agent_id` / `provider` /
  `model` / `adapter` / `run_id` as distinct fields, vs today's single string.) This is the
  contributor's mirror of #3: **`agent_id` must not be `model_id`** is to the contributor what
  **`claim_id` must not depend on storage** is to the object — identity must not be its carrier.
- **Why this comes after #3.** `claim_id` is the identity of the *knowledge object*; `agent_id` is the
  identity of the *contributor*. Both are fundamental, but the **object comes first** — a contributor
  identity is only meaningful once the objects it contributes to have stable identity.

## Identity is not its carrier (a theme across #3, #6, #5)

Three of these frontiers are the **same invariant** seen from three angles — *identity must not depend
on the substrate that happens to carry it*:

- **the knowledge object** — `claim_id` must not depend on storage (#3 — proven for a read projection).
- **the contributor** — `agent_id` must not be `model_id` (#6).
- **the registry / organization** — identity must survive having no single registry (#5).

A **theme, not an order**: #3 came first only because an object must have a stable identity before a
contributor's identity means anything. The other two remain open — naming the theme recognizes that
they test one principle in three places; it is not a commitment to sequence them.

The principle is likely **transversal**, beyond identity-of-knowledge: any future referent — `org_id`,
`team_id`, `policy_id`, `workflow_id` — would have to satisfy *identity is never defined by its
carrier*. (Candidate for a general Daryl framing once a second referent proves it; incubating, not
canonized.)

## Two families of invariants

The six frontiers are not independent — they fall into two families:

- **Identity** — *is it still the same thing when the carrier changes?*  `claim_id` (#3) → `agent_id`
  (#6) → registry / organization identity (#5).
- **Behavior** — *does the system still act correctly under load?*  derived standing at scale (#1) →
  concurrent resolutions (#2) → knowledge compiler (#4).

Identity asks whether the *referent* survives; behavior asks whether the *system* holds. Two different
kinds of invariant — still a map, not a schedule.

---

## How to read this file
Each entry is a **falsifiable frontier**, not a plan. An invariant that cannot survive its test here
is a discovery, not a failure — it tells us where a demonstrated property was actually a property of
*scale-one*. The second epoch's first experiment will not aim to prove Daryl works; it will aim to
**check that a demonstrated property still holds when the system grows.** No entry graduates anywhere
without the same discipline that closed the first epoch: a real transcript, then a Proof Log
movement. Related: `OPEN_QUESTIONS.md` (general register), `MVP_DEMO_SCENARIO.md` (what is proven).
