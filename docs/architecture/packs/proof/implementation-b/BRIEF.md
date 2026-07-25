# Brief — implementation B of the Daryl pack resolver

You are writing a **clean-room implementation** of a specification. A first implementation exists. You are
not allowed to see it, and nothing in this workspace reveals it. The point of the exercise is that two
implementations built independently either agree exactly or expose a hole in the specification — so any
peeking, however small, destroys the result you are being asked to produce.

## Absolute constraints

1. **Read only `/tmp/implb/inputs/`.** Everything you are permitted to know is in there.
2. **Do not read, list, grep, glob or open anything under `/tmp/daryl`, `/tmp/quarantine_A`, `/tmp/out`,
   `/root/.claude`, or any other path outside `/tmp/implb`.** Do not `find` for Python files elsewhere. Do
   not look for a reference implementation, a test harness, an expected-output file, or a git history. If you
   find one by accident, stop immediately and say so in your final message instead of using it.
3. **Do not search the web** for this specification or for prior art.
4. **No dependency on any Daryl module.** Do not import `dsm_primitives` or anything from the Daryl
   packages. Implement the canonicalisation and the hash yourself from the formula written in the ADR — it is
   two lines of `json` + `hashlib`. Python standard library only. `pyyaml` is available if you want to read
   the YAML examples, but the vector file already carries every pack document as JSON, so you probably do not
   need it.
5. **You have no expected outputs.** `inputs/resolution-vectors.INPUTS-ONLY.json` has had every machine
   oracle stripped (`expected` on each vector, `content_hash` on each pack). This is deliberate. Your job is
   to produce *your* answer, not to match someone else's. The oracles are revealed only after you have
   emitted your results.

## What to build

A resolver implementing `ADR-PACK-0001` — `resolve(packs, evaluated_at, resolver_version) → Resolved |
Refused` — whose outputs conform to `pack-resolution.v0.1.schema.json`.

Read, in this order: `inputs/ADR-PACK-0001-composition-and-precedence.md` (the law — where it and the schema
disagree, the ADR governs and the schema is the defect), `inputs/ADR-PRL-0014-pack-context-referents.md` (the
referents), `inputs/pack.v0.1.schema.json` and `inputs/pack-resolution.v0.1.schema.json` (the shapes),
`inputs/examples/` and `inputs/compatibility-matrix.example.yaml` (worked material),
`inputs/resolution-vectors.INPUTS-ONLY.json` (the inputs you must replay — its `why` fields are prose
documentation and are legitimate reading), and `inputs/REPLAY-ENVELOPE.md` (the output container; it is a
container only and contains no resolution rule).

Read the ADR carefully and more than once. It is short, dense, and every rule in it is load-bearing. Several
rules are stated in one sentence and have consequences across the whole algorithm — R3bis's longest-matching
control declaration and its fail-closed default, R4's value-identity test between peers, R9's phase staging
and total sort key, R12's `content_hash` with `provenance.source_ref` removed, and R12bis's derivation of
trace fields from the *resolved value* rather than from your traversal are the ones most easily missed.

## Architecture requirement

Your implementation must be **structurally your own**. Choose an algorithmic shape, justify it, and write it
down in `ARCHITECTURE.md`: how you represent contributions, how you evaluate a path, where each phase lives,
and — specifically — **why permutation-invariance is true by construction in your design rather than
something you tested for afterwards**. If you find yourself writing "then fold each pack in turn into an
accumulator", ask whether a shape that never sequences packs at all would express the rules more directly.

Do not copy the ADR's five-phase structure as your class layout just because it is numbered; the phases are
*normative outputs* (which refusals terminate resolution, and when) and you must honour them exactly, but
they do not dictate the internal shape of your evaluator.

## Deliverables, all under `/tmp/implb/`

| File | Contents |
|---|---|
| `resolver_b.py` | The implementation. Self-contained, stdlib only, no I/O inside `resolve()`. |
| `replay_b.py` | Replays every vector under **every** permutation of its pack list and writes `results-b.json` exactly as `inputs/REPLAY-ENVELOPE.md` specifies. |
| `results-b.json` | Your complete result. |
| `ARCHITECTURE.md` | Your design, in prose. Include the "why permutation-invariance is structural" argument. |
| `COMMANDS.md` | Every shell command you ran, in order, one per line, with a one-line note on what it was for. This is an audit trail for the independence claim — write it as you go, not from memory at the end. |

`replay_b.py` must report, per vector, `distinct_outputs` across permutations. **Every vector must have
`distinct_outputs == 1`.** If any vector fans out, that is a defect in your resolver, not a variation: fix it
before you finish. Do not "fix" it by discarding permutations.

## What "done" means

`results-b.json` exists, covers all 19 vectors, replays 101 permutations in total, and every vector has
`distinct_outputs == 1`. Your resolver refuses where the rules say refuse and resolves where they say
resolve — according to *your own* reading of the ADR. You will not know whether you agree with the other
implementation, and you should not try to find out.

In your final message, report: the architecture you chose in two or three sentences, the vector-by-vector
outcome you produced (`resolved` / `refused` with phase and codes), anything in the ADR or the schemas you
found **ambiguous, contradictory, or insufficient to decide a case** — this last point is the most valuable
thing you can give back, so be precise about the rule number and the case — and confirmation that you read
nothing outside `/tmp/implb/inputs/`.
