# ADR-PRL-0001 — PRL Epistemic Registry Constitution

**Status:** Accepted · **Version:** v1 · **Date:** 2026-06-26 · **Regime:** `declared`
**Supersedable:** yes — this ADR is itself a governed artifact, subject to the rules it enacts.
**Scope:** founding constitution. Architecture, types, and APIs are **out of scope** and belong to ADR-PRL-0002.

> **PRL does not make project knowledge true. It makes project knowledge governable.**

---

## Governance rule for this document

No new idea enters this ADR until v1 is frozen. Any idea that emerges during
drafting goes to **§7 Future Deliberations** — it does not reopen §1–§6. This rule
exists because the deliberation that produced this document was generative: without
a holding pen, the constitution would never freeze. (Same discipline that froze the
recall benchmark at six confirmed questions instead of padding to ten.)

---

## 1. Mission

PRL does not make project knowledge true. It makes project knowledge **governable**.

**What PRL is.** An *epistemic registry* for the knowledge of a project: it governs
the *lifecycle* of claims about the work — observation → proposal →
acceptance/rejection/supersession → retrieval → reuse → challenge → new proposal.
It records what exists, who said it, why, in what trust regime, and whether it can
be challenged. It is **agent-neutral**: any agent (Claude, GPT, OpenClaw, a future
local model) is a *client* of the same project memory; the project owns the memory,
agents are replaceable producers and consumers.

**What PRL is not.** Not an assistant, a chatbot, or an agent. Not a knowledge base
that asserts "here is what I know." Not a system with authority over truth.

**Difference vs DSM.** DSM answers *"can I trust this event wasn't altered?"* — it
governs integrity. PRL answers *"can I trust how this knowledge should be
interpreted and reused?"* — it governs epistemics. PRL composes DSM as its
persistence and integrity substrate; it does not replace it. (See §2.)

**Difference vs RAG / a vector DB.** RAG retrieves similar text; it does not know
*why* it believes a passage, in what regime it was produced, or whether it has been
superseded. PRL attaches provenance, confidence, and standing to every claim.

**Difference vs Obsidian / notes.** Notes are human-authored documents with no
governed provenance, no proposal lifecycle, no machine-checkable trust regime.

**Difference vs a Knowledge Graph.** A KG asserts entities and relations as facts.
PRL distinguishes *observed* facts from *derived* interpretations, never confuses a
proposal with a fact, and treats every edge as a governed claim with standing.

---

## 2. The two Constitutions

DSM and PRL are **parallel, not competing** constitutions. Same philosophy — *make
the property impossible to violate, do not merely document it* — pointed at two
different questions.

### DSM — Integrity Constitution
Fundamental question: **Can I trust this event wasn't altered?**
Protects: integrity, immutability, traceability.
Invariants (already enforced in DSM today): the kernel is append-only; Read Relay is
the only read path (ADR-0001); Storage is writable only by registered writers; every
write is traceable through the hash chain.

### PRL — Epistemic Constitution
Fundamental question: **Can I trust how this knowledge should be interpreted and reused?**
Protects: provenance, confidence, governance, salience.
Invariants: enumerated in §4.

**Cross-contamination is forbidden.** An invariant is only safe in the tier where it
is true; a true invariant in the wrong tier becomes a cage. DSM's `append-only`
immutability is correct for the **Observed/Integrity** layer and must **not** leak
onto the **Derived/Epistemic** layer, where the correct invariant is *versioned and
recomputable*, not immutable. Freezing interpretations as immutable truth is the one
failure this entire constitution exists to prevent.

---

## 3. The Laws

No technique here — only the constitution.

1. **Memory of work, not person.** PRL records *stated* rationale as an observed
   artifact ("the ADR argues X"); it never infers motive, disposition, personality,
   or preference.
2. **Three tiers.** *Observed* (artifacts/events as they exist) / *Derived*
   (interpretations over the observed) / *Person-model* (about the person — never
   persisted).
3. **Witnessed-forward vs Reconstructed-backward.** What PRL captured as it happened
   may become strong; what PRL reconstructs after the fact stays probabilistic. The
   regime determines a claim's default confidence.
