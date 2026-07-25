# Design journal — implementation B

**Append-only.** Entries are added in the order decisions were taken and are never edited or deleted
afterwards. If a later entry contradicts an earlier one, both stay and the later one says so explicitly.

**Discipline in force while this journal is open:** implementation A is absent from disk under
`/tmp/daryl/docs/architecture/packs/` (its `tools/`, `proof/` and frozen vector file are held elsewhere and
are not opened). No expected output and no expected hash is available to B: the vector file B reads is
`inputs/resolution-vectors.INPUTS-ONLY.json`, from which 19 `expected` blocks and 20 pack `content_hash`
values were removed before B started.

---

## E01 — Scope of admissible inputs

Everything B is built from lives in `/tmp/implb/inputs/`: `ADR-PACK-0001-composition-and-precedence.md`,
`ADR-PRL-0014-pack-context-referents.md`, `pack.v0.1.schema.json`, `pack-resolution.v0.1.schema.json`,
`REPLAY-ENVELOPE.md`, `compatibility-matrix.example.yaml`, `examples/*.yaml`,
`resolution-vectors.INPUTS-ONLY.json`.

The compatibility matrix is read as documentation only: it declares itself non-normative and explicitly *not*
an input to resolution, and its row order carries no meaning. B never loads it at runtime.

## E02 — Architectural shape: relations and queries, not a fold

Decision: B is a **relational pipeline**. Ingestion normalises the pack set exactly once into two flat
relations:

- `DECL(path, rank, pack_ref, merge?, override?)` — one row per control declaration;
- `CONTRIB(leaf_path, rank, pack_ref, value)` — one row per governed leaf actually carried by a pack.

Every subsequent phase is a **pure query over these relations** returning a set of refusals. Composition is a
**memoised recursive value function over the fixed four-element rank lattice**, `val_upto(r)`, and every
downstream fact — which ranks changed the value, which permission applies there, which rule strength to
report, which packs are `selected_from` — is *queried from that value vector after the fact*, never
accumulated while walking.

Rationale, and why permutation-invariance is structural rather than tested: the input list is consumed once,
in a normalisation that builds sets and dictionaries keyed by derived identity. After that step no code in B
can observe the order the caller supplied, because no ordered structure derived from the input list survives
it. Every later ordering in B is a sort by a key derived from content (`(layer_rank, pack_id, pack_version)`,
`(code, path, pack_refs)`, canonical form). `distinct_outputs == 1` is therefore a *consequence* of the shape,
and any fan-out would indicate a leak of caller order into a derived structure — a defect, not a variation.

Note on independence: this shape was chosen deliberately so that no function of B corresponds to a function
of A. B has no per-pack "apply into accumulator" step and no narration produced during traversal.

## E03 — Canonicalisation and hashing

`canonical_bytes(v) = json.dumps(v, sort_keys=True, separators=(",",":"), ensure_ascii=True,
allow_nan=False).encode("utf-8")`; `hash_v1(v) = "v1:" + sha256(canonical_bytes(v)).hexdigest()`. Taken
verbatim from ADR-0002 as quoted in ADR-PACK-0001 and in `REPLAY-ENVELOPE.md`. Implemented from the formula
with `json` + `hashlib` only; no Daryl module is imported.

`cform(v)` (the canonical *string*) is used as the value-identity test everywhere the ADR says "identical
value" — R4 peer identity, R12bis `selected_from`, dedup of `union` elements.

## E04 — `content_hash` and pack identity

R12: a pack's `content_hash` is the canonical hash of the pack document **with `provenance.source_ref`
removed**. Decision on a detail the ADR does not spell out: when `source_ref` is the only key of
`provenance`, B keeps `provenance` as an empty object `{}` rather than deleting the `provenance` key. Reason:
the rule says to remove one field, not to remove its parent; removing the parent would make a pack that
declares only `source_ref` hash-equal to a pack that declares no provenance at all, which is a stronger
erasure than the rule asks for.

Consequence, intended by the vector `same-pack-different-source-ref`: two documents differing only in
`provenance.source_ref` have the same `content_hash`, so the ingest deduplicates them and the pack set has
three members, not four.

## E05 — Control resolution is per axis, and an omitted key is not a declaration

