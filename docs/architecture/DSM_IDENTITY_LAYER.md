# DSM Identity Layer — Provable Agent Identity & Evolution

## 1. Overview

The DSM Identity Layer provides **verifiable, replayable agent identity** on top of DSM's append-only memory.

It allows any system to answer:

- Who is this agent?
- How was it created?
- How has it evolved?
- Are its behaviors consistent with its declared evolution?

All answers are derived from **DSM replay**, not generated heuristics.

---

## 2. Problem

Modern AI agents suffer from:

- No persistent identity across sessions
- Hallucinated or fabricated history
- No traceability of evolution
- No auditability of behavior changes

DSM solves **memory integrity**.
The Identity Layer solves **agent continuity and provenance**.

---

## 3. Core Principles

- Append-only identity events
- Hash-chain integrity (inherits DSM guarantees)
- Deterministic replay
- No mutation of past identity
- No static narrative storage
- Separation from DSM kernel (layer above)

---

## 4. Identity Model

Identity is not stored as a static object.
It is reconstructed dynamically via replay of events stored in the `identity` shard.

```python
identity = replay_identity(storage, agent_id="agent_X")
```

The identity object is derived, not persisted.

---

## 5. Identity Event Schema

Each identity event is a standard DSM entry stored in shard `identity`.

The schema below describes the `data` payload of a DSM `Entry`, not the entry itself. DSM handles `id`, `timestamp`, `session_id`, `hash`, `prev_hash`, and `version` at the entry level.

Required structure inside `data`:

```json
{
    "agent_id": "string",
    "event_type": "genesis | skill_added | model_change | behavior_change",
    "event_version": "1.0",
    "origin_component": "system/component name",
    "payload": {}
}
```

Notes:

- `event_type` replaces ambiguous `event`
- `origin_component` identifies the system that produced the event (distinct from the entry-level `source` field)
- `payload` contains event-specific data
- DSM handles `hash`, `prev_hash`, ordering

---

## 6. Genesis Event (Agent Birth)

```json
{
    "event_type": "genesis",
    "payload": {
        "created_by": "buralux",
        "purpose": "DSM media engine",
        "initial_capabilities": ["brief_generation"],
        "constraints": ["append_only", "no hallucinated claims"]
    }
}
```

This event MUST be the first identity event for an agent.
A second genesis event for the same `agent_id` MUST be treated as invalid.

---

## 7. Evolution Events

### Skill Added

```json
{
    "event_type": "skill_added",
    "payload": {
        "skill": "compare_competitors",
        "reason": "enable competitive analysis"
    }
}
```

### Model Change

```json
{
    "event_type": "model_change",
    "payload": {
        "from": "mock",
        "to": "zai/glm-4.7",
        "reason": "production activation"
    }
}
```

### Behavior Change

```json
{
    "event_type": "behavior_change",
    "payload": {
        "change": "context_propagation_improved",
        "impact": "better consistency"
    }
}
```

---

## 8. Identity Replay

```python
def replay_identity(storage, agent_id):
    events = read_identity_events(storage, agent_id)
    return reconstruct_identity(events)
```

Returns:

- origin (genesis)
- capabilities
- model state
- constraints
- evolution timeline

Replay is deterministic: filter by `agent_id`, sort chronologically, reject or flag invalid events.

---

## 9. No Static Narrative

The system MUST NOT store identity narratives (e.g. markdown summaries).

Narratives must be generated dynamically from replay:

```python
identity = replay_identity(storage, agent_id)
narrative = generate_narrative(identity)
```

This guarantees:

- no hallucinated identity
- no drift between memory and description

---

## 10. Identity Integrity vs Behavioral Reality

Declared identity (events) may diverge from actual behavior.

Example:

- model updated without logging `model_change`
- hidden fine-tuning
- external system modification

This creates a **discontinuity**.

This gap is designated **Gap 7: Identity Continuity** — cryptographic identity (signing key) is not computational identity (weights, config, behavior).

---

## 11. Identity Guard (Behavioral Consistency)

A separate module detects inconsistencies:

```
src/dsm/identity/identity_guard.py
```

Responsibilities:

- detect behavioral shifts not explained by identity events
- compare historical vs current decision patterns
- flag inconsistencies

Example:

- sudden change in response style
- change in tool usage pattern
- shift in decision logic

If no corresponding identity event exists:
→ raise alert → flag as "unverified evolution"

The Identity Guard does not prove behavior cryptographically. It provides **heuristic detection** of unverified behavioral discontinuities. In v1, it is best-effort and non-authoritative.

---

## 12. Architecture

```
src/dsm/identity/
    identity_manager.py   # write events
    identity_replay.py    # reconstruct identity
    identity_guard.py     # detect inconsistencies
```

Layered above:

```
src/dsm/core/   (frozen kernel)
```

---

## 13. Integration Pattern

**Write**

- on agent creation → genesis
- on change → append identity event

**Read**

- before reasoning → replay identity
- for audit → replay + verify

**Validate**

- after behavior → run identity_guard

---

## 14. Out of Scope (v1)

- Identity snapshots
- Cross-agent identity merging
- Identity NFTs
- Semantic identity search

---

## 15. Status

- Specification defined
- Ready for minimal implementation
- Designed for incremental extension
