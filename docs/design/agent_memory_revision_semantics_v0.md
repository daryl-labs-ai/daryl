# Agent Memory — Revision Semantics (design only, v0)

**Status:** design only. **No code follows from this document.**
**Origin:** adversarial audit, experiment 3 — "changement d'avis".
**Question:** should Agent Memory reuse or project the existing PRL revision
primitives to represent supersession, contradiction, withdrawal, current
standing, and change of mind?

---

## 0. Why this is a design document and not a patch

Experiment 3 recorded two incompatible decisions in Agent Memory and observed
that both persist with equal weight: nothing marks one as revised, retracted,
or no longer current. The obvious reflex is to add a `superseded` flag to
Agent Memory.

That reflex is wrong for a specific reason. The word `superseded` **already
exists twice in this repository, meaning two unrelated things**, and adding a
third meaning inside Agent Memory would make the ambiguity permanent and
load-bearing. This document exists to prevent that.

---

## 1. The word `superseded` today — two existing, unrelated meanings

### 1.1 DSM `search_memory` — lexical, query-relative, not a business fact

`src/dsm/recall/search.py:322-345` (`_apply_temporal_status`) marks a match
`superseded` when:

- the match's classified type is `historical_decision` or `working_assumption`
  (`_SUPERSEDABLE_TYPES`, `search.py:90-92`), **and**
- another match in the same result set has a strictly greater timestamp, **and**
- the older match's *query-matched token set* is a subset of the newer one's
  (`mi_tokens.issubset(oj_tokens)`).

Three properties disqualify this as revision semantics:

| Property | Consequence |
|---|---|
| **Query-relative** — compares tokens matched *by the query*, not entry content | The same pair of entries is superseded under one query and not under another |
| **Result-set-relative** — the scan runs after ranking and truncation to `max_results` (`search.py:419-428`) | Status flips when `max_results` changes, with no change in the data |
| **Purely lexical + temporal** — no author, no subject, no declared relation | "I changed my mind" and "someone else wrote a longer sentence later" are indistinguishable |

This label is a **recall-ranking hint**. It is not a claim about the world, and
it must never be read as one.

> **Constraint, restated:** `search_memory().time_status == "superseded"` must
> not be promoted into business semantics. Any future revision feature must be
> distinguishable from it by name, not merely by documentation.

### 1.2 PRL `ResolutionDecision` — declared, human, receipt-backed

`src/prl/types.py:54` — `ResolutionDecision = Literal["accepted", "rejected",
"superseded", "withdrawn"]`, carried by `ResolutionNode` (`types.py:239-263`),
minted by `make_resolution` (`src/prl/collectors/resolution.py:27-62`), which
forces `Carrier(provider="human")` (`resolution.py:54`).

This is a governance act: a human records a decision against a `claim_id`. It
is append-only, receipt-backed, and never mutates anything.

**These two meanings share a word and nothing else.** One is a token-subsumption
heuristic over recall results; the other is a recorded human decision.

---

## 2. The vocabulary this document proposes

To keep the boundary permanent, the design distinguishes three things by name:

```text
lexical supersession
    A ranking hint derived from token overlap and recency.
    Query-relative and result-set-relative. Not a fact about the world.
    Today: dsm.recall.search time_status.

governed revision semantics
    A recorded act by an identified party, declaring how a prior position
    stands now. Append-only, receipt-backed, derived-never-stored.
    Today: PRL ResolutionNode + derive_standing.

declared supersession (with successor)
    A governed revision that additionally NAMES the replacement, and whose
    latest-wins effect is applied only when the chain is valid and unambiguous.
    Today: prl.swarm DecisionReceipt.supersedes + replay validation.
    Absent from PRL core.
```

---

## 3. What PRL already provides

### 3.1 Standing — computed, never stored

`src/prl/query/standing_read.py:3-4` states the invariant: *"standing is never
a stored or mutated field."* Three derived layers:

| Concept | Values | Function |
|---|---|---|
| raw `standing` | `proposed` / `accepted` / `rejected` / `superseded` / `withdrawn` | `derive_standing`, `standing_read.py:130-154` |
| `governed_standing` | the above **+** `contested` | `derive_governed_standing`, `standing_read.py:121-127` |
| `object_standing` | `contested` / `accepted` / `rejected` / `proposed` | `derive_object_standing`, `subject_read.py:100-122` |

Rule: latest-wins over resolutions in authoritative record order
(`standing_read.py:145`). `StandingView` (`standing_read.py:49-68`) exposes the
**full ordered decision history**, not only the current value.

