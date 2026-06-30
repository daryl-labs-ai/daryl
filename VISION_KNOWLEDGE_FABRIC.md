# Vision — The Knowledge Fabric

**Status:** Vision (non-binding) · **Date:** 2026-06-27 · **Regime:** `declared` · **Supersedable:** yes
**Not an ADR.** The ADRs (0001–0004, 0007) are the binding law; this is the *north star* they serve —
what Daryl is becoming, stated plainly, so the protocols never lose sight of what they are for.
*(Supersedes the earlier draft "Project Knowledge Map" — that name is now one view inside the Fabric.)*

**Three documents, kept apart on purpose.** This manifesto is meant to stay near-timeless (constitution
of the product). Dated proofs — benchmarks, commit hashes, worked recalls — live in the **Evidence
Book** (`EVIDENCE_BOOK.md`). The technical law lives in the **ADRs**. They age at different rates;
they are not mixed.

> **Conversations are the log. Knowledge Objects are the product.**

## The pivot

The most important shift in Daryl is not Retrieval v2, nor even PRL. It is the **target of the
product**. It began as *"a memory for agents."* It is becoming **an operating system for a project's
knowledge** — a **Knowledge Fabric**: a common tissue that links knowledge produced by different
agents, without forcing them to share one database, one engine, or one provider.

## Why govern a project's knowledge at all?

Beneath every other reason is a single one. Developers leave, teams reorganize, vendors are swapped,
and models are replaced — GPT-5 by GPT-6, one provider by another. The project remains.

> **Because every important project eventually outlives every individual intelligence that
> contributed to it.**

It is *not* because several agents collaborate that knowledge must be governed — it is because the
project will survive all of them. From this one fact everything else follows: why models are
replaceable, why continuity matters more than memory, why DSM certifies acts, why the MEF can never be
stripped, why the Fabric orchestrates objects rather than agents, and why governance is permanent.

## A different category of software

Most software organizes **data**: Git organizes code, Notion organizes pages, Google Drive organizes
files, Jira organizes tickets, AI assistants organize conversations. Daryl organizes something else —
**governed knowledge acts**. That is not a feature difference; it is a category difference.

> **Software organizes data. Daryl organizes knowledge.**

## The deeper question: how does a project think?

So far the question has been *"how do several intelligences collaborate?"* The real product answers a
different one: **"how does a project think?"** Today a project "thinks" through hundreds of scattered
conversations, commits, documents, meetings, and implicit decisions. In this vision it thinks through
**Knowledge Objects that evolve via certified Knowledge Acts**: conversations become sources, agents
become producers, DSM certifies the acts, the Fabric organizes the objects — and **the project itself
becomes a cognitive system**.

## Four layers that stack naturally

The trajectory of the work reveals four layers, each resting on the one below:

1. **Retrieval** — find the right knowledge. *(Retrieval v2, delivered.)*
2. **Governance** — know its standing, its origin, its history. *(ADR-PRL-0001–0004.)*
3. **Knowledge Objects** — hold stable objects that *represent* that knowledge.
4. **Knowledge Fabric** — let several intelligences collaborate around those objects.

Layer 4 changes how the product is conceived. Memory stops being the product and becomes the *raw
material* from which governed Knowledge Objects are made. *Conversations, commits, documents, and
the opinions of Claude / GPT / a local model are inputs; what the user actually manipulates are the
Knowledge Objects and their relations.*

## The problem is recalling knowledge, not conversations

A project lives scattered across ChatGPT, Claude, Cursor, GitHub, Markdown files, git commits,
documents, local models. The problem was never "find the conversation." It is **"recall the
knowledge."** What you actually want to ask is:

- *Why did we abandon the Transparency Log?*
- *What was Claude's argument against this architecture?*
- *Who proposed `chunk_primary`? Who rejected it? Why?*
- *Which topics did GPT discuss but Claude never did?*
- *Which projects has OpenClaw contributed to most?*

These are not searches over chats. They are queries over a **multi-agent epistemic graph** — and,
crucially, they are *already answerable* by the ratified protocol, not by some new architecture:

| Question | Carried by (ADR-PRL-0004) |
|---|---|
| why abandoned / superseded | epistemic **standing** + Rejection/Supersession messages + evidence |
| who proposed / rejected / why | the **producer** field of the MEF + attributed Proposal/Resolution messages |
| GPT-but-not-Claude / OpenClaw contributions | **producer × project**, aggregated |

