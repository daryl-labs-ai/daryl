# REPRODUCTION_REPORT

Everything below was re-run at the gate. No number is quoted from a report.

## Core identity — the strongest result in this body of work

The immutable archive's SHA-256 matches the historically reported value exactly:

```
268f0f08362982c2c6e85d5672d9f2e9efcc34f2e3306d40f5ee23e3763ca999
```

Five separate working copies of the Core exist across the labs. All five hash to the
same tree digest as a fresh extraction of that archive:

```
2bbc2d4fc6afa4298b2528f40825f8e1a81271621766f213344396eb5063e5c3   n=27  (fresh extraction)
2bbc2d4fc6afa4298b2528f40825f8e1a81271621766f213344396eb5063e5c3   n=27  zdepth/control
2bbc2d4fc6afa4298b2528f40825f8e1a81271621766f213344396eb5063e5c3   n=27  audit/immutable_from_tgz
2bbc2d4fc6afa4298b2528f40825f8e1a81271621766f213344396eb5063e5c3   n=27  audit/extracted
2bbc2d4fc6afa4298b2528f40825f8e1a81271621766f213344396eb5063e5c3   n=27  audit/work
2bbc2d4fc6afa4298b2528f40825f8e1a81271621766f213344396eb5063e5c3   n=27  paraphrase/core
```

**§8 answered: yes.** Later experiments genuinely ran against the same frozen Core.
There is no divergence to locate. This is unusually clean.

## Core v0.1 test suite

Run from a *fresh extraction of the archive*, not from any working copy:

| Python | Result |
|---|---|
| 3.10.12 | 68 passed |
| 3.12.13 | 68 passed |
| 3.14.6 | 68 passed |

3.10, 3.12 and 3.13 are DARYL's CI matrix; 3.10 and 3.12 were exercised directly.

## Acceptance verifier

`verify_acceptance.py` — **20/20 criteria pass** on 3.10, 3.12 and 3.14, including
the architectural boundary checks (no agent-per-Hex, no six-neighbour routing, no
Hex-to-Hex LLM chatter, no DSM dependency, no packet-as-truth).

## MERIDIAN-9 integration

Reproduced, and the regenerated `integration_results.json` is **field-for-field
identical** to the recorded run:

| Measure | Value |
|---|---|
| project store | 170,855 tokens |
| peak active state | 5,384 tokens (budget 6,000) |
| store : active ratio | 31.7x |
| retrieval accuracy | 1.00 |
| authority accuracy | 1.00 |
| epochs / rotations | 4 / 3 |

Note the ratio is **31.7x on this fixture** — not a general property.

## Adapter v0.1

| Python | Result |
|---|---|
| 3.10.12 | 34 passed |
| 3.12.13 | 34 passed |
| 3.14.6 | 34 passed |

Smoke reproduces the reported figures: store 101,627 tokens, mean model-visible
context 336, peak 363, store:visible ≈ 280x, session reset OK.

Core tree digest after the full Adapter suite is unchanged. **Core unchanged: yes.**

## Paraphrase experiment (§10)

Deleted the recorded `results/summary.json`, re-ran `run_experiment.py`, and
compared. **Bit-for-bit identical.** The experiment is fully deterministic (zero
model calls). The recorded file was restored to its original digest
(`2e064b62…`), so no frozen evidence was disturbed.

Reproduced figures:

| Slice | n | retrieval acc | Hit@1 | Hit@3 | authority acc |
|---|---|---|---|---|---|
| Original baseline | — | 1.000 | — | — | 1.000 |
| P1 (light) | 13 | 1.000 | 0.846 | 0.923 | 0.714 |
| P2 (medium) | 13 | 0.769 | 0.385 | 0.615 | 0.286 |
| P3 (heavy) | 13 | 0.692 | 0.385 | 0.538 | 0.286 |

Verdict **B — "BM25 sufficient with caveats"** is *arithmetically* supported, but
"with caveats" is carrying real weight: authority accuracy falls to **0.286** under
medium and heavy paraphrase. See LIMITATIONS.

## LIVE 001 — external API (§13)

288 calls, **170 HTTP 200 / 118 HTTP 400**. Per-cell accuracy over full
denominators:

| Checkpoint | normal | hexashard |
|---|---|---|
| 10k | 11/24 | 11/24 |
| 25k | 10/24 | 11/24 |
| 50k | 19/24 | 19/24 |
| 100k | 12/24 | 12/24 |
| 250k | **0/48** | **0/48** |

At 250k *both* arms scored zero. The HexaShard arm's model-visible context there
was ~1.2k tokens, so this cannot be a context-window failure — it is credit
exhaustion, an environmental failure. Accuracy also *fell* at 100k for both arms,
consistent with the run degrading mid-flight.

**Verdict F — INCONCLUSIVE is correct and independently confirmed.** The machine
letter `A` in `summary.json` was computed on successful calls only; rejecting it
was the right call. LIVE 001 supports no claim in either direction.

## LIVE 001-L — local model (§14)

Verified from raw rows, not from the report:

- model identity: `qwen3.6:35b-a3b` on every one of 240 rows
- **n = 240**, 120 per arm, 24 per arm per checkpoint — balanced
- **pairing: identical `(query_id, checkpoint, rep)` sets across arms** — fair
- truncation: `False` on all 240 rows
- **denominators are full**: 150 correct answers reconcile exactly against n=24
  cells, and the failed `normal` 250k cell is scored **0/24, not excluded**

**No successful-call-only bias.** This is the methodological failing that sank
LIVE 001, and 001-L does not repeat it.

| Checkpoint | normal | hexashard | normal visible | hexashard visible |
|---|---|---|---|---|
| 10k | 11/24 | 11/24 | 7,761 | 1,158 |
| 25k | 12/24 | 11/24 | 18,434 | 1,158 |
| 50k | 19/24 | 19/24 | 35,171 | 1,191 |
| 100k | 23/24 | 22/24 | 69,241 | 1,211 |
| 250k | **0/24 (CONTEXT_LIMIT)** | 22/24 | — | 1,233 |

**Verdict B is justified, and must be read narrowly.** What the data shows is that
at equal accuracy HexaShard used ~1/58th the model-visible context, and completed
the checkpoint where the Normal arm could not run at all. What it does **not** show
is that HexaShard answers better: at 10k–100k the two arms are within one question
of each other, and at 100k Normal is marginally *ahead*. The replication is **n=1,
one model, one machine**.
