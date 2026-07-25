# Architecture of implementation B

## The shape in one paragraph

B is a **relational pipeline**. It normalises the pack set exactly once into two flat relations, then answers
every question the law asks as a **query over those relations**. Composition is not a traversal: it is a
**memoised recursive value function over the fixed four-element rank lattice**, `val_upto(rank)`, and every
fact the trace has to report — which ranks changed the value, which permission governed each of those
changes, which rule strength to name, which packs were selected from and which were overridden — is obtained
by *interrogating the resulting value vector*, after it exists, rather than by remembering what happened while
building it.

## The two relations

Ingestion (`PackSet`) is the only code in B that touches the caller's sequence. It builds a dictionary keyed
by `content_hash` — which is where the R12 deduplication of two documents differing only in
`provenance.source_ref` happens — then a dictionary keyed by `pack_id@pack_version`. From that point on, the
input list no longer exists in any form.

```
DECL    (path, rank, pack_ref, merge?, override?)     one row per control declaration
CONTRIB (leaf_path, rank, pack_ref, value)            one row per governed leaf a pack actually carries
```

`DECL` carries the two control axes as **independently optional columns**. A control that declares `override`
but not `merge` produces a row with no `merge` column, and it therefore does not participate in any question
about `merge`. This is deliberate and is argued in the design journal (E05): a JSON-Schema `default` is a
reader convenience, not an act of authorship, and R3 fixes `merge` by an act of introduction.

`CONTRIB` is built only for the two in-scope sections. Reserved sections are accepted in the envelope and
never enter a relation, so they cannot be composed and cannot reach a hash.

## How a path is evaluated

`evaluate_leaf` runs five steps, and each one is a query whose input is the output of the previous:

1. **Peer reduction.** Group `CONTRIB` rows for the leaf by rank. Within a rank, if the contributions are not
   all canonically equal, then `union`/`intersect` fold them commutatively and `replace`/`append` raise
   `peer_conflict` (R4). The result is one value per contributing rank.
2. **The value function.** `val_upto(r)` returns the value the leaf has after every rank up to and including
   `r` has spoken, memoised on `r`. It is defined recursively on the ranks *below* `r`, never on an iteration
   variable. Evaluating it over the contributing ranks yields a **value vector**.
3. **Which ranks changed the value.** A rank changed the value iff `cform(val_upto(r))` differs from
   `cform(val_upto(previous contributing rank))`. This is a comparison of two members of the value vector —
   it is asked *of the answer*, not recorded during the computation of the answer.
4. **Permission at each changing rank.** The `override` floor at rank `r` is `max()` over every declaration
   covering the leaf at ranks `≤ r` (R3's monotone tightening), and `forbidden` short-circuits before any
   derogation is consulted (R5). `requires_derogation` looks for a derogation carried at that rank that
   *literally* names the leaf, and classifies: none → `derogation_required`; present but outside
   `[not_before, expires_at)` → `derogation_expired`; live → `derogated_override`.
5. **Trace facts from the resolved value (R12bis).** `selected_from` is every contributing pack whose own
   value is canonically equal to the *effective* value; `overridden_sources` is every contributing pack whose
   value is not. Under `append`/`union`/`intersect` every contribution survives into the result by
   construction, so `selected_from` is all of them and `overridden_sources` is empty. `resolution_rule` is the
   strongest fact true across the ranks, under the ordering the ADR gives.

Steps 3 and 5 are the reason the value function exists. If the rule strength and the source attribution were
accumulated during a fold, they would be facts about *the walk*; derived from the value vector, they are facts
about *the value*, which is what R12bis requires.

## Where the phases live

The phases are normative outputs, not a class layout. In B each is a **free function taking relations and
returning a list of refusals**:

```
phase_p1(packs)                          -> unknown_referent, duplicate_pack_identity
phase_p2(packs, resolver_version)        -> compatibility_violation
phase_p3(decl)                           -> merge_semantics_conflict, strategy_relaxation_refused
phase_p4(derogations)                    -> derogation_invalid
(composition)                            -> peer_conflict, forbidden_override,
                                            derogation_required, derogation_expired
```

`resolve` stages them and returns at the first phase that produced anything, reporting **all** of that
phase's refusals (R9). P5's refusals are the union of the refusals every leaf evaluation produced, which is
why a P5 refusal reports every contested leaf and not just the first one encountered.

Refusals are deduplicated by canonical form and sorted by `(code, path, pack_refs)` with the canonical form of
the whole refusal object as tie-break.

## Why permutation-invariance is structural, not tested

The claim is not "we ran the permutations and they agreed". The claim is that **no ordered structure derived
from the caller's list survives ingestion**, so there is nothing later in B that *could* depend on input
order.

Concretely:

- The caller's `Sequence[dict]` is read exactly once, in `PackSet.__init__`, into a dict keyed by
  `content_hash`. Dict insertion order is the only residue, and it is never read: every accessor
  (`all_refs`, `canonical_refs`, `refs_by_pack_id`) returns a **sorted** list.
- Where two documents collide on a key, the tie is broken by content (`cform`), not by arrival.
- `DECL`, `CONTRIB` and the derogation relation are each sorted by a content-derived key at construction.
- Each phase iterates over sorted relations and returns refusals that are sorted again by a content-derived
  total key before emission.
- Peer reduction under `union`/`intersect` folds over values sorted by `cform`, and both folds are
  commutative and idempotent on the element set, so the sort is belt-and-braces rather than load-bearing.
- The value function recurses on **ranks**, which come from the packs' declared layers, not from position.
- The manifest's `packs` list is sorted by `(layer_rank, pack_id, pack_version)` — R7's derived canonical
  order, used for reporting only.

The consequence is that `distinct_outputs == 1` is a **prediction of the design**. A value above 1 would not
be a variation to be tolerated or averaged; it would locate a specific leak of caller order into a derived
structure. There is a second, independent confirmation of the same property visible in the results:
`three-layer-baseline`, `three-layer-permuted` and `same-pack-different-source-ref` produce the *same*
`effective_manifest_hash`, because after ingestion their pack sets are literally the same set.

## Purity

`resolve()` performs no I/O, reads no clock, consults no environment variable, no locale, no filesystem
listing and no randomness (R10). `evaluated_at` is a parameter (R8). All file access lives in `replay_b.py`.

## What B does not do

B does not validate pack documents against `pack.v0.1.schema.json`. The vector file marks one pack
`schema_valid: false`, and the law requires the resolver to refuse it on its own terms — which it does, in P1,
because `regulator` is not one of the four layers. A resolver that relied on schema validation having happened
would be trusting a step outside itself.