R3bis gives the longest matching declaration for a leaf, with the fail-closed default
`{merge: replace, override: forbidden}` when no declaration covers it.

**Ambiguity found.** `pack.v0.1.schema.json` gives `merge` a JSON-Schema `default` of `"replace"` and
`override` a `default` of `"forbidden"` *inside* a control object. A control that declares `path` and
`override` but not `merge` can therefore be read two ways: (a) it declares `merge = replace` explicitly, so it
participates in the R3-introduction rule and in the R3bis equal-length `merge` disagreement test; or (b) it
declares nothing about `merge`, and `merge` for that leaf is decided by whatever *other* declaration covers
it, falling back to the fail-closed default only if none does.

Decision: **(b)** — B resolves the two axes independently, and a control row participates in an axis only if
it carries that axis's key. Rationale: reading (a) makes an author who only wanted to tighten `override`
silently *introduce* a `merge` semantics that R3 then freezes permanently and R3bis can put into conflict
with a sibling — a large, invisible effect from an omitted key. The ADR describes `merge` as fixed *by the
introducing layer*, i.e. by an act of declaration, and a JSON-Schema `default` is a reader convenience, not an
act of authorship. Also recorded because it is testable: `jurisdiction.ma@0.5.0` declares
`{path: required_checks.retention_years, override: open}` with no `merge`, and under reading (a) that pack
would additionally have to be checked against `fiduciaire.base`'s `merge: replace` at the same path — same
value, so no conflict either way here, but the readings are not equivalent in general.

Flagged for the ambiguity register: **the ADR does not state whether schema defaults inside a control are
declarations.**

## E06 — `detail` on a refusal is hash-affecting and unspecified — the largest gap found

`pack-resolution.v0.1.schema.json` allows an optional `detail` object on each refusal and says of it:
"Canonical, machine-comparable discriminators only. Free prose here would break hash equality between
independent implementations." The refusal object is hashed whole (`refusal_hash`) and R9's tie-break sorts on
the canonical form of the whole refusal object. Therefore **`detail` participates in both the hash and the
order**, yet neither ADR-PACK-0001 nor the schema says what it contains for any code.

This is not academic. The vector `refusal-ordering-tie-break` gives one pack two unmet `requires_packs`
entries; both produce `compatibility_violation` with the *same* `path` (`""`) and the *same* `pack_refs`
(`[jurisdiction.ma@0.8.0]`). Without `detail` they are the same object and collapse to one refusal, and the
tie-break the vector exists to exercise never fires. With `detail`, its exact content decides both the hash
and which of the two sorts first. The specification does not determine this.

Compounding it, the vector file's own prose (`why` on `refusal-ordering-by-path`) describes `detail` as
"prose", which directly contradicts the schema's "no free prose" sentence.

Decision for B: emit `detail` **only where `(code, path, pack_refs)` does not already identify the defect
uniquely**, and never as prose:

- `compatibility_violation` → `{"pack_id": <required id>, "version_range": <required range>}` for a `requires_packs` miss; `{"requires_resolver": <min_version>}` for a resolver-version miss;
- `derogation_invalid` → `{"derogation_id": <id>}`;
- every other code → no `detail` key at all.

This is B's own reading, taken before any comparison. **If A differs here, the divergence is to be classified
as category 1 — ADR ambiguity — and not as a defect of either implementation, and it must be resolved by a
separate amendment, never by editing the ADR, the schema or the vectors.**

## E07 — Refusal ordering

R9: the first phase that produces any refusal terminates resolution and reports **every** refusal of that
phase, sorted by the total key `(code, path, pack_refs)` with the canonical form of the whole refusal object
as tie-break. B sorts on `(code, path, tuple(pack_refs), cform(refusal))` and deduplicates refusals by
canonical form before sorting, so the same refusal discovered twice is reported once.

## E08 — `pack_refs` membership per code

The ADR does not enumerate, code by code, which packs go in `pack_refs`. B's rule: **the packs whose act
constitutes the refusal**, sorted.

