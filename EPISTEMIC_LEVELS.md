# Epistemic Levels — a discipline for the manifesto (so it never drifts into philosophy)

**Status:** Discipline / method (non-binding) · **Date:** 2026-06-27

As the abstraction has climbed, a new risk appeared: turning experimental success into permanent
truth, and turning vision intuitions into architectural rules. This grid protects the project *against
itself* by forcing every statement to declare its level.

## The governing invariant

The deepest invariant of the project is not Retrieval, not DSM, not even the Knowledge Fabric:

> **Every important idea in Daryl must have a governed lifecycle.**

Claims, Knowledge Acts, Knowledge Objects, ADRs, metaphors, questions, proofs, visions — each one
*emerges, is tested, is governed, evolves, and may disappear.* A concept without a governed lifecycle
is, from now on, an exception. This property depends on no LLM, no DSM, no Retrieval — it describes how
the project evolves its **own** ideas. The four rules below — **promotion** (only the proven),
**demotion** (whatever evidence invalidates), **classification** (each claim at its level), and
**non-answer** (`OPEN_QUESTIONS.md`) — together with the **Proof Log** (`PROOF_LOG.md`) are how this
invariant is enforced. The project governs its ideas the way it asks a project to govern its knowledge.

## The test

For any sentence in the docs, ask:

> **Can I still build Daryl if I delete this sentence?**

- **No** → it is a **Law** (Level 1).
- **Yes, but the product becomes incomprehensible** → **Vision** (Level 2).
- **Yes, and only the explanation becomes less elegant** → **Interpretation** (Level 3).
- **Yes, still** → **Positioning** (Level 4).

## The four levels

**Level 1 — Law.** Impossible to remove without breaking the architecture. Lives in the ADRs.
Examples: *Accepted ≠ True · the registry is a projection · the MEF (non-strippable) · the Knowledge
Act · the Adapter Strategy (integrations adopt PRL, not models).*

**Level 2 — Vision.** Follows *mechanically* from the laws. Lives in the manifesto. Examples:
*Models are replaceable; governance is permanent · the Knowledge Object is the unit of collaboration ·
a project is an accumulating body of governed knowledge.*

**Level 3 — Interpretation.** Strong and clarifying, but still philosophical — excellent for
*explaining*, not *necessary for building*. Lives in the manifesto **but is watched**. Examples:
*the project becomes a cognitive system · Daryl is an operating system · software organizes
knowledge.* Not false — *less falsifiable*. These are the sentences to monitor over time.

**Level 4 — Positioning.** Analogies: ERP, Ledger, ABI, Git. Very useful, fully replaceable. Lives in
the **incubating framings**, never in the law.

## Watch-list (current Level-3 interpretations)

Keep — they explain well — but treat as interpretation, not as law or proven vision; revisit if they
stop earning their place:

- "The project becomes a cognitive system."
- "Daryl is the operating system through which a project … evolves its knowledge."
- "Software organizes data. Daryl organizes knowledge."
- "A project is no longer … files, conversations, and tickets …" *(borderline Vision/Interpretation.)*

## Movement: promotion is never permanent

The project already has a promotion rule (incubating → canon), the classification rule above, and a
non-answer rule (`OPEN_QUESTIONS.md`). The loop closes with a fourth: a **demotion rule.**

> **No statement is promoted permanently. Every statement remains demotable by evidence.**

Retrieval v2 taught this directly: an idea that looked excellent — symmetric RRF as "best of both" —
was invalidated by a later experiment. The same discipline that built the engine governs the
concepts. Statements move *both ways*:

- a **Vision** can drop back to **Interpretation** if it stops following mechanically from the laws;
- an **Interpretation** can return to an **Incubating Framing** if it stops explaining well;
- a **Positioning** metaphor can be **deleted** if it stops predicting the right calls;
- even an **Accepted ADR** can be **superseded** — more rarely, and only by a new ADR.

Movement is bidirectional by design. **Promotion proves; demotion protects.**

### Signals (so movement rests on usage history, not impression)

Tracked in `FRAMING_DECISION_LOG.md` (which framing influenced which real decision):

- **Promotion signal.** A framing may be *reviewed for promotion* after it has supported at least
  **3 meaningful decisions without contradiction**.
- **Demotion signal.** A framing *must be reviewed* if it causes **2–3 misleading decisions, failed
  integrations, or protocol inconsistencies**.

The signal opens a *review*, it does not auto-promote or auto-demote — a human still ratifies the move
(and the move is recorded in `PROOF_LOG.md`).

## Why this matters

It keeps the manifesto from quietly becoming a philosophy paper, keeps the ADRs free of poetry, and
keeps positioning analogies from hardening into architecture. Each claim stays at its true altitude.
