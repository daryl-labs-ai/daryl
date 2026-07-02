# PROOF_LOG

Append-only record of hypotheses tested and the rule each one fired. One entry per adopted change.

---

## PRL Agent Consultation v1 (ADR-PRL-0008)

- **Hypothesis:** ADR-0008 can be implemented without kernel change.
- **Experiment:** R-consult v1 implementation + tests + RR read + forbid-storage.
- **Change:** Consultation Knowledge Act adopted.
- **Rule fired:** promotion / implementation adoption.

---

## PRL Agent Consultation v2 — read/display (ADR-PRL-0008)

- **Hypothesis:** A certified consultation act can be consumed through the existing RR read path without new writers or kernel changes.
- **Experiment:** R-consult v2 implementation + ConsultationQuery + CLI consultations + RR e2e tests.
- **Change:** Consultation Knowledge Acts are now writable and readable/displayable.
- **Rule fired:** HOLD / evidence added, no conceptual promotion.

---

## PRL Agent Consultation v3 — real agent invocation (ADR-PRL-0008)

- **Hypothesis:** a real agent produces a DSM-certified Knowledge Act without knowing PRL.
- **Experiment:** R-consult v3 + OpenAIClient + real `prl consult` transcript (gpt-4o, real receipt `v1:d1df9edab5ed4d0e00e82c433ba03e00da27a856ee47c8972de1c3dde2470779`).
- **Change:** external commercial model contributed a certified, retrievable project act.
- **Rule fired:** PROMOTION / first real-agent certified act.

---

## Resolution / Standing v1 — first governed decision from a real agent Proposal (ADR-PRL-0008)

- **Hypothesis:** Human ratification can turn a certified agent Proposal into a *governed decision* — with the claim's standing **derived by replay** — **without mutating** the original claim.
- **Experiment:** Real gate (no credentials for the governance chain — ratification is human): gpt-4o `consult --propose` on KO-7 → `claim_7c765d2988fd` → `human:mohamed resolve --decision accepted` → `standing` read via RR.
- **Change:** The chain *certified Proposal → human Resolution → derived Standing* is closed in runtime. The Proposal was DSM-certified (receipt `v1:97d271…0c6e`); a human Resolution was DSM-certified (`decision = accepted`, receipt `v1:b9901b…214a`); the claim's standing read back as `ACCEPTED`, derived from the Resolution (same receipt) — no stored standing field, no mutation. Step 5 of `MVP_DEMO_SCENARIO.md` passes.
- **Rule fired:** PROMOTION / first governed decision from a real agent Proposal. Merged: PR #77 (`2e28245`); `LEGITIMATE_WRITERS` = 20 unchanged, `types.py` on `prl._canonical`, kernel untouched; latest-wins ordering fix guarded by a kernel regression test.

---

## R-explain v1 — MVP Demo Scenario completed end-to-end (ADR-PRL-0008)

- **Hypothesis:** "Why this decision?" can be answered by **reconstruction from certified acts**, not narration above them — closing the MVP scenario (*real agent → certified Proposal → human Resolution → derived Standing → reconstructed explanation*), end-to-end.
- **Experiment:** Real gate: `prl explain --claim claim_7c765d2988fd` over the merged KO-7 chain (gpt-4o Proposal `v1:97d271…` → `human:mohamed` Resolution `v1:b9901b…` → derived Standing).
- **Change:** `explain` reconstructed the chain from the certified acts alone — each line backed by a DSM receipt (`proposal.receipt` / `resolution.receipt` == the `commit_act` tip hashes), standing from `standing_of` (single source), no Proposal fabricated, **no LLM, no summarization**. Output: `why claim_7c765d2988fd is ACCEPTED` / proposal `v1:97d271…` / resolution `resolver=human:mohamed v1:b9901b…` / `standing ACCEPTED (derived)`. The **MVP Demo Scenario is now complete end-to-end** (steps 1–6).
- **Rule fired:** PROMOTION / MVP scenario completed end-to-end. Merged: PR #78 (`859aa30`); `LEGITIMATE_WRITERS` = 20 unchanged, `types.py` untouched, no new `action_name`. Consequence: framing #7 graduates (a contribution becomes a governed project asset) — the manifesto/framings corpus changes (`VISION_KNOWLEDGE_FABRIC.md`, `FABRIC_FRAMINGS_INCUBATING.md`) are deferred to a dedicated manifesto-port PR (not yet on `main`).

