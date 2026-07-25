# ADR-PACK-0001 — Pack Composition, Precedence and Resolution Refusal

**Status:** Proposed — **awaiting human ratification** · **Version:** v0.1 · **Date:** 2026-07-25 · **Regime:** `declared`
**Depends on:** ADR-PRL-0014 (pack context referents), ADR-PRL-0010 (`org_id`, cited), ADR-0002 (canonical JSON + `v1:` hashing), ADR-PRL-0004 (protocols/MEF), ADR-PRL-0011 (governed standing — vocabulary disambiguated, §R14)
**Axis:** composition / governance contract. **Nature:** defines **a contract, not an engine.** No interpreter, no
runtime, no MCP surface, **no kernel change** (`src/dsm/core/` is frozen).

> **Composition is a governed act, not a merge.** Layering rules is not "the last file wins". A pack layer
> may only change what a lower layer *permitted* it to change, under a strategy the lower layer *fixed*,
> and every silent ambiguity must become an **explicit typed refusal** rather than an arbitrary winner.

## Why now

`ADR-PRL-0014` names the context (`domain`, `pack_id`, `pack_version`, `jurisdiction`, plus `org_id` from
0010). Naming context is worthless if composing over it is undefined. The natural-language picture — *core,
then business, then jurisdiction, then organization, then derogation* — reads like a stack but is not one:
it contains a category error that would have shipped into the schema.

**The error:** derogation was drawn as the top precedence layer while `forbid_override` was drawn as a merge
strategy. Those two cannot coexist. If derogation sits above everything, `forbid_override` is decorative — a
sufficiently high derogation lifts it. If `forbid_override` is real, derogation is not a layer. Daryl cannot
ship a rule that reads as absolute and behaves as negotiable; that is precisely the failure mode a
professional-liability system exists to prevent.

**This ADR resolves it by demotion:** derogation is **removed from the precedence chain** and becomes a
**field-level, signed, scoped, expiring permission effect**, evaluated *inside* composition rather than above
it. And the single overloaded `merge_strategy` enum is split into two orthogonal axes, because "how values
combine" and "who may change them" are not the same kind of thing (§R3, and see **Deviations** at the end).

## Decision (the rule)

> Pack composition is a **total order over four layers** — `core < domain < jurisdiction < organization` —
> applied **per field**, under a **`merge` semantics fixed by the field's introducing layer** and an
> **`override` permission that may only be tightened**. **Derogation is not a layer.** Any ambiguity that
> would require input order, list order or import order to settle is a **typed refusal of resolution**, never
> a winner. Resolution is a **pure function** of *(pack set, evaluation instant, resolver version)*.

## The load-bearing invariant

> **Permutation-invariance or refusal.** Two independent implementations, given the same packs in **any**
> input order, must either produce the **same effective manifest by value identity and the same canonical
> hash**, or produce the **same typed refusal**. There is no third outcome. Any construct whose result would
> depend on the order the packs arrived in is, by definition, not a resolution — it is a refusal.

This is the same shape as the `ADR-PRL-0013` proof (two independent registries reconcile to identical derived
readings by **value identity**, with no shared tip). Composition is that property applied to rules instead of
acts.

## The rules (contract-level)

### R1 — Four layers, one total order, no fifth

`layer ∈ {core, domain, jurisdiction, organization}` with ranks `0 < 1 < 2 < 3`. The chain is closed: v0.1
adds no layer, and an unknown layer value is `unknown_referent` (§R11), never a silent extra rank.

### R2 — Derogation is not a layer

A derogation **never wins a value**. It only answers one question about one field: *was this override
permitted?* It is evaluated inside §R6, at the rank of the pack invoking it. Consequently a derogation can
never introduce a value, never outrank the organization layer, and never lift `forbidden` (§R5).

### R3 — Per-field control has two orthogonal axes

Every governed field declares, **at its introducing layer**, a control pair:

| Axis | Values | Mutability |
|---|---|---|
| `merge` — *how values combine* | `replace` · `append` · `union` · `intersect` | **Fixed at introduction. Immutable. Never overridable.** |
| `override` — *who may change it* | `open` · `requires_derogation` · `forbidden` | **Monotonically tightenable only** (`open < requires_derogation < forbidden`). |

