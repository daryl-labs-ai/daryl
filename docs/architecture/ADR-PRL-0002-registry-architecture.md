# ADR-PRL-0002 — PRL Registry Architecture

**Status:** Accepted — ratified-by-Mohamed 2026-06-26 · **Version:** v1 · **Date:** 2026-06-26 · **Regime:** `declared`
**Supersedes:** nothing · **Depends on:** ADR-PRL-0001 (Epistemic Registry Constitution)
**Abstraction test:** this document must remain true if the implementation is rewritten
in another language. If any sentence here would change because of Python, JSON, a database,
or an API shape, it belongs in 0003/0004, not here.

> **PRL does not make project knowledge true. It makes project knowledge governable.**

**ADR series (Git-like progression — invariants before implementation):**
0001 Constitution (laws) · **0002 Architecture (boundaries, actors, objects)** ·
0003 Vocabulary (normative glossary) · 0004 Protocols (contracts, message/event shapes) ·
0005 Implementation (types, APIs, storage, language).
This document is **architecture only**: roles, boundaries, responsibilities. No protocols, no types, no code.

---

## 1. Architectural Principles

Consequences of 0001 — no technique. Everything below derives from these.

1. **Registry ≠ Storage.** Storage persists bytes; the Registry governs the standing of claims about them.
2. **Registry ≠ Memory.** Memory is the governed *material*; the Registry is the *product*.
3. **Proposal ≠ Knowledge Object.** Nothing becomes a Knowledge Object except through recorded events.
4. **Observed ≠ Derived.** Facts are observed and immutable; interpretations are derived and versioned.
5. **Read Contract ≠ Write Contract.** Entering the registry and leaving it are governed separately and symmetrically.
6. **Governance wraps existing layers; it never replaces them.** P0→P9 stays intact underneath.
7. **Salience is governed, not neutral.** Selection and ranking exercise authority and must be auditable.
8. **Authority over truth is external.** It belongs to humans or witnesses, never to the Registry or to inference.
9. **Boundaries precede actors.** Rights are derived from what cannot be crossed, not asserted.
10. **Identity precedes attributes.** What an object *is referenceable as* is defined before what it contains.

---

## 2. Boundaries — the founding chapter

The architecture is defined first by what **cannot** happen. These flows are impossible
to cross; every future design, in any language, must preserve them.

**Allowed flows**

| From | To | Meaning |
|---|---|---|
| Agent | Proposal | an agent may only ever submit a proposal |
| Collector | Observed (Imported/Witnessed) | a collector records what it observed |
| Proposal | Registry | the registry receives proposals |
| Registry | Registry Event | standing changes only by recorded events |
| Ratified events | Knowledge Object | an anchor emerges only from ratification |
| Knowledge Object | Read Contract → consumer | knowledge leaves only through the read contract |

**Forbidden flows (impossible by construction)**

| Forbidden | Why |
|---|---|
| Agent → Knowledge Object | an agent never creates a stable anchor directly (L7) |
| Agent → Observed | an agent cannot forge a fact (L2) |
| Ranker → Registry Event | ordering must never change a claim's standing (L10/L12) |
| Read Contract → mutate state | reading never writes (L5/L11) |
| Derived → Observed | an interpretation cannot become a fact without a witness (L3/L14) |
| Imported → Witnessed | you cannot witness retroactively (L14) |
| any actor → naked claim | nothing leaves without its Minimal Epistemic Frame (L5/L6) |

Citizens (next) are simply the actors named by these boundaries; their rights are the
allowed flows, their prohibitions are the forbidden ones.

---

## 3. Citizens

Derived directly from §2 — and therefore from 0001's laws.

| Citizen | May | Never |
|---|---|---|
| Human | accept / reject / ratify, declare boundaries | forge an Observed fact |
| Agent | propose, consume (via read contract) | ratify; write Observed; create a Knowledge Object directly |
| Collector | observe (Witnessed/Imported) | derive; interpret |
| Extractor | derive (produce candidates) | observe; ratify its own output |
| Ranker | order / select (produce salience) | change a claim's standing; emit a registry event |
| Governance | record events, enforce transitions, apply policy | decide truth |
| Registry | record what exists and its standing | assert truth; rank; interpret |

Every "Never" traces to a forbidden flow in §2 and a law in 0001. That traceability is
the point: rights are not granted, they are what's left after the boundaries.

---

## 4. Core Objects

Roles and relationships only — no attributes (attributes are 0003/0004).

- **Claim** — anything the registry holds standing about. The unit everything else qualifies.
- **Proposal** — a claim *offered* by a producer for governance. The only thing an agent may create.
- **Evidence** — what a proposal points to in support of itself. Referenced, not owned.
- **Registry Event** — a recorded, attributed fact about a claim's standing changing
  (`Observed`, `Imported`, `Proposed`, `Referenced`, `Accepted`, `Rejected`, `Superseded`, `Withdrawn`).
  The only thing that moves standing.
- **Knowledge Object** — a claim that has reached stable standing through ratified events;
  the durable anchor many observations attach to. Emerges; is never authored directly.