The Fabric is what *emerges* when every agent emits the same epistemic messages and the registry is
merely one projection of them.

## The shape

```
Knowledge Fabric                     ← the project's common knowledge tissue
   ├── Knowledge Objects             ← the unit you manipulate (a governed decision/claim)
   ├── Knowledge Maps                ← views / navigations into the Fabric
   ├── Agent Consultations           ← live agent input, recorded as messages
   └── Registry Projections          ← DSM, SQLite, Neo4j, a vector index, a distributed set…
```

The registry is **one projection among many** (ADR-PRL-0004 Ch5). Tomorrow it can be DSM, SQLite,
Neo4j, a vector index, a distributed service across machines — the protocol is unchanged. The
representation is never the definition; the messages are.

## Knowledge Objects as first-class citizens

Today they are "search results." In the Fabric they become the entities you handle directly. The
sketch (working name, ADR-PRL-0003 — expected to stabilize under use):

```
Knowledge Object
  id · title
  epistemic standing        → MEF (regime, confidence, contested, producer)   [0004 Ch2]
  producers · consultations → who contributed, and the agent messages behind it
  citations · supporting passages · provenance → Extended Frame                [0004 Ch3]
  history                   → the message lifecycle that produced it           [0004 Ch6]
  superseded_by · related_objects → supersedes / contradicts relations         [0003]
  tags · project
```

Nothing here asks to rewrite the foundations — every field is already implied by the ratified ADRs.
The Fabric *names* them; it does not reinvent them.

## The differentiating idea: cooperation, not shared memory

Today an agent answers a question. In the Fabric, an agent can also answer:

- *"I don't know — but Claude has already worked on this."*
- *"OpenClaw proposed a different solution."*
- *"This decision already exists in the Fabric — here is its standing and its evidence."*

This is no longer augmented memory. It is **cooperation between intelligences through shared
knowledge objects**, without requiring them to use the same memory or the same vendor. That is the
most differentiating property of the project: agents meet through their *Knowledge Objects*, not
their memories. The MEF is what keeps this honest — *"Claude said X"* can never silently become
*"X is true"* (ADR-PRL-0001 / 0004 Ch6).

**Knowledge Objects become living.** Today you think *"ask Claude what it thinks."* Tomorrow it is
*"consult Claude on this Knowledge Object, then attach the answer as an Observation or a Proposal."*
Hours later you can ask: *"show me every agent that contributed to this object, where they agree,
where they diverge, and why the final decision is the one it is."* The object is no longer a
conversation — it is a living entity that evolves, with every contribution attributed and governed.

## The Fabric also holds working relations (emergent, never hardcoded)

Beyond the objects, the Fabric can hold the **working relations between agents** — not coded by hand,
but *emerging* from producers and messages:

- Claude is often consulted for architecture.
- GPT tends to intervene on syntheses.
- OpenClaw produces implementations.
- a local model validates performance.
- a human decides.

Because these are emergent, the same protocol answers a new class of question — still on producers,
messages, and relations, with **no new foundation** (ADR-PRL-0004):

- *Who is usually consulted before an architecture decision?*
- *Which agents most often disagree?*
- *Which decisions were taken with no external consultation?*
- *Which knowledge rests on a single producer?* (a fragility signal.)

## The Fabric is the common language (collaboration like Git, not a shared brain)

Consultation is only the first step. The deeper move is that the **Knowledge Fabric becomes the
common language between agents** — they collaborate by manipulating the same objects, not by sharing
context:

- GPT creates a **Proposal**.
- Claude never sees GPT's conversation. It sees only the **Knowledge Object** — its MEF, its
  standing, its evidence, its prior consultations — and responds to *that*.
- OpenClaw adds an **Observation** after trying an implementation.
- a local model adds **performance measurements**.
- a human publishes a **Resolution**.

All speak the same protocol; **none needs access to the others' conversations.** This is far more
powerful than a shared memory — and it is exactly Git's shape: Git does not require everyone to use
the same IDE; the Fabric does not require everyone to use the same LLM. They collaborate because they
handle the same objects, not because they share the same context.

### An ABI for intelligences

