# RTM v0 — Relational Trust Model

**Status:** Unifying hypothesis, NOT an architecture to integrate.
**Frozen:** 2026-07-04
**Supersedes:** `experiments/RELATIONAL_TRUST_MODEL.md` (Boucle 5 draft)
**Derived from:** 6 experimental loops on isolated clone of `daryl-labs-ai/daryl` @ `a5e56dc`
**Kernel modified:** No. All experiments live in `experiments/`.

---

## What this document is

This is **not** a proposal to modify the canonical repository. It is a candidate
theory that explains why six independent experimental loops converged on
structurally identical findings, and a model under which those findings
dissolve.

It has been subjected to one active falsification loop (Boucle 6). It survived
on its core (integrity relations), and revealed an honest boundary
(authenticity). Its correct status is **unifying hypothesis**, not
"demonstrated result" and not "next architecture."

> **DSM a une intégrité locale forte ; RTM explore l'intégrité relationnelle authentifiée.**

---

## 1. The single observation

Six experimental loops, each starting from a different question (performance,
integrity, trust boundary, inter-agent, theory, falsification), converged on
one structural fact:

> **DSM protects objects. It does not protect the relations between them.**

| Loop | Started from | Vocabulary used | What it actually found |
|------|--------------|-----------------|------------------------|
| 1 | RR perf | "O(K) read" | The `index→entry` relation is rebuilt by re-scanning |
| 2 | hash perimeter | "3 unprotected fields" | `entry↔id`, `entry↔shard` relations are not pinned |
| 3 | trust boundary | "audit/query bypass" | Unpinned relations cross trust boundaries |
| 4 | inter-agent | "causality / identity gaps" | Cross-object relations are implicit, not first-class |
| 5 | theory | "0 % relation-objects" | Formalised the implicit graph (I/V/C/P) |
| 6 | falsification | "minimal? counter-example? regression?" | I/V/C/P resists; reveals missing 5th property A |

Each loop, read alone, looks like a set of component findings. Read together,
they describe one thing: **the integrity model is object-local.**

---

## 2. The implicit Relation Graph

DSM is, structurally, a directed graph. It is not described as one anywhere in
the codebase. The objects and the references between them form a graph whether
or not it is named.

**Nodes** (8 object types): Entry, Agent, Session, Receipt, DispatchRecord,
ComputeAttestation, RegisterEvent, Shard.

**Edges** (25 unique relation types), found by exhaustive static scan
(`experiments/rg1_edge_inventory.py`):

```
Entry ──prev_hash──▶ Entry              Entry ──source──▶ Agent
Entry ──session_id──▶ Session           Entry ──cited_entry_hash──▶ Entry
Receipt ──entry_hash──▶ Entry           Receipt ──issuer_agent_id──▶ Agent
Receipt ──dispatch_hash──▶ Dispatch     Receipt ──shard_tip_hash──▶ Shard
Dispatch ──dispatcher_entry_hash──▶ Entry
Dispatch ──target_agent_id──▶ Agent
Attestation ──entry_hash──▶ Entry       Attestation ──agent_id──▶ Agent
Attestation ──model_id──▶ Model
RegisterEvent ──agent_id──▶ Agent       RegisterEvent ──public_key──▶ Agent
... (25 total)
```

The graph already exists. It is distributed across the fields of eight object
types and is never materialised, traversed, or verified as a whole.

---

## 3. The five properties — I/V/C/P/A

For a relation to be a *trust object* in its own right — verifiable
independently of its endpoints, and attributable to a known author — it must
satisfy five properties.

| | Property | Question it answers |
|---|---|---|
| **I** | Integrity | Has the edge value been modified? |
| **V** | Verifiability | Can the edge coherence be recomputed and checked? |
| **C** | Completeness | Is a missing/truncated target detected? |
| **P** | Portability | Does the edge verify outside its local context? |
| **A** | Authenticity | Is the edge attributable to a known, verifiable identity? |

The first four (I/V/C/P) cover **relational integrity**. The fifth (A) covers
**identity authenticity**, and was identified by falsification (Boucle 6),
not by the original model.

---

## 4. The matrix — measured, not asserted

Classifying each of the 25 unique edges against I/V/C/P
(`experiments/rg2_edge_matrix.py`):

```
                          Integrity   Verifiability   Completeness   Portability
                          H/M  S      Y    N          Y    N         Y    N
Edge count                11   14     8    17         1    24        19   6
                          44%  56%    32%  68%        4%   96%       76%  24%
```

Decisive metric:

> **Edges satisfying I ∧ V ∧ C ∧ P: 0 / 25.**
> **Edges satisfying I ∧ V ∧ C ∧ P ∧ A: 0 / 25.**

Zero relations in DSM are end-to-end verifiable trust objects. The worst
coverage is **Completeness (4 %)**: 24 of 25 edge types produce silent dangling
references when their target disappears.

A (Authenticity) is **implicitly 0 %** because no current edge binds a
signature to a verifiable identity binding (see §6).