This is the single most important asset for Agent Memory. It is a worked,
tested answer to "what is the current position, and how did it get there?"
that never mutates a record.

### 3.2 Conflict — inferred, and explicitly not the same as revision

`detect_conflict`, `standing_read.py:84-118`, rule D3: a conflict requires two
**distinct** `agent_id` issuing substantively opposite decisions
(`accepted` vs `rejected`). The code says so directly at `standing_read.py:92-94`:

> A single author changing their mind (same `agent_id`, accepted then rejected)
> is a **supersession, not a conflict**.

PRL has already drawn the exact line experiment 3 is about, and drawn it
correctly. **Change of mind ≠ contradiction.** Agent Memory should not
re-derive this distinction differently.

Note also: conflict never changes standing (`standing_read.py:63-65`) — the two
axes are orthogonal.

### 3.3 Withdrawal

`withdrawn` is a resolution decision on a claim. There is **no author
self-retraction** anywhere in PRL: no `retract` act kind, no consultation
withdrawal, no CLI path.

### 3.4 The one real gap in PRL core — no successor pointer

`ResolutionNode` has no `superseded_by`, no `replacement_claim_id`
(`types.py:249-263`). The record says *"claim X is superseded"* and stops there.
**"Superseded by what?" is unanswerable from PRL core data.**

`PRODUCT_OBSERVATIONS.md:157-159` records this friction as observed in real use:
understanding why a subject flipped to `REJECTED` required manually chaining
between two commands.

### 3.5 Declared supersession already exists — in `prl.swarm`

`src/prl/swarm/types.py:268` — `DecisionReceipt.supersedes: str | None`,
documented at `swarm/types.py:238-245`:

> it never deletes or rewrites the older record, and its effect (latest-wins)
> is applied only by the replay projection when the supersession chain is valid
> and unambiguous.

`_derive_decision_standings` (`swarm/replay.py:221-330`) validates the chain and
refuses to guess: `self_supersession`, `missing_reference`,
`supersession_type_mismatch`, `supersession_cycle`, and — the important one —
`concurrent_supersession`, where two receipts supersede the same target and the
projection sets `supersession_ambiguous=True` **instead of picking a winner**
(`replay.py:304-317`). `DecisionStanding` (`replay.py:117-135`) carries
`status`, full `history`, `superseded_by`, and `supersession_ambiguous`.

This is a complete, falsifiable model of declared revision. It is not reachable
from the PRL CLI, and Agent Memory does not know it exists.

---

## 4. The five mandated questions

### Q1 — Should Agent Memory reference PRL?

**Not as a runtime dependency. Yes as the normative source of the semantics.**

Agent Memory's current design is deliberately thin: four record kinds, an
append-only shard, and a bounded traversal
(`src/dsm/memory/agent_memory.py`). Taking a hard dependency on PRL would
invert the layering — PRL is a consumer of DSM (`src/prl/store/dsm_commit.py`
is a DSM writer, `scripts/forbid_storage_access.py:94`), not a substrate for it.

What Agent Memory should adopt is PRL's **shape**, not its imports:

1. revision is a **new recorded act**, never a mutation of a prior record;
2. standing is **derived at read time**, never a stored field;
3. the derivation exposes the **full ordered history**, not only the winner;
4. "changed my mind" (same author) and "we disagree" (different authors) are
   **different axes** and must not collapse into one label;
5. when the chain is ambiguous, the projection **declines to pick a winner**
   and says so.

Point 5 is the one that matters most for this repository's discipline: it is
the difference between reporting a fact and manufacturing one.

### Q2 — Should PRL provide a common projection?

**Yes, eventually — and it is the only way to avoid two competing systems.**
But not as the first step, and not without a decision that is out of scope here.

The natural target is a shared derivation over a common act shape:

```text
           acts (DSM entries, append-only)
                        │
        ┌───────────────┴────────────────┐
   PRL resolutions              Agent Memory revisions
        └───────────────┬────────────────┘
                        │
          one derive_standing-shaped projection
            → current standing
            → ordered history
            → superseded_by | ambiguous
```

Two obstacles are real and must be named rather than waved past:

- **No cross-stream global ordinal.** `knowledge_object.py:474-475` and
  `agent_org_read.py:42-44` both state that record order is *per-stream* and
  that no global timeline exists. "Latest-wins" across two streams is therefore
  not currently well-defined. A shared projection needs an ordering rule that
  does not silently invent one.
