# A/B double replay — comparison report and verdicts

Branch `feat/daryl-packs-contracts-v0.1`, HEAD at the time of comparison `a17a89c`. Nothing pushed.
Both ADRs remain `Proposed`. `CAPABILITY_REGISTER.md` unchanged. No ADR, schema or vector was edited
at any point, before or after the comparison.

## What was compared

| | |
|---|---|
| A | the reference resolver, `docs/architecture/packs/tools/`, frozen; its result file `proof/results-a.json` |
| B | `resolver_b.py`, written in quarantine from the ADRs, schemas, examples, matrix and oracle-free vectors |
| B sealed at | `2026-07-25T20:46:52Z`, canonical hash `v1:5588919f360e0fb06b2010faa6a568c71d477aeeaa6b347305a7f870e58aaeaa` |
| vectors | 19, identical set in both files |
| permutations | 101, identical count per vector in both files |
| `distinct_outputs` | 1 for every vector in both implementations |

B's results were hashed and timestamped **before** implementation A was restored to the working tree
and before `results-a.json` was reopened. The comparison script verifies those hashes on every run
and aborts if a sealed artefact has moved.

## The seven axes, pre-correction

This is the independence result: B exactly as sealed, before it had seen anything of A.

| axis | agree | differ |
|---|---|---|
| 1 — resolved / refused status | **19** | 0 |
| 2 — effective manifest, by value identity | **19** | 0 |
| 5 — effective manifest hash | **19** | 0 |
| 3 — resolution trace | 14 | 5 |
| 4 — refusals and their R9 order | 6 | 13 |
| 6 — refusal hash | 6 | 13 |
| 7 — referenced artifacts | 1 | 18 |

49 axis divergences over 133 comparisons. Against the frozen oracles: A 0 divergences, B 18.

Five distinct causes, classified in `DIVERGENCE-JOURNAL.md` and recorded in `divergences-raw.json`
**before any correction**:

| # | divergence | class |
|---|---|---|
| D1 | `resolution_rule` on a commutative fold that crosses a layer | error in B |
| D2 | the content of `refusal.detail` | schema insufficiency + ADR ambiguity |
| D3 | `pack_refs` membership for `merge_semantics_conflict` | ADR ambiguity + schema insufficiency |
| D4 | `path` when the offending control declares a prefix | ADR ambiguity |
| D5 | multiplicity in the `artifacts` index | error in A + ADR ambiguity |
| D6 | `refusal-ordering-tie-break` cannot discriminate the tie-break | incomplete vector |

One implementation defect. Four places where the specification stops.

## The seven axes, post-correction

D1 alone was corrected, in B, after the journal and the raw divergence file were fixed on the record.
D2 through D5 were deliberately left divergent: they are specification holes, and closing them by
copying A's answer into B would replace a measurement of the specification with a measurement of
transcription.

| axis | agree | differ |
|---|---|---|
| 1 — resolved / refused status | **19** | 0 |
| 2 — effective manifest, by value identity | **19** | 0 |
| 3 — resolution trace | **19** | 0 |
| 5 — effective manifest hash | **19** | 0 |
| 4 — refusals and their R9 order | 6 | 13 |
| 6 — refusal hash | 6 | 13 |
| 7 — referenced artifacts | 5 | 14 |

40 axis divergences. Against the oracles: A 0, B 13 — and B now matches the oracle on **every one of
the six resolved vectors**, including `trace_hash`.

`results-b.r2.json`, canonical hash
`v1:eff8a7bb22f66691ea4c5366d29c87dd560180986ea3ae2860e9814885de3794`.

## What this establishes, and what it does not

**The resolved path is reproducible.** Two implementations with different internal architectures,
one of which never read the other, produce the same effective manifest by value identity and the same
canonical hash on all 19 vectors, under all 101 permutations, and — after B's one genuine defect was
removed — the same resolution trace and the same trace hash. That covers R3, R3bis, R4's commutative
cases, R5, R6's valid case, R7, R8, R10, R12 and R12bis. In particular:

- The **`content_hash` stripping rule** of R12 was reproduced exactly: B's independently written
  canonicaliser produced `v1:a502de35…`, `v1:3cd910ce…`, `v1:58a3a019…` for the three demo packs, the
  same values as A. Reproducing the hash proves the canonicaliser too, as the vector file says.
- **Permutation invariance is structural in both.** `distinct_outputs == 1` for every vector in both
  files, and the three vectors whose pack sets are equal after deduplication produce the same manifest
  hash in both.

**The refused path is not reproducible as specified.** All 13 refused vectors agree on outcome, on
phase, on refusal codes, on refusal count and on R9 ordering — and disagree on `refusal_hash`, every
one of them, because the refusal object contains fields the specification does not determine:
`detail` (unconstrained, optional, hashed), `pack_refs` membership (untyped per code, hashed) and
`path` under a prefix declaration (undecided, hashed *and* order-affecting). Two implementations can
both conform to `pack-resolution.v0.1.schema.json` and still cannot agree. This is not a defect in A
or in B; it is the schema permitting what its own field description says must not be permitted.

