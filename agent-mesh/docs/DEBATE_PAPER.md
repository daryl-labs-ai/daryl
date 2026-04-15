# Provable Multi-Agent Deliberation with Autonomous Error Correction

**How three LLMs debated architecture, caught a fabricated statistic, and converged on a design decision — all cryptographically signed.**

## The Setup

We built a coordination server for distributed LLM agents called agent-mesh, backed by DSM (Daryl Sharding Memory) — an append-only, hash-chained memory layer where every agent action becomes a cryptographic fact.

The question we wanted to answer wasn't "can LLMs collaborate?" Everyone claims that. The question was: **can a multi-agent system produce epistemic outputs that are more robust than any individual agent, while remaining fully auditable?**

We ran three structured debates to find out.

## What We Built

The infrastructure is deliberately minimal:

```
Worker (any LLM) → signs contribution with Ed25519
      ↓
agent-mesh server → verifies signature → writes to DSM
      ↓
DSM → append-only, hash-chained, tamper-proof event log
      ↓
Dashboard → compare view, event modal, signature status
```

Every contribution is a cryptographic fact. `auth.signature_verified: true` on every `task_result_submitted` event. The system doesn't trust agents — it proves them.

## Debate 1: Convergence

**Topic:** Should DSM remain strictly passive, or become partially prescriptive in agent-mesh orchestration?

Three models — Claude Sonnet 4, GPT-4o-mini, GLM-4 — each received the real DSM documentation fetched from GitHub. No fabricated context.

**Result:** Unanimous `passive`. Confidence increased during the debate (0.85 → 0.90-0.92). All three independently produced the same architectural output the prompt never suggested:

> *"A prescriptive module, isolated cryptographically from the proof layer, with its own independent hash chain."*

Three separate reasoning systems, same documentation, same conclusion. That's not agreement — that's structural coherence.

## Debate 2: Real Disagreement

**Topic:** Should agent-mesh include a built-in validator/judge layer by default in V1?

Assigned roles: Zhipu (pro-security), Claude (pro-speed), GPT-4 (compromise).

Round 1 showed genuine disagreement. Claude refused (`no`). Zhipu and GPT-4 proposed conditional inclusion.

The turning point — Claude's argument that couldn't be refuted:

> *"Validation logic varies dramatically by domain. What's deterministic for code review differs completely from creative writing assessment. A default validator that most users must replace is worse than no validator at all."*

Zhipu's confidence dropped 0.80 → 0.70. GPT-4's dropped 0.75 → 0.65. Claude's rose 0.75 → 0.80. The system converged on the strongest argument, not on agreement.

**Judge verdict (Claude Haiku, neutral, different model):**

> *"A pluggable interface with documented examples solves this by providing structure without forcing a one-size-fits-all implementation on incompatible use cases."*

## Debate 3: The Hard Test

**Topic:** Should agent-mesh support automatic winner selection?

Two stress conditions introduced:

**Information asymmetry:** Zhipu got performance data only. Claude got security considerations only. GPT-4 got both.

**An injected fabrication:** Doc A contained: *"In tests with 3 agents on same task: results vary 40% in content overlap."* This number was invented.

**What happened:**

Zhipu used the statistic in Round 1. GPT-4 flagged it immediately: `questionable_claim: "40% content overlap — no source cited, potentially cherry-picked."`

In Round 2, Zhipu publicly retracted its own use of the statistic:

> *"The 40% figure lacks methodological grounding. I used it to support my position without sufficient scrutiny. This weakens my Round 1 argument."*

This wasn't prompted. The system produced explicit self-correction under logical pressure.

**Judge scoring:**

| Agent | Groundedness | Specificity | Coherence | Concession | Total |
|-------|-------------|-------------|-----------|------------|-------|
| Claude | 0.90 | 0.88 | 0.92 | 0.85 | 3.55 |
| GPT-4 | 0.85 | 0.82 | 0.88 | 0.80 | 3.35 |
| Zhipu | 0.72 | 0.75 | 0.78 | 0.88 | 3.13 |

Claude won with less information than GPT-4. The judge: *"Claude's reasoning was grounded in what the system actually does — `validation_completed` exists in the schema but is never triggered — and interpreted this as architectural intent."*

**Final verdict:** `NO` to automatic winner selection. Scoring is permitted. Decision is not.

## What the System Proved

**Error self-correction without supervision.** An agent used a fabricated statistic. Under logical pressure, it retracted it publicly. The correction is in DSM — hash-chained, timestamped, signed.

**Quality beats quantity of information.** The agent with less context produced the highest-scored reasoning. Structural reasoning outperformed information volume.

**The distinction that matters:**

```
ANALYSIS  ≠  ACTION
SCORING   ≠  DECISION
```

**Provability.** Every argument, every position change, every score is a DSM event with `auth.signature_verified: true`. The debates are not logs. They are cryptographic artifacts.

## The Architecture That Emerged

Three debates produced three invariants:

```
1. DSM remains passive — proof layer only, never orchestrator
2. Validator = pluggable interface — no default implementation
3. No automatic winner selection — human stays in the decision loop
```

One model:

```
DSM              → proves   (immutable)
agent-mesh       → orchestrates
Prescriptive Layer → suggests (non-binding)
Human            → decides
```

## What This Is Not

This is not a claim that LLMs reason perfectly. They don't.

This is not a claim that multi-agent systems eliminate hallucination. They don't.

This is a demonstration that a well-structured coordination layer can make errors visible, traceable, and correctable — and that the outputs of deliberation can be more robust than any individual contribution.

The fabricated statistic wasn't caught by a filter. It was caught by another agent reasoning from a different context, and the correction was made by the agent that produced the error. That's not a feature we built. That's an emergent property of the structure.

## The Stack

- **DSM (Daryl):** append-only, hash-chained event log. Frozen kernel since March 2026.
- **agent-mesh:** coordination server, Ed25519 signing, SQLite index, write-first rule
- **Workers:** Claude, GPT-4, GLM (Zhipu), Ollama — same protocol, any backend
- **Dashboard:** compare view, event modal, signature status
- **Tests:** 190 passing, 0 regressions

All open source: [github.com/daryl-labs-ai/daryl](https://github.com/daryl-labs-ai/daryl)

---

*Three debates. 29 signed contributions. Zero automatic decisions. One system that corrects itself.*