- `unknown_referent` → the offending pack alone.
- `duplicate_pack_identity` → every ref sharing the contested `pack_id`.
- `compatibility_violation` → the requiring pack alone (the requirement is its act; the absent pack has no ref).
- `merge_semantics_conflict` → every pack declaring `merge` at the contested path.
- `strategy_relaxation_refused` → the relaxing pack alone.
- `derogation_invalid` → the pack carrying the malformed derogation.
- `peer_conflict` → the peers contributing the distinct values.
- `forbidden_override` / `derogation_required` / `derogation_expired` → the pack whose contribution at the offending rank changed the value.

Flagged for the ambiguity register: **`pack_refs` membership is not specified per code.**

## E09 — `path` for refusals that are not leaf-scoped

The schema says `path` is "the contested leaf path, or `\"\"` for refusals that are not path-scoped (P1/P2)".
P4's `derogation_invalid` is not covered by that sentence. B uses `path: ""` for it: R6 makes an invalid
derogation refuse the whole resolution unconditionally *even if the path it names is never contested*, so the
refusal is not about a path. The derogation is identified in `detail` instead (E06).

For P3, `merge_semantics_conflict` and `strategy_relaxation_refused` use **the declared control path**, which
may be a prefix rather than a leaf — the conflict is between declarations, and it exists whether or not any
leaf under that prefix is carried by anyone.

Flagged for the ambiguity register: **the `path` of a P4 refusal, and whether a P3 refusal's `path` is the
declared prefix or each affected leaf.**

## E10 — Empty sections and the empty pack set

For a pack set carrying no governed content, B emits `sections: {}` rather than
`{"vocabulary": {}, "required_checks": {}}`, and `entries: []`, `contested_paths: []`. Rationale: the manifest
reports what was composed; a section nobody contributed to was not composed. The alternative reading — that
the two in-scope sections are always present because the proof scope is fixed — is defensible, and this
decision changes `effective_manifest_hash` for the `empty-packset` vector. Recorded as a decision, not a
certainty.

Flagged for the ambiguity register: **whether `sections` always carries the two in-scope section keys.**

## E11 — `derogation_applied` when no derogation was consumed

The trace-entry schema marks `derogation_applied` optional, types it `["object","null"]`, and describes it as
"null when none was needed". B emits `"derogation_applied": null` on every entry that consumed no derogation,
rather than omitting the key. Rationale: the description says what the null means, which only makes sense if
the null is written. This affects `trace_hash` for every resolved vector.

Flagged for the ambiguity register: **omit versus explicit null.**

## E12 — Version ranges and resolver version

`version_range` is only ever `>=A.B.C <D.E.F` (schema-pinned). B compares semver triples as integer tuples,
inclusive lower bound, exclusive upper. `requires_resolver.min_version` is satisfied when the running
resolver's triple is `>=` the required triple.

## E13 — Derogation window

R6: valid within `[not_before, expires_at)` — lower bound inclusive, upper exclusive. `evaluated_at` is an
explicit input (R8); B never calls a clock. Timestamps are compared as strings, which is order-correct for
the schema-pinned `YYYY-MM-DDTHH:MM:SSZ` form.

Form validity (P4) is checked independently of any window: a derogation whose `not_before >= expires_at` is
malformed regardless of `evaluated_at`, and that is a P4 refusal, not a P5 expiry.

## E14 — Which contributions are governed

Only the two in-scope sections, `vocabulary` and `required_checks`, are flattened, composed or hashed. The
seven reserved sections are accepted in the envelope and ignored entirely. Leaves are scalars and arrays;
objects are namespaces and are recursed into.

## E15 — Correction: the scope of `detail`, restated input-independently

First run of `replay_b.py` succeeded, and reviewing its refusals against E06 exposed a **drift between this
journal and the code**: the code was emitting `detail` on six codes (`unknown_referent` → `{layer}`,
`duplicate_pack_identity` → `{pack_id}`, `merge_semantics_conflict` → `{declared}`,
`strategy_relaxation_refused` → `{declared, floor}`, `peer_conflict` → `{merge}`, `derogation_expired` →
`{derogation_id}`), while E06 had committed to only two.

Worse, E06's own wording — "only where `(code, path, pack_refs)` does not already identify the defect
uniquely" — is **input-dependent**: whether two refusals collide depends on the pack set, so the same code
would carry `detail` in one vector and not in another. A refusal's shape must not depend on whether a
collision happens to occur.

Restated rule, which is what B now implements:

