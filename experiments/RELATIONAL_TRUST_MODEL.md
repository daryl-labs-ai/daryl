# Relational Trust Model — A theory of verifiable relations between DSM objects

**Status:** Research draft — produced by experimental loop on isolated clone
**Date:** 2026-07-04
**Derived from:** 4 experimental loops (RR performance, hash perimeter, trust boundary, inter-agent)
**Kernel modified:** No. This is a model above the freeze line.

---

## 1. The single observation

Four independent experimental loops, each starting from a different question
(performance, integrity, trust boundary, inter-agent), converged on the same
finding, stated in different vocabularies:

> **DSM protects objects. It does not protect the relations between them.**

This is not a bug list. It is a structural property of the architecture. The
four loops are four readings of the same underlying fact:

| Loop | Vocabulary used | What it actually found |
|------|-----------------|------------------------|
| 1 (RR perf) | "O(K) read" | The relation `index→entry` is rebuilt by re-scanning |
| 2 (hash perimeter) | "3 unprotected fields" | The relations `entry↔id`, `entry↔shard` are not pinned |
| 3 (trust boundary) | "audit/query bypass" | Those unpinned relations cross trust boundaries |
| 4 (inter-agent) | "causality / ownership / identity gaps" | Cross-object relations are implicit, not first-class |

Each loop, read alone, looks like a set of component findings. Read together,
they describe one thing: **the integrity model is object-local.**

---

## 2. The Implicit Relation Graph

DSM is, structurally, a directed graph. It is not described as one anywhere
in the codebase. But the objects and the references between them form a graph
whether or not it is named.

### 2.1 Nodes

The first-class objects of the trust layer:

```
Entry            the atomic append-only record
Agent            an identity (registry / manager)
Session          a grouping of entries
Receipt          a portable attestation about an entry
DispatchRecord   a causal binding A→B
ComputeAttestation  an input→output binding
RegisterEvent    an identity claim
Shard            a physical partition of the log
```

### 2.2 Edges

Every field on every object that references another object *is* an edge. An
exhaustive static scan of the trust layer (`rg1_edge_inventory.py`) found:

```
Total implicit edges identified:  39
Unique relation types:            25 (after dedup by (source, field, target))
```

The edges distribute across the object layer as follows:

```
Entry ──prev_hash──▶ Entry              (chain)
Entry ──session_id──▶ Session
Entry ──source──▶ Agent                 (produced_by, implicit)
Entry ──cited_entry_hash──▶ Entry       (citation, convention only)
Entry ──cited_entry_id──▶ Entry

Receipt ──entry_hash──▶ Entry
Receipt ──entry_id──▶ Entry
Receipt ──issuer_agent_id──▶ Agent
Receipt ──dispatch_hash──▶ Dispatch
Receipt ──routing_hash──▶ Router
Receipt ──shard_tip_hash──▶ Shard

Dispatch ──dispatcher_entry_hash──▶ Entry
Dispatch ──dispatcher_agent_id──▶ Agent
Dispatch ──target_agent_id──▶ Agent
Dispatch ──routing_hash──▶ Router

Attestation ──entry_hash──▶ Entry
Attestation ──agent_id──▶ Agent
Attestation ──model_id──▶ Model
Attestation ──dispatch_hash──▶ Dispatch

RegisterEvent ──agent_id──▶ Agent
RegisterEvent ──public_key──▶ Agent
RegisterEvent ──owner_id──▶ Owner
```

The graph already exists. It is distributed across the fields of seven object
types and is never materialised, traversed, or verified as a whole.

---

## 3. The four properties a verifiable relation must have

For a relation to be a *trust object* in its own right — verifiable
independently of its endpoints — it must satisfy four properties. These are
not arbitrary; each is the formalisation of a failure mode observed in a
prior experimental loop.

### I — Integrity
The edge value is covered by a cryptographic hash. Mutation of the edge is
detectable on the carrying object alone.

