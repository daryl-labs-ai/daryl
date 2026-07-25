# Amendment proposals — ADR-PACK-0001 and `pack-resolution.v0.1.schema.json`

**Status: proposed, nothing applied.** No ADR, no schema and no vector was edited in producing this
document or anything that led to it. Both ADRs remain `Proposed`. `CAPABILITY_REGISTER.md` is
unchanged. Nothing is pushed. Adoption of any amendment below is a human decision, separate from
ratification, separate from the capability register, separate from the push.

These four amendments come from the A/B double replay recorded in `DIVERGENCE-JOURNAL.md`. They exist
because of one finding: the resolved half of the acceptance criterion is reproducible today and the
refused half is not. Two implementations with different internal architectures produced the same
effective manifest, by value identity and by canonical hash, on all 19 vectors under all 101
permutations — and could not produce the same `refusal_hash` on a single one of the 13 refused
vectors, because the refusal object is hashed and three of its fields are left to the implementer.

**None of the four touches the composition law.** The layer order, the two control axes and their
lattices, R4's peer rule, R5's absolute `forbidden`, R6's derogation conditions, R7's set semantics,
R8's explicit `evaluated_at`, R9's phase table and sort key, R10's purity, R11's ten codes, R12's
content-addressing and R12bis's label partition are all left exactly as they stand. What changes is
the determinacy of three fields the law already relies on, and one question about the replay envelope
that the envelope never answered.

A word on method before the proposals. Implementation A's outputs are recorded in the frozen vectors,
so any amendment that happens to match A's current behaviour costs nothing to adopt and any amendment
that does not costs a re-derivation. That asymmetry is a reason to be careful, not a reason to
choose. Each proposal below is argued on its merits, and each states plainly whether it coincides
with what A does today. Where it does not, the churn is named. Choosing A's answer *because* it is
A's answer would ratify a reference implementation as the specification, which is the failure mode
this whole exercise was built to detect.

---

## A1 — `refusal.detail` must be determined per refusal code

### The defect

`pack-resolution.v0.1.schema.json` defines the field as:

```json
"detail": {
  "description": "Canonical, machine-comparable discriminators only. Free prose here would break
                  hash equality between independent implementations.",
  "type": "object"
}
```

It is optional — absent from `required: ["code","path","pack_refs"]` — it is unconstrained, and it is
inside the object over which `refusal_hash` is computed. The description states the exact consequence
of getting the field wrong and the schema then specifies nothing that would let two implementations
get it right. A emits `detail` on all ten codes; B omits it on six and emits narrower objects on
three. Both conform. Neither can be said to be wrong.

R9 makes this worse than an equality problem. Its own rationale says the total tie-break exists
because *"two refusals sharing `(code, path, pack_refs)` and differing only in `detail` would
otherwise be ordered by whichever the implementation happened to construct first."* The ordering rule
therefore leans on `detail` as a sort key while the schema leaves `detail` undetermined — and
`refusal-ordering-tie-break`, the one vector whose declared purpose is to pin that tie-break, is
exactly the case where both refusals are identical in `(code, path, pack_refs)`. In this comparison
it agreed in both implementations only because `fiduciaire.aaa` sorts before `fiduciaire.zzz` under
both key sets. Rename A's `missing` key to `subject` and the agreement becomes a coin toss.

A second observation, about A rather than about the specification: A's `detail` for
`merge_semantics_conflict` carries `"reason": "merge semantics are fixed by the introducing pack…"`
and for `duplicate_pack_identity` carries `"reason": "same pack_id at multiple versions in one
resolution"`. Those are free prose in the field whose description forbids free prose, and they are
hashed. Separately, A uses two different key sets for one code: `compatibility_violation` is
`{requirement, pack_id, expected, actual}` when the required pack is present at a wrong version and
`{requirement, missing, expected}` when it is absent. One code with two shapes reintroduces
shape-dependence into the tie-break.

### The proposal

Make `detail` **required on every refusal**, **closed** (`additionalProperties: false`), and
**branched on `code`** in the schema via `allOf` / `if`-`then`. Add to R11 the sentence: *"Every
refusal carries a `detail` object whose key set is fixed by its code. The key set is closed: an
implementation emits exactly those keys, with those types, and no others. `detail` carries
discriminators, never explanation — no key whose value is a human-readable sentence."*

