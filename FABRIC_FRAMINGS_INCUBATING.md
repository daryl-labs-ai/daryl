# Knowledge Fabric — Incubating Framings (not canon)

**Status:** Incubating · **Date:** 2026-06-27 · **Not normative. Not an ADR. Not (yet) in the manifesto.**

These are framings that *might* become as load-bearing as the manifesto's four laws — but haven't
earned it yet. They live here on purpose, the same way Retrieval v2's design lived as experimental
findings before it was frozen.

**Promotion rule.** A framing graduates to `VISION_KNOWLEDGE_FABRIC.md` (or a law) only if, over the
coming months, it keeps *naturally explaining* product and architecture decisions. If it stops
earning its keep, it stays here or is dropped. Metaphors that merely sound good do not graduate;
metaphors that keep predicting the right call do.

---

## 1. The Knowledge Ledger (for product presentations)

A project could be described as a **Knowledge Ledger** — in the *accounting* sense, not the
blockchain sense:

- each **Knowledge Act** is an entry,
- each **Resolution** closes an operation,
- each **Supersession** opens a new period,
- each **Knowledge Object** is the **current balance**,
- **DSM** is the **certified ledger**.

Why it lands with enterprises: they already know a *balance sheet* matters more than the *last
invoice*. In the same way, a Knowledge Object matters more than the last conversation. Keep this for
product/sales narratives; **do not put it in an ADR** — it is metaphorical, not normative.

## 2. "Projects augment intelligences" (candidate category line)

The market says *"AI augments humans."* Daryl's inversion:

> **AI augments people. Daryl lets projects augment intelligences.**

GPT, Claude, OpenClaw, or a future model do not get individually smarter. But the moment they work on
a project that has a Knowledge Fabric, they instantly inherit the project's entire *governed
cognitive heritage*. So it is no longer only the human who is augmented by the AI — it is **every
intelligence, human or artificial, augmented by the project itself.**

If this keeps explaining architecture and product decisions over time, it may reach the status of the
four laws. Until then: let it live, don't write it into an ADR.

## 3. The system of record for knowledge (ERP analogy — for executives/investors)

A potentially stronger market analogy than Git. Git manages the evolution of *code*; but enterprises
already know a system that resembles Daryl even more closely: the **ERP**. An ERP became
indispensable because it is the **system of record for operations** — the surrounding apps change, the
employees change, the suppliers change, but the ERP stays. Daryl aims for the same position, for
**cognition**:

> **ERP is the system of record for operations. Daryl becomes the system of record for knowledge.**

This speaks immediately to executives, CIOs, and investors, and it is coherent with the "SCALE OS /
Operations of Record" lineage. Keep it for positioning; promote it only if it keeps predicting the
right product and go-to-market calls — same rule as above.

## 4. Cognitive capability, not knowledge (candidate next inversion)

The manifesto says *knowledge belongs to the project* and *a project is an accumulating body of
governed knowledge*. The next conceptual inversion may be one level up:

> **Organizations don't own knowledge. They own cognitive capability.**

An organization can hold enormous knowledge and still decide badly. What has value is the *capacity to
keep turning knowledge into better decisions*. This connects to the manifesto's finality (knowledge →
decisions → project evolution), but pushes it toward *capability* as the real asset. Not yet
demonstrated by Daryl — so it incubates here, not in the manifesto, under the same promotion rule.

## 5. Cognitive identity (candidate hierarchy extension)

The manifesto's chain is *Knowledge Acts → Knowledge Objects → Knowledge Fabric*. A possible
extension reads it one level higher:

```
Knowledge Acts → Knowledge Objects → Project Memory → Project Identity
```

> **The cognitive identity of a project emerges from its governed Knowledge Acts.**

The claim: what is described is no longer only a memory, but a persistent *cognitive identity*. Two
projects can share the same files, tickets, models, and developers, and still not be the same project
— if they do not share the same history of decisions, critiques, validations, and supersessions.
Promising, but not yet demonstrated; if in six months it keeps explaining design choices, it
graduates. Until then it lives here, beside the Ledger and Cognitive Capability framings.

## 6. The design discipline as a methodology (meta-framing)

The project's own six registers increasingly resemble a *scientific process applied to software
architecture*: the **ADRs** act as an operational theory; the **Evidence Book** as the experiments;
the **Manifesto** as the research program; the **Open Questions** as unresolved hypotheses; the
**Epistemic Levels** (with promotion + demotion) prevent confusing hypothesis, theory, interpretation,
and metaphor. The striking part: the project imposes on its *own* evolution the same governance it
offers a project's *knowledge*.

If this holds over time, it may outgrow Daryl — a way to build *research-grade software* where
architecture, vision, and evidence evolve together without contaminating each other. Strictly a
meta-framing for now: it must keep proving it produces better decisions before it is claimed as a
methodology. (Note: by its own grid, this very statement is Level-3/4 — which is exactly why it lives
here, not in the manifesto.)

## 7. "A contribution becomes a governed project asset" (✅ GRADUATED 2026-06-28 → manifesto)