4. **No stable inferred anchor without ratification.** A derived object becomes a
   stable anchor only when ratified — by a human or by witnessed-at-creation
   provenance — never by inference alone.
5. **No naked claim.** A claim never leaves the registry without its epistemic frame.
6. **Every claim carries an MEF** (Minimal Epistemic Frame). See §5.
7. **Every Knowledge Object begins as a Proposal.** An agent writes proposals, never
   objects or facts.
8. **Accepted ≠ True.** Registry states are *events* ("someone accepted this"), never
   verdicts of truth.
9. **Negative findings are claims.** "None found" must expose the same provenance as
   a positive finding (detector, coverage, confidence). Absence is information and is
   governed. Includes empty retrieval results.
10. **Ranking is governed.** Selection and ordering exercise authority over
    *salience*; that authority must be explicit, evidenced, and auditable. The ranker
    is a producer.
11. **No epistemic authority over truth.** PRL never asserts a claim is true, or even
    probably true. It records what exists and its standing. Authority over truth
    belongs to humans or witnesses, never to the registry or to inference.
12. **No component may silently alter or misrepresent the epistemic standing of a
    claim.** Inflation, suppression, and concealment (e.g. hiding a contradiction)
    are all forbidden; any change of standing must be an observable, attributed event.
13. **Every stored object must justify its existence.** It enters only if it improves
    recall, provenance, context, or work-continuity. Serving governance/provenance is
    itself a valid justification (so the audit trail is never purged). Protects
    against data-hoarding; honesty about provenance is not a licence to capture
    everything.
14. **Imported is never promoted to Witnessed.** You cannot witness retroactively.

---

## 4. The Invariants

Each law becomes a property that cannot hold false. (Mechanisms in §5; enforcement in §6.)

| Law | Invariant |
|---|---|
| No naked claim (L5) | Impossible to construct a `ClaimView` without a Minimal Epistemic Frame. |
| Every claim carries an MEF (L6) | A claim cannot exist without `claim_id`, `regime`, `confidence`, `contested?`. |
| Every object begins as a Proposal (L7) | An agent has no path that writes anything but a `Proposal`. |
| Accepted ≠ True (L8) | No claim or state contains a `truth` boolean. |
| Negative findings are claims (L9) | An empty search returns an `EmptyClaim` (with provenance), never `None`/null. |
| Ranking is governed (L10) | Every ranked result carries a `ranking_policy_id` and policy version. |
| No silent change of standing (L11, L12) | Every standing change occurs only via an attributed, recorded epistemic event. |
| Imported ↛ Witnessed (L14) | The transition is absent from the legal state-transition table. |
| Observed immutable / Derived versioned (L2) | Integrity invariants have no reference path into the Derived tier; Derived has no append-only-immutability path. |
| Person-model never persisted (L2) | There is no persistence path for person-tier inferences. |
| Justify existence (L13) | No ingestion or derivation path exists without a declared purpose. |

> **One guarantee, two ends.** "Accepted ≠ True" (no stored truth field) and "No
> naked claim" (non-strippable MEF) are the same guarantee seen from the write side
> and the read side. Neither alone suffices: truth suppressed at write returns at
> read if a claim can be stripped of its frame.

---

## 5. Enforcement mechanisms

Mechanisms only — no implementation.

- **Proposal lifecycle.** Agents emit *proposals* (type, producer, regime,
  confidence, evidence, status, `contradicts`/`supersedes`). The registry records
  them; it does not judge them.
- **Registry events.** A claim's standing moves only through recorded events:
  `Observed`, `Imported`, `Proposed`, `Referenced`, `Accepted`, `Rejected`,
  `Superseded`, `Withdrawn`. Events are facts ("someone accepted"), not judgments.
- **State machine with forbidden transitions.** Legal transitions are explicit; the
  forbidden ones (notably `Imported → Witnessed`) are as load-bearing as the allowed
  ones.