---

## Identity across projections v1 — identity survives a second read projection (Second epoch #3)

- **Hypothesis:** the existing identity model survives a **second registry projection** — the same `claim_id` threads Proposal → Resolution → Standing → Explanation **identically** whether read via RR or via another projection, *without* designing new identity.
- **Experiment:** real gate on the merged KO-7 chain (no credentials): `explain --claim claim_7c765d2988fd` via **RR**, then `project-sqlite` (materialize a second projection), then `explain … --projection sqlite`.
- **Change:** the two explanations are **byte-identical** — `claim_7c765d2988fd` → proposal `v1:97d271…0c6e` → resolution `v1:b9901b…214a` (`human:mohamed`) → `ACCEPTED (derived)`; the SQLite projection materialized 2 acts. The same `StandingQuery`/`ExplainQuery` code runs on both backends (one derivation by construction); `claim_id` stays in `content` (never re-minted) and DSM receipts are carried **verbatim**. **Reserve:** the certification *substrate* stays DSM — receipts are **projection-relative** (a substrate swap would re-issue them, not carry them); identity-retrieval is still a linear scan over an action bucket (scale-tension #1). Both out of scope here.
- **Rule fired:** PROMOTION / first robustness invariant proven (read projection). Merged: PR #82 (`0a0d5ee`); `LEGITIMATE_WRITERS` = 20 unchanged, `types.py` untouched, no new `action_name`, `projections/` imports no `Storage` (reads via RR, ADR-0001).

---

## Structured contributor attribution v1 — `agent_id` ≠ `model_id` (ADR-PRL-0009)

- **Hypothesis:** a logical contributor's identity can survive a change of carrier — the **same `agent_id`** can produce certified acts across **different models/providers**, establishing the **second identity pillar** (`agent_id` ≠ `model_id`, the contributor's mirror of `claim_id` ∉ storage). Second epoch frontier #6.
- **Experiment:** real gate with a real agent: two `consult` acts under one `--agent-id agent.architect`, on **gpt-4o** then **gpt-5**, then `consultations`.
- **Change:** both acts show the **same `agent_id` (`agent.architect`)** with **different carriers** (`openai:gpt-4o` → receipt `v1:eb97eba5…d782f`; `openai:gpt-5` → receipt `v1:1f9c4abc…706ee`), each a distinct certified act. Contributor identity is now **structured and carrier-independent** (ADR-PRL-0009): `agent_id` is frame-level in the MEF, the carrier-of-record sits alongside, `producer` is a display projection, and the *type* (human/agent) lives in the carrier (`human:` prefix dropped; humans are `prenom.nom`). **Backward compatibility holds:** pre-0009 acts read with `agent_id = None` (`(unknown)`), byte-identical, no inference.
- **Rule fired:** PROMOTION / second identity pillar established. Merged: PR #84 (`d59f9f4`), ratified by **ADR-PRL-0009**; `LEGITIMATE_WRITERS` = 20 unchanged, agent never ratifies unchanged. With two referents now proven (`claim_id` ∉ storage, `agent_id` ≠ `model_id`), the transversal principle *"identity is never defined by its carrier"* earns its second leg → incubated in `FABRIC_FRAMINGS_INCUBATING.md` with a gate for a third referent.

---

## Organization referent v1 — `org_id` ≠ carrier — third identity referent (ADR-PRL-0010)