> **GRADUATED.** The promotion gate below was met: `MVP_DEMO_SCENARIO.md` ran end-to-end through
> step 5 (Resolution/Standing) **and** step 6 (continuity / `explain`), with a real agent (gpt-4o),
> without cheating — Proposal `v1:97d271…` → human Resolution `v1:b9901b…` → derived Standing →
> `explain` reconstructed *why*, every line backed by a receipt. This framing is now an **observed
> property** in `VISION_KNOWLEDGE_FABRIC.md` ("A contribution becomes a governed project asset
> (observed)"). Dated proof: Proof Log entries 2026-06-28 (Resolution/Standing v1 + R-explain v1).
> The text below is kept as the incubation record of how it was framed before it graduated.

A candidate one-sentence definition of Daryl, sharper than "Knowledge Fabric" because it names what
actually changes:

> **Daryl is the first system where a contribution from an intelligence becomes a governed asset of
> the project.**

Before: `LLM → answer → copied → forgotten`. With Daryl: `LLM → Knowledge Act → DSM certification →
Knowledge Object → project asset`. The rationale (the triplet): *a model is a compute provider; a
project owns the knowledge; Daryl is the system that turns the first into an asset of the second.*
The deep differentiator: a project **acquires** something from an external intelligence **without
depending durably on it**.

**What is and isn't demonstrable today (the honest status).** Demonstrable now: a contribution can
become a Knowledge Act, certified by DSM, retrievable via RR, displayable to a human — i.e. a
**certified registry of contributions** (already a real achievement). *Not* demonstrable yet: that
the contribution became a project asset *in the strong sense*. Two properties are missing: the
**governed decision** (Resolution / Standing) and the **temporal continuity** ("why this decision?"
weeks later). Without them: a certified registry. With them: the project actually *owns* the
knowledge — it influences future decisions and survives both people and models.

**The asset is not the Act.** The Knowledge Act is the *unit of contribution* (the first citizen);
the **asset** is the *governed corpus* that emerges from accumulated acts + human resolutions +
history + supersessions + reuse. (Consistent with the manifesto: "the first citizen is the Knowledge
Act" and "the true asset is the governed ability to keep improving knowledge.") Economic value lives
in their **governance over time**, not in any single act.

**Promotion gate (precise, falsifiable — by design).** This sentence is an *ambition* today; it
becomes an *observable property* only when a real project demonstrates that **a contribution from an
agent became a governed decision that is retrievable, explainable, and reusable** — i.e. when
`MVP_DEMO_SCENARIO.md` runs end-to-end (specifically through step 5 Resolution/Standing **and** step 6
continuity), with real agents, without cheating. Only then does it graduate to the manifesto as an
observed property — not before. It does not *replace* the manifesto; it is a consequence of it,
pending its proof. (R-consult v3 + Resolution/Standing are what unlock the demo, hence this line.)

## 8. "Identity is never defined by its carrier" (✅ GRADUATED 2026-06-28 → manifesto)

> **GRADUATED.** The promotion gate below was met: a **third independent referent** — `org_id` ≠
> carrier (PR #88, real gate: same `org.acme` across `openai:gpt-4o`/`gpt-5`) — joins `claim_id` ∉
> storage and `agent_id` ≠ `model_id`. The principle now stands on **three legs** and is an **observed
> property** in `VISION_KNOWLEDGE_FABRIC.md`. Dated proof: Proof Log entries 2026-06-28 (Identity
> across projections, Structured contributor attribution, Organization referent). The text below is the
> incubation record of how it was framed before it graduated.

A candidate general principle of Daryl, broader than identity-of-knowledge:

> **Identity is never defined by its carrier.** The substrate is interchangeable; the referent is not.

It already stands on **two proven legs** (see `PROOF_LOG.md`):

- **`claim_id` is not storage** — proven (Identity across projections v1: the same `claim_id` threads
  the chain identically across RR and a SQLite read projection).
- **`agent_id` is not `model_id`** — proven (Structured contributor attribution v1: the same
  `agent_id` `agent.architect` produced certified acts across `openai:gpt-4o` and `gpt-5`).

The precise current status (do not overstate it):

> *Identity is never defined by its carrier — **proven** for `claim_id` — **proven** for `agent_id` —
> **not yet testable** for registry / organization identity, because the referent is absent.*

This is stronger than "not yet proven": **the third leg has no object yet.** Grounding #5
(`IDENTITY_REGISTRY_GROUNDING.md`, NOT PROVEN) found no `org_id`/`tenant`/`registry_id` in code, and
`project_id`/`run_id`/`shard` do not replace it. So #5 was split: **#5a — organization identity (the
referent)** is the only sub-question that can become this third leg; **#5b — distributed certification**
is a kernel-shaped substrate question, separate.

If it holds, the principle would later cover any fundamental referent (`org_id`, `team_id`,
`policy_id`, `workflow_id`). It is *the* generalization of the project's earliest principle — *knowledge
is not its representation* — applied beyond knowledge.

**Promotion gate (falsifiable).** Two legs make it **incubating, not canonical** (2/3). It graduates to
the manifesto only when a **third referent** is *established and then shown to survive its carrier* —
specifically **#5a organization identity** (`org_id` independent of project/storage/shard/deployment).
Until a third independent referent exists and proves it, the principle stays here — a strong hypothesis
with no object for its third leg, not a law. It does not replace the manifesto's four laws; it would
*generalize* them.
