# Product Observations — the construction phase's journal

**Status:** Practice (a log of *observed* product signals, not proofs) · **Date:** 2026-07-01

The Second Epoch had the **Proof Log** — *why the model moved.* The construction phase adds this: a log of
**what using the surfaces reveals**, and how it **steers** product decisions. An observation is not a proof
(🟢) and not a shipped surface (🔵) — it is a **signal from real use** that advances or defers a frontier.
The rule that governed robustness holds here too: **we do not introduce new machinery until an observed
behaviour makes it necessary.**

---

## O-001 — KnowledgeObjectProjection v1.1 · raw claim content removes the motivation for a content compiler

**Surface:** `KnowledgeObjectProjection` v1.1 (`prl object --subject`, PR #111) · **Method:** observation
protocol on **eight realistic objects** (clean / aligned-multi / contested-claim / divergent /
3-claim-divergent / unsettled / recent / old), run repo-side, raw answers visible · **Date:** 2026-07-01 ·
**main = 6ea6ff9**

**Observation.** Across eight realistic objects, exposing the raw claim `answer`s **removed the primary
motivation for content compilation**. Reading a divergent object (`✓ PostgreSQL` / `✗ SQLite (simpler ops)`;
`✓ OAuth2 with PKCE` / `✗ Stateless JWT` / `? Server-side sessions`), the user does **not** mentally
*synthesize a third statement* — they **compare competing alternatives**. The object reads as an **argued
history / a decision space**, not a document to compile.

**The reframe (the real finding).** The Object View was assumed to answer *"what does the object say?"*. In
use, it answers, much better, *"why is this the decision that governs?"* — and that second question is
**exactly what DSM already does** (proposals, resolutions, standing, receipts). The value was under-read,
not missing.

**What it defers.** **#4b-C (content/lineage compiler) is deferred** — **not disproven**, but **no longer
the natural next step.** There is, as of this observation, **no observed need to "compile content"**: raw
answers + governed standing + reason already let the user read the object.

**What it reveals (the new, different need).** Reading the alternatives, the natural next want is to
**navigate the decision space**, not to compile it: *when* did PostgreSQL win, *who* rejected SQLite,
*why*, *which receipt*, *what discussion* led there. The dominant unmet need is **richer navigation
(history, receipts, discussions, current-vs-alternative)** — exploration, not synthesis.

**The hypothesis it invalidates.** We implicitly held `Object View → missing content → compiler`. The run
shows instead `Object View → raw content sufficient → need navigation`.

**The good news.** The model built during the Second Epoch is **more expressive than assumed**: the first
product surface already works on **derived projections**, with **no compiled object** required. #4b-C, if it
ever returns, would *improve what is displayed*, not *define what an object is*.

**Steer.** Next product move = **richer navigation of the decision space** (a Knowledge-Object navigation
surface), **not** #4b-C. Candidate shapes to ground/confirm:
`Object → Current decision → Alternative decisions → History`, or
`Knowledge Object → { Decision · Timeline · Discussion · Receipts · Claims }`.

*(Caveat: one observation is not proof #4b-C is useless — it is the first product signal that it is not the
next natural step.)*

---

## How to add an entry
One entry per real-use signal that changes a product decision. State: the surface, the method, the
observation, what it **advances** or **defers**, and the **steer**. Not a proof (🟢) and not a build (🔵) —
a signal. No steer without an observation to back it.