- **Identity mismatch.** PRL keys on `MEF.claim_id`; Agent Memory keys on DSM
  `entry_hash`. A shared projection needs one addressing scheme, or an explicit
  mapping.

**Recommendation:** do not build the shared projection until an Agent Memory
revision act exists and has been exercised. Building the abstraction first
would be guessing at its shape.

### Q3 — Is a new explicit act needed?

**Yes.** No existing mechanism can carry it:

| Candidate | Why it fails |
|---|---|
| `search_memory` `time_status` | Lexical, query-relative, result-set-relative (§1.1) |
| `depends_on` | Expresses derivation, not replacement |
| `source_refs` | Existence only, by construction (source-ref integrity v0) |
| A new record *kind* (`fact`/`hypothesis`/`inference`/`decision` + a fifth) | A revision is a relation between two records, not a fifth kind of record |
| Mutating the superseded record | Violates append-only. Non-negotiable. |

The act must, at minimum:

- name the **target** record (`entry_hash`);
- name the **successor**, or explicitly declare there is none (withdrawal);
- carry the **author**, so change-of-mind is separable from disagreement
  (PRL rule D3, `standing_read.py:84-118`);
- be a **normal append-only DSM entry**, changing no hash or storage format —
  exactly as Agent Memory records are today.

It must **not** carry a truth field. PRL states the reason at `types.py:246`:
*"Accepted ≠ True."* The same applies here: revised ≠ false.

### Q4 — How to avoid two competing systems?

Four rules, in priority order:

1. **Do not reuse the word `superseded` unqualified.** It is already taken,
   twice, with incompatible meanings. Whatever Agent Memory records must be
   nameable without ambiguity in a sentence that also mentions
   `search_memory`.
2. **One derivation function, not two.** If Agent Memory grows its own
   `derive_standing`, the two implementations will diverge on the first edge
   case. Prefer extracting PRL's rule to a shared pure function over
   re-deriving it — even before a shared projection is warranted.
3. **Keep standing derived.** The moment either system stores a standing field,
   they can disagree with each other *and* with the act log.
4. **Adopt the swarm ambiguity discipline from day one.** Concurrent
   supersession must yield `ambiguous`, never an arbitrary winner
   (`swarm/replay.py:304-317`). Retrofitting this later means silently changing
   answers already given.

### Q5 — Smallest falsifiable future test

The experiment-3 scenario, made mechanical. In one shard, one author:

```text
1. record decision D1 : "Use REST for the API."
2. record decision D2 : "Use gRPC for the API."
3. record a revision act: D1 revised by D2, author = A
```

Then assert:

| # | Assertion | Falsifies |
|---|---|---|
| 1 | Current standing of D1 is not "current"; D2 is | "Agent Memory keeps two incompatible decisions with equal weight" |
| 2 | D1 is still readable, its hash unchanged, `verify_shard` still OK | Any temptation to mutate or delete |
| 3 | The history returned lists D1 **then** D2, in order | A winner-only projection that loses the change of mind |
| 4 | Same author ⇒ **not** flagged as conflict | Collapsing revision into contradiction |
| 5 | Two authors, opposite positions, no revision act ⇒ flagged as conflict, standing unchanged | Collapsing contradiction into revision |
| 6 | Two revision acts targeting D1 ⇒ **ambiguous**, no winner chosen | The system inventing a resolution it was not given |
| 7 | With no revision act recorded, D1 and D2 both stand — and `search_memory` may still label one lexically `superseded` **without** that affecting standing | The two meanings of the word leaking into each other |

Assertion 7 is the one that pins this whole document: it is the mechanical
statement that lexical supersession and governed revision are different things.

---

## 5. Explicitly out of scope

- Any code. This document produces none.
- Modifying PRL. Q2's shared projection would touch PRL and is deferred
  pending an explicit decision.
- Inferring revision from content. If nobody records a revision, no revision
  happened — the same discipline as source-ref integrity v0, where existence is
  reported and relevance is not inferred.
- Promoting `search_memory().time_status` to business semantics. Prohibited.

---

## 6. Recommendation in one line

**Agent Memory should adopt PRL's revision *shape* — a new append-only act,
standing derived at read time, ordered history preserved, author-aware,
ambiguity reported rather than resolved — under a name that cannot be confused
with `search_memory`'s lexical `superseded`; and the shared PRL/Agent Memory
projection should wait until that act exists and has been exercised.**