The **introducing layer** of a path is the lowest-rank layer contributing it. A later declaration of a
*different* `merge` for the same path is `merge_semantics_conflict` (§R11) — not a re-negotiation. A later
declaration of a **strictly looser** `override` is `strategy_relaxation_refused`. Tightening is `max()` over
all declarations at ranks ≤ *r*, which is commutative and therefore permutation-invariant even among peers.

*Why two axes:* "tightening" is only well-defined on a permission lattice. `union → replace` is not a
tightening, it is a different semantics; folding both into one enum makes the mandatory invariant
*"la stratégie … ne peut être que resserrée"* unstatable. See **Deviations §D1**.

### R3bis — Control scope, and the fail-closed default

Governed content is an object tree. **Objects are namespaces; leaves are scalars or arrays**, and a leaf is
addressed by its dotted path (`vocabulary.terms.exercice.synonyms`). Merge semantics are defined on leaves
only: `replace` on any value; `append`, `union`, `intersect` on arrays (`union`/`intersect` compare elements
by canonical form and re-sort canonically, which is what makes them commutative).

A control declaration may name **a leaf path or a path prefix**; for a given leaf, the **longest matching
declaration wins**. Two declarations of equal length disagreeing on `merge` → `merge_semantics_conflict`;
disagreeing on `override` → resolved by `max()` (tightening, §R3), never by conflict.

A leaf covered by **no** declaration takes the **fail-closed default `{merge: replace, override: forbidden}`**.
This is a *declared* default, not a silent one: an author who forgets a control does not get a permissive
field, they get a field no higher layer can touch — and the first layer that tries gets `forbidden_override`
naming the exact path. Failing closed on an undeclared control mirrors `verify_hash` failing closed on an
unknown prefix (ADR-0002).

> **Asymmetry, deliberate:** controls may be declared by prefix; **derogation scope may not** (§R6 names leaf
> paths literally). A control is authored by the layer that *owns* the field, so breadth is convenience. A
> derogation is an exception granted *against* an owner's rule, so breadth is a loophole.

### R4 — Peer contributions are permitted only where they commute

Two packs at the **same rank** are **peers** — `jurisdiction.ma` and `jurisdiction.fr`, two domain packs,
two organization profiles. Nothing distinguishes them, so nothing may order them.

| `merge` | Peers at the same rank |
|---|---|
| `union`, `intersect` | **Allowed** — commutative and associative; peer contributions are folded, then folded into the accumulator. |
| `replace`, `append` | **Refused** (`peer_conflict`) as soon as ≥2 distinct packs at that rank contribute to the path with **non-identical values**. Their outcome would depend on order. |

Identical values from peers are **not** a conflict: value identity is the reconciliation criterion, exactly as
in ADR-PRL-0013. Two peers asserting byte-identical canonical values assert one thing, not two.

### R5 — `forbidden` is absolute

`override: forbidden` cannot be lifted — not by a higher layer, not by a derogation, not by an organization
profile, not by an authority of any rank. Any contribution at a rank above the introducing layer that would
change a `forbidden` path is `forbidden_override`. **There is no escape hatch, by construction**: the
derogation check in §R6 is only reached when the effective permission is `requires_derogation`.

### R6 — `requires_derogation` demands authority, scope and expiry — all three

A derogation is valid for a path at `evaluated_at` **only if all** hold:

1. **Signing authority** — `granted_by = {authority_id, key_id}`, both present and non-empty.
2. **Explicit scope** — `scope` is a **finite, literal list of field paths**. No wildcards, no prefixes, no
   "all". A derogation that does not literally name the path does not cover it.
3. **Bounded expiry** — `not_before` and `expires_at`, both RFC 3339 UTC, `not_before < expires_at`. An
   open-ended derogation is malformed, not permanent.
4. **Justification** — `justification`, non-empty. A derogation without a stated reason is malformed.
5. **Signature present** — `signature` over the canonical derogation body.

Missing 1–5 → `derogation_invalid`, **fail-closed and unconditional**: a malformed derogation anywhere in the
input refuses the whole resolution, even if the path it names is never contested. Well-formed but outside
`[not_before, expires_at)` at `evaluated_at` → `derogation_expired`. No covering derogation at all →
`derogation_required`.

> **Signature verification is declared here and NOT delivered in v0.1.** Ed25519 exists in `dsm-primitives`
> but is **not wired into the governance path**. v0.1 checks *presence and structure*, never cryptographic
> validity. See **Known prerequisites**. Until wired, a derogation is an *audit trail*, not an *authorization*.

