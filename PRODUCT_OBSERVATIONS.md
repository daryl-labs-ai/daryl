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

## O-002 — Object View v2: decision navigation is sufficient before content compilation

**Surface:** Object View v2 (`prl object --subject`, five sections — Current decision · Alternatives ·
Discussion · History · Receipts, PR #112) · **Method:** observation run on **seven realistic objects**
(clean / accepted / contested-conflict / divergent-rich / 3-alternative / unsettled / recent), repo-side,
throwaway store, no credential · **Date:** 2026-07-02 · **main = 8bbe60c**

After exercising Object View v2 on seven realistic objects, the dominant product signal is that users can
understand the object as a governed decision space: current decision, alternatives, discussion, history, and
receipts. Even on rich divergent objects such as database.choice, the raw claim answers plus governed status
and decision-thread history make the object understandable without requiring a compiled content statement.

This does not prove #4b-C is unnecessary. It shows that #4b-C is not the next observed need. The next product
need remains navigation and presentation over certified decisions, not content merging.

**Decision.** #4b-C stays **deferred durably** (not disproven). Continue with product / navigation surfaces.
The reading held on the *complete* surface (v2), including the strongest test case (`database.choice`): the
user reads "PostgreSQL won · SQLite was the rejected alternative · why/when/by whom · receipts · navigable" —
and does **not** first reach for a compiled "what the object concludes".

---

## O-003 — Content search makes Knowledge Objects findable without introducing persistent map entities

**Surface:** Object search v1 (`prl objects --search`, PR #115) · **Method:** observation run on **seven
realistic objects** across two orgs, five queries (content · resolver · decision · org · a negative case),
repo-side, throwaway store, no credential · **Date:** 2026-07-02 · **main = 076c82e**

An object is now findable along **several dimensions already present in its acts**: content
(`--search postgres` → `database.choice`, via a raw `answer`), resolver (`--search alice` → the three objects
alice *resolved*, never proposed), organization (`--search org.acme`), and decision (`--search rejected`). Each
result carries its **provenance** (`match [answer]`, `match [agent]`, `match [decision]`, `match [org]`), so the
search stays **explainable**. A negative term (`--search oracle`) returns nothing — no false positives. Measured
cost is ~3.6 ms for the **whole** `discover_objects` pipeline (per-subject standings + governance recompute *and*
the match), which justifies **no persistent index** at this scale.

*(Honest note: `--search rejected` returns four objects, not the three the run prompt predicted — the prediction
was inconsistent with its own seed. `cache.strategy` carries a certified `rejected` resolution (bob, the #2
conflict), so it legitimately matches `[decision] rejected`. The behaviour is correct — decision search surfaces
conflict resolutions too, which is the right and useful reading: an object where a claim was rejected **is**
relevant to "rejected". The actual (4) is reported, not adjusted to the prediction.)*

**The reframe (the real finding).** O-003 is not merely "search works". It is that **Knowledge Objects are now
discoverable by their derived semantics — without becoming persisted entities.** We build a **derived map** (a
reverse read over the acts), but introduce **no authoritative node** (`Agent`, `Org`, …). Discovery gained a new
axis with no new model.

**Continuity — navigation keeps winning over modeling.** Three successive product observations point the same
way: O-001 — the user *navigates* decisions rather than a compiled document; O-002 — even with the complete
enriched view, the compiler (#4b-C) does not become necessary; O-003 — objects are now *found* by what they
represent, without a persistent graph. The value keeps coming from **navigation over derived projections**, not
from new entities or a content compiler.

**The trajectory it inverts (the most interesting result of this phase).** At the start of the construction phase
the natural path looked like `Knowledge Object → Compiler (#4b-C) → Maps`. After O-001 / O-002 / O-003 it reads
instead `Knowledge Object → Navigation → Navigation → Navigation → (perhaps, one day, #4b-C)`. Three product
observations in a row pushed the compiler's necessity back — **without ever modifying the model.** This does not
prove #4b-C is useless; it shows it is **no longer the next problem to solve**. That is exactly the kind of
decision the discipline (observe before building) was meant to make possible.

**Steer.** Continue navigation over derived projections. Candidate next moves stay on that axis (agent/org as
*navigable views* — still not authoritative nodes; object↔object relations; the decision-layer ↔ code-graph
bridge), or a governance rule ((ii) authority / (iii) required supersession). #4b-C remains deferred durably.

---

## How to add an entry
One entry per real-use signal that changes a product decision. State: the surface, the method, the
observation, what it **advances** or **defers**, and the **steer**. Not a proof (🟢) and not a build (🔵) —
a signal. No steer without an observation to back it.