Proposed key sets, one per code:

| code | `detail` keys | type / domain |
|---|---|---|
| `duplicate_pack_identity` | `pack_id` | string |
| `unknown_referent` | `referent`, `value` | string, string |
| `compatibility_violation` | `requirement`, `subject_pack_id`, `expected_range`, `actual_version` | string, string, string, string or `null` when the pack is absent |
| `merge_semantics_conflict` | `declared`, `introduced` | sorted array of merge values; the introducing merge, or `null` at equal specificity |
| `strategy_relaxation_refused` | `floor`, `attempted` | override value, override value |
| `derogation_invalid` | `derogation_id`, `reasons` | string; sorted array over the closed enum below |
| `derogation_expired` | `derogation_id`, `window`, `evaluated_at` | string; `[not_before, expires_at]`; RFC 3339 |
| `derogation_required` | `layer_rank` | integer 0–3 |
| `forbidden_override` | `layer_rank`, `source` | integer 0–3; `"declared"` or `"fail_closed_default"` |
| `peer_conflict` | `layer_rank`, `merge`, `value_hashes` | integer 0–3; merge value; sorted array of `v1:` hashes of the competing canonical values |

Closed enum for `derogation_invalid.reasons`, one per R6 condition, so that the reason set is
mechanically derivable from the rule text: `missing_granted_by`, `missing_authority_id`,
`missing_key_id`, `scope_absent`, `scope_empty`, `scope_not_literal`, `bounds_absent`,
`non_positive_window`, `justification_empty`, `signature_absent`.

Three of these deserve their argument stated. `forbidden_override.source` distinguishes a control an
author wrote from the R3bis fail-closed default; those are the same refusal to a machine and very
different news to a human debugging a pack, and today only the vector name records which happened.
`peer_conflict.value_hashes` replaces A's `distinct_values` count: the count says two peers disagreed,
the hashes say what they disagreed about, both are machine-comparable, and the hashes are strictly
more useful at identical cost. `derogation_expired.window` makes the refusal self-contained — with
`evaluated_at` alone the reader must go back to the pack to see which side of the window was missed.

### Impact

This coincides with A on no code exactly. Up to 13 `refusal_hash` values in
`resolution-vectors.v0.1.json` change, and `refusal-ordering-by-path` and `refusal-ordering-tie-break`
must have their refusal *order* re-derived, not merely their hashes: `detail` is the final sort key.

**Those values are re-derived by hand and reviewed, never regenerated by running a resolver and
copying its output.** The distinction is the whole point: an expected block written by running the
implementation under test measures nothing. The procedure is to write the ten `detail` objects the
amended rule requires for the 13 refused vectors, order them under R9 by hand, canonicalise, hash,
and only then check that an implementation agrees.

---

## A2 — `pack_refs` membership must be fixed per refusal code

### The defect

The schema types `pack_refs` as an array of `pack_ref` and says nothing about what it contains. R11
lists the codes and does not say, for any of them, which packs the field names. The field is hashed
and it is the third key of the R9 sort.

A and B diverge on `merge_semantics_conflict`: A names only the pack attempting to redeclare the
semantics, `["jurisdiction.ma@0.7.0"]`; B names both the pack that introduced them and the pack
attempting to change them, `["fiduciaire.base@0.1.0","jurisdiction.ma@0.7.0"]`. Both readings are
defensible. Where the refusal is symmetric — two peers declaring different merges at equal
specificity — both implementations independently named both packs, which suggests the underlying
intuition is shared and only the asymmetric case is unpinned.

### The proposal

Add to R11: *"`pack_refs` names every pack whose contribution is constitutive of the refusal — the
packs without which the refusal would not arise — in canonical `(layer_rank, pack_id, pack_version)`
order. It is never empty."* Then the per-code table:

| code | `pack_refs` |
|---|---|
| `duplicate_pack_identity` | every pack sharing the `pack_id` |
| `unknown_referent` | the pack declaring the unrecognised value |
| `compatibility_violation` | the pack declaring the requirement (never the missing pack — it is named in `detail`) |
| `merge_semantics_conflict` | the introducing pack **and** the redeclaring pack; at equal specificity, both declarers |
| `strategy_relaxation_refused` | the pack attempting the relaxation, and the pack that set the floor |
| `derogation_invalid` | the pack carrying the malformed derogation |
| `derogation_expired` | the pack invoking the derogation |
| `derogation_required` | the pack attempting the change |
| `forbidden_override` | the pack attempting the change, and the pack that declared `forbidden` — the latter omitted when the floor is the R3bis fail-closed default, since no pack declared it |
| `peer_conflict` | every peer contributing a distinct value at that rank |