---

## 5. The model

### 5.1 Definition

A **Relation** is a first-class object:

```
Relation = (relation_type, source_hash, target_hash, payload, signature)
```

where `source_hash` and `target_hash` are *hashes of objects*, not references
to them.

### 5.2 The relation hash

```
relation_hash = hash_canonical({
    "relation_type": relation_type,
    "source_hash":   source_hash,
    "target_hash":   target_hash,
    "payload":       payload,
})
```

The relation hash pins **both endpoints by their canonical hash**. It does not
name them by id, shard, or path.

### 5.3 Properties satisfied by construction

- **I (Integrity)** — `relation_hash` covers type, both endpoint hashes, and
  payload. Any mutation is detected by recomputation.
- **V (Verifiability)** — `Relation.verify(source_obj, target_obj)`
  recomputes each endpoint's canonical hash and confirms it matches the
  pinned hash.
- **C (Completeness)** — if the target object is absent, its hash cannot be
  recomputed; verification fails with a specific "target missing" reason,
  not a silent dangling reference.
- **P (Portability)** — verification needs only the endpoint hashes, not the
  storage. A relation verified in context A verifies identically in context B.

### 5.4 Authenticity — the open property

A Relation may carry an Ed25519 signature over `relation_hash`. But that
signature proves only that *someone* held the private key. **Binding the key
to a claimed identity** requires a verifiable key→identity mapping — which
DSM's current `IdentityRegistry` does not provide (latest-wins, no owner
verification on re-registration, Boucle 4 IA3).

Therefore: **I/V/C/P are satisfied by the Relation construction; A is not.**
A is a separate problem (authenticated identity) that the Relation Object
*reports* but does not solve.

### 5.5 Prototype validation

`experiments/rg3_signed_relation.py` implements `SignedRelation` and tests it
against the five attack classes discovered across the prior loops:

```
Attack                           Result        Loop that exposed it
─────────────────────────────────────────────────────────────────────
R1  mutation of entry.id         survives ✓    Loop 3
R2  mutation of entry.shard      survives ✓    Loop 3
R3  agent identity forgery       detected ✓    Loop 4 (IA3)
R4  mutation of entry content    detected ✓*   Loop 2
R5  cross-context portability    verified ✓    Loop 4 (IA5)
```

\* R4 requires *composition*: `Relation.verify()` pins the expected hash;
`verify_hash(entry)` confirms the live entry matches it. The two together
form the complete proof.

---

## 6. Falsification results (Boucle 6)

Three active attempts to refute the theory:

### F1 — Minimality of {I, V, C, P}

**Hypothesis tested:** one property is derivable from another (reducible to 3).

**Method:** for each of the 6 pairwise reductions, search the empirical matrix
for a counter-example (an edge satisfying the reducer but not the reduced).

**Result:** all 6 reductions have counter-examples.
`experiments/f1b_full_minimality.py`. Plus a concrete demonstration: suffix
deletion of a 5-entry chain leaves `verify_chain` returning `corrupted=0` —
V passes, C fails. C ⊄ V.

**Verdict:** {I, V, C, P} is 2-by-2 independent → **minimal**. Theory resists.

### F2 — Counter-example without Relation Object

**Hypothesis tested:** a simpler mechanism (no new object) satisfies I/V/C/P.

**Three candidates analyzed** (`experiments/f2_counterexample.py`):

| Mechanism | I | V | C | P | Verdict |
|---|:---:|:---:|:---:|:---:|---|
| M1 — extend existing hashes | ✓ | ✗ | ✗ | ✓ | V, C uncovered |
| M2 — add ad hoc verify functions | ✗ | ✓ | ✓ | ✗ | I, P uncovered |
| M3 — reciprocal hash (bidirectional) | ~ | ✓ | ✓ | ✓ | circularity → converges to Relation Object |

The combination M1+M2 *would* cover all four, but equals a Relation Object
distributed across 25 sites instead of unified. The Relation Object is the
**non-redundant factorisation** of any complete solution.

**Verdict:** no simple mechanism covers I/V/C/P alone. Theory resists.

### F3 — Regression

**Hypothesis tested:** the Relation Object creates a new unprotected graph
requiring meta-Relations → infinite regress.

**Method** (`experiments/f3_regression.py`): enumerate the Relation's own
outgoing edges and check coverage.

**Result:**
- source/target hashes: auto-covered (in `relation_hash`).
- chaining (`prev_relation`): reuses the already-proven `verify_chain`
  mechanism — no meta-regression (demonstrated with a 3-relation chain).
- signature: **reports** the identity gap (Q3) — does not solve it.
- `relation_hash` is self-referential: covers its own outgoing edges, so the
  regression stops at level 1.

**Verdict:** no infinite regress. But the model **honestly reports** the
authenticity gap rather than closing it. This is what revealed property A.

---

## 7. Limits of the theory — what RTM does NOT do