**Nothing here establishes cognitive independence.** B was written in the same session as A by the
same author. The quarantine removed A from the filesystem and the audit trail shows what was read and
when, but it could not remove A from the author's context. That is what the clean-room kit is for.

---

# Verdict 1 — local implementation B

**Mechanical equivalence: demonstrated for the resolved path, NOT demonstrated for the refused path.**

Demonstrated, on all 19 vectors and all 101 permutations, for: outcome, effective manifest by value
identity, effective manifest hash, resolution trace and trace hash (post-correction), refusal phase,
refusal codes, refusal count and R9 ordering.

Not demonstrated for: the refusal object and its hash, on 13 of 13 refused vectors; and the artifact
index on the one vector where the same pack arrives under two `source_ref` values. In each case the
divergence is traced to a specification gap, not to a disagreement about the law.

**Architectural independence: supported.**

B is a relational pipeline — two flat relations, phases as free queries, composition as a memoised
recursive value function over the four-rank lattice, and every trace fact derived by interrogating
the resulting value vector rather than accumulated during a walk. It is not a rewrite, a translation
or a permutation of A: it does not fold, and it has no per-pack traversal to record facts against.
The evidence for the claim is `ARCHITECTURE.md`, the append-only `DESIGN-JOURNAL.md` whose entries
E01–E18 were written before B ever met an oracle, and `COMMANDS.md`. The support is documentary, and
a reader is entitled to weigh it as such.

**Cognitive clean-room independence: NOT established.**

Stated without qualification. Constraint 2 of the original mandate — that B's author must not consult
the reference resolver's code during development — cannot be made true in a session whose context
already contains A. The filesystem quarantine, the audit trail and the pre-registered journal are
real and worth what they are worth; they are not this. B must therefore be described as an
**independent-architecture implementation**, never as a **clean-room independent implementation**.

# Verdict 2 — the external clean-room kit

**Clean-room kit: complete.**

`/tmp/out/daryl-pack-resolver-cleanroom-v0.1.tar.gz`, 34 549 bytes, sha256
`c60b0b1e69305f10b7a87800050344bf653ea297a7cbe5a54c330dbf5b831281`, built reproducibly. 16 files,
`KIT-MANIFEST.sha256` verifying `OK` on every line, manifest sha256
`94a75a472125c3ac0cbca89fba75c1adb806584ae2ed45e5cc17f790d30ef67c`.

Contains exactly what the mandate specified: the two normative ADRs, the two schemas, the five
example packs, the compatibility matrix, the 19 vectors stripped of all 19 `expected` blocks and all
20 per-pack `content_hash` values, the implementation brief, the result format, the normative
canonicalisation and hash rules, and the return protocol. Contains none of: A's code, any algorithmic
excerpt or function name from A, any result of A, any frozen oracle, any comment revealing how A
performs a step, and no defect journal.

Two leaks are disclosed in the kit README rather than removed: `ADR-PACK-0001` states in its own
normative text that a first implementation exists and refers to a `tools/` directory not shipped, and
its R9 rationale mentions that the ordering vectors' refusals sort on `detail` against their paths.
The ADR ships verbatim because shipping a mutilated law would create a larger divergence risk than
the one it removes.

**Ready for external implementation: yes.**

With one recommendation, which the comparison has now made concrete rather than hypothetical. The
kit's `BRIEF.md` already names `AMBIGUITIES.md` as the most valuable item in the return. The five
divergences found here are exactly the five things an external implementer will hit, and D2 in
particular means an external implementation **will** disagree on `refusal_hash` no matter how careful
it is. The kit is fit to send as it stands; sending it after the D2/D3/D4 amendments land would
produce a sharper result, because the refused half of the acceptance criterion would then be
answerable.

---

# Final recommendation

## `ADR specification still incomplete`

Not because the composition law is wrong — the resolved path came out identical, hash for hash,
between two independently architected implementations, which is the strongest evidence available that
the law itself is well posed. But the acceptance criterion the ADR sets for itself is:

> "Two independent implementations receiving the same packs, in any input order, must either produce
> the same effective manifest by value identity and the same canonical hash, **or produce the same
> typed refusal**."

The second clause is currently unsatisfiable. The refusal object is hashed, and three of its fields
are left to the implementer. Two conforming implementations cannot produce the same typed refusal,
and the one vector whose job is to pin the ordering tie-break agrees only by coincidence.

Four amendments close it, and they are small. They are written up separately in
`AMENDMENT-PROPOSALS.md`: fix `detail` per refusal code, fix `pack_refs` membership per code, decide
`path` for a prefix-declared control, and decide whether `artifacts` is an index or a ledger. None
touches the composition law. None requires regenerating an oracle — though closing D2 will change 13
`refusal_hash` values in the vector file, and that change is an amendment, adopted deliberately, not
a re-run of a generator.

Ratification, the capability register and the push remain three separate decisions, none of them
taken here.