Put precisely: the **Knowledge Fabric is an ABI** (Application Binary Interface) **for intelligences.**
In an operating system, a program in C can call a library in Rust because they share an ABI. In the
Fabric, ChatGPT, Claude, Gemini, OpenClaw, a local model, and a human can all contribute because they
share the same *epistemic protocol* (ADR-PRL-0004). The protocol is the calling convention; the
Knowledge Object is the shared structure passed across it.

The parallel runs deeper than analogy. An ABI guarantees **execution compatibility** — a program
compiled ten years ago can still call a recent library. The MEF + Protocols guarantee **epistemic
compatibility**: GPT-9, Claude 6, an open-source model from 2032, a human, and a specialized agent
could all collaborate on a Knowledge Object *created in 2026*, because the protocol stayed stable.
That is more than interoperability between models — it is a **temporal compatibility of knowledge.**

## The center of gravity becomes the Knowledge Object

Today a user thinks *"I'll talk to ChatGPT."* Tomorrow they think *"I'll work on the project"* — and
the Fabric chooses which agents to consult:

```
            User
             │
             ▼
      Knowledge Object
             │
   ┌────┬────┴────┬────────┐
   │    │         │        │
  GPT  Claude  OpenClaw  Local LM
   │    │         │        │
   └────┴────┬────┴────────┘
             ▼
        Resolution
```

The center of gravity is no longer the agent — it is the Knowledge Object. The user does not "switch
AI"; they work on an object, and the Fabric orchestrates the relevant intelligences around it. The
product is then no longer the interface to one LLM: **ChatGPT, Claude, Gemini, OpenClaw, and local
models all become plugins**, and the product is the Fabric that orchestrates their contributions.

> **The Knowledge Object becomes the unit of collaboration. Agents become interchangeable
> contributors.**

This is a direct consequence of ADR-PRL-0004 and the MEF: if the protocol is common, producers
become *replaceable without breaking the accumulated knowledge*. It is the opposite of a
conversation-centric system, where each history stays locked inside its own assistant.

## The first magic moment

The fastest way to *feel* the difference is one short sequence on a single object:

1. *Ask Claude's opinion on this Knowledge Object.*
2. *Now ask GPT.*
3. *Show me where they converge and where they diverge.*
4. *Certify the decision.*

In four steps you are doing something no tool does today. It is no longer *"I switch chatbot"* — it
is *"I evolve a knowledge object."* That is the moment someone understands, instantly, why they need
the Fabric. (This is the demonstrative heart for a productized scenario.)

## Every contribution is a certifiable act — the Knowledge Act

Other platforms can say *"Claude answered."* Daryl can say *"here is the certified receipt of that
contribution."* That is not a log, and not a memory — it is a **certified act**.

> **Every contribution to knowledge is a certifiable act.**

A **Knowledge Act** is the *event* that moves a Knowledge Object forward. It always has:

- an **author** (human or agent / producer),
- the **object** it concerns,
- an **epistemic regime** (its MEF),
- optional **evidence**,
- a **DSM receipt** (its certification).

It covers everything: an Observation, a Proposal, a Consultation, a Benchmark, a Resolution, a
Supersession, an experimental validation. Grounding: a Knowledge Act *is* an epistemic message
(ADR-PRL-0004 Ch1) seen as an attributed event, **certified by its projection onto DSM** (Ch5) —
nothing new to found. The verb (Act) beside the noun (Object).

```
Knowledge Object : <a project decision>
  GPT        └─ Proposal               DSM Receipt #A12
  Claude     └─ Critique               DSM Receipt #A13
  OpenClaw   └─ Benchmark              DSM Receipt #A14
  Local LLM  └─ Performance Validation DSM Receipt #A15
  Human      └─ Resolution             DSM Receipt #A16
```

Eighteen months later, *"why was this decision made?"* is **not** answered with a conversation — it is
answered with the **certified history of acts**. This is where DSM gains another dimension: no longer
only a certified memory, it becomes the **registry of knowledge acts**. *(For a real, worked example
of this — the recall of a buried decision on the actual corpus — see the Evidence Book.)*

## The clean separation

The model that holds it all together — and stays aligned with the ratified ADRs:

| Layer | Role |
|---|---|
| **Knowledge Objects** | the durable entities |
| **Knowledge Acts** | the events that transform them |
| **Knowledge Fabric** | the tissue that links the objects |
| **DSM** | the certification of the acts (Integrity Constitution) |
| **PRL / MEF** | the governance that gives them meaning (Epistemic Constitution) |