1. **Does not solve authenticity.** A signed Relation does not prove the
   signing key belongs to the claimed identity. Property A requires a
   separate, verifiable key→identity binding (orthogonal problem).

2. **Does not specify Relation storage.** Whether Relations live in a
   dedicated shard or in the source object's metadata is undecided. Each
   choice has completeness implications.

3. **Does not specify a composition calculus.** When does R1 ∧ R2 imply R3?
   The model describes verifiable edges, not a logic over them.

4. **Does not prove minimality of {I,V,C,P,A}.** Pairwise independence was
   shown for {I,V,C,P}; A was added by falsification, not by independence
   proof. A could in principle reduce to one of I/V/C/P — this has not been
   tested.

5. **The Relation Object is not strictly necessary.** F2 showed M1+M2 covers
   I/V/C/P, just unfactored. RTM is the *canonical form*, not the *only*
   solution.

6. **Prototype only.** The validation is a 5-test prototype, not an
   integration. No claim is made about how a Relation layer would behave
   under the full DSM test suite.

---

## 8. Criteria for promotion to a canonical proposal

RTM is currently a **hypothesis**. For it to become a **canonical proposal**
(an ADR, a branch, anything the canonical repo would consider), the following
gates must be passed — in order, each blocking the next:

### Gate G1 — Independence of A
Prove (or disprove) that A is independent of {I,V,C/P} by the same
counter-example method used in F1. If A reduces to one of them, drop it and
the model stays at 4. If A is independent, the model is {I,V/C/P/A}.

### Gate G2 — Authenticity mechanism
Define a concrete mechanism for property A: a verifiable key→identity
binding that does not rely on latest-wins. Without this, RTM only covers
relational integrity, not authenticated trust.

### Gate G3 — Minimality over real DSM edges
Re-run the matrix classification on the *current* canonical `main` (not the
frozen clone) and confirm the 0/25 finding still holds. The matrix was
measured at `a5e56dc`; if `main` has drifted, re-measure.

### Gate G4 — Integration prototype
Port the `SignedRelation` prototype into a real DSM shard (dedicated
`relation` shard or metadata-embedded), run the **full** test suite, and
confirm: (a) no regressions, (b) the 5 attack classes still resist, (c) the
completeness property holds under the existing `verify_shard` infrastructure.

### Gate G5 — Composition semantics
Demonstrate at least one non-trivial composition: e.g. "R1(A produced E) ∧
R2(B cited E) ⟹ R3(B trusts E via A)" with a verifiable proof. Without this,
RTM is a model of edges, not of trust flow.

**Until G1–G5 are passed, RTM remains a hypothesis. No integration.**

---

## 9. What changes, what does not — if RTM is ever adopted

### Does not change

- The kernel (`src/dsm/core/`) — RTM lives above the freeze.
- The canonical hash (ADR-0002) — the 6-field entry hash is the *input* to
  relations, not what RTM replaces.
- The append-only invariant — Relations are themselves append-only records.
- Existing objects — Entry, Receipt, Dispatch keep their current shape.

### What RTM would add

- A `Relation` object type, with `relation_hash` covering both endpoint
  hashes.
- A `verify_relation()` that composes with existing `verify_hash()`.
- A way to name trust claims as cryptographic objects rather than storage
  fields.
- (Pending G2) a verifiable key→identity binding for property A.

### What it does not require

- Modifying any existing edge. S-edges can remain S-edges. RTM is *additive*.

---

## 10. Reproducibility

All claims in this document are reproducible from the experiment scripts in
`experiments/`:

```
rg1_edge_inventory.py     — §2: 39 edges / 25 unique
rg2_edge_matrix.py        — §4: the I/V/C/P matrix (0/25 complete)
rg3_signed_relation.py    — §5.5: prototype validation (5/5 attacks)
rg3b_r4_correction.py     — §5.5 footnote: R4 composition
f1_minimality.py          — §6.F1: C ⊄ V (suffix deletion)
f1b_full_minimality.py    — §6.F1: all 6 pairwise independences
f2_counterexample.py      — §6.F2: M1/M2/M3 analysis
f3_regression.py          — §6.F3: no meta-regression, A gap reported
```

Run with the project venv (Python 3.12). No network. No canonical-repo
access. No kernel modification.

---

## 11. Closing position

RTM v0 is an explanatory model that:

- **Unifies** six independent experimental loops under one structural fact
  (DSM protects objects, not relations).
- **Resists** falsification on its core (I/V/C/P minimal, no simpler
  counter-example, no regression).
- **Delimits** its own boundary honestly (property A — authenticity — is
  reported, not solved).
- **Blocks** its own promotion to architecture via five explicit gates
  (G1–G5), none of which have been passed.

Its correct use is not "implement this." Its correct use is **as a lens**:
when a future finding in DSM looks like a component bug, ask first whether it
is an instance of the object-vs-relation gap that RTM names. Six loops out of
six, the answer was yes.

That regularity is the strongest evidence that the hypothesis is pointing at
something real — and the explicit gates are what keep it honest.
