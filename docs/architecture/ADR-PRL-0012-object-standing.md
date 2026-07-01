# ADR-PRL-0012 — Object Standing (subject-scale governed reading)

**Status:** Accepted — ratified-by-Mohamed 2026-07-01 · **Version:** v1 · **Date:** 2026-07-01 · **Regime:** `declared`
**Depends on:** ADR-PRL-0001 (Constitution), 0004 (MEF), 0008 (Resolution / Standing — latest-wins), 0011
(Governed Standing Layer); builds on #4a (object referent `subject_id`) and #4b (coherence visibility).
**Axis:** governance / object-standing contract. **Nature:** the **object-scale analog of ADR-0011** —
the compiler's **standing half** (#4b-S). It defines a *reading*, not a content compiler.

> **A subject's object standing is a *derived reading above its claims* — it does not compile their
> content, and it never lets an object read `accepted` while one of its claims is `contested`.**

## Why now
The object-standing grounding found this **tractable**: everything an object standing needs is already
gathered read-only (the #4a claims + the #4b `coherence`), and it is **exactly the ADR-0011
governed-standing pattern lifted to subject scale** — a new authoritative reading **above** the per-claim
standings, bending **no** invariant. ADR-0011's own reserve pointed here (*"a subject has no governed
standing — deferred to the #4b compiler"*). So `#4b` **splits**: **#4b-S** (object *standing*, this ADR)
is derivable now; **#4b-C** (object *content* / provenance / lineage) stays deferred — it needs
claim↔claim relations (schema) that do not exist.

## Decision (the rule)

> Daryl derives an **`object_standing`** for a `subject_id` — a **read-only authoritative reading above**
> the #4a gather and the #4b coherence. It is derived, never stored; it creates no `object_id`; it does
> **not** compile the object's content.
>
> **Derivation (precedence: `claim contested` > `subject divergent` > `aligned decision` > `unsettled`):**
> 1. **any** constituent claim is itself `governed_standing = contested` (#2-contested) → **`contested`**;
> 2. else `coherence = divergent` → **`contested`**;
> 3. else `coherence = aligned` → the **shared decision** (all live-governed claims `accepted` →
>    `accepted`; all `rejected` → `rejected`);
> 4. else (`coherence = unsettled`) → **`proposed`**.

## The load-bearing invariant

> **The object standing is a reading *above* the gather, never a compiled object and never a stored
> field.** The raw per-claim standings (latest-wins), each claim's `governed_standing` (ADR-0011), and the
> #4b `coherence` are **all unchanged**; `object_standing` is **derived every call**, keyed by
> `subject_id`, and creates **no `object_id`** and **no new field on any act**.

## The rules (minimal, contract-level)
1. **Subject-scale reading.** `object_standing` is keyed by the **`subject_id`** referent (#4a), derived
   from its gathered claims + the #4b `coherence`.
2. **The derivation + precedence** as above. The precedence is load-bearing: **an object is never
   `accepted`/`rejected` while a constituent claim is itself `contested`** — a claim's contestation
   propagates to the object.
3. **Derived from the acts/signals, never stored.** Recomputed every call; **no `object_id`**, no new
   field on any node; drop everything and it recomputes from the acts.
4. **A value, not a gate.** `object_standing ∈ {proposed, accepted, rejected, contested}` is a **reading**
   — it **blocks no write**, resolves nothing, forces no supersession.
5. **Standing only, not content.** It decides the object's **standing**, **not** its content/answer, and
   **not** provenance/lineage. That is **#4b-C**, deferred (it needs claim↔claim relations — a separate,
   heavier ADR).
6. **Above the projection.** It reads the per-claim standings (raw), each claim's `conflict`
   (`governed_standing = contested`), and `coherence`; it **changes none of them** (no ripple).

## Non-goals (hard scope fence)
**No `object_id`**; **no content merge**; **no provenance / lineage**; **no claim↔claim relations**; **no
write / no gate**; no kernel change, no new `action_name`, no new writer. #4a gather, #4b coherence,
ADR-0011 `governed_standing`, and raw latest-wins are **untouched**. `object_standing` does **not** block
anything.

## Notes on the choice
- **Precedence rationale.** `claim contested` outranks even an `aligned` decision so that an object is
  **never declared `accepted` (or `rejected`) while one of its constituent claims is governed
  `contested`** — a contested part contaminates the whole, visibly.
- **Vocabulary.** `contested` and `proposed` are the object-scale values a raw claim standing may not take
  at object scale in the same way; they are readings, mirroring ADR-0011's `contested`.
- **Rejected alternatives.** Creating an `object_id` or compiling content — **rejected** for #4b-S (needs
  schema/relations, deferred to #4b-C). A write/gate on object standing — **rejected** (a value, like
  ADR-0011).

## Governance
This is a **governance-scale reading** (a new authoritative reading at object scale); per the project's
discipline it must be **human-ratified** before any design/build.

## Future proof gate (defined, not executed)
`object_standing` is proven when, in runtime/tests (functional, no credential): (1) a subject with a
**`divergent`** coherence reads `object_standing == contested`; (2) a subject that is **`aligned`** with a
constituent **`contested`** claim reads `object_standing == contested` (**precedence**), while a subject
**`aligned`** with no contested claim reads the **shared decision**; (3) an **`unsettled`** subject reads
`proposed`; (4) it is **derived** (drop/rebuild identical; **no `object_id`**, no stored field); (5) the
raw per-claim standings, `governed_standing`, and #4b `coherence` are **unchanged**. Passing proves the
compiler's **standing half** (#4b-S) — a `PROOF_LOG.md` entry; #4b-C (content/lineage) stays open.

## Consequences & sequence
- This is a **contract**: it fixes **what** `object_standing` is, not **how** wired.
- **Ratification first.** Then a **design/build**: a pure `derive_object_standing(claims, coherence)`,
  exposed on the subject reading (e.g. `SubjectStandingsView.object_standing` + the `subject-standings`
  render / a CLI line) — **without** an `object_id`, without touching content. Then the proof gate, then
  the `PROOF_LOG.md` entry.
- **#4b-C** (object content merge + provenance/lineage) is a **separate, later** frontier and ADR.