- **H** — the field is inside a canonical hash (entry hash, receipt hash,
  attestation hash).
- **M** — the field is in `metadata`, which is itself inside the entry hash.
- **S** — the field is a separate attribute, mutable without invalidating
  its carrier.

### V — Verifiability
A function exists that checks the *coherence* of the edge: that the target
it names is the target it should name. Integrity protects the edge value;
verifiability protects the edge *meaning*.

- **Y** — a `verify_*` function (or equivalent) validates the relation.
- **N** — no such function exists; the edge is stored but never checked.

### C — Completeness
A dangling edge — target deleted, truncated, or never existed — is detected.

- **Y** — orphan/missing targets are reported at read time.
- **C** is almost universally absent in DSM (see §4). The pin-based tip
  check is the lone exception, and it covers only one edge type.

### P — Portability
The edge survives export/import across contexts. A relation verified in
shard X is verifiable in shard Y, or off-storage entirely.

- **Y** — the edge is hash-based; verification is context-free.
- **N** — the edge is id/path-based; resolution depends on local state.

---

## 4. The matrix — measured, not asserted

Classifying each of the 25 unique edges against the four properties
(`rg2_edge_matrix.py`):

```
                          Integrity   Verifiability   Completeness   Portability
                          H/M  S      Y    N          Y    N         Y    N
Edge count                11   14     8    17         1    24        19   6
                          44%  56%    32%  68%        4%   96%       76%  24%
```

The decisive metric:

> **Edges satisfying all four (I ∧ V ∧ C ∧ P): 0 / 25.**

Zero relations in DSM are end-to-end verifiable trust objects. Every relation
has at least one property missing. The architecture treats relations as
storage fields, not as cryptographic subjects.

The property with the worst coverage is **Completeness (4%)**: 24 of 25 edge
types produce silent dangling references when their target disappears. This
is the structural reason Loop 1 found `resolve_entries` returning stale
results and Loop 4 found transitive trust breaking silently under
truncation.

---

## 5. Why the four loops told one story

The matrix is the link between the empirical loops and the theory.

- **Loop 1 (RR performance)** operated on the `index→entry` edge. That edge
  is **S/N/N/Y** (separate, no verify, no completeness, portable). The
  O(K) cost was a *symptom* of rebuilding an unverifiable relation on every
  read.

- **Loop 2 (hash perimeter)** operated on `entry↔id`, `entry↔shard`,
  `entry↔version`. These are **S/N/N/N** and **S/N/N/Y**. The unprotected
  fields were not exceptions; they were three instances of a general
  pattern (56% of edges are S).

- **Loop 3 (trust boundary)** showed that S-edges which feed trust
  decisions (`shard`→audit policy, `id`→query join) produce real bypasses.
  The bypass is the *consequence* of V=N: there is no verify function to
  catch a mutated edge.

- **Loop 4 (inter-agent)** operated on `receipt↔dispatch`,
  `receipt↔entry`, `register↔agent`. These are all **S/N/N/Y** or
  **H/N/N/Y**. Even hash-protected edges (H) lacked verifiability (V=N):
  the issuer is hashed, but no function checks the issuer is *registered*.

The loops were not discovering different things. They were probing different
edges of the same graph and finding the same missing properties.

---

## 6. The Relational Trust Model (RTM)

### 6.1 Definition

A **Relation** is a first-class object:

```
Relation = (relation_type, source, target, payload)
```

where `source` and `target` are *hashes of objects*, not references to them.

### 6.2 The relation hash

```
relation_hash = hash_canonical({
    "relation_type": relation_type,
    "source_hash":   source,            # hash of source object
    "target_hash":   target,            # hash of target object
    "payload":       payload,           # relation-specific metadata
})
```

The relation hash pins **both endpoints by their canonical hash**. It does
not name them by id, shard, or path.

### 6.3 The four properties, satisfied by construction