### R7 — No implicit order may ever arbitrate

Input is a **set**. Any list, directory listing, import statement, glob expansion, YAML document order or
argument position that carries the packs is **transport, not semantics**. Implementations **must not** read
it. The only ordering the resolver may use is the derived canonical order `(layer_rank, pack_id,
pack_version)`, and that order may only drive **reporting and commutative folding** — never the outcome of a
`replace` or an `append` between peers (§R4).

### R8 — Evaluation time is an explicit input

`evaluated_at` (RFC 3339 UTC) is a **parameter of resolution**, never `now()`. A resolver that reads the wall
clock is non-conforming: it cannot be replayed, and Daryl's whole discipline is replay. Two resolutions at
two instants over the same packs are **two different resolutions** and are expected to differ.

### R9 — Refusal is phase-staged, complete within its phase, and canonically ordered

"First error encountered" is order-dependent and therefore forbidden. Resolution runs five phases; the
**first phase producing any refusal terminates resolution and reports every refusal of that phase**, sorted
by the total key given below:

| Phase | Codes |
|---|---|
| P1 identity & referents | `unknown_referent`, `duplicate_pack_identity` |
| P2 compatibility | `compatibility_violation` |
| P3 field control | `merge_semantics_conflict`, `strategy_relaxation_refused` |
| P4 derogation well-formedness | `derogation_invalid` |
| P5 composition | `peer_conflict`, `forbidden_override`, `derogation_required`, `derogation_expired` |

The ordering key is `(code, path, pack_refs)` and — **as a total tie-break** — the canonical form of the
whole refusal object. The tie-break is not decoration: two refusals sharing `(code, path, pack_refs)` and
differing only in `detail` would otherwise be ordered by whichever the implementation happened to construct
first. That is precisely the input-order dependence this rule exists to remove, reintroduced inside a
structure that gets hashed.

Two conforming implementations therefore agree on the **complete refusal set**, not merely on "it failed".
The refusal object is itself canonically serialized and hashed (§R12), so *"the same typed refusal"* is a
**hash equality**, not a judgement call.

Because this rule is invisible whenever a refusal set has only one member, it is pinned by two vectors that
exist for no other purpose. `refusal-ordering-by-path` produces three refusals sharing one code whose
`detail` fields sort in the opposite order to their paths, so an implementation that sorts the whole object
canonically — or that omits `path` from the key — produces a different `refusal_hash`.
`refusal-ordering-tie-break` produces two refusals identical in `(code, path, pack_refs)`, listing the
offending requirements in anti-canonical order in the pack document, so an implementation without the total
tie-break falls back on the order its author typed. Both were added after a mutation run showed that
reverting the key to a naive canonical sort still passed every other vector in the file: a rule no vector
can falsify is a comment, not a rule.

### R10 — Resolution is a pure function

`resolve(packs: Set, evaluated_at: Instant, resolver_version: Str) → Resolved(manifest, trace) | Refused(refusals)`

No I/O, no clock, no network, no locale, no environment, no randomness, no filesystem order. Same inputs →
byte-identical canonical output. This is what makes the acceptance criterion testable rather than aspirational.

### R11 — The refusal taxonomy is closed and typed

`peer_conflict` · `forbidden_override` · `derogation_required` · `derogation_invalid` · `derogation_expired` ·
`strategy_relaxation_refused` · `merge_semantics_conflict` · `compatibility_violation` · `unknown_referent` ·
`duplicate_pack_identity`.

Ten codes, closed in v0.1. An unrecognized code **fails closed** (mirroring `verify_hash`, ADR-0002): a
consumer that cannot type a refusal must treat it as refusal, never as success.

### R12 — The effective manifest is canonical and content-addressed

