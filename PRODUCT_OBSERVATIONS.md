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

## O-004 — Agent/Org views: navigation by projection is sufficient; the next need is seamless traversal between projections, not a graph model

**Surface:** Agent / Org Navigation Views v1 (`prl agent` / `prl org`, PR #117) · **Method:** observation
run on the **seven-object corpus** extended with a legacy (unknown-agent) act and a cross-org resolution,
six views (four agents incl. `unknown`, two orgs), repo-side, throwaway store, no credential ·
**Date:** 2026-07-02 · **main = 5be4d63**

**Observation.** Starting from an agent or an organization, their **participation is understandable with
zero new persistent structure**: contributed vs resolved (by certified decision, `⚠ contested` as a derived
flag), owned vs touched (disjoint, the resolution `org_id` finally in use), the unknown/legacy bucket
explicit. **No need for a graph appears.** What appears is a need for a **change of viewpoint**.

**The trajectory it completes.** Four observations now draw one coherent line:
O-001 — *I don't want a compiler, I want to understand why a decision governs.*
O-002 — *Raw answers suffice; I compare alternatives, I don't ask for a synthesis.*
O-003 — *I want to find objects by what they say, not only by their identifier.*
O-004 — *I can now start from an agent or an org and understand their participation — with no new
persistent structure.*
The "Knowledge Map" we imagined is **no longer a graph to build**. It is progressively appearing as a
**collection of projections**. That is the important discovery.

**The roadmap it rewrites.** The implicit route at the start of the construction phase was
`Knowledge Objects → Knowledge Map → Knowledge Compiler`. After four observations it reads
`Knowledge Objects → Navigation projections → Different entry points → (perhaps, one day) Knowledge
Compiler`. The compiler keeps receding.

**The doctrinal signal (now an architectural invariant, not merely a product decision).** The `agent` and
`org` views never read as *entities*. One never reads *"Here is Alice."* One reads *"Here is the world as
seen from Alice."* This confirms a doctrine that keeps stabilizing: **everything is a projection** — the
object is a projection, the agent is a projection, the organization is a projection. None of them needs to
exist as an authoritative node.

**The one new need (the steer).** Reading these pages, the missing thing is **not a data structure — it is
the hyperlink**: from `database.choice`, jump to `agent.architect`, then `org.acme`, then `search.engine`,
then `alice`, **without ever leaving the same navigation space**. Today every hop is a new CLI command (the
run's honest superseded-datum illustrates it: understanding why `auth.method` flipped to `REJECTED` after
dave's cross-org `superseded` act required manually chaining `prl agent dave` → `prl object auth.method`).
The next projection is therefore probably not "Knowledge Map v1" but something like **Linked Projections**
(Projection Navigation): each projection simply exposes the **already-existing identifiers**
(`subject_id`, `agent_id`, `org_id`, `claim_id`) **as navigation points**. Still zero entity, zero
persistent index, zero new model.

**Why this one matters.** This is an inversion even deeper than O-003's. At the start, we thought we were
building a *map*. After four observations, we may be building a **web of projections**. It is the first
genuinely new result of the product phase — no longer an interface refinement but an **architecture
hypothesis born from use**, exactly as the nine robustness frontiers were born from proofs.

---

## O-005 — Linked Projections v1 makes the projection web usable; the friction is missing direct edges, not missing state

**Surface:** Linked Projections v1 (`prl go <type> <id>` + typed annotations + the two display
fixes, PR #119) · **Method:** observation run under the **follow-annotations-only** discipline (a
hop may only target an id printed with its `[go …]` annotation on the current page; an un-offered
hop is a datum), primary + reverse chains on the O-004 corpus, per-hop friction log, repo-side,
throwaway store, no credential · **Date:** 2026-07-02 · **main = f9bebbb**

**Observation.** Linked Projections v1 makes the projection web **usable without an interactive
navigation shell**. The dominant friction is **not lack of state** — it is a **small set of missing
direct edges**, especially **agent→org**, plus the **separately emerging receipt hop**. `prl nav`
remains deferred.

**What the run confirms.** `go` works; the annotations work; claim↔object works in both directions;
the **object hub** works (every traversal meets an object); the noise rule is right (second bare
occurrences were never wanted); explicit typing is right; **no persistent graph and no entity are
needed.** The "web of projections" model (O-004) **holds in use**.

**The observed gaps, ranked.**
1. **Agent→org direct — the sharpest.** From an agent page one wants the orgs touched/involved
   (`orgs touched: org.acme [go org org.acme] · …`). Not `prl nav` — one missing printed edge (the
   `org_id` is already on the agent's acts; purely derivable).
2. **Object→object siblings — a weak signal, deliberately not built.** From an object one may want
   neighbours (same org, same agent, perhaps same decision status). This is closer to a real map:
   **noted as a signal, to be grounded later, not now.** (First time this deferred item surfaces
   from actual use.)
3. **Receipt hop — real but separate.** Receipts are printed everywhere; the absence of
   `prl receipt <hash>` is starting to show. Classified as an **independent candidate surface**,
   not a fix to `go`.
4. **Unknown/legacy bucket not link-reachable — acceptable for v1.** It is a diagnostic bucket,
   not daily navigation.

**Decision.** No `prl nav` now. **Agent→Org links (v1.1)** is the probable next increment. The
receipt hop stays a **separate candidate surface**. Object↔object relations get **grounded later**,
on more signal.

**The doctrinal conclusion.** The projection web works by **explicit edges, not by an interactive
session.** Navigation keeps being display + dispatch over derived projections — still zero entity,
zero persistent index, zero new model.

---

## How to add an entry
One entry per real-use signal that changes a product decision. State: the surface, the method, the
observation, what it **advances** or **defers**, and the **steer**. Not a proof (🟢) and not a build (🔵) —
a signal. No steer without an observation to back it.