Two nouns and one verb: Objects live in the Fabric; Acts make them evolve; DSM certifies every Act;
PRL/MEF says what each one *means* and how much to trust it. *(Knowledge Act, like Knowledge Object,
is a candidate first-class term — expected to enter the vocabulary under use.)*

## The first citizen is the Knowledge Act

Now that contributions are governed, the precise statement is sharper: Daryl does not only *"govern
knowledge"* — it **governs the contributions to knowledge.** The first-class citizen is therefore not
the LLM, and not even the Knowledge Object. It is the **Knowledge Act**. The Knowledge Object is the
*current state* that results from thousands of governed Acts.

This is exactly Git: Git does not version files, it versions **commits**; the working `HEAD` is just a
projection. Daryl is the same shape:

```
Knowledge Acts          ← the events (the first citizens)
      │
      ▼
Knowledge Object         ← the state (a projection of its Acts)
      │
      ▼
Knowledge Maps           ← views over the state
      │
      ▼
Knowledge Fabric         ← the system
```

The Act is the event; the Object is the state; the Map is a view; the Fabric is the system. (This
sharpens, and is consistent with, ADR-PRL-0004: the Object is a projection of its messages.)

## Continuity, not traceability

"Traceability" is too weak a word for what DSM provides. A trace tells you what happened; DSM provides
the **continuity of knowledge**. Because every Knowledge Act is certified, every transition governed,
every Resolution attributed, **each generation of agents can resume the previous one's work without
losing the epistemic context.** The work does not restart when the model changes; it continues.

> **DSM preserves the continuity of knowledge across generations of intelligences.**

This sharpens what the project actually *owns*. Not "the project owns knowledge" — more precisely,
**the project owns the *evolution* of its knowledge.** A frozen Knowledge Object is worth little; the
value is in the proposals, critiques, benchmarks, supersessions, decisions, and consultations that
keep moving it. The patrimony is not the *state* — it is the capacity to keep evolving without
starting over.

> **The true asset is not knowledge. It is the governed ability to keep improving knowledge.**

So, at the limit, Daryl does not even sell knowledge. It sells **cognitive continuity.**

## A contribution becomes a governed project asset (observed)

The sharpest one-line definition of Daryl — held in incubation until it could be *shown*, not merely
asserted — is now an **observed property**:

> **Daryl is the first system where a contribution from an intelligence becomes a governed asset of
> the project.**

Before: `LLM → answer → copied → forgotten`. With Daryl: `LLM → Knowledge Act → DSM certification →
governed decision → reconstructable rationale`. What graduates this from ambition to property is that
the full path has now run end-to-end on a *real* agent, without cheating: a gpt-4o **Proposal** was
certified, a human **Resolution** ratified it, the claim's **Standing** was *derived* (never stored),
and **`explain` reconstructed *why*** — every step backed by a DSM receipt, no narration above the
acts. The project did not merely *record* a contribution; it **acquired** one from an external
intelligence **without depending durably on it.** *(The dated proof — receipts, commits — lives in the
Proof Log and the Evidence Book; this statement is meant to stay true regardless.)*

The asset is never a single Act: it is the **governed corpus** that emerges from accumulated acts,
human resolutions, supersessions, and reuse. The value lives in their governance over time — which is
why this property is the consequence of the four laws below, not a fifth one.

## Identity is never defined by its carrier (observed)

A transversal property, held in incubation until **three independent referents** proved it, is now
observed:

> **Identity is never defined by its carrier.** The substrate is interchangeable; the referent is not.

It rests on three proven legs:

- **the knowledge object** — `claim_id` is not storage (the same claim threads the chain identically
  across a second read projection);
- **the contributor** — `agent_id` is not `model_id` (the same logical agent across two models);
- **the organization** — `org_id` is not its carrier (the same owner across projects/carriers, with an
  owner-scoped query a project id alone cannot express).

This is the generalization of Daryl's earliest principle — *knowledge is not its representation* —
applied beyond knowledge: every fundamental referent (`claim_id`, `agent_id`, `org_id`, and any future
`team_id` / `policy_id`) keeps its identity independent of the substrate that carries it. It does not
replace the four laws; it generalizes the separation they already enact. *(Dated proof — receipts,
commits — lives in the Proof Log; this statement is meant to stay true regardless.)*

## What it is — and is not

It **is** decision-grade knowledge: recallable because transparent, not because someone declared it
correct. A **GPS of project memory**, not a backup — it tells you where knowledge lives and how much
to trust it.