- **Hypothesis:** an organization's identity can survive its carrier — the **same `org_id`** can scope certified acts across different projects/carriers, establishing the **third identity referent** (`org_id` ≠ carrier), after `claim_id` ∉ storage and `agent_id` ≠ `model_id`. Second epoch frontier #5a (the referent half of the split #5).
- **Experiment:** real gate with a real agent: two `consult` acts under one `--org-id org.acme`, on **gpt-4o** then **gpt-5**, then the owner-scoped query `consultations --org org.acme`.
- **Change:** both acts carry the **same `org_id` (`org.acme`)** across **different carriers** (`openai:gpt-4o` → receipt `v1:9c296538…ebb2`; `openai:gpt-5` → receipt `v1:7477259e…9c96`), and `consultations --org org.acme` returns **exactly** them — an **owner-scoped query `project_id` alone cannot express**. Organization identity is now a real referent (ADR-PRL-0010): declared at the project (source of truth), carried via a thin ownership context **beside the MEF** (ownership ≠ epistemic, **MEF untouched**); carrier-independent; optional, never inferred (backward-compatible, byte-identical for pre-0010 acts).
- **Rule fired:** PROMOTION / third identity referent established. Merged: PR #88 (`f964b43`), ratified by ADR-PRL-0010; `LEGITIMATE_WRITERS` = 20 unchanged, MEF untouched. **Consequence:** with three independent referents proven (`claim_id` ∉ storage, `agent_id` ≠ `model_id`, `org_id` ≠ carrier), the transversal principle *"identity is never defined by its carrier"* earns its **third leg** and **graduates** from the incubator to the manifesto (`VISION_KNOWLEDGE_FABRIC.md`).

---

## Derived standing at scale v1 — the invariant survives a performance optimization (#1)

- **Hypothesis:** a central proven property — *standing is **derived**, never stored or authoritative* (Resolution v1) — can **survive performance pressure**: a non-authoritative projection can bound per-claim query cost **without** turning standing into stored truth. Second epoch frontier #1 (Behavior family); grounding verdict was **PARTIAL** (correct but O(N)-per-query bucket scan).
- **Experiment:** a **measured** kernel test (real Storage/RR, no credential): commit resolutions across many claims; compare `StandingIndex` (one-pass act grouping) vs `StandingQuery` (full-bucket scan per claim), and prove the standing is identical and the index disposable.
- **Change:** `StandingIndex` memoizes **the grouping of resolution acts by `claim_id`** (one scan), **never the standing**: `standing_of` still derives via the single-source `derive_standing` every call. Measured (M=6 claims / 18 acts): **StandingIndex = 1 bucket scan (build) + 0 per query** vs **StandingQuery = 6 scans (one per query)** — `O(N)`-per-query → `O(N)`-once + `O(1)`/`O(k)`-per-query, **identical standing** for every claim, and **dropping the index recomputes the same standing from the acts** (the index is a projection, the acts are the source). The load-bearing invariant — *standing is never stored* — is preserved (only the act grouping is cached).
- **Rule fired:** PROMOTION / #1 PARTIAL → PROVEN at scale. Merged: PR #90 (`703b87a`); **no ADR** (this *preserves* the standing rule, it does not change it); `LEGITIMATE_WRITERS` = 20 unchanged, `types.py` untouched, no kernel change. *(A measured proof, reproducible in CI — unlike the identity gates, no agent transcript was needed.)*

---

## Concurrent resolutions v1 — a conflict can no longer be invisible (#2)

- **Hypothesis:** when two human authorities resolve the same claim **incompatibly**, the conflict must not stay **invisible** — it can be **detected and surfaced** as a derived signal, *without* governing it (no authority model) and *without* changing the standing. Second epoch frontier #2 (Behavior family); grounding verdict was **PARTIAL** (deterministic and auditable, but **not governed** — incompatible resolutions silently overrode by record order, `MEF.contested` unread).
- **Experiment:** a **functional in-suite** proof (pure, no credential): build incompatible resolutions on one claim and assert the derived signal. Definition **D3**: a claim is in conflict when **two distinct `agent_id`** issue **opposite** decisions (one `accepted`, one `rejected`); a single author flipping their own decision is a **supersession, not a conflict**; `superseded`/`withdrawn` are transitions; **legacy fallback** (unknown `agent_id`) **surfaces** opposite decisions rather than silently ignoring them.
- **Change:** a pure `detect_conflict` (D3 + legacy fallback) is read **alongside** latest-wins inside `derive_standing`: the standing stays the **latest** decision **UNCHANGED**, and `StandingView`/`Explanation` gain a **derived** `conflict` flag + parties; `render` shows `⚠ CONFLICT`. Proven cases: two authorities (`alice:accepted` → `bob:rejected`) → **standing `rejected` (unchanged) + conflict `{alice,bob}`**; self-flip → **no conflict** (supersession); legacy-unknown opposite → **surfaced**, never silently `False`; the conflict is **derived** (`StandingIndex` inherits it; drop/rebuild identical; **no stored conflict field**). `standing`/`decisions`/`last_receipt` stay byte-identical (regression OK).
- **Rule fired:** PROMOTION / #2 PARTIAL → conflict visibility proven. Merged: PR #92 (`cfb785f`); **no ADR** (a derived read-only signal; the conflict *definition* is a revisable design choice, not yet a binding rule), no kernel, `LEGITIMATE_WRITERS` = 20 unchanged, `types.py` untouched, **`MEF.contested` still unread** — governance (contested-as-standing / authority) is **deliberately deferred** to step (c). *(Functional in-suite proof, reproducible in CI — no agent transcript needed, like #1.) Daryl does not yet govern conflict; it now guarantees an incompatible human resolution cannot stay invisible.*

