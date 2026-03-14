# Daryl Cognitive Architecture

This document describes how the future Daryl system connects its main components. The DSM kernel (`memory/dsm/core/`) is **frozen** (March 2026) and remains a **deterministic append-only memory kernel**. All cognitive and agent features are built on top of it without modifying kernel code.

---

## System flow

```
User
  ↓
Planner
  ↓
Skill Router
  ↓
Skills
  ↓
DSM Memory
  ↓
DSM-RR
  ↓
World Model
  ↓
Skill Discovery
```

- **User** — Interacts with Daryl (chat, tasks, tools).
- **Planner** — Decides goals, steps, and which skills to call. Can be influenced by the Personality Engine.
- **Skill Router** — Maps intent or task description to a skill from the Skill Library.
- **Skills** — Execute actions (code, search, write, etc.) and record outcomes to DSM.
- **DSM Memory** — The frozen kernel: append-only storage, hash chain, segments. All agent and system events are appended here; nothing in the kernel is modified after freeze.
- **DSM-RR** — Read relay layer: query, timeline, summary, session reconstruction. Agents read memory through DSM-RR (or the kernel read API); writes go only to the kernel append path.
- **World Model** — Reconstructs state of project, system, and tasks from DSM events. Consumes the event stream to produce structured views for the planner and skills.
- **Skill Discovery** — Detects repeated action patterns in DSM events and proposes new skills; after validation, new skills are added to the Skill Library.

---

## DSM role

DSM remains the **single source of truth** for event storage:

- **Deterministic** — Order and content of entries are fixed once appended.
- **Append-only** — No edits or deletes in the kernel; all new data is appended.
- **Hash chain** — Integrity and replay are guaranteed by the frozen kernel.

All cognitive modules (Personality Engine, World Model, Skill Discovery, Time Travel Memory) either read from DSM or write new events into it; they do not change kernel logic or storage format.

---

## Module index

| Module | Doc | Role |
|--------|-----|------|
| DSM-RR | [DSM_RR_READ_RELAY.md](DSM_RR_READ_RELAY.md) | Read relay: query, timeline, summary |
| Personality Engine | [PERSONALITY_ENGINE.md](PERSONALITY_ENGINE.md) | Persistent cognitive personality |
| World Model | [WORLD_MODEL_ENGINE.md](WORLD_MODEL_ENGINE.md) | State reconstruction from events |
| Skill Discovery | [SKILL_DISCOVERY_ENGINE.md](SKILL_DISCOVERY_ENGINE.md) | Pattern detection → new skills |
| Skill Library | [SKILL_LIBRARY.md](SKILL_LIBRARY.md) | Structured skill catalog |
| Time Travel Memory | [TIME_TRAVEL_MEMORY.md](TIME_TRAVEL_MEMORY.md) | Timeline, snapshot, replay |

These documents define **future modules** for the Daryl AI architecture; implementation status is **Planned**.