The constitutive reading — B's — is proposed over A's offending-pack-only reading for one reason
beyond symmetry with the equal-specificity case: a refusal is a statement about an incompatibility
between packs, and a reader who is handed one pack ref has to go and find the other end of the
conflict by inspection. Every code in the table above then reads the same way, which the
offending-pack-only reading cannot do for `peer_conflict`.

The `forbidden_override` row carries a sub-decision worth naming: under the fail-closed default the
array has one member and under a declared `forbidden` it has two, so the same code produces two
lengths. That is correct — the two cases genuinely differ in who is party to the refusal — and
`detail.source` from A1 makes the difference explicit rather than inferable from the length.

### Impact

Coincides with A on the symmetric cases, differs on `merge_semantics_conflict` (2 vectors),
`strategy_relaxation_refused` and declared-`forbidden` `forbidden_override`. Hash-affecting and
potentially order-affecting; re-derived by hand under the same procedure as A1.

---

## A3 — `path` when the offending control is declared on a prefix

### The defect

R3bis permits a control to name a leaf path **or a prefix**, longest match winning. The refusal schema
describes `path` as *"the contested leaf path, or `""` for refusals that are not path-scoped
(P1/P2)"*. A P3 refusal about a control declared on a prefix is neither case: it is path-scoped, and
the contested thing is a declaration rather than a leaf.

A reports the concrete leaf, `vocabulary.aliases.grand_livre`. B reports the declared prefix,
`vocabulary.aliases`. `path` is hashed and is the second key of the R9 sort. In this vector both
readings sort between `required_checks.checks` and `vocabulary.terms`, so the order survives — the
vector being kind, not the rule being determinate.

### The proposal

**Report the declaration site: the path as declared, prefix or leaf.** Add to R11: *"`path` is the
path at which the refused act occurred. For P3 refusals — which are about declarations — that is the
path the control declares, whether leaf or prefix. For P5 refusals — which are about values — it is
the contested leaf. For P1 and P2 it is `""`."*

This is B's reading, and the argument for it is that the alternative does not close. A prefix
declaration may cover several leaves, so reporting a leaf forces a second question the ADR has never
answered: one refusal per covered leaf, or one refusal naming one of them? If one per leaf, a single
bad declaration over a wide prefix produces an unbounded refusal set that grows with unrelated
content. If one naming one of them, the choice of which leaf is arbitrary and it is hashed. Reporting
the declaration site avoids both, and it is also the more accurate statement of what went wrong: the
author declared a conflicting `merge` on `vocabulary.aliases`, and that is true whether or not
`grand_livre` exists.

The counter-argument, which a reviewer should weigh, is operational: a consumer wanting to know which
concrete leaves are affected must expand the prefix themselves. If that matters, the expansion belongs
in `detail` as a sorted `covered_leaves` array, not in `path` — one refusal, one declaration site, and
the affected set carried alongside. That variant is compatible with everything else proposed here.

### Impact

1 vector, hash-affecting. Differs from A.

---

## A4 — `artifacts` is an index, not a ledger

### The defect

`REPLAY-ENVELOPE.md` says the envelope lists `pack_content` *"for every pack that reached the pack
set"* and does not say whether `artifacts` is a set of distinct content-addressed keys or a bag of
citations. On `same-pack-different-source-ref` A lists four `pack_content` entries, with
`jurisdiction.ma@0.1.0` appearing twice under the same key; B lists three. Both computed the same
`content_hash` values, and both produced a three-pack effective manifest from the four input
documents.

A's inconsistency is internal rather than interpretive: it deduplicated for the manifest and not for
the artifact index, in the same run, from the same set. No oracle covers this — none of the 19
`expected` blocks contains an `artifacts` key — so no vector could have caught it.

### The proposal

