# HexaShard v0.1 — Evidence

What was actually measured, what it supports, and what it does not. Every figure here
was independently reproduced at a pre-merge gate before this branch was created.

The raw research trees are deliberately **not** in this repository: they are hundreds
of megabytes of fixtures, raw provider logs and superseded working copies. This is the
summary; the recorded runs kept alongside it are in [`evidence/`](evidence/).

## How the architecture was arrived at

HexaShard did not start here. The sequence below is what the artifacts support.

| Stage | Question | Result |
|---|---|---|
| Cursor replication | does a hex-agent topology beat plain sharding? | **No.** Sharding supported; hex agents, six-neighbour routing and packets-as-truth not supported. Summary + retrieval won; pins restored constraints. |
| DSM partnership | is DSM needed as working memory? | **No.** Pins + retrieval reproduce the operational benefit. |
| DSM namespacing | does isolated DSM add unique value? | **No.** Audit/provenance only. |
| Core v0.1 | can the surviving mechanism be built small? | Yes — 68 tests, 20/20 acceptance criteria. |
| Independent cross-audit | does it hold up from outside? | Held up. |
| Paraphrase | does lexical retrieval survive rewording? | **Partly** — see below. |
| Z-depth / spatial / ports | does geometry earn a place? | **No** as a retrieval prior. Direct addressing and logical relations kept. |
| LIVE 001 (API) | does it hold with a real model? | **Inconclusive** — the run failed environmentally. |
| LIVE 001-L (local) | same question, local model | Bounded context completed where full context could not. n=1. |
| Adapter v0.1 | can it drive a real chat turn? | Yes — 34 tests, provider-independent. |

The surviving architecture is **summary + primary-source retrieval + pinned invariants
+ bounded active state**. Everything else on that list was removed.

## Core

Frozen as an archive before any downstream experiment ran:

```
268f0f08362982c2c6e85d5672d9f2e9efcc34f2e3306d40f5ee23e3763ca999
```

Five working copies existed across the labs. All five were verified byte-identical to
that archive, so every downstream result was produced against the same Core. The
modules in `src/hexashard/` are those same bytes.

**68 tests pass on Python 3.10, 3.12 and 3.14. The 20-criterion acceptance verifier
passes on all three.**

### MERIDIAN-9 — synthetic long project

260 turns over a 170,855-token store, with a live supersession at turn 80:

| Measure | Value |
|---|---|
| project store | 170,855 tokens |
| peak active state | 5,384 tokens (budget 6,000) |
| mean active state | 2,936 tokens |
| store : active ratio | **31.7x on this fixture** |
| epochs / rotations | 4 / 3 |
| handoff after rotation | 389 / 544 / 690 tokens |
| retrieval accuracy | 1.00 (10 planted queries) |
| authority accuracy | 1.00 |
| model calls | 0 |

Reproduced field-for-field after migration into this repository.

## Retrieval under paraphrase

The honest weak point. Frozen paraphrase bank against the same fixture:

| Level | n | retrieval acc | Hit@1 | Hit@3 | authority acc |
|---|---|---|---|---|---|
| original | — | 1.000 | — | — | 1.000 |
| P1 light | 13 | 1.000 | 0.846 | 0.923 | 0.714 |
| P2 medium | 13 | 0.769 | 0.385 | 0.615 | 0.286 |
| P3 heavy | 13 | 0.692 | 0.385 | 0.538 | 0.286 |

Recall degrades gracefully. **Rank-1 authority selection degrades sharply.** The
verdict recorded was "BM25 sufficient with caveats"; the caveats are load-bearing.
Embeddings were explicitly not adopted on this evidence.

## Adapter

**34 tests pass on Python 3.10, 3.12 and 3.14.** The Core tree digest is unchanged
before and after the suite.

Smoke project, 64 sources:

| Measure | Value |
|---|---|
| project store | 101,627 tokens |
| mean model-visible context | 336 tokens |
| peak model-visible context | 363 tokens |
| store : visible | **≈280x on this fixture** |
| session reset | correct |
| model prose written as a source | never |

A question with no supporting source produced an explicit no-source warning rather
than an unattributed answer.

## Live models

### LIVE 001 — external API — INCONCLUSIVE

288 calls, 170 HTTP 200 and 118 HTTP 400. At the 250k checkpoint **both** arms scored
0/48; the HexaShard arm's visible context there was ~1.2k tokens, so this was credit
exhaustion, not a context limit. Accuracy also fell at 100k for both arms.

A machine-computed verdict of `A` was produced from successful calls only. It was
rejected, correctly. **This experiment supports no claim in either direction and is
not cited anywhere in this documentation.**

### LIVE 001-L — local model — narrow but sound

`qwen3.6:35b-a3b` via Ollama, `num_ctx` 262,144, temperature 0, 240 evaluation rows,
120 per arm, paired on identical queries, no truncation. Failures are scored, not
excluded.

| Stored project | normal | hexashard | normal visible | hexashard visible |
|---|---|---|---|---|
| 10,359 | 11/24 | 11/24 | 7,761 | 1,158 |
| 26,118 | 12/24 | 11/24 | 18,434 | 1,158 |
| 50,535 | 19/24 | 19/24 | 35,171 | 1,191 |
| 100,716 | 23/24 | 22/24 | 69,241 | 1,211 |
| 251,187 | **0/24 — context limit** | 22/24 | — | 1,233 |

**What this supports:** at equal accuracy the bounded arm used roughly 1/58th the
model-visible context, and it completed the largest checkpoint where the ordinary
full-context arm could not run at all.

**What this does not support:** that HexaShard produces better answers. Below the
limit the arms are within one question of each other, and at 100k the full-context arm
is marginally ahead. **n=1, one model, one machine.**

## Claims this evidence does not license

Stated explicitly so they are not made later by accident:

- infinite or unlimited context
- prevention of hallucination
- any universal token-saving multiple — 31.7x and 280x are fixture measurements
- better model intelligence or answer quality
- semantic retrieval — retrieval is lexical
- any advantage from spatial or geometric structure — that was tested and rejected
