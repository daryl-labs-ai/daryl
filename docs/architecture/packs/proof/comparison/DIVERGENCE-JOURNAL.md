# Divergence journal — A versus B, and each against the frozen oracles

**Written before any correction.** The machine-readable record it classifies is
`divergences-raw.json`, produced by `compare_ab.py` at the moment the two result files were first
placed side by side. `results-b.sealed.json` (sha256
`5588919f360e0fb06b2010faa6a568c71d477aeeaa6b347305a7f870e58aaeaa`) is B exactly as sealed at
`2026-07-25T20:46:52Z`, before B's author had any contact with A or with an oracle.

Classification grid, as fixed before the comparison:

| # | class |
|---|---|
| 1 | ambiguity in the ADR |
| 2 | insufficiency of the schema |
| 3 | incorrect or incomplete vector |
| 4 | error in A |
| 5 | error in B |

A divergence may carry more than one class. No expected output was regenerated. No ADR, schema or
vector was edited.

---

## 0. The raw numbers

| | |
|---|---|
| vectors | 19, identical set in both files |
| permutations | 101 in both files |
| `distinct_outputs == 1` | every vector, both implementations |
| A/B axis divergences | **49** over 7 axes × 19 vectors = 133 comparisons |
| A against the frozen oracles | **0 divergences** on 19 vectors |
| B against the frozen oracles | **18 divergences** on 19 vectors |

Per axis, agree / differ over 19 vectors:

| axis | agree | differ |
|---|---|---|
| 1 — resolved / refused status | **19** | 0 |
| 2 — effective manifest, by value | **19** | 0 |
| 5 — effective manifest hash | **19** | 0 |
| 3 — resolution trace | 14 | 5 |
| 4 — refusals and their R9 order | 6 | 13 |
| 6 — refusal hash | 6 | 13 |
| 7 — referenced artifacts | 1 | 18 |

Read the top three rows first. **Every vector, in both implementations, reaches the same
resolved/refused verdict; every resolved vector reaches the same effective manifest by value
identity; and every one of those manifests has the same canonical hash.** That is the substantive
half of the acceptance criterion, and it holds without exception. The divergences are all in the
*reporting* surfaces — the trace label, the refusal discriminators, the artifact index — and they
concentrate in exactly the places the specification stopped short.

A caveat on the A-against-oracle column: it is not by itself evidence that A is right. Whether those
19 expected blocks were authored independently of A or derived from it is not established by
anything in this workspace, so a 0 there is consistent with A being correct and equally consistent
with the oracle being A's own output. It is reported, not relied on.

---

## D1 — `resolution_rule` on a commutative fold that crosses a layer

**Axis 3. Five vectors** (`three-layer-baseline`, `three-layer-permuted`,
`same-pack-different-source-ref`, `peer-union-commutes`, `derogation-valid`), two paths each
(`required_checks.checks`, `vocabulary.terms`).

    A: "commutative_fold"        B: "layer_override"

Every other field of every other trace entry is identical in the two implementations: same path set,
same `effective_value`, same `merge`, same `override`, same `selected_from`, same
`overridden_sources`, same `derogation_applied`. The divergence is one string in two entries.

B's reading was recorded in advance, in design journal entry E16: R12bis orders the labels weakest to
strongest and asks for *the strongest fact true of the path*; when a `union` fold also crosses a
layer boundary, B judged both facts true and took the stronger one.

**Classification: 5 — error in B.** On re-reading R12bis after the comparison, the ADR does not leave
this open. It binds each label to a merge strategy explicitly: *"`commutative_fold` when a higher
layer changed it under `union`/`intersect`, `layer_override` under `replace`/`append`"*. Under
`union`, `layer_override` is not a weaker true fact — it is not a true fact at all. B's E16 reading
imported the strength ordering into a place where the ADR had already partitioned the cases.
The specification decided this; B misread it.

**Residual editorial note (class 1, non-blocking).** Because the four conditions are mutually
exclusive on merge strategy, the "strongest fact true of it" ordering only ever discriminates
`derogated_override` from the rest. The sentence is correct but reads as if the ordering does more
work than it does, and it invited exactly the misreading B made. A one-clause clarification would
remove the trap without changing any behaviour. Recorded as a proposal, not applied.