---

## Object referent v1 — `subject_id` reaches a subject's governed state, read-only (#4a)

- **Hypothesis:** before a knowledge *compiler* can exist, the **object referent** must be settled — can `subject_id` gather the governed state of all its claims, across producers, **read-only, with no new identity**? Second epoch frontier #4, referent half (**#4a**); grounding verdict was **PARTIAL REFERENT — NOT SUFFICIENT TODAY** (`subject_id` spans producers/claims but stops at the consultation; the `subject → claim → standing` bridge is latent, no read path).
- **Experiment:** a **functional in-suite** proof (pure, no credential): a read-only `standings_of_subject` that walks the latent bridge `subject_id → consultation.claim_id → standing_of(claim)`, plus a **live smoke** on real certified acts.
- **Change:** `SubjectStandingsQuery.standings_of_subject` composes the existing `ConsultationQuery` (subject → claims) and `StandingQuery` (claim → standing) over one shared projection, returning a subject's claims **side by side** — **gather, not compile**. Proven: a subject spans **two carriers and distinct claims** (the `KO` shape); a **resolved** proposal surfaces its real standing (`ACCEPTED`) **beside** an unresolved `PROPOSED` one — the gather **reaches the governed layer**; two opposite standings stay **side by side** (no merged "object standing" field on the view); the per-claim #2 `conflict` is inherited **verbatim**, never aggregated; the gather is **derived** (drop/rebuild identical). Live smoke: `subject-standings --subject KO` → claims across `openai:gpt-5` / `openai:gpt-4o`, one `ACCEPTED` (governed reach) + one `PROPOSED`, a decoy subject not leaking. `subject_id` is therefore a confirmed **minimal read-only referent that reaches the governed layer — without a new identity**.
- **Rule fired:** PROMOTION / #4a object referent established (read-gather). Merged: PR #94 (`f2e3b59`); **no `object_id`, no new field** (`subject_id` not added to resolutions), `types.py` untouched, no writer/kernel/ADR, `LEGITIMATE_WRITERS` = 20; `#1`/`#2` derivations reused unchanged. **Reserve:** this is the **referent (gather)**, **not** the compiler — reconciling many claims into one coherent Object (conflict / supersession / provenance *across* claims) is the deferred **#4b**; `subject_id` stays unnormalized (F4) and the object-vs-session ambiguity unpinned (F5).

---

## Object coherence visibility v1 — incoherence across a subject's claims is no longer invisible (#4b)