> `detail` carries the **identity of the sub-object of a pack that the refusal is about**, when that
> sub-object is not already named by `(code, path, pack_refs)`. Nothing else. Never prose, never a restatement
> of a fact already recoverable from the pack documents.

Which yields exactly three sites:

- `compatibility_violation` → `{"pack_id", "version_range"}` (the requirement entry) or `{"requires_resolver"}`;
- `derogation_invalid` → `{"derogation_id"}`;
- `derogation_expired` → `{"derogation_id"}`.

All other codes are about a pack and/or a path, both already named, and carry **no `detail` key**. The code
was aligned to this rule and the replay re-run. This correction was made **before any comparison with the
oracles or with implementation A**, and it does not change which vectors resolve or refuse, only the content
of `refusal_hash` for the affected codes.

E06's finding stands unchanged and is the important part: **`detail` is hash-affecting and unspecified.** Any
A/B divergence located in `detail` is category 1 — ADR ambiguity — and is to be settled by a separate
amendment, never by editing the ADR, the schema or the vectors.

## E16 — `resolution_rule` when a commutative fold also crosses a layer

R12bis says `resolution_rule` is the **strongest** fact true across ranks, ordered
`introduction < commutative_fold < layer_override < derogated_override`.

A leaf under `merge: union` contributed by two layers is simultaneously (a) a commutative fold and (b) a value
that changed at a higher rank under a control the introducing layer left `open`. Both facts are true; the
ordering says report the strongest, so B reports `layer_override`.

The contrary reading is arguable: a commutative fold is *not* an override in the ordinary sense — nothing was
displaced, everything survived — so one could hold that `commutative_fold` is the only fact true and
`layer_override` is reserved for `replace`/`append`. The ADR gives an ordering but does not say which facts
are "true" for a fold that crosses a layer boundary.

Decision: B reports the strongest true fact, i.e. `layer_override`. Concretely this makes
`required_checks.checks` in `derogation-valid` and `vocabulary.terms` in `three-layer-baseline` report
`layer_override` rather than `commutative_fold`.

Flagged for the ambiguity register: **whether a value-changing contribution at a higher rank under a
commutative merge counts as `layer_override` or only as `commutative_fold`.** This is trace-hash-affecting.

## E17 — What `duplicate_pack_identity` means

Reading taken: the pack set may not contain two **distinct** members sharing a `pack_id`. Two versions of the
same pack in one set is therefore a P1 refusal, which is what the vector `duplicate-pack-identity` (base +
`jurisdiction.ma@0.1.0` + `jurisdiction.ma@0.2.0`) exercises. Two documents that differ only in
`provenance.source_ref` are **not** two members: they collapse at ingest on equal `content_hash` (E04), which
is what `same-pack-different-source-ref` exercises. The two vectors together pin this reading, so it is a
reading the vectors support rather than a free choice.

`pack_refs` lists every ref sharing the contested `pack_id`; `path` is `""`.

## E18 — First complete run, before sealing

`python3 replay_b.py` → exit 0. 19 vectors, 101 permutations, `distinct_outputs == 1` for every vector.

| vector | outcome |
|---|---|
| three-layer-baseline | resolved |
| three-layer-permuted | resolved (same manifest hash as baseline) |
| same-pack-different-source-ref | resolved (same manifest hash as baseline) |
| peer-union-commutes | resolved |
| derogation-valid | resolved |
| empty-packset | resolved |
| peer-conflict-replace | refused P5_composition · peer_conflict |
| forbidden-override | refused P5_composition · forbidden_override |
| derogation-required | refused P5_composition · derogation_required |
| derogation-expired | refused P5_composition · derogation_expired |
| derogation-malformed | refused P4_derogation_form · derogation_invalid |
| strategy-relaxation-refused | refused P3_control · strategy_relaxation_refused |
| merge-semantics-conflict | refused P3_control · merge_semantics_conflict |
| undeclared-control-fails-closed | refused P5_composition · forbidden_override |
| unknown-referent-layer | refused P1_identity · unknown_referent |
| duplicate-pack-identity | refused P1_identity · duplicate_pack_identity |
| compatibility-violation | refused P2_compatibility · compatibility_violation |
| refusal-ordering-by-path | refused P3_control · merge_semantics_conflict ×3, sorted by path |
| refusal-ordering-tie-break | refused P2_compatibility · compatibility_violation ×2, separated only by `detail` |

