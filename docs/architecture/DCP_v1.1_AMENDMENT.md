# DCP v1.1 — Amendment: Protocol Between Actors

**Status:** AMENDMENT to DCP v1.0
**Date:** 2026-07-08
**Changes:** adds `join_project` primitive; formalises active vs passive
providers; reframes DCP from "tool-to-DSM" to "actor-to-actor via DSM".

---

## The reframing

DCP v1.0 defined the protocol as: *tool → DSM*.

DCP v1.1 reframes it as: **actor → actor via DSM**.

```
v1.0:                              v1.1:

Claude                             Claude
  │                                  │
  ▼                                 ├──┐
 DCP                               │   │
  │                              LM Studio  │
  ▼                                │       │
 DSM                              Cursor   │
                                    │       │
                                  GitHub ──┘
                                          │
                                          ▼
                                   DCP (the contract)
                                          │
                                          ▼
                                    DSM Kernel
```

The protocol does not describe how to talk to DSM. It describes **how an
actor joins and participates in a project's continuity**. DSM is the
substrate; DCP is the social contract.

---

## New primitive: `join_project`

### Why it exists

The Hot Swap scenario implicitly assumes an actor is already a recognised
participant before calling `catch_up()`. In v1.0, identity registration
and context recovery were conflated. They are separate concerns:

- **Identity**: who am I, and am I authorized to participate?
- **Context**: what has happened in this project before me?

`join_project` formalises the identity+authorization step. It is called
once, before the first `catch_up()`.

### Signature

```
join_project(project_id, actor_identity) → ParticipationContext
```

Where `actor_identity` contains:
- `agent_id` (required)
- `owner_id` (required)
- `public_key` (optional, for signed receipts)
- `capabilities` (optional: what this actor can do)
- `provider_type` (active | passive — see below)

Returns `ParticipationContext`:
- project exists? (yes/no)
- authorization status (allowed / denied / pending)
- project summary (entry count, last activity)
- then internally calls `catch_up()` and includes the ContextBundle

### Contract

- An actor MUST call `join_project` before its first `catch_up`.
- If authorization is denied, the actor MUST NOT call `publish_receipt`.
- `join_project` is idempotent: calling it again is a no-op (the actor
  is already a participant).

---

## The five DCP v1.1 primitives

| # | Primitive | When | Purpose |
|---|-----------|------|---------|
| 0 | `join_project` | Once, on arrival | Identity + authorization + initial context |
| 1 | `catch_up` | Before each work session | Recover full project state |
| 2 | `publish_receipt` | After completing work | Write decision + portable proof |
| 3 | `verify` | Anytime | Check project integrity |
| 4 | `project_context` | On demand | Prompt-ready provenance block |

---

## Active vs Passive providers

Not all actors in a project continuity are LLM agents. CI pipelines,
issue trackers, and notification systems also contribute. DCP v1.1
formalises two provider types.

### Active providers

Actors that **produce work** by reasoning (LLM, agent, human).

- They call all 5 primitives.
- `catch_up` is rich: they use the recovered context to produce new work.
- Examples: Claude, ChatGPT, Cursor, Zcode, LM Studio.

### Passive providers

Actors that **publish events** without reasoning (CI, webhook, bot).

- They call `join_project` + `publish_receipt` + `verify`.
- `catch_up` is minimal or skipped: they don't need project context to
  produce their event.
- Examples: GitHub Actions, Slack bot, Jira webhook, CI runner.

### Compliance matrix

| Primitive | Active (mandatory) | Passive (mandatory) |
|-----------|:------------------:|:-------------------:|
| `join_project` | ✓ | ✓ |
| `catch_up` | ✓ | — |
| `publish_receipt` | ✓ | ✓ |
| `verify` | ✓ | ✓ |
| `project_context` | optional | — |

A passive provider claiming DCP 1.1 compliance MUST implement
`join_project` + `publish_receipt` + `verify`. It MAY skip `catch_up`
and `project_context`.

---

## Compliance claim format (updated)

```
<Tool Name> Continuity Provider
DCP Version: 1.1
Type: active | passive
Compliance: Core [+ <extensions>]
Method: full | assisted | read-only
```

Examples:

```
Claude Continuity Provider
DCP Version: 1.1
Type: active
Compliance: Core + signatures + dispatch_binding
Method: assisted
```

```
GitHub Actions Continuity Provider
DCP Version: 1.1
Type: passive
Compliance: Core
Method: full
```

---

## DCP Conformance Test Suite (proposed)

The path from internal protocol to open standard requires a conformance
test suite that any team can run against their own provider.

### Proposed test scenarios

| Test | What it validates | Active | Passive |
|------|-------------------|:------:|:-------:|
| **T1: Hot Swap** | Actor joins, catches up, publishes, next actor continues | ✓ | — |
| **T2: Receipt integrity** | Published receipt verifies INTACT + CONFIRMED | ✓ | ✓ |
| **T3: Context reconstruction** | Fresh actor recovers full project state from catch_up | ✓ | — |
| **T4: Tamper detection** | Mutated entry is detected by verify | ✓ | ✓ |
| **T5: Identity continuity** | join_project + publish_receipt shows correct agent attribution | ✓ | ✓ |
| **T6: Replay rejection** (optional) | Duplicate receipt is rejected (requires replay_protection extension) | opt | opt |

A provider passing T1-T5 may claim **"DCP 1.1 Core Certified"**.

### Certification levels

| Level | Tests passed | Claim |
|-------|-------------|-------|
| Core | T2, T4, T5 (+ T1 or T3 for active) | DCP 1.1 Core Certified |
| Core+ | Core + T1 + T3 | DCP 1.1 Active Certified |
| Extended | Core+ + T6 | DCP 1.1 Extended Certified |

---

## Updated registry

| Provider | DCP version | Type | Status |
|----------|-------------|------|--------|
| Zcode | 1.0 (upgradable to 1.1) | active | Core compliant |
| LM Studio | 1.0 (upgradable to 1.1) | active | Core compliant |
| Claude Desktop | 1.1 (planned) | active | NOT YET IMPLEMENTED |
| ChatGPT Desktop | 1.1 (planned) | active | NOT YET IMPLEMENTED |
| Cursor | 1.1 (planned) | active | NOT YET IMPLEMENTED |
| GitHub Actions | 1.1 (planned) | passive | NOT YET IMPLEMENTED |

---

## What changed from v1.0

| Aspect | v1.0 | v1.1 |
|--------|------|------|
| Direction | tool → DSM | actor → actor via DSM |
| Primitives | 4 | 5 (added `join_project`) |
| Provider types | one | active + passive |
| Conformance | claimed | testable (T1-T6) |
| Compliance levels | Core / Extensions | Core / Active / Extended |

v1.0 providers are forward-compatible: adding `join_project` is
additive, no existing primitive changed.

---

## What does NOT change

- The kernel. Frozen.
- The doctrine. Frozen.
- The four v1.0 primitives. Unchanged signatures.
- The Hot Swap as acceptance test. Still the central validation.

DCP v1.1 is an additive refinement. It makes the protocol more complete
(without changing what works) and more testable (without adding burden
to compliant providers).