The effective manifest is a JSON object serialized by **`dsm_primitives.canonical_json`** and hashed by
**`dsm_primitives.hash_canonical`** → `v1:<sha256>`. **No new hashing law is introduced.** The manifest
contains the referents, `evaluated_at`, `resolver_version`, the pack set (canonically sorted, with each
pack's content hash) and the resolved governed sections — and **nothing order-dependent, no timestamps of
execution, no host, no paths**.

A pack's **`content_hash`** is `hash_canonical(pack_document)` with **`provenance.source_ref` removed** — a
`source_ref` records *where a copy was found*, and a referent is never its carrier (ADR-PRL-0014). Two
deployments loading the same pack from different paths must obtain the **same** `content_hash`, or the
value-identity criterion fails for a reason that has nothing to do with the rules.

The **effective manifest** and the **full resolution trace** are stored as **content-addressed artifacts**
keyed by their own `v1:` hash. They are not embedded in receipts.

### R12bis — The trace entry is *derived*, never narrated

The trace is hashed, so every field of it is part of the contract. A trace field that records *how a
particular implementation walked the input* — rather than *what is true of the finished value* — silently
breaks the acceptance criterion, because both implementations reach the same manifest and still disagree on
its trace hash. The three derived fields are therefore defined against the **resolved value**, not against
the fold:

**`selected_from` / `overridden_sources`.** For `merge: replace`, `selected_from` is every contributing pack
whose value is **canonically equal to the effective value**, and `overridden_sources` is every contributing
pack whose value is not; a pack at a lower layer that happens to have declared the same value is *not*
overridden, because value identity is the test, not rank. For `append`, `union` and `intersect` every
contribution survives in the result, so `selected_from` is all contributing packs and `overridden_sources`
is empty. Both lists are sets of `pack_id@pack_version`, canonically sorted.

**`resolution_rule`.** Ordered weakest to strongest: `introduction` < `commutative_fold` < `layer_override` <
`derogated_override`. A path's rule is the **strongest fact true of it** across all ranks — `introduction`
when no layer above the introducing one changed the value, `commutative_fold` when a higher layer changed it
under `union`/`intersect`, `layer_override` under `replace`/`append`, and `derogated_override` when a
derogation was consumed to permit the change. Taking the strongest rather than the last means the label does
not depend on which rank is visited last, and "a derogation was used here" cannot be masked by a later
ordinary change.

### R13 — The `PackResolutionReceipt` carries hashes, not content

Inline, and only: `resolver_version`, `evaluated_at`, `packs[] = {pack_id, pack_version, content_hash}`,
`effective_manifest_hash`, `trace_hash`, `outcome ∈ {resolved, refused}`, `refusal_codes[]` (sorted, when
refused), `contested_paths[]` (sorted). **No effective values, no trace entries, no pack bodies.** A receipt
is a citation, not a copy.

Three distinct acts, three receipts: **`PackLoadedReceipt`** (a pack entered the process),
**`PackResolutionReceipt`** (a rule set was composed), **`WorkReceipt` / `ReviewReceipt`** (work was done
under it, citing `effective_manifest_hash`). Per **Rule A**, a receipt is issued only after the DSM write
returns non-`None`.

### R14 — `contested_paths` is not `MEF.contested`

`contested_paths` = paths whose resolution overrode a lower-layer value **or** consumed a derogation. It is a
**composition** fact. `MEF.contested` (ADR-PRL-0011) is an **epistemic** fact about disagreeing agents. The
two are unrelated, must never be merged, and neither is derived from the other. The word is shared; the
referent is not.

### R15 — `accepted ≠ true`, restated for rules

A resolved manifest records **which rules were in force**, not **which rules were correct**. Composition is
governance, never truth. A conforming resolver that produces a manifest asserts nothing about the quality of
the packs it composed.

## Envelope and proof scope (v0.1)

The pack envelope **reserves** all fourteen sections so that later versions need not rewrite the envelope:

`identity` · `compatibility` · `composition` · `vocabulary` · `roles` · `capabilities` · `input_contracts` ·
`output_contracts` · `required_checks` · `validation_policies` · `risk_classes` · `evaluation_cases` ·
`provenance` · `signatures`

**The v0.1 proof carries only `vocabulary` and `required_checks`.** Every other governed-content section is
`reserved`: declarable, schema-shaped, but **not composed and not hashed into the effective manifest** by a
v0.1 resolver. Reserving a name is not proving a behaviour — the register discipline (`⚪🟡🔵🟢🏛`) applies
here as everywhere.

`required_checks` is deliberately in scope: it already exists in `swarm.v0.1`'s `WorkReceipt` as one of three
never-merged axes (`required_checks` / `claimed_checks` / `actual_checks`, coverage computed in replay, never
trusted from the author). Packs supply the *required* axis; they do not touch the other two.

## Non-goals (hard scope fence)

No engine, no interpreter, no resolver in `src/`. **No kernel change** — `src/dsm/core/` is frozen and
untouched. No MCP exposure. No permissions, tenancy or isolation mechanism. No signature verification (§R6).
No RR index change. No new hashing law (§R12). No pack registry, distribution, discovery or trust
bootstrapping. No claim about retrieval performance. **DSM remains infrastructure**: memory, provenance and
justification. Packs are *content DSM records*, and this ADR does not make DSM a business platform or an
agent framework.

## Known prerequisites, not delivered by this ADR

1. **RR index on `metadata`** — promoting `metadata` keys to first-class Read Relay index keys is validated on
   `proto/phase-7a-rr-action-name-index` (commit `58d7789`, navigator fix `e570841`) and is a **Phase 7b
   prerequisite not merged into `main`**. Until it lands, receipts can *record* `(pack_id, pack_version)` but
   cannot be *queried* by them at the sanctioned read path.
2. **Signature wiring in the governance path** — Ed25519 lives in `dsm-primitives` and is **not wired into the
   append/governance path**. §R6 therefore validates derogation *structure*, not *authority*. Until wired,
   **`requires_derogation` is procedurally enforced, not cryptographically enforced**, and must not be
   described as an authorization control.

Both are stated here so no reader infers a capability from a contract.

## Governance

This ADR is **Proposed** and must be **human-ratified**. It was drafted by an agent; drafting is a proposal,
never a ratification — an agent cannot move its own ADR to Accepted. Nothing in `CAPABILITY_REGISTER.md`
moves on this document: no row, no count, no proof-velocity line. A contract is not a proof.

## Proof gate

Executed at contract level in this lot, by `resolution-vectors.v0.1.json` + the non-normative checker in
`tools/`:

1. three fictional layers load, resolve, and produce a **canonical effective manifest** with a reproducible
   `v1:` hash and complete provenance;
2. **every permutation** of the input order yields the **identical** hash;
3. each refusal class fires on a dedicated vector, and its **complete refusal set** is stable under permutation;
4. the vectors were themselves checked by **deliberately breaking the rules and confirming they go red** —
   twenty-one seeded defects across both the expectations and the reference resolver, each caught. Two of the
   rules stated here were, before that run, satisfied by the implementation but falsifiable by nothing, and
   two vectors were added to close that gap. A passing vector file proves nothing until it has been shown
   capable of failing.

Not executed, and deliberately deferred to runtime: **a second, independent implementation.** Vectors make
the criterion falsifiable by a foreign implementer; they do not themselves constitute the two-implementation
proof. Promotion to 🟢 requires that second implementation and a real transcript — never a passing test in
this repository.

## Consequences & sequence

- **Ratification first.** Then a placement design, then a resolver, then the two-implementation proof.
- The schema (`pack.v0.1.schema.json`) is the **shape**; this ADR is the **law**. Where they disagree, this
  ADR governs and the schema is the defect.
- `ADR-PRL-0014` supplies the referents this ADR composes over and is not modified by it.
- A `PROOF_LOG.md` entry only on real proof.

## Deviations from the drafting brief

Recorded here rather than in a side channel, because a contract that silently reinterprets its brief is the
failure this series exists to prevent.

**D1 — `merge_strategy` split into `merge` + `override`.** The brief specified one enum,
`replace | append | union | intersect | forbid_override`. That enum mixes two categories: four *semantics*
and one *permission*. Two mandatory invariants become unstatable over it — *"forbid_override est absolu"*
(absolute relative to what other permissions? the enum has none) and *"la stratégie … ne peut être que
resserrée"* (there is no tightening order on `union`/`replace`). The two axes of §R3 preserve both invariants
exactly and lose nothing: `forbid_override` is `override: forbidden`, and the four semantics are `merge`.

**D2 — a fifth refusal code for expiry.** The brief's derogation requirements imply expiry checking but name
no code. `derogation_expired` is separated from `derogation_invalid` because *well-formed but out of force* and
*malformed* demand different operator responses — renew versus repair — and collapsing them would hide which
one happened.

**D3 — `resolver_version` at the trace envelope, not per entry.** The brief's trace object listed
`resolver_version` alongside `effective_value` on each entry. It is constant per resolution; repeating it on
every entry inflates a content-addressed artifact without adding information. It is carried once, at the
trace envelope and in the effective manifest. No information is lost.

**D4 — a fail-closed default control (§R3bis).** The brief did not say what happens to a leaf with no declared
control. Leaving it undefined would have made conformance untestable, and any permissive default would have
contradicted the refusal-over-ambiguity invariant.