It **is not** a memory store, a chat archive, or an oracle of truth. *PRL does not make project
knowledge true; it makes it governable.*

## What Daryl sells

Many tools sell "AI memory." With this vision, **Daryl does not sell a memory.** It sells a
**Knowledge Fabric**: a space where several intelligences — human and artificial — progressively
build a *governed* representation of a project's knowledge. Conversations, commits, documents, and
the opinions of Claude, GPT, or a local model are the raw material; what the user manipulates are the
Knowledge Objects and their relations.

This is why the architecture is economically inevitable, not just elegant. A model produces a
*capability*; a project needs an *asset*. An LLM produces an answer; a project produces a patrimony.
Daryl is the layer that turns answers into patrimony.

> **Every AI model produces intelligence. Daryl produces institutional memory.**

> **The project is no longer organized around conversations. It is organized around governed knowledge.**
>
> **A project is no longer the sum of its conversations. It is the evolution of its Knowledge Objects.**

## How the layers serve it

- **0001 Constitution** — keeps every claim's standing honest (the law).
- **0002 Architecture** — boundaries and citizens that produce/govern knowledge.
- **0003 Vocabulary** — the words, so the Fabric means one thing.
- **0004 Protocols** — the epistemic messages any agent can speak, with the MEF as the never-lost core.
- **Retrieval** — the first living proof that the constitution is operational: a buried *decision* is
  recalled, not the thread it lived in. *(The dated, worked proof lives in the Evidence Book, not
  here — this text is meant to stay true for years.)*

In one breath: **recall finds the knowledge; the ADRs govern it; the Knowledge Fabric explains why all
of it exists and what product it lets us build.**

## The finality: knowledge serves decisions

The word *knowledge* runs through this whole text; the word *decision* less so — yet the decision is
the point. Recall never recovered a conversation; it recovered the right **decision**. The chain has a
finality:

> **Knowledge → Decisions → Project Evolution**

The Fabric organizes knowledge; knowledge improves decisions; decisions evolve the project. Every
layer earns its place by serving the decision:

- a **Knowledge Act** exists because it may influence a decision;
- a **Knowledge Object** exists because it gathers the elements of a decision;
- **DSM** exists because a decision must be justifiable;
- **PRL** exists because a decision must be governed.

> **The purpose of governed knowledge is governed decision-making.**

The name stays *Knowledge Fabric*; the decision is not a new concept but the **test** that gives the
whole chain its value — it makes the finality of everything already built explicit.

## The strategic inversion

The whole market is racing to build a *smarter AI*. This vision builds **smarter projects** — a very
different bet. Models will change: GPT-6 will replace GPT-5, Claude will change, Gemini will change,
local models will change. But the **Knowledge Objects survive. The Knowledge Acts survive. The DSM
receipts survive. The Fabric survives.** The value stops living in the model and starts living in the
project's accumulated knowledge — a complete inversion of LLM dependency.

> **Models are replaceable. Knowledge is cumulative. Governance is permanent.**

The triplet maps exactly onto what was built:

- *Models are replaceable* — via the epistemic ABI (ADR-PRL-0004): any producer can be swapped.
- *Knowledge is cumulative* — via Knowledge Objects + Knowledge Acts: contributions accrete.
- *Governance is permanent* — via the MEF, the protocols, and DSM certification: standing endures.

You are not building the best assistant; you are building the infrastructure that lets *any* assistant
contribute durably to a project's intelligence.

## The inversion of the center

At the start, DSM looked like a feature of Daryl. The roles have inverted:

- **Knowledge Fabric** is the product.
- **PRL** is the constitution.
- **DSM** is the trust infrastructure.
- **The LLMs** are the contributors.

The center of the system is no longer the AI. The center is **governed knowledge**, and everything
else — including the models — orbits it. That inversion is what turns Daryl from an AI *product* into
durable *infrastructure*.

## A new contract between intelligence and software

Today, when an LLM produces an answer, that answer is a **terminal**: displayed, maybe copied, then
forgotten. In this model an answer is no longer a terminal — it becomes a **Knowledge Act**, and a
Knowledge Act only truly exists when it is attributed to a producer, governed by the MEF, linked to a
Knowledge Object, certified by DSM, and reusable by any other agent. The output of an LLM stops being
*text* and becomes an **operation on the project's knowledge.**