- **Hypothesis:** the "make visible before governing" discipline (proven for *per-claim* conflict, #2) lifts to the **object scale** — a subject's agreement/disagreement **across its claims** can be detected and surfaced as a **derived descriptor**, **without** merging the claims, **without** giving the subject a standing, and **without** resolving. Second epoch frontier #4, compiler half (**#4b**); grounding verdict was **ABSENT** (Daryl gathers, does not compile — no cross-claim conflict / supersession / provenance / standing).
- **Experiment:** **functional in-suite** (pure, no credential) **+ a live smoke**: a read-only coherence descriptor over the #4a gather.
- **Change:** `detect_coherence` (rule **C-d**) reads the subject's **live governed** claims (standing ∈ {`accepted`, `rejected`}; `superseded`/`withdrawn` **excluded** as closed transitions) and derives `aligned` / `divergent` / `unsettled`, read **alongside** the #4a gather (the #2 pattern). `SubjectStandingsView` gains a `coherence` descriptor + `divergent_claims` — **not a subject standing** (the view has **no `standing` field**). Proven: one `accepted` + one `rejected` under a subject → `divergent`, both claim_ids surfaced, **claims still side by side, no subject verdict, standings not merged**; governed claims agreeing → `aligned`; proposed-only → `unsettled`; the per-claim #2 `conflict` is **orthogonal** (a conflicted-but-`accepted` single claim → `aligned`). The gather is byte-identical (no compilation).
- **Rule fired:** PROMOTION / #4b v1 object coherence visibility. Merged: PR #96 (`b08c4b0`); **no object-standing / no verdict**, no merge, **no `object_id`, no new field** on acts, no claim↔claim relation, `types.py` untouched, no writer/kernel/ADR, `LEGITIMATE_WRITERS` = 20; `#1`/`#2`/`#4a` reused unchanged. **Reserve:** this is **visibility, not governance** — reconciling a subject's claims into one coherent Object (object-standing / authority) is the **deferred object-scale analog of #2's step (c)**; the coherence rule (C-d) is a revisable design choice, not a binding rule.

---

## Governance layer v0 — a governance posture derives read-only above latest-wins (step (c))

- **Hypothesis:** the two deferred governance steps (c) — of #2 (per-claim conflict) and #4b (inter-claim divergence) — **converge into one governance layer**: a posture `clear | contested | divergent` can be **derived above latest-wins**, **read-only**, consolidating the proven #2/#4b signals, **without** changing the standing or blocking any write. Grounding verdict was **ABSENT** (latest-wins is the sole rule; `MEF.contested` inert; no authority; supersession never required).
- **Experiment:** **functional in-suite** (pure, no credential) **+ a live smoke**: a read-only governance layer deriving the posture.
- **Change:** a new read-only layer (`governance_read`) composes `StandingQuery` (#2 `conflict`) + `SubjectStandingsQuery` (#4b `coherence`) and derives the posture (rule **G-1**, collapsed precedence **`divergent > contested > clear`**): a claim is `contested` iff #2 conflict, else `clear`; a subject is `divergent` iff #4b `coherence` divergent, else `contested` iff any claim is contested, else `clear`. The posture is **distinct-vocabulary** (never `accepted`/`rejected`), read **alongside** the standing (**latest-wins byte-identical**). Proven: a contested claim shows `CONTESTED` **beside its unchanged `REJECTED` standing**; a divergent subject shows `DIVERGENT` with its `contested_claims`; precedence holds. The layer has **no write path**, blocks nothing, and `MEF.contested` stays **unread** (0 consumers). Step (c) moves from **ABSENT** to **the governance seam is proven** (read-only; governs nothing).
- **Rule fired:** PROMOTION / step (c) v0 governance seam. Merged: PR #98 (`90d34de`); no standing change, no write blocking, **no `MEF.contested` consumption**, no authority, no required supersession, no ADR/manifeste/kernel/writer, `types.py` untouched, `LEGITIMATE_WRITERS` = 20; `#1`/`#2`/`#4a`/`#4b` reused unchanged. **Reserve:** this is the **seam** (a read-only posture), **not** governance — what `contested`/`divergent` should **do** (contested standing / authority / required supersession) is the **first governing rule** = the project's **first governance ADR**, still deferred.

---

## Governed standing v1 — the first governed reading (ADR-PRL-0011)

- **Hypothesis:** the governance seam (step (c) v0) can gain **consequence** *without bending an existing invariant*: a **`governed_standing`** derived **above** latest-wins (ADR-PRL-0011, mechanism B) — `contested` when the claim is #2-contested, else the raw standing — becomes the **authoritative reading**, while **`raw_standing` (latest-wins) stays unchanged**. This is the **first governance *rule*** (all 13 prior movements were additive derived signals).
- **Experiment:** **functional in-suite** (pure, no credential) **+ a live smoke**: derive `governed_standing` from the raw standing + the #2 conflict, and surface it to the `standing` / `explain` readings.
- **Change:** `derive_governed_standing` (pure) returns `contested` iff #2 conflict, else the raw standing; `StandingView`/`Explanation` gain `governed_standing` (**derived, never stored**); the `standing` reading now reports the **governed** value as authoritative and `explain` shows **both** governed and raw. Proven: a contested claim reads `governed_standing == contested` while `raw_standing` stays `rejected` (**latest-wins, unchanged**); a non-contested claim reads `governed == raw`; the governed reading is **derived** (drop/rebuild identical; `MEF.contested` **unread** — 0 consumers); **#4b coherence and the governance layer keep reading raw** — **no ripple** (the load-bearing invariant: the governed reading is added **above** the projection, never into it). This is the **first time a divergence signal has a consequence on what a standing *is*.**
- **Rule fired:** PROMOTION / step (c) v0 seam → v1 first governed reading. Merged: PR #101 (`8e8cd29`), on ratified **ADR-PRL-0011**; **no `MEF.contested` consumption** (contested derived from #2), `raw_standing` byte-identical, **#4b / governance unchanged** (0 `governed_standing` refs), `types.py` untouched, no writer/kernel, `LEGITIMATE_WRITERS` = 20; `#1`/`#2`/`#4a`/`#4b` intact. *(The **first reading-modifying** movement — 3 `explain`-render assertions were updated to the new format.)* **Reserve:** **claim scale only** (a subject has no governed standing — deferred to the #4b compiler); the other governance mechanisms — **(ii) authority**, **(iii) required supersession** — remain deferred **beyond** this first (i-like) rule.

---

## Object standing v1 — the compiler's standing half (ADR-PRL-0012, #4b-S)

- **Hypothesis:** the governed-standing pattern (ADR-0011, *claim* scale) **lifts to *subject* scale** — an **`object_standing`** can be derived **above** the #4a gather + #4b coherence — a read-only authoritative reading, never stored, **no `object_id`, no content merge** — so a subject finally has a governed reading **without compiling its content**. This is the compiler's **standing half** (#4b-S); the **content / lineage** half (#4b-C) stays deferred.
- **Experiment:** **functional in-suite** (pure, no credential) **+ a live smoke**.
- **Change:** `derive_object_standing` (precedence **`claim contested` > `divergent` > `aligned` decision > `unsettled`**) derives the subject's `object_standing` from its claims + `coherence`; `SubjectStandingsView` gains `object_standing` (derived, never stored); the `subject-standings` render shows it. Proven: `divergent` → `contested`; `aligned` **with** a constituent `contested` claim → `contested` (**precedence** — an object is **never** `accepted`/`rejected` while a claim is `contested`); `aligned` with none contested → the **shared decision**; `unsettled` → `proposed`; **derived** (drop/rebuild identical, **no `object_id`**). The two governance rules **compose**: `object_standing` consumes `governed_standing`'s contestation (via `ClaimStanding.conflict`) — a contested claim **propagates** to a contested object. **No ripple:** the raw per-claim standings, `governed_standing`, and `coherence` are unchanged.
- **Rule fired:** PROMOTION / #4b-S object standing proven. Merged: PR #104 (`d117508`), on ratified **ADR-PRL-0012**; **no `object_id`, no content merge, no write/gate**, no `MEF.contested`, `types.py` untouched, no writer/kernel, `LEGITIMATE_WRITERS` = 20; `#4a`/`#4b`/ADR-0011 intact. **Consequence:** governance is now proven on **both scales** — `governed_standing` (claim, ADR-0011/PR #101) + `object_standing` (subject, ADR-0012/PR #104), the **same shape** (a governed reading **above** the projection, derived never stored, primitive intact). **Reserve:** **#4b-C** (object *content* merge + provenance / lineage) stays **deferred** — it needs claim↔claim relations.

---

## Distributed certification v1 — certification survives no single registry (#5b, option A)

- **Hypothesis:** Daryl's guarantees survive with **no single registry** — two **independent** DSM registries, **no shared tip**, can certify + reconcile the **same acts** while preserving identity, `standing`, `governed_standing`, `object_standing`, and receipt verifiability — by **per-registry independent chains** reconciled **read/proof-side** (**option A**), *not* a global tip / consensus (option b). The **last** substrate frontier (#5b).
- **Experiment:** a **repo-side falsifiable run — the run *is* the proof** (CI-reproducible, **no credential**): two independent DSM instances (separate storage roots ⇒ separate tips), the **same value-identical acts** materialized into each, reconciled via the **existing** kernel primitives (`verify_shard`, `exchange` portable receipts, `witness` attestation) + the #3 value-identity join.
- **Change (proven):** the **8-point gate held** (PR #106): (1) two separate DSM instances; (2) **different tips** (`R_A v1:ee2d15dd…` ≠ `R_B v1:1aa3d786…`, no shared `last_hash`); (3) each chain `verify_shard`-valid; (4) same `claim_id`/`subject_id` reconciled by **value-identity**; (5) **identical governed standings both sides** (`K1 = contested`, `K3 = accepted`, `S.object_standing = contested`, ADR-0012 precedence); (6) `R_A`'s **portable receipt CONFIRMED** against `R_A`'s DSM from `R_B` (`exchange`); (7) a tampered act → **HASH_MISMATCH**; (8) both tips **witness-attested**, no merged chain. **Receipts differ across registries** — expected, substrate-relative (#3); the proof is **semantic identity + portable-receipt verification + attestation**, *not* receipt-equality. The rupture that would have demanded a distributed substrate (a receipt unverifiable cross-registry, or diverging standings) **did not occur**.
- **Rule fired:** PROMOTION / #5b proven (option A) — the last robustness frontier. Merged: PR #106 (`87c3daf`); **one new test file**, `src/dsm` + `src/prl` **untouched**, `verify_shard`/`exchange`/`witness` used as-is; **no core change** (`Storage.append` / `Entry.hash` / `prev_hash` / `verify_shard` intact, no global tip / quorum / consensus / signature-in-path); **no new identity or standing rule** (reconciliation **is** the #3 value-identity join); `LEGITIMATE_WRITERS` = 20. **Consequence:** certification **survives no single registry, by per-registry chains** — the three pillars (semantic value-identity, cross-registry portable receipts, attestation membership) hold separately and together **without a global tip**; the contract is ratified as **ADR-PRL-0013**. Option (b) (a true distributed substrate) remains a **deferred fallback**, warranted only if the invariant ever fails.

---

## 2026-07-01 — Knowledge Object surface v1: the model becomes visible (first product surface) (PROMOTION ⚪→🔵, not a runtime proof)

**Level: Construction movement (⚪ → 🔵 Implemented), not a runtime proof (🟢).** The Proof Log is the project's **canonical journal of movements** — not proofs only — so this belongs here, but the level is stated explicitly so it is never confused with the robustness proofs above (⚪ = idea; 🔵 = implemented / shipped; 🟢 = property demonstrated at runtime). A product surface is **not** "proven" because it exists — it is **delivered**; a future 🔵 → 🟢 move would require a defined product-validation methodology (adoption / stability / usage), which does not exist today.

- **Hypothesis:** with the model proven, a Knowledge Object can be made **visible to a user** as a **projection**, not an entity — *the model already knows what an object is; the surface renders it.* This opens the **construction phase** (after the Second Epoch close): the question shifts from *"is this property true?"* to *"how does a user see it?"*
- **Experiment:** build + tests (green, no credential) — a read-only surface composing the proven derivations; the movement is **⚪ Idea → 🔵 Implemented** (a shipped surface, **not** a runtime 🟢 proof; real-use proving would be a later 🔵 → 🟢 move).
- **Change:** `KnowledgeObjectProjection` — a **derived view, never stored**, keyed by the `subject_id` referent (**no `object_id`**, no entity). Two surfaces: **`prl objects`** (discovery — *"what objects do I own?"*, recency-first + filters) and **`prl object --subject`** (the one-page Object View). It **composes only** the proven derivations — object standing (ADR-0012), coherence (#4b), governance (step (c)), per-claim `governed_standing` (ADR-0011), and the receipt-backed timeline (`explain`) — **recomputing nothing and adding no rule**. Deliberately **deferred**: **content compilation (#4b-C)** — build the surface first, then *observe* whether compiled content is felt as missing; and **actions** (they open permissions/workflows).
- **Rule fired:** PROMOTION / ⚪ Idea → 🔵 Implemented — the first product surface. Merged: PR #108 (`a77ecf6`); a new read-only module + additive CLI (`objects`/`object`); `types.py` / kernel / ADRs / manifeste **untouched**, no `object_id`, no writer, `LEGITIMATE_WRITERS` = 20. **Consequence:** the construction phase is open, and — faithful to the whole campaign — even the first product surface is a **derived projection** (the discipline of `standing`/`governed_standing`/`object_standing`: derived, droppable, never a second source of truth). The frozen kernel still has not moved.
