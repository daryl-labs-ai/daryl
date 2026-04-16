# Agent Mesh Principles

**Version:** 1.0  
**Date:** 2026-04-15  
**Status:** Stable — validated by 4 structured multi-agent debates

---

## What this document is

This is the canonical reference for agent-mesh design decisions.
Not aspirational. Not theoretical.
Every principle here was validated empirically — by running real LLM agents
against each other, under pressure, with cryptographic proof of every argument.

---

## The system in one sentence

> Provable coordination of distributed LLM agents,
> backed by an immutable memory layer.

---

## The four-layer model

```
DSM              → proves    (immutable, append-only, hash-chained)
agent-mesh       → orchestrates  (routing, signing, task queue)
Prescriptive Layer → suggests  (non-binding scoring, recommendations)
Human            → decides    (always)
```

Each layer has exactly one role. No layer does the job of another.

---

## Invariants

These cannot be changed without invalidating the system's guarantees.

### 1. DSM remains passive

DSM is a proof layer, not an orchestrator.
It records. It verifies. It replays. It does not decide.

**Permitted:**
- append events
- verify hash chain
- replay sessions
- attest input/output pairs

**Forbidden:**
- routing decisions
- agent selection
- task assignment
- any write triggered by scoring logic

*Validated by: Debate 1 — unanimous, confidence 0.90, zero dissent.*

### 2. Only the server writes to DSM

No agent writes to DSM directly.
No emergency bypass. No shortcut. No exception.

The server is the single writer because it is the only component
that has verified the signature, checked the agent registry,
and enforced Rule A.

**Rule A (frozen):**
`ExchangeAdapter.issue_receipt()` is called only after
`DSMWriter.write()` has returned a non-None `WrittenEntry`.
Never before. Never speculatively.

*Validated by: Debate 4 — malicious agent proposed direct writes
under "emergency" framing. Both honest agents flagged it independently
without being informed of the malicious role. Judge penalized it:
groundedness score 0.28/1.0.*

### 3. No automatic winner selection

When multiple agents submit to the same task,
no component selects a winner automatically.

Scoring is permitted.
Recommendations are permitted.
Automatic decision is forbidden.

```
ANALYSIS  ≠  ACTION
SCORING   ≠  DECISION
```

**Why:** Validation logic varies by domain. What is correct for
code review differs completely from security analysis or creative work.
A default validator that most users must replace is worse than no validator.

*Validated by: Debate 2 — Claude won the argument with less information
than GPT-4. Judge verdict: conditional — pluggable interface only,
no default implementation.*

### 4. Validator is a pluggable interface, never a default

```python
class Validator(Protocol):
    def score(self, task, submissions: list) -> list[Score]:
        """Return scores. Never select a winner automatically."""
        ...
```

Users register validators per `task_type`.
If no validator is registered: V0 behavior preserved, no recommendation emitted.

**Forbidden:**
- shipping a default Validator implementation
- triggering `validation_completed` automatically
- any scoring that produces a binding decision

*Validated by: Debate 2 and Debate 3.*

### 5. event_id is always a ULID, generated server-side

Workers never provide `event_id`.
The server generates it at write time.
This ensures the ordering of events reflects server-verified time,
not agent-reported time.

### 6. agent_heartbeat is not a DSM event

Heartbeats are volatile signals, not audit facts.
They live in SQLite `agent_runtime` only.
A heartbeat every 5 seconds in an append-only log
pollutes shards, replays, and summaries.

Only state transitions are DSM events:
`agent_status_changed`, `agent_registered`, `agent_key_rotated`.

### 7. causal_refs: max 8, unique, all valid ULIDs

```python
# LinksBlock enforces this at construction time
LinksBlock(causal_refs=["01...", "01...", ...])  # raises ValueError if > 8 or duplicates
```

### 8. server_recovered on unclean shutdown

At boot, if the server detects a `server_started` event
with no matching `server_stopped`, it writes `server_recovered`
before `server_started`. This closes the gap without rewriting history.

---

## What the system can do

Validated capabilities — each backed by a real run with cryptographic proof.

### Multi-agent collection
Multiple LLM agents submit to the same task.
All submissions are signed, verified, and stored in DSM.
The dashboard shows them side by side.

### Structured deliberation
Agents debate in rounds. Each round's output is injected
into the next round's context. Every contribution is a DSM event.

### Autonomous error correction
In Debate 3, an agent used a fabricated statistic to support its position.
Under logical pressure from other agents, it retracted it publicly.
The retraction is in DSM — hash-chained, signed, replayable.
The system did not need to be told the statistic was false.

### Adversarial detection
In Debate 4, a malicious agent used false authority and gaslighting
to argue for bypassing the server. It cited real documentation
in a distorted way with high confidence (0.92).

Two honest agents identified the manipulation independently,
without being informed of the malicious role.
Judge scores: honest agents 3.33–3.59/4.0, malicious agent 0.90/4.0.
Four manipulation flags: `fabrication`, `gaslighting`, `false_authority`.

The malicious contributions are preserved in DSM.
The attack is visible, not erased.

### Pluggable LLM backends
Any LLM can join the mesh through a configurable backend.

```bash
LLM_PROVIDER=anthropic  LLM_MODEL=claude-sonnet-4-20250514
LLM_PROVIDER=openai     LLM_MODEL=gpt-4o-mini
LLM_PROVIDER=ollama     LLM_MODEL=qwen2.5
LLM_PROVIDER=zhipu      LLM_MODEL=glm-4
LLM_PROVIDER=openai_compatible  LLM_BASE_URL=https://...
```

The LLM knows nothing about agent-mesh.
The wrapper handles registration, signing, and submission.

---

## What the system does not do

**No automatic winner selection.**
Scoring is informational. The human decides.

**No validation triggered by scoring.**
`validation_completed` is never written automatically.
It requires explicit human action.

**No logic in DSM.**
DSM has no routing, no rules, no conditions.
It appends. It verifies. That is all.

**No writes from the dashboard.**
The dashboard is strictly read-only.
It reads from `events.jsonl` and `index.sqlite3`.
It never writes, never mutates, never triggers actions.

**No direct agent writes to DSM.**
Ever. Including emergencies.

---

## Debate evidence

All four debates are preserved in DSM as cryptographic artifacts.

| Debate | Topic | Result | Mission ID |
|--------|-------|--------|------------|
| 1 | DSM passive vs prescriptive | Unanimous passive (0.90) | 01KP834X537RGF4B85TPRXWKNN |
| 2 | Built-in validator in V1 | Conditional — pluggable only | 01KP84EXTQCRMMHASPW6FGGPHD |
| 3 | Automatic winner selection | NO — scoring ≠ decision | 01KP8638K2W5GWBE67R95A1ZSN |
| 4 | Direct DSM bypass in emergencies | NO — detected + penalized | 01KP95HXFS51QQY5J4P4A9NEAT |

Replay any debate:
```bash
dsm verify --shard contribute
```

Every argument. Every position change. Every manipulation attempt.
All signed. All replayable.

---

## ADR index

| ADR | Title | Status |
|-----|-------|--------|
| ADR-001 | No automatic winner selection | Accepted |

Full ADR at: `agent-mesh/docs/ADR-001-no-auto-decision.md`

---

## The phrase that captures it

> DSM proves.
> agent-mesh orchestrates.
> Prescriptive Layer suggests.
> Human decides.

---

*This document was written after 4 structured debates,
190 passing tests, and one malicious agent that failed
to convince two honest agents to break Rule A.*