**Untested edge, found while classifying.** R12bis conditions `commutative_fold` on a higher layer
having *changed* the value. No vector covers a `union` contribution from a higher layer that adds
nothing — a subset — where the value is unchanged. Under a literal reading the label there is
`introduction`. Nothing in the vector set pins it. Class 3, incomplete vector; no amendment needed,
one vector would close it.

**Correction status: corrected in B after this journal was written.** See §"Post-correction replay".

---

## D2 — the content of `refusal.detail`

**Axes 4 and 6. All 13 refused vectors.** This is the single largest source of divergence in the
comparison, and it accounts for every one of the 13 `refusal_hash` mismatches.

A emits a `detail` object on every refusal. B emits one on exactly three codes and omits the key on
the other six. Where both emit one, the contents differ:

| vector | A's `detail` | B's `detail` |
|---|---|---|
| `peer-conflict-replace` | `{"distinct_values":2,"layer_rank":2,"merge":"replace"}` | *(absent)* |
| `forbidden-override` | `{"layer_rank":3}` | *(absent)* |
| `undeclared-control-fails-closed` | `{"layer_rank":3}` | *(absent)* |
| `derogation-required` | `{"layer_rank":2}` | *(absent)* |
| `strategy-relaxation-refused` | `{"attempted":["open"],"floor":"requires_derogation"}` | *(absent)* |
| `unknown-referent-layer` | `{"referent":"layer","value":"regulator"}` | *(absent)* |
| `duplicate-pack-identity` | `{"reason":"same pack_id at multiple versions in one resolution"}` | *(absent)* |
| `merge-semantics-conflict` | `{"attempted":["replace"],"introduced":"union","reason":"merge semantics are fixed by the introducing pack…"}` | *(absent)* |
| `refusal-ordering-by-path` ×3 | as above, plus `{"declared":["replace","union"],"reason":"competing merge semantics at equal specificity"}` | *(absent)* |
| `derogation-expired` | `{"derogation_ids":["der.ma.retention.2026"],"evaluated_at":"2027-06-01T00:00:00Z"}` | `{"derogation_id":"der.ma.retention.2026"}` |
| `derogation-malformed` | `{"derogation_id":"der.ma.retention.malformed","reasons":["non_positive_window"]}` | `{"derogation_id":"der.ma.retention.malformed"}` |
| `compatibility-violation` | `{"actual":"0.1.0","expected":">=0.2.0 <0.3.0","pack_id":"fiduciaire.base","requirement":"requires_packs"}` | `{"pack_id":"fiduciaire.base","version_range":">=0.2.0 <0.3.0"}` |
| `refusal-ordering-tie-break` ×2 | `{"expected":">=1.0.0 <2.0.0","missing":"fiduciaire.aaa","requirement":"requires_packs"}` | `{"pack_id":"fiduciaire.aaa","version_range":">=1.0.0 <2.0.0"}` |

**Classification: 2 — insufficiency of the schema, and 1 — ambiguity in the ADR.
Not an error in either implementation.**

`pack-resolution.v0.1.schema.json` defines the field as:

```json
"detail": {
  "description": "Canonical, machine-comparable discriminators only. Free prose here would break
                  hash equality between independent implementations.",
  "type": "object"
}
```

It is **optional** — absent from the `required` list — it is **unconstrained** — `{"type":"object"}`
with no `properties`, no `required`, no per-code branch — and it is **inside the object the refusal
hash is taken over**. Those three facts together are a contradiction the schema states and then does
not resolve: its own description says that getting this field wrong breaks hash equality between
independent implementations, and it then specifies nothing that would let two independent
implementations get it right. B recorded this before running anything, in design journal entries E06
and E15, and it is what the comparison found.

Two consequences worth stating plainly:

1. **No two conforming implementations can be expected to agree on `refusal_hash`.** Both A and B
   satisfy the schema on all 13 refused vectors. They cannot agree, because the schema permits the
   field to be present or absent and permits any object when present. The refused half of the
   acceptance criterion is, as written, unsatisfiable by construction.
