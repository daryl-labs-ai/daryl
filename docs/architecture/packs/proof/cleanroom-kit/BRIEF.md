# Implementation brief

## What you are building

A resolver for the Daryl pack composition law:

    resolve(packs, evaluated_at, resolver_version) -> Resolved | Refused

whose outputs conform to `spec/pack-resolution.v0.1.schema.json`, and a replay harness that runs it over
every vector in `inputs/resolution-vectors.INPUTS-ONLY.json` under **every** permutation of each vector's pack
list, emitting one result file exactly as `spec/REPLAY-ENVELOPE.md` specifies.

Language, runtime and internal design are yours. If you use Python, the standard library is enough — the
canonicalisation and the hash are two lines of `json` + `hashlib`.

## Reading order

1. `spec/ADR-PACK-0001-composition-and-precedence.md` — **the law**. Where it and a schema disagree, the ADR
   governs and the schema is the defect. Read it more than once; it is short, dense, and every rule is
   load-bearing.
2. `spec/ADR-PRL-0014-pack-context-referents.md` — what the referents are, and what they are not.
3. `spec/pack.v0.1.schema.json` and `spec/pack-resolution.v0.1.schema.json` — the shapes.
4. `inputs/examples/` and `inputs/compatibility-matrix.example.yaml` — worked material. The matrix declares
   itself non-normative and is **not** an input to resolution; its row order carries no meaning.
5. `inputs/resolution-vectors.INPUTS-ONLY.json` — the inputs you must replay. Its `why` fields are prose
   documentation of intent and are legitimate reading.
6. `spec/REPLAY-ENVELOPE.md` — the output container. It is a container only: it states no precedence, no
   merge semantics, no refusal ordering.

## Rules most easily missed

Stated here as pointers, not as answers — each is fully specified in the ADR and you must read it there:

- **R3bis**: a control may name a leaf path **or a prefix**; for a given leaf the longest matching declaration
  wins, and a leaf covered by no declaration takes a fail-closed default.
- **R4**: whether two peers conflict is a question about **values**, not about pack count.
- **R7**: the input is a **set**. No list order, import order, directory order or YAML order may arbitrate
  anything.
- **R8**: `evaluated_at` is an explicit input. Calling a clock anywhere is a defect.
- **R9**: phases are staged; the first phase that produces any refusal terminates resolution and reports
  **every** refusal of that phase, in a total order. "It failed" is not a result.
- **R12**: a pack's `content_hash` is computed over the pack document with one specific field removed.
- **R12bis**: the trace's `selected_from`, `overridden_sources` and `resolution_rule` are derived from the
  **resolved value**, not from the order in which your code happened to visit things.

## Architecture requirement

Your implementation must be **structurally your own**, and you must write down what you chose and why, in
`ARCHITECTURE.md`: how you represent contributions, how you evaluate one path, where each phase lives, and —
specifically — **why permutation-invariance is true by construction in your design rather than something you
tested for afterwards**.

Do not adopt the ADR's five-phase numbering as your class layout merely because it is numbered. The phases are
*normative outputs* — which refusals terminate resolution, and when — and you must honour them exactly, but
they do not dictate the shape of your evaluator.

## Deliverables

| File | Contents |
|---|---|
| your resolver source | The implementation. No I/O inside `resolve()`. |
| your replay source | Replays every vector under **every** permutation and writes the result file. |
| `results-<label>.json` | Your complete result, per `spec/REPLAY-ENVELOPE.md`. |
| `ARCHITECTURE.md` | Your design in prose, including the permutation-invariance argument. |
| `COMMANDS.md` | Every command you ran, in order, one per line, with a one-line note on what it was for. |
| `AMBIGUITIES.md` | See below. This is the most valuable thing in the return. |

`<label>` is the implementation label you were given in `RETURN-PROTOCOL.md`.

## The acceptance number

Your replay must report, per vector, `distinct_outputs` across permutations. **Every vector must have
`distinct_outputs == 1`.** A value above 1 means your output depended on the order its input arrived in. That
is a defect in your resolver, not a variation, and it must be fixed — never by discarding permutations.

The full run is 19 vectors and 101 permutations.

## `AMBIGUITIES.md` — read this twice

You have no expected outputs, so you cannot resolve a doubt by testing. When the specification does not decide
a case, **you must decide it, record the decision, and record that the specification did not decide it.**

For each such point, write: the rule number, the exact case, the readings you saw, which you chose, why, and
whether your choice changes a hash. Be precise; "the ADR is vague about derogations" is not usable, "R6 does
not say whether the derogation window's upper bound is inclusive, and my choice changes `trace_hash` for
vector X" is.

This file is the reason the exercise exists. Two implementations that agree tell us the specification is
reproducible. Two that disagree tell us **where** it is not — and your record of *why* you chose as you did is
what turns a disagreement into an amendment rather than an argument.

## Forbidden

1. **Do not seek out, read or accept any other implementation of this specification**, in any language, in
   whole or in part, before your results are emitted and returned. If you encounter one by accident, stop and
   say so in your return instead of using it.
2. **Do not seek out expected outputs, expected hashes or any oracle for these vectors.** They exist. They are
   withheld deliberately. Obtaining them destroys the only result this exercise can produce.
3. **Do not depend on any Daryl module.** Implement the canonicalisation and the hash yourself from
   `CANONICALISATION.md`.
4. **Do not modify anything in `spec/` or `inputs/`.** If you believe a spec file is wrong, that is an entry in
   `AMBIGUITIES.md`, not an edit. A specification changed to make an implementation pass has proved nothing.

## What "done" means

Your result file exists, covers all 19 vectors, replays 101 permutations, and every vector has
`distinct_outputs == 1`. Your resolver refuses where the rules say refuse and resolves where they say
resolve — **according to your own reading**. You will not know whether you agree with anyone else, and you
should not try to find out.