Add to `REPLAY-ENVELOPE.md`: *"`artifacts` is an index, not a ledger. It contains one entry per
distinct `(role, ref, key)` triple, in canonical order. A pack that arrives twice under different
`provenance.source_ref` values has one `content_hash` under R12 and therefore one entry. The index is
a projection of the pack set, and the pack set is a set."*

An index is proposed over a ledger because the envelope's purpose is to let a reader fetch what the
result refers to, and a duplicate key is not a second thing to fetch. If provenance multiplicity ever
needs recording — which `source_ref` values contributed a given content hash — that is a separate
field with a name that says so, not multiplicity in a lookup table.

### Impact

1 vector materially; A's behaviour changes, B's does not. No expected block changes, because no
expected block covers this axis — which is itself worth fixing: an `artifacts` assertion should be
added to at least `same-pack-different-source-ref`.

---

## Two items that are not amendments

**E1 — an editorial clarification to R12bis.** The rule reads: *"A path's rule is the strongest fact
true of it across all ranks — `introduction` when no layer above the introducing one changed the
value, `commutative_fold` when a higher layer changed it under `union`/`intersect`, `layer_override`
under `replace`/`append`, and `derogated_override` when a derogation was consumed to permit the
change."* The four conditions are mutually exclusive on merge strategy, so the strength ordering only
ever discriminates `derogated_override` from the rest. The sentence is correct and it reads as if the
ordering does more work than it does; B misread it in exactly that direction, took `layer_override` as
a weaker-but-true fact about a `union` fold that crossed a layer, and was wrong on five vectors. A
half-clause — noting that the labels partition on merge strategy and that the ordering discriminates
only the derogated case — removes the trap and changes no behaviour. Not an amendment because nothing
normative changes.

**E2 — two vector gaps.** First, R12bis conditions `commutative_fold` on a higher layer having
*changed* the value; no vector covers a `union` contribution from a higher layer that adds nothing —
a subset — where the value is unchanged and the label should, under a literal reading, be
`introduction`. One vector closes it. Second, `refusal-ordering-tie-break` cannot discriminate the
tie-break while `detail` is unspecified; A1 closes it, and after A1 lands the vector should be
re-checked to confirm it still exercises the total tie-break rather than agreeing by coincidence —
if the amended `detail` key sets make the two refusals differ earlier in the sort key, the vector has
stopped testing what it was built to test and needs a new pair.

---

## Adoption sequence

Order matters, because A1 changes the sort key that A2 and A3 also feed.

1. Adopt or amend the A1 key-set table, code by code. It is the largest change and everything else
   is downstream of it.
2. Adopt A2 and A3 — both are one sentence in R11 plus a table row each.
3. Amend `pack-resolution.v0.1.schema.json`: `detail` required and branched per code with
   `additionalProperties: false`; `pack_refs` documented per code; `path` documented per phase.
4. Re-derive, by hand, the `refusals` array of each of the 13 refused vectors: write the amended
   `detail`, apply the amended `pack_refs` and `path`, sort under R9, canonicalise, hash. Review the
   diff as a diff — 13 blocks, each small — and record the re-derivation as an amendment adopted, not
   as a regeneration.
5. Adopt A4 in `REPLAY-ENVELOPE.md` and add an `artifacts` assertion to at least one vector.
6. Apply E1 and add the E2 vectors.
7. Re-run both implementations against the amended vectors. The refused half of the acceptance
   criterion becomes answerable at this point and not before.

Step 4 is the one that can go wrong. No expected output in this file may be produced by running a
resolver and copying what it printed. A specification whose oracle is its implementation's output has
proved nothing, and the 0-divergence score A currently posts against these oracles is uninformative
for precisely that reason: nothing in the workspace establishes whether the 19 expected blocks were
authored independently of A or derived from it.

## What is deliberately not proposed

No change to the layer order or to the claim that derogation is not a layer. No change to the merge
or override lattices, to R4's peer rule, to R5, to R6's five conditions, to R7, to R8, to R9's phase
table or its `(code, path, pack_refs)` sort key, to R10, to R11's ten codes, to R12's stripping rule
or to R12bis's label partition. No change to any pack schema. No new refusal code. The composition
law came through the double replay intact — identical manifests, identical manifest hashes, and after
one defect in B was removed, identical traces and trace hashes on every resolved vector under every
permutation. Nothing above is an argument for touching it.