2. **A's own `detail` violates the field's stated intent.** `merge_semantics_conflict` carries
   `"reason": "merge semantics are fixed by the introducing pack…"` and `duplicate_pack_identity`
   carries `"reason": "same pack_id at multiple versions in one resolution"`. These are free prose in
   the field whose description forbids free prose. That is a class 4 observation about A —
   independent of which content is chosen, prose in a hashed discriminator is exactly the failure the
   schema warns against.

**Correction status: not corrected.** Aligning B's `detail` with A's would be writing the oracle into
B after seeing it, which is the one thing this exercise exists to avoid. The gap goes to an
amendment: the schema must specify, per refusal code, the exact key set of `detail`, and must make it
required-or-forbidden per code rather than optional. Until it does, the refusal hash is not a
conformance instrument.

---

## D3 — membership of `pack_refs` for `merge_semantics_conflict`

**Axis 4. Two vectors** (`merge-semantics-conflict`, `refusal-ordering-by-path` — 2 of its 3
refusals).

    A: ["jurisdiction.ma@0.7.0"]
    B: ["fiduciaire.base@0.1.0", "jurisdiction.ma@0.7.0"]

A names only the pack attempting to redeclare the merge semantics. B names both the pack that
introduced the semantics and the pack attempting to change them.

**Classification: 1 — ambiguity in the ADR, and 2 — insufficiency of the schema.**

The schema types `pack_refs` as an array of `pack_ref` and says nothing about membership. R11 lists
the codes; nothing in the ADR states, per code, which packs the field names. B pre-registered its
reading in journal entry E08 — "the packs whose act constitutes the refusal" — which for a conflict
between an introduction and a redeclaration is two packs, since neither alone constitutes it. A's
reading — the offending pack only — is equally defensible and arguably more useful operationally.
Both are conforming. The specification does not choose.

Note that the third refusal in `refusal-ordering-by-path`, the equal-specificity one, has *identical*
`pack_refs` in A and B: `["jurisdiction.fr@0.7.0","jurisdiction.ma@0.7.0"]`. Where the refusal is
symmetric between two peers, both implementations name both. The divergence appears only in the
asymmetric introduction-versus-relaxation case.

**Correction status: not corrected.** Goes to amendment: R11 should fix `pack_refs` membership per
code. This field is hash-affecting.

---

## D4 — `path` when the offending control declares a prefix

**Axis 4. One vector** (`refusal-ordering-by-path`, its second refusal).

    A: "vocabulary.aliases.grand_livre"      B: "vocabulary.aliases"

A reports the concrete leaf the conflict is about. B reports the path as the two packs declared it —
a prefix under R3bis.

**Classification: 1 — ambiguity in the ADR.**

R3bis establishes that a control may name a leaf **or a prefix** and that the longest match wins.
The refusal schema describes `path` as "the contested leaf path, or `""` for refusals that are not
path-scoped (P1/P2)". A P3 refusal about a control declared on a prefix is neither: it is
path-scoped, but the contested thing is a declaration, not a leaf. B pre-registered its choice in
journal entry E09. Nothing arbitrates.

Two observations that make this more than cosmetic. First, `path` is the second key of the R9 sort,
so the choice is order-affecting as well as hash-affecting — in this vector both readings happen to
sort between `required_checks.checks` and `vocabulary.terms`, so the order survives, but that is the
vector being kind, not the rule being determinate. Second, a prefix declaration may cover several
leaves; A's reading then has to answer "which leaf?" and the ADR does not say whether that is one
refusal per covered leaf or one refusal naming one of them.

**Correction status: not corrected.** Goes to amendment.

---

## D5 — multiplicity in the `artifacts` index

**Axis 7. One vector materially** (`same-pack-different-source-ref`); the other 17 differ on this
axis only because the trace hash or the refusal hash they cite differs, which is D1 and D2 seen
through a second surface, not an independent finding.

    A: pack_content ×4 — jurisdiction.ma@0.1.0 listed twice, with the same key both times
    B: pack_content ×3 — listed once

The two documents in question differ only in `provenance.source_ref` and therefore have the same
`content_hash`. **Both implementations computed that hash identically** — `v1:3cd910ce17c5…` — which
is an independent confirmation of R12's stripping rule, and both produced a 3-pack effective manifest
from the 4 documents.

