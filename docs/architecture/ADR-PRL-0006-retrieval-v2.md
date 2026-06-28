# ADR-PRL-0006 — PRL Retrieval v2 — Recall Engine (NOT a registry ADR)

**Status:** Accepted — ratified-by-Mohamed 2026-06-27 · **Version:** v2.0 · **Date:** 2026-06-27 · **Regime:** `declared`
**Axis:** **recall-engine** — this ADR governs *how PRL retrieves a session from a question*. It is
**not** a registry-constitution ADR and decides nothing about epistemic governance, contracts, or
state. The constitution series (0001–0005) is untouched; 0004/0005 stay reserved.
**Depends on:** ADR-PRL-0001 (Constitution), ADR-PRL-0003 (Vocabulary)
**Supersedes:** the experimental note `PRL_RETRIEVAL_V2_FINDINGS.md` (which remains the evidence record).
**Nature:** *engineering decision, experimentally grounded.* Every load-bearing claim below is
backed by a falsifiable measurement on the real corpus. Where a measurement did not settle a
question, this ADR says so and does not decide it.

> **PRL does not make project knowledge true. It makes project knowledge governable.**

**Axis note.** This ADR sits on the **recall-engine** axis (how PRL retrieves the right session
from a natural-language question — the P7-v2 / query layer), *not* the registry-constitution axis.
The constitution series — 0001 Constitution · 0002 Architecture · 0003 Vocabulary · **0004
Protocols** (next) · 0005 Implementation — is unchanged; 0004 and 0005 remain reserved and
deferred. This ADR neither advances nor blocks them.

**Reading note.** This document freezes a *level of knowledge*, not a finished engine. It records
the best design demonstrated to date and draws an explicit line where the evidence stops.

---

## 1. Context — measurement designed this engine

After P9 the MVP was complete and the next phase was **measurement, not implementation**
(`PRL_EVAL_PROTOCOL.md`). A human-ratified benchmark (`questions_v2.json`: 15 questions, 5 easy /
7 normal / 3 hard, 0 provisional, 15 distinct gold conversations) was replayed against the real
ChatGPT export through a sequence of single-variable experiments (A–F). Each experiment
**eliminated a wrong design before it became architecture.**

What the data falsified, in order:

- **Not the binder.** Misses were recall-bound, not ranking-bound; the binder rescued cases but
  was never the bottleneck.
- **Not the ranking.** When the gold reached the candidate set, ordering handled it.
- **Not the 200-char preview length.** Widening the opening window (Exp A) *hurt* — and was
  confounded by the model's 256-token cap; a single global vector is simply the wrong unit.
- **Not chunking alone.** Chunking recovered buried decisions (Q6) but regressed clean title
  matches (Q2) — not a strict win.
- **Not RRF alone.** Symmetric RRF-sum is a compromise: piecewise-dominated (preview better on
  normal, chunk better on hard) and it *actively harmed* title-mismatch hard cases.
- **Not the fusion policy alone.** The asymmetric chunk-primary policy won the aggregate but did
  **not** rescue the title-mismatch hard frontier (Q15).

This convergence — by elimination, on data — is the substance of this ADR.

## 2. Decision — Retrieval Policy v2.0

PRL retrieval v2 is **two independent retrievers fused by an asymmetric, chunk-primary policy,
then boosted by the binder**:

```
query
  ├─ Retriever A : conversation-level (title + preview)   → title-evident cases
  └─ Retriever B : passage-level (transcript chunks)      → buried decisions
        │
   Fusion = CHUNK-PRIMARY, PREVIEW-GATED
     • chunk is the base ranker
     • preview adds a bonus ONLY when its rank ≤ gate (gate = 10)
     • a poor preview rank contributes nothing — it can never penalize a strong chunk hit
        │
   binder boost   (title-independent signal, tiebreaker)
        │
   Top-K  (conversation + best supporting passage)
```

**Frozen parameters (best measured to date):** combiner `chunk_primary`, `preview_gate = 10`,
`rrf_k = 10`, `chunk_chars = 500`. These are **configuration, never constants** — recorded as the
measured optimum, not as eternal truths.

**Measured result (15 ratified questions):**

