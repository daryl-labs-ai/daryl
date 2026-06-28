# ADR-PRL-0003 — PRL Vocabulary (Normative Glossary)

**Status:** Accepted — ratified-by-Mohamed 2026-06-26 · **Version:** v1 · **Date:** 2026-06-26 · **Regime:** `declared`
**Depends on:** ADR-PRL-0001 (Constitution), ADR-PRL-0002 (Architecture)
**Nature:** *normative*, not documentary. These definitions bind. A protocol or
implementation that uses a term against its definition here is wrong, not creative.

> **PRL does not make project knowledge true. It makes project knowledge governable.**

**ADR series:** 0001 Constitution · 0002 Architecture · **0003 Vocabulary** ·
0004 Protocols · 0005 Implementation. Vocabulary precedes protocols on purpose: protocols
*use* these words, so their meaning is fixed first, or each protocol redefines them by accident.

**Reading note.** Each entry gives a **Definition**, the **Always** / **Never** clauses that
make it binding, and **Derives from** (the law or boundary it answers). Terms marked
*(working name)* are deliberately provisional — kept for the whole design phase, expected to
stabilize under use, as DSM's own vocabulary did.

---

## Core objects

**Claim**
Definition: the smallest reusable epistemic statement the registry holds standing about.
Always: transported with a Minimal Epistemic Frame. Never: implies truth.
Derives from: L5, L6, L8.

**Proposal**
Definition: a suggested interpretation emitted by a producer, offered for governance.
Always: attributed to its producer. Never: modifies registry state directly; never the same
thing as the Claim it proposes. The *only* object an agent may create.
Derives from: L7, Boundaries §2.

**Evidence**
Definition: what a proposal points to in support of itself.
Always: referenced. Never: owned by a single proposal; never itself an assertion of truth.
Derives from: L5, L12.

**Registry Event**
Definition: a recorded, attributed fact that a Claim's standing changed.
Always: attributed and recorded. Never: silent. The *only* thing that moves standing.
Derives from: L8, L11, L12.

**Knowledge Object** *(working name)*
Definition: a Claim that has reached stable standing through ratified Registry Events — the
durable anchor many observations attach to.
Always: emerges through ratification. Never: created directly by any actor.
Derives from: L4, L7. *Provisional name — too generic; revisit when the architecture lives.*

---

## Tiers

**Observed**
Definition: a fact — an artifact or event as it exists, independent of PRL.
Always: immutable. Never: produced by inference; never altered.
Derives from: L2.

**Derived**
Definition: an interpretation computed over the Observed.
Always: recomputable and versioned; attributed to its producer. Never: immutable; never
promoted to Observed.
Derives from: L2, L3.

**Person-model**
Definition: an inference about the *person* (personality, psychology, preference).
Always: out of scope. Never: persisted by PRL.
Derives from: L1, L2. (Defined here precisely to forbid it.)

---

## Regimes & standing

**Witnessed**
Definition: a regime of the Observed — captured by PRL at the moment it happened.
Always: strong default trust. Never: assignable after the fact.
Derives from: L3, L14.

**Imported**
Definition: a regime of the Observed — recorded after the fact from external history.
Always: probabilistic default trust. Never: promoted to Witnessed.
Derives from: L3, L14.

**Recovered**
Definition: a regime of the Observed — reconstructed from partial or secondary traces.
Always: lowest observed-trust, flagged. Never: presented as Witnessed.
Derives from: L3.

**Declared**
Definition: asserted by a human as a starting point (a Knowledge Space, a config, this ADR).
Always: attributed to the human who declared it. Never: treated as a derived inference.
Derives from: L4.

**Witnessed-forward / Reconstructed-backward**
Definition: the two epistemic regimes — knowledge PRL saw as it happened vs knowledge it
reconstructs afterward. Always: the regime sets a claim's default confidence. Never: blended
so a reconstructed claim looks witnessed.
Derives from: L3.

**Epistemic Standing**
Definition: a Claim's current governed status — the cumulative result of its Registry Events
(e.g. proposed, accepted, rejected, superseded, withdrawn).
Always: changes only through Registry Events. Never: a truth value.
Derives from: L8, L11.

**Ratification**
Definition: the act that promotes a derived candidate to stable standing.
Always: performed by a human or by witnessed-at-creation provenance; itself recorded and
attributed; revocable. Never: performed by inference; never permanent-by-default.
Derives from: L4, L11.

---

## Frames

**Minimal Epistemic Frame (MEF)**
Definition: the non-strippable envelope a Claim always carries — regime, confidence,
contested?, and a handle to fetch more.
Always: present on every emitted claim. Never: stripped, at write or read.
Derives from: L5, L6.

**Extended (Epistemic) Frame**
Definition: the full dossier, fetched on demand via the MEF handle — provenance, producer,
evidence, ranking explanation, producer/policy version, contradictions.
Always: reachable. Never: mandatory inline (tiered disclosure, to respect a finite context).
Derives from: L5, L10.

---

## Producers & salience

**Producer**
Definition: any actor that creates a Claim, a Registry Event, or an ordering — human, agent,
collector, extractor, ranker.
Always: identified. Never: anonymous.
Derives from: L10, L12.

**Policy (Ranking Policy)**
Definition: the versioned, attributed rule that produces an ordering.
Always: attributed and versioned; exposes its reasons. Never: neutral or hidden.
Derives from: L10.

**Salience**
Definition: the authority PRL exercises when it selects, ranks, or pushes context.
Always: explicit, evidenced, auditable. Never: a claim of truth; never silent.
Derives from: L10, L11.

---

## Spaces & relations

**Knowledge Space**
Definition: the boundary of a project — a curated set of sources (repos, chats, docs, mail…)
that may span many and to which an item may belong to several or none.
Always: anchored by human declaration/curation; inference only suggests membership. Never:
reduced to a single folder path.
Derives from: 0001 §"what is a project", L13.

**contradicts / supersedes**
Definition: governed relations between Claims representing disagreement and replacement.
Always: preserved and visible. Never: silently flattened; superseded claims are retained,
visibility (not existence) is what changes.
Derives from: L9 (negative/contested findings), §7 state machine.

---

## Identity (handles — full roles in 0002 §5)

**ClaimID / ProposalID / EvidenceID / ProducerID / PolicyID / KnowledgeObjectID**
Definition: stable handles that let a thing be *referenced across time without implying truth*.
Always: identity precedes attributes. Never: a handle by itself asserts standing or truth.
Derives from: 0002 Principle 10. *(How they are formed is 0005.)*

---

## Consequences

- These definitions bind 0004 (Protocols) and 0005 (Implementation): a protocol that uses a
  term against its definition here is in error.
- Like 0001/0002, this is a declared, supersedable artifact — ratified by Mohamed (human
  authority root); PRL never ratifies itself.
- *(working name)* terms — currently **Knowledge Object** — are tracked for renaming once the
  architecture is in use; a rename is a superseding ADR, not an in-place edit.

> **PRL does not make project knowledge true. It makes project knowledge governable.**