**Classification: 4 — error in A, with 1 — ambiguity in the ADR as the mitigating reading.**

`REPLAY-ENVELOPE.md` says the envelope lists `pack_content` "for every pack that reached the **pack
set**". Under R12 and R7 the pack set is a set, deduplicated by `content_hash` — which is precisely
why the manifest has three entries. A produced a three-member manifest and a four-member artifact
list from the same input in the same run: it deduplicated for one surface and not for the other.
That internal inconsistency is what makes this a class 4 rather than a pure class 1. The mitigating
reading is that neither the ADR nor the envelope says whether `artifacts` is an index of distinct
content-addressed keys or a ledger of citations, and A may have intended the latter.

**Correction status: not corrected in either implementation.** Goes to amendment: state whether
`artifacts` is a set keyed by `(role, ref, key)` or a bag. Note that no oracle covers this axis at
all — the 19 `expected` blocks contain no `artifacts` key — so no vector could have caught it.

---

## D6 — the tie-break vector does not test the tie-break

**Not an A/B divergence. A finding about the vector set, surfaced by the comparison.**

`refusal-ordering-tie-break` produces two refusals that are identical in `(code, path, pack_refs)` in
both implementations:

    A: ("compatibility_violation", "", ("jurisdiction.ma@0.8.0",))  ×2
    B: ("compatibility_violation", "", ("jurisdiction.ma@0.8.0",))  ×2

The R9 sort therefore falls through to its final tie-break, the canonical form of the whole refusal
object — which means it falls through to `detail`, the field D2 shows is unspecified. A orders on
`{"expected":…,"missing":"fiduciaire.aaa",…}` before `…"missing":"fiduciaire.zzz"…`; B orders on
`{"pack_id":"fiduciaire.aaa",…}` before `{"pack_id":"fiduciaire.zzz",…}`.

Both put `aaa` before `zzz`. **The vector passes in both implementations for different reasons, and
would pass for a third implementation with a third `detail` schema, as long as the pack id happened
to fall early in whatever key that implementation chose.** It agrees by luck: `aaa` sorts before
`zzz` under both key sets. Change A's key from `missing` to `subject` and the agreement is a
coin-toss.

**Classification: 3 — incomplete vector.** It is the one vector whose declared purpose is to pin the
tie-break, and it cannot pin it while `detail` is unspecified. Closing D2 closes this too; until then
the vector should be read as testing nothing.

---

## Summary of classification

| # | divergence | axes | vectors | class | corrected |
|---|---|---|---|---|---|
| D1 | `resolution_rule` on a fold crossing a layer | 3, 7 | 5 | **5** (+1 editorial, +3 edge) | **yes, in B** |
| D2 | content of `refusal.detail` | 4, 6, 7 | 13 | **2 + 1** (+4 on prose) | no — amendment |
| D3 | `pack_refs` membership for `merge_semantics_conflict` | 4, 6, 7 | 2 | **1 + 2** | no — amendment |
| D4 | `path` for a prefix-declared control | 4, 6, 7 | 1 | **1** | no — amendment |
| D5 | multiplicity in `artifacts` | 7 | 1 | **4 + 1** | no — amendment |
| D6 | tie-break vector does not discriminate | — | 1 | **3** | no — closed by D2 |

One divergence was an implementation defect. **Four were the specification running out.**

---

## Post-correction replay

D1 alone was corrected, in B, after this journal was written and after `divergences-raw.json` and
`results-b.sealed.json` were fixed on the record. The correction is one condition in
`evaluate_leaf`: the label for a value-changing rank under an `open` floor is now `commutative_fold`
when the leaf's merge is `union` or `intersect` and `layer_override` when it is `replace` or
`append`, per R12bis's own partition, and the unconditional pre-seeding of `commutative_fold` for
commutative merges was removed.

Nothing else in B was touched. D2, D3, D4 and D5 are left divergent on purpose: correcting them would
mean copying A's answer into B after reading it, which would convert a measurement of the
specification into a measurement of my ability to transcribe.

Post-correction numbers are in `COMPARISON-REPORT.md`. The pre-correction numbers above remain the
independence result; the post-correction numbers show only what is left once B's one genuine defect
is removed.