Relationships: a Proposal *is a candidate* Claim; Evidence *supports* a Proposal; a
Registry Event *changes the standing of* a Claim; a Knowledge Object *is* a Claim whose
standing was ratified; Claims may `contradict` or `supersede` one another.

---

## 5. Identity

Why each identity exists — not how it is formed (that is 0004). Identity exists so that
things can be *referenced across time without implying truth*, exactly as DSM defined
`EventID` / `Hash` / `HashChain` before any implementation.

- **ClaimID** — refer to a claim regardless of its current standing.
- **ProposalID** — refer to a specific offering, distinct from the claim it proposes.
- **EvidenceID** — refer to a piece of support independently of the proposals citing it.
- **ProducerID** — attribute *who/what* produced a claim, event, or ordering (human, agent, collector, extractor, ranker).
- **PolicyID** — attribute the *ranking policy* (and version) that produced a given salience.
- **KnowledgeObjectID** — refer to a durable anchor stably as observations accrete around it.

Identity precedes attributes (Principle 10): a thing must be referenceable before it is describable.

---

## 6. Contracts

Responsibilities only — message/event shapes are 0003, types are 0004.

**Write Contract** — how a claim *enters*. Responsibilities: accept only Proposals from
authorized producers; record every standing change as an attributed Registry Event;
enforce legal transitions and refuse forbidden ones; never let a producer write Observed
it did not witness, nor a Knowledge Object directly.

**Read Contract** — how a claim *leaves*. Responsibilities: never emit a naked claim;
always attach the **Minimal Epistemic Frame** (regime, confidence, contested?, and a
handle); make the **Extended Frame** (provenance, producer, evidence, ranking explanation,
producer/policy version, contradictions) reachable on demand; never suppress a
contradiction; never strip confidence or regime.

**Supporting responsibilities:** **Ranking Policy** — every ordering is attributable to a
versioned policy and exposes its reasons. **Producer Identity** — every claim, event, and
ordering names its producer. These make salience and provenance auditable (Principle 7).

The two contracts are symmetric: the write contract keeps PRL honest about what it stores;
the read contract keeps consumers honest about what they believe. "Accepted ≠ True" (no
stored truth) and "No naked claim" (non-strippable MEF) are one guarantee seen from both ends.

---

## 7. State Machine

With boundaries, actors, and objects fixed, the transitions become natural. At role level
(no storage): a claim's standing is the sequence of Registry Events applied to it.

- **Legal transitions** flow through events: a proposal is `Proposed`, may be `Referenced`,
  then `Accepted` or `Rejected`; an accepted claim may later be `Superseded` or `Withdrawn`;
  an observed claim is `Witnessed` or `Imported` at entry.
- **Forbidden transitions** are as load-bearing as legal ones — chiefly `Imported → Witnessed`
  (no retroactive witnessing), and any standing change not carried by an attributed event.
- **Promotion to a Knowledge Object** is a transition gated by ratification (human or witness),
  never by inference.
- Nothing is deleted: `Rejected` / `Withdrawn` / `Superseded` are retained; **visibility**,
  not existence, is the governed property.

---

## 8. Mapping to DSM / P0→P9

The reassuring chapter: the registry is **additive**, a governance wrap, not a rewrite.

- **Observed** already exists — events, artifacts, content hashes captured by P1/P2/P6.
- **Storage / hash chain / RR** already exist — DSM (P3) writes, RR (P5) is the only read path.
- **Derived** already exists — the recall/adjacency work (P5/P8/P9), in-memory and recomputable.

The registry layers *over* these: proposals and events become the governed entry/standing
mechanism; the read contract becomes the governed exit; `content_hash` remains the universal
join key; RR remains the only read path. P0→P9 is unchanged underneath. The same discipline
that carried ten milestones — additive, atomic, kernel untouched — governs the registry's
construction.

---

## 9. Non-goals

PRL explicitly does **not** do:

- psychology, personality, or preference modeling of the person;
- asserting truth (or "probable truth");
- reasoning, planning, or dialogue — those belong to agents;
- making decisions — it records the standing of decisions, it does not take them;
- replacing DSM (it composes it), replacing agents, or replacing LLMs;
- being a general-purpose vector database or a general-purpose knowledge graph.

Stating these here removes the most likely misreadings before they appear.

---

## 10. Consequences

- This document stays at the level of roles, boundaries, and responsibilities. **Vocabulary**
  (normative definitions of the terms used here) is ADR-PRL-0003; **Protocols** (contract/event
  shapes, the MEF's concrete form) are ADR-PRL-0004; **Implementation** (objects' attributes,
  identity formation, storage, language, APIs) is ADR-PRL-0005.
- Like 0001, this is a declared, supersedable artifact — now ratified by Mohamed (the human
  authority root). It was not self-accepted; the Registry never ratifies itself.
- New ideas surfacing during 0002 do not edit it — they go to a Future Deliberations holding
  pen and are taken up only via a superseding ADR.

> **PRL does not make project knowledge true. It makes project knowledge governable.**