- **Integrity (I=H):** `relation_hash` covers type, both endpoint hashes,
  and payload. Any mutation is detected by recomputation.
- **Verifiability (V=Y):** `Relation.verify(source_obj, target_obj)`
  recomputes each endpoint's canonical hash and confirms it matches the
  pinned hash. The relation is checked against live objects.
- **Completeness (C=Y):** if the target object is absent, its hash cannot
  be recomputed, and verification fails with a specific "target missing"
  reason — not a silent dangling reference.
- **Portability (P=Y):** verification needs only the endpoint hashes, not
  the storage. A relation verified in context A verifies identically in
  context B.

### 6.4 Prototype validation

`rg3_signed_relation.py` implements `SignedRelation` and tests it against
the five attack classes discovered across the prior loops:

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
form the complete proof. Neither alone is sufficient — and this composition
is precisely the boundary the object-local model does not formalise.

All five attacks that broke the current architecture are absorbed by a
Relation treated as a first-class trust object.

---

## 7. What changes, what does not

### Does not change

- The kernel (`src/dsm/core/`) — untouched. The model lives above the freeze.
- The canonical hash (ADR-0002) — the 6-field entry hash is the *input* to
  relations, not something RTM replaces.
- The append-only invariant — relations are themselves append-only records.
- Existing objects — Entry, Receipt, Dispatch keep their current shape.

### What the model adds

- A `Relation` object type, with `relation_hash` covering both endpoint
  hashes.
- A `verify_relation()` that composes with existing `verify_hash()` —
  closing the V and C gaps for any edge promoted to a Relation.
- A way to name trust claims ("A produced E", "B cited E", "R attests E")
  as cryptographic objects rather than as storage fields.

### What it does not require

- Modifying any existing edge. S-edges can remain S-edges. RTM is
  *additive*: a relation layer can be built over the current object layer
  without changing the object layer.

---

## 8. Consequences of the model

If the model holds, three things become possible that are not possible today:

1. **Transitive trust as a verifiable path.** Today, "C trusts A via B" is
   reconstructed by walking `prev_hash` and breaks silently if B is
   truncated (Loop 4, IA5). Under RTM, the path A→B→C is a chain of
   Relations, each individually verifiable, and a missing link is a
   detectable event, not an silent orphan.

2. **Cross-context proof portability.** A Receipt-plus-Relation bundle
   proves "B acted on A's dispatch" in any context that can recompute
   the endpoint hashes — no shard access required. The relation is
   self-contained evidence.

3. **A completeness metric for the trust layer.** Today there is no way
   to ask "what fraction of this agent's claimed relationships are
   verifiable?" The matrix in §4 gives the method; under RTM, the answer
   becomes a measurable coverage of the relation graph, not an absence.

---

## 9. Open questions (research, not implementation)

- **Relation storage.** Should Relations live in a dedicated shard, or be
  embedded in the metadata of their source object? Each has implications
  for the completeness check.
- **Relation ordering.** Does a Relation need its own `prev_hash`, or is
  it purely a typed edge? The answer affects whether the relation graph
  is itself chainable.
- **Minimality.** Which of the 25 implicit edges *need* promotion to
  Relations? The matrix suggests a priority order: edges feeding trust
  decisions (audit policy, query joins, identity claims) before edges
  feeding display or routing.
- **Composition laws.** Is there a calculus of relations — when does
  `R1 ∧ R2` imply `R3`? This is the question that would move RTM from a
  model to a logic.

---

## 10. Status

This document is the output of a research loop on an isolated clone. It is
not a proposal to modify the canonical repository. It is a candidate theory
that explains why four independent experimental loops converged on
structurally identical findings, and a model under which those findings
dissolve.

The empirical claims (§3, §4, §6.4) are measured and reproducible from the
experiment scripts in `experiments/rg*.py`. The theoretical claims (§5, §8)
are consequences of the model, not yet independently validated beyond the
prototype.