| Policy | Top-1 | Top-3 | Top-5 | easy | normal | hard |
|---|---|---|---|---|---|---|
| chunk alone | 20% | 53% | 53% | 20/80/80 | 14/29/29 | 33/**67/67** |
| fusion sum (k10) | 47% | 60% | 67% | 80/100/100 | 29/43/57 | 33/33/33 |
| **chunk_primary gate10** | **60%** | **67%** | **67%** | **100/100/100** | **43/57/57** | 33/33/33 |

No other measured policy does better overall. `chunk_primary gate10` is therefore the **production
retrieval policy v2.0**.

## 3. What is proven (acquired)

1. **Passage retrieval is necessary.** It is the only mechanism that recalls buried decisions a
   single conversation vector misses (Q6: RECALL_MISS → Top-1).
2. **Conversation retrieval remains useful.** Preview owns title-evident cases (easy + most
   normal); the gated preview bonus recovered Q2 (RECALL_MISS under pure chunk → Top-1).
3. **`chunk_primary gate10` is the best measured policy to date** — best aggregate, perfect easy,
   best normal, while keeping Q6.
4. **The binder still adds value** as a title-independent tiebreaker.
5. **The remaining problem is no longer `k`.** Among simple RRF settings k=10 dominates, but the
   open frontier is unaffected by `k`. Tuning `k` further would optimize the wrong knob.

## 4. The open frontier — competition between evidence types

Misleading-title hard cases (Q14 `d3b7294a`, Q15 `8ef4e1a1`) are **not solved by any
conversation-level fusion policy**, and chunk_primary even *regresses* Q15:

| hard Q | chunk alone | chunk_primary gate10 |
|---|---|---|
| Q6 `fe732b68` | HIT(1) | HIT(1) |
| Q14 `d3b7294a` | RANK(11) | RANK(18) — never recovered by anything |
| Q15 `8ef4e1a1` | **HIT(3)** | RANK(24) — demoted |

**Why — the statistical property, not a bug.** "Non-subtractive on the gold" is **not**
"rank-preserving." The gated preview bonus subtracts nothing from Q15's gold (its title is
misleading, so it earns no bonus), but it is **additive for the many title-evident competitors**,
which rise *above* Q15's strong chunk hit. **Making the easy documents better mechanically pushes a
perfectly valid hard document down in relative rank.** A better global ranking can degrade a valid
hard case. At conversation level this is a **zero-sum competition inside one ranked list**:
empirically, every fusion variant scores hard 33/33/33; only pure chunk keeps Q15 — and pure chunk
destroys easy and normal. No single conversation-level policy holds title-evident easy *and*
title-mismatch hard in the Top-5 simultaneously.

**Consequence for diagnosis:** the next lever is not "how to fuse better." It is **"how to stop
documents of different natures from competing directly."** Q15 is a highly specialized passage; Q2
is an obvious title; they should probably never fight head-to-head in one score-ranked list.

(Also persistently recall-bound, independent of fusion: Q4 `fffd0544` — 2-message gold; Q10, Q13 —
the true recall wall, recorded for the recall-side work, not the fusion work.)

## 5. Recognized next direction — NOT opened here

The experiments are beginning to *demand* a **two-phase retrieval architecture** — recorded as the
named successor, deliberately **not decided** by this ADR:

```
Phase 1 — recall, identity preserved
  conversation retrieval → passage retrieval → binder retrieval
  (each retriever keeps its own identity; nothing is flattened yet)

Phase 2 — controlled selection
  policy → controlled selection → Top-K
```

The shift it implies: **we stop fusing scores and start fusing recall hypotheses.** That is a
different design, to be validated by its own falsifiable experiments — not adopted because it is
elegant. **Retrieval v3 is not opened.** This level of knowledge is frozen first.

## 6. Convergence with the Constitution

This finding is the same principle as ADR-PRL-0001, discovered independently on the retrieval side:
**do not flatten different regimes too early.** A passage is not a conversation; a conversation is
not a link; a link is not a binder. Collapsing them into one score too soon destroys information —
exactly as collapsing Observed / Derived / Person-model, or witnessed-forward vs
reconstructed-backward, would. The two-phase direction is the retrieval expression of the
constitutional law *preserve distinctions until the last responsible moment.* The recall engine and
the registry are converging on one architecture of restraint.

## 7. Non-goals (what this ADR does not claim)

- It does **not** claim to solve title-mismatch hard recall (Q14, Q15) — that is the open frontier.
- It does **not** lock the two-phase design; that is named, not decided.
- It does **not** re-open `k` tuning; `k=10` is recorded, and the frontier is `k`-independent.
- It does **not** touch the DSM kernel or the registry-constitution ADRs (0004/0005 reserved).

## 8. Consequences

- **Frozen:** Retrieval Policy v2.0 = `chunk_primary`, `preview_gate=10`, `rrf_k=10`,
  `chunk_chars=500`, with two independent retrievers + binder boost.
- **Implementation, when it comes, is additive over P0→P9** — two retrievers + an asymmetric
  combiner as a wrapper over the existing semantic + chunk indexing; combiner mode, gate, `k`, and
  chunk size all configuration. Indices must be persisted (fusion ≈ 440–465 ms vs preview 27 ms).
- **v3 deferred:** the two-phase ("fuse recall hypotheses, not scores") architecture is the
  recognized successor, opened only when this level is exploited and a new experiment demands it.
- **Registry axis unchanged:** ADR-PRL-0004 (Protocols) remains the next constitutional step,
  independent of this engine decision.