The three vectors that resolve to the *same* manifest hash do so because their pack sets are equal after the
`content_hash` deduplication of E04 — that identity is a prediction of the design, not a coincidence.

`refusal-ordering-tie-break` emits `fiduciaire.aaa` before `fiduciaire.zzz` although `jurisdiction.ma@0.8.0`
declares them in anti-canonical order: the sort is on the canonical form of the whole refusal object, not on
declaration order. This vector is only discriminating **because** B emits `detail` there (E06/E15); an
implementation that emits no `detail` collapses the two refusals into one and the tie-break is never
exercised.

Sealing B now: `results-b.json` is hashed and timestamped before implementation A is restored or consulted.

---

## E19 — post-comparison correction of `resolution_rule` (D1)

**Recorded after the comparison, and after `DIVERGENCE-JOURNAL.md`, `divergences-raw.json` and
`results-b.sealed.json` were fixed on the record.** This is the first entry in this journal written with
knowledge of another implementation's output, and it is marked as such so that nothing above it is
contaminated by hindsight.

E16 chose `layer_override` for a `union` fold that also crosses a layer, reasoning that both facts were true
and that R12bis asks for the strongest. Re-reading R12bis after the comparison, that reasoning was wrong on
its own terms: the ADR does not offer four independently-true facts to be ranked, it partitions the four
labels by merge strategy — *"`commutative_fold` when a higher layer changed it under `union`/`intersect`,
`layer_override` under `replace`/`append`"*. Under `union`, `layer_override` is not a weaker true fact; it is
not true. The strength ordering does real work only for `derogated_override`.

E16 is therefore withdrawn as a reading of the ADR. It stands as a record of what a first reader concluded,
which is the reason it is not deleted: the sentence invited the error, and that invitation is worth an
editorial amendment even though the sentence is correct as written.

Two lines changed in `evaluate_leaf`:

- the unconditional pre-seeding of `commutative_fold` for commutative merges is removed — R12bis conditions
  the label on the value having *changed*, not on a fold having occurred;
- a rank that changes the value under an `open` floor now scores `commutative_fold` for `union`/`intersect`
  and `layer_override` for `replace`/`append`.

`append` moves from `commutative_fold` to `layer_override` as a consequence. No vector exercises `append`
across ranks, so this is unverified by replay; it follows the ADR text literally, and it is flagged as an
untested edge in the divergence journal along with the unchanged-value `union` case.

**Not corrected:** D2 (`detail`), D3 (`pack_refs` membership), D4 (`path` under a prefix declaration),
D5 (`artifacts` multiplicity). Each is a place where the specification does not decide, and aligning B with A
there would be transcription, not implementation. They go to amendment proposals instead.

---

## E20 — the sealed source is recovered, verified, and committed alongside the corrected one

**Recorded while assembling the commit.** A gap in the record, found and closed rather than described.

The D1 correction of E19 was applied to `resolver_b.py` in place. That left the workspace holding the
sealed *output* — `results-b.json`, sha256 `5588919f…` — with no source that produced it: the file whose
hash the comparison harness checked no longer matched, and the pre-correction resolver existed only as a
description of two edits in this journal. A sealed result whose source has been overwritten is a weaker
artefact than it looks, because nobody downstream can rebuild it.

The pre-correction source was reconstructed byte-exactly by inverting the two recorded edits, and the
reconstruction is verified twice over, mechanically: its sha256 is `d86d7ea931e1e91d488bcfc41208c6781d20ec55
8b25f60558750c447dbe3299`, the value the harness sealed before the comparison; and running it over the
oracle-free vectors reproduces `results-b.json` bit for bit, sha256 `5588919f…`. Both checks are re-runnable
from the committed tree via `reproduce.sh sealed`.

Both variants are therefore committed as sources, not merely as outputs: `sealed/` is B as it was when it
had seen nothing of A, `r2/` is B after D1. `MANIFEST.sha256` pins all seven files, and the comparison
harness verifies the variant it is asked for before it reads anything.

Nothing about the result changed. This entry records a repair to the *evidence*, not to the implementation:
what was a claim backed by a hash of a file that no longer existed is now a claim anyone can rebuild.
