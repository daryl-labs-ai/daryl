# ADR-PRL-0011 — Governed Standing Layer (`governed_standing` above `raw_standing`)

**Status:** Accepted — ratified-by-Mohamed 2026-07-01 · **Version:** v1 · **Date:** 2026-07-01 · **Regime:** `declared`
**Depends on:** ADR-PRL-0001 (Constitution), 0004 (MEF), 0008 (Resolution / Standing v1 — latest-wins);
builds on the governance seam (step (c) v0) and #2 conflict visibility.
**Axis:** governance / standing contract. **Nature:** the project's **first governance *rule*** — the
first movement that changes **what a standing *means*** (all prior movements were additive derived
signals). Contract-level: it names the two standings and the derivation; the wiring is a later design/build.

> **Latest-wins is the raw projection. The *governed* reading is what counts when a claim is contested.**

## Why now
Thirteen Proof Log movements have all been **additive derived signals that preserved the rules**. The
governance **seam** (step (c) v0) proved a posture `clear | contested | divergent` can be **derived
read-only above latest-wins** — but it is **inert**: no consumer acts on it. The step (c) v1 grounding
found the **minimal consequential rule** is a **claim-scale contested standing, derived, as a *layer
above* latest-wins (mechanism B)** — which **bends no existing invariant**. This ADR fixes that rule as a
**contract** before any build, because it is the first change to what standing means and must be
**human-ratified**.

## Decision (the rule)

> Daryl distinguishes **`raw_standing`** from **`governed_standing`**.
> - **`raw_standing`** is **latest-wins** (Resolution v1) — **unchanged**, the projection primitive.
> - **`governed_standing`** is the **authoritative reading** of a claim's standing: it is **`contested`**
>   when the claim is in a #2 conflict (two distinct authorities opposed), and **otherwise equals
>   `raw_standing`**.
> `governed_standing` is the authoritative answer to *"what is this claim's standing?"*; `raw_standing`
> remains available as the raw projection.

## The load-bearing invariant

> **The governed reading is added *above* the projection, never *into* it.** `raw_standing` (latest-wins)
> is untouched; `governed_standing` is **derived every call, never stored** (mirrors #1). The rule adds a
> *reading*, it does not mutate the acts, the standing derivation, or the write path.

## The rules (minimal, contract-level)
1. **Two standings.** `raw_standing` (latest-wins, the projection) and `governed_standing` (the
   authoritative reading). They coincide **except** on contested claims.
2. **The governed value.** `governed_standing = contested` iff the claim is #2-contested, else
   `= raw_standing`. **`contested` is a `governed_standing` value that `raw_standing` never takes**
   (raw stays in `proposed | accepted | rejected | superseded | withdrawn`).
3. **Derived from the acts, not from a flag.** `contested` is derived from the **#2 conflict signal**
   (two distinct `agent_id` opposed). **`MEF.contested` is NOT consumed** — it stays the inert
   declarative hook it is today. Divergence must remain **provable from the certified acts**, never read
   from an ungoverned written flag.
4. **Claim scale only.** `governed_standing` is defined **per claim**. A **subject has no
   `governed_standing`** in v1 — it has no standing at all (#4b refused an object standing), so
   subject-scale governance **waits on an object standing** (the deferred #4b compiler).
5. **Derived, never stored (mirror #1).** Recomputed every call; drop every index/projection and it
   recomputes from the acts. No stored governance field on any node.
6. **A value, not a gate.** `contested` is a **standing value a consumer reads**; it does **not** block,
   escalate, or refuse any write. Committing resolutions is **unchanged**.

## What "authoritative" means (scope of the consequence)
`governed_standing` is the reading a consumer uses when it wants the **governed truth**; `raw_standing`
stays available as the projection primitive. In particular, **#4b coherence keeps reading raw governed
decisions** (`accepted`/`rejected`) — a contested claim's `raw_standing` is still its latest decision, so
**coherence is unaffected** and there is **no ripple**. The consequence of this ADR is precisely that a
**governed reading now exists and is declared authoritative** — the first time a divergence signal has a
consequence on what the standing *is*.

## Non-goals (hard scope fence)
No consumption of `MEF.contested`; **no write rule** (no required supersession); **no authority /
precedence** among resolvers; **no subject/object standing** (deferred to #4b); no kernel change, no new
`action_name`, no new writer. `raw_standing` (latest-wins), `claim_id`/`agent_id` minting, append-only
writes, and resolver equality are **untouched**. `contested` does **not** gate or block anything.

## Alternatives considered & rejected (for v1)
- **(A) Change `derive_standing` (latest-wins) directly** so the standing itself becomes `contested` —
  **rejected**: bends the latest-wins contract **and ripples** to `detect_coherence` (its
  `standing ∈ {accepted, rejected}` filter would exclude a contested claim), `explain`, and the
  governance layer. B achieves the same consequence **without** touching the projection.
- **Consume `MEF.contested`** — **rejected**: it is a **written-but-ungoverned** hook; consuming it now
  introduces a **premature write-time dependency** and lets a declared flag stand in for a proven
  divergence. Deriving `contested` from #2 keeps it **provable from the acts**.
- **Write rule (required supersession)** — **rejected for v1**: bends append-only validity, touches the
  write/commit path.
- **Authority / precedence** — **rejected for v1**: bends resolver equality, introduces an authority
  model (identity-adjacent). Heavier; a later, separate decision.

## Governance
This is the **first governance rule**; per the project's own discipline it must be **human-ratified**
before any design or build. (Daryl applies its own governance to its own model.)

## Future proof gate (defined, not executed)
`governed_standing` is proven when, in runtime/tests (functional, no credential): (1) a #2-**contested**
claim reads **`governed_standing == contested`** while its **`raw_standing`** is unchanged (its latest
decision); (2) a **non-contested** claim reads `governed_standing == raw_standing`; (3) `governed_standing`
is **derived** (drop/rebuild identical; `MEF.contested` still unread); (4) **#4b coherence is unaffected**
(it reads raw). Passing moves step (c) from **seam** to **first governed reading** — a `PROOF_LOG.md`
entry, and the law's **first governance property**.

## Consequences & sequence
- This is a **contract**: it fixes **what** `raw_standing` / `governed_standing` are, not **how** wired.
- **Ratification first.** Then a **design/build**: derive `governed_standing` (pure, from `raw_standing`
  + the #2 conflict), expose it (a query field / CLI reading), and decide **which consumers** read the
  governed reading (e.g. `explain`, the `standing` command) — **without** rewiring `#4b` (which stays on
  raw). Then the proof gate above, then the `PROOF_LOG.md` entry.
- A `FRAMING_DECISION_LOG.md` row only if a transversal framing guided the call; the manifesto is
  untouched (this enters the law as an **ADR**, not a manifesto property).