- **Minimal Epistemic Frame (MEF), non-strippable.** Always attached:
  `regime + confidence + contested? + claim_id`. The `claim_id` is the handle by
  which the Extended frame is fetched.
- **Extended Epistemic Frame (lazy).** Available on demand, not force-fed:
  provenance, producer, evidence, ranking explanation, extractor/policy version,
  contradictions. This tiered disclosure is the compromise between a finite LLM
  context budget and epistemic honesty.
- **Producer identity.** Every claim attributes its producer — extractor, agent,
  human, or ranker — with version.
- **Ranking policy as artifact.** Salience is produced by a versioned, attributed
  ranking policy; "why shown" exposes both the features and the policy that combined
  them.
- **Conflict relations.** `contradicts` and `supersedes` represent disagreement
  between proposals rather than flattening it; supersession preserves the link.
- **Write contract / Read contract.** Two symmetric contracts: how a claim *enters*
  (proposals, events, forbidden transitions, authorized producers) and how a claim is
  *read* (MEF non-strippable, contradictions never suppressed, ranking shows reasons).

---

## 6. Enforcement (how each mechanism breaks CI)

A law is only real if its violation is *detectable*. The proven precedent is DSM's
own: ADR-0001 ("RR is the only read path") is not prose — it is
`scripts/forbid_storage_access.py`, a lint that fails CI, which is why a new Storage
writer must be a registered, deliberate decision rather than a silent drift. Each PRL
invariant must name its enforcement in the same spirit:

- **Invariant → type → lint → CI.** Make illegal states unconstructable
  (e.g. `ClaimView` requires an MEF; no type carries a `truth` boolean).
- **State transition → validator → CI.** Forbidden transitions (`Imported →
  Witnessed`) fail a transition validator.
- **Read contract → typed API → impossible compile/runtime path.** A claim cannot be
  obtained without its MEF; confidence and regime are not droppable.
- **Tier isolation → boundary lint → CI.** No reference path from integrity
  invariants into the Derived tier, and none from person-tier into persistence.
- **Producer/ranker attribution → schema check → CI.** A ranked result without a
  `ranking_policy_id`, or a claim without a producer, fails validation.

A law without a check is decoration. A law with a check is a constitution.

---

## 7. Future Deliberations (holding pen — not part of v1)

Recorded so they do not reopen §1–§6. To be taken up only after v1 is frozen, the
recall `report.md` exists, and the first additive increment is built.

- **Lifecycle / forgetting / retention.** Decay, deletion, right-to-delete — none
  governed yet. Tension with "nothing is deleted; visibility is the governed property."
- **Multi-writer conflict beyond `supersedes`.** Richer contradiction resolution when
  many agents disagree.
- **Meta-governance.** The constitution is versioned; who governs changes to the
  governance policy itself (the recursion).
- **Team-scale "work, not person".** At multi-person scale, "memory of the work"
  edges toward "who decided/argued what" — an ethics decision, not a drift.
- **Salience policy evolution.** How ranking policies are proposed, compared, and
  superseded as governed artifacts.
- **Performance of provenance.** Keeping the MEF/Extended split cheap at scale so the
  read contract is never bypassed under load.

---

## 8. Consequences

- The next document is **ADR-PRL-0002 (Architecture)** — `Claim`, `Proposal`,
  `KnowledgeObject`, `RegistryEvent`, write/read contracts, APIs, types. It may be
  written only after this ADR is frozen. Order is **0001 = Constitution, 0002 =
  Architecture**, never the inverse.
- In parallel and independent of this document, the **empirical act** proceeds: the
  recall `report.md` on real data. The constitution never tells you whether recall
  works; the benchmark never tells you whether knowledge is honestly governed. Both
  are required; neither waits on the other.
- Implementation, when it comes, is **additive over P0→P9** — a governance wrapper the
  existing observed/derived layers grow into, not a rewrite — under the same atomic,
  kernel-untouched discipline that carried ten milestones.
- Even this Constitution is a declared, versioned, supersedable artifact, subject to
  the rules it enacts. Nothing is above the registry, including the registry's charter.

> **PRL does not make project knowledge true. It makes project knowledge governable.**