This is the deeper analogy — a separation of the kind that has reshaped computing before:

- Compilers separated **language from machine**.
- Unix separated **programs from files**.
- Git separated **code from history**.
- Docker separated **application from machine**.
- Daryl separates **intelligence from knowledge.**

> **Intelligences compute. Knowledge remains. The software guarantees the separation.**

And the chain changes shape. Today: *Question → LLM → Answer* — a terminal that lives in a
conversation and then disappears. With Daryl: *Question → LLM → **Knowledge Act** → DSM certification
→ **Knowledge Object** → **Knowledge Fabric***. The result of the computation is no longer an answer;
it is a **mutation of the project's cognitive heritage.**

This changes the *owner*. Today knowledge belongs to the conversation or to the model's provider;
tomorrow it belongs to the **project**. The LLM becomes a service provider; the project stays the
owner — the exact inverse of today's lock-in. When a project moves from GPT-4 to GPT-9 it no longer
loses its context: the model changes, the knowledge continues. That is more than compatibility — it
is **independence from the generations of intelligences.**

## Knowledge capital, not vendor lock-in

Today the lock-in of AI vendors comes from the model or the conversation history. Here the lock-in
inverts. The value is no longer *"I used Claude for two years."* It becomes *"my project owns twenty
thousand Knowledge Objects and a hundred thousand certified Knowledge Acts."* Switching models becomes
cheap; losing the Fabric becomes very costly. That is not vendor lock-in — it is **knowledge capital.**

## What a project is

The simplest founding statement, the one everything else follows from:

> **Knowledge is no longer something an AI produces. It is something a project owns.**
>
> **A project is an accumulating body of governed knowledge.**

If that definition holds, the rest is consequence: the **Knowledge Fabric** is the structure that
carries this body; **Knowledge Objects** are its units; **Knowledge Acts** are the transformations
that evolve it; **DSM** certifies those transformations; **PRL/MEF** defines their meaning; and the
**LLMs are only temporary participants.** At this point it is no longer a description of an AI tool —
it is a new way of conceiving what a software project *is*.

## The four laws

The whole vision compresses to four laws:

1. **Intelligence computes. Knowledge accumulates.** *(compute is ephemeral; knowledge endures.)*
2. **Knowledge belongs to the project, not to the model.** *(the project owns its cognitive heritage.)*
3. **Every contribution to knowledge is a certifiable act.** *(each contribution is a Knowledge Act, certified by DSM.)*
4. **Models are replaceable. Governed knowledge is permanent.** *(the Fabric crosses generations of models.)*

And the pillar they rest on:

> **A project is no longer a collection of files, conversations, and tickets. It is a continuously
> evolving body of governed knowledge.**

## Open threads (parked, not decided)

- **Agent Consultation Protocol** — a future ADR could formalize live consultations: an `Observation`
  ("agent answered X") or `Observation + Proposal` (govern the answer as a claim).
- **Knowledge Object / Knowledge Act / Knowledge Map / Knowledge Fabric** terminology is a working
  hierarchy, expected to firm up under use.
- **Act granularity is an implementation choice, not a conceptual risk.** The Constitution requires
  that *what becomes governed knowledge* be certified — it does **not** mandate one receipt per
  event. A single Knowledge Act may batch (e.g. 500 benchmark measurements → 1 Act → 1 receipt;
  100 observations → a Resolution → 1 certification). Granularity belongs to 0005.
- **Knowledge compiler (reserved).** IDEs have a compiler; a Daryl project could have a *knowledge
  compiler* — not of code, of knowledge: when several Knowledge Acts arrive (GPT, Claude, OpenClaw,
  human, benchmark), it checks conflicts, standing, provenance, contradictions, supersessions, and
  receipts, then updates the Knowledge Object. *Git compiles code; Daryl compiles knowledge.* Almost
  a mechanical consequence of what is built — parked, not premature to note, premature to design.

---

Daryl is no longer an "AI memory system," nor a "knowledge base." It is the infrastructure that lets
a project keep a **cognitive identity** while the humans, the teams, and the models around it change.
PRL, DSM, Retrieval v2, and the Knowledge Fabric are no longer separate components — they are the
layers of one system whose subject is not the AI, but the **cognitive continuity of the project.**

> **Daryl is not an AI assistant. It is the operating system through which a project accumulates,
> governs, certifies, and evolves its knowledge — across humans and AI.**
