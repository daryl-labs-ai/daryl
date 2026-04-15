# ADR-001 — No Automatic Decision

**Status:** Accepted
**Date:** 2026-04-15
**Validated by:** 3 structured multi-agent debates (DSM events, cryptographically signed)

## Decision

agent-mesh will never automatically select a winner among agent contributions.
Scoring is permitted. Automatic decision is forbidden.

## Invariants (non-negotiable)

1. DSM remains passive — proof layer only, never orchestrator
2. Validator = pluggable interface — no default implementation
3. No automatic winner selection — human stays in the decision loop

## Rationale

Three structured debates between Claude Sonnet 4, GPT-4o-mini, and GLM-4 (Zhipu)
converged independently on this boundary across different topics and framings.

Key finding from Debate 3: an agent used a fabricated statistic to support its position,
then publicly retracted it under logical pressure from other agents.
This self-correction is preserved in DSM as a cryptographic artifact.

The architectural insight that emerged from all three debates:

    ANALYSIS  ≠  ACTION
    SCORING   ≠  DECISION

## Permitted

- Multi-agent submission collection
- Scoring via pluggable Validator interface
- Non-binding recommendations
- Judge synthesis (separate agent, read-only)

## Forbidden

- Automatic winner selection
- Automatic validation_completed emission
- Automatic writes to DSM based on scoring
- Any mutation of mesh state from the prescriptive layer

## Model

    DSM                → proves       (immutable, frozen kernel)
    agent-mesh         → orchestrates
    Prescriptive Layer → suggests     (non-binding)
    Human              → decides

## Debate Evidence

| Debate | Topic | Result |
|--------|-------|--------|
| 1 | DSM passive vs prescriptive | Unanimous passive (0.90 confidence) |
| 2 | Built-in validator in V1 | Conditional — pluggable only (judge verdict) |
| 3 | Automatic winner selection | NO — scoring ≠ decision (9/9 sigs verified) |

Full debate transcripts preserved in DSM:
- mission_01KP834X537RGF4B85TPRXWKNN (debate 1)
- mission_01KP84EXTQCRMMHASPW6FGGPHD (debate 2)
- mission_01KP8638K2W5GWBE67R95A1ZSN (debate 3)

Replay any debate: `dsm verify --shard contribute`
