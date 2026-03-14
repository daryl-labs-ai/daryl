# AGENTS.md — Guide for AI agents (Daryl / DSM)

This document explains how AI agents should interact with **DSM (Daryl Sharding Memory)** in the Daryl project. It is intended for both human developers and AI agents that need to log events, read memory, implement skills, and structure agent–DSM interaction.

---

## 1. What DSM is

**DSM (Daryl Sharding Memory)** is the deterministic memory kernel of the Daryl architecture.

- **Append-only storage**: Events are written as JSONL entries. Existing entries are never modified or deleted.
- **Shard-based**: Data is organized by **shards** (e.g. `sessions`, `default`, or custom names like `daryl_identity`). Each shard is a logical log; physically it may be one or several segment files.
- **Chained integrity**: Each entry can carry a hash of its content and a reference to the previous entry’s hash (`prev_hash`), enabling integrity checks and **deterministic replay** of a shard.
- **Session-aware**: Sessions are a first-class concept: agents start a session, record events (snapshots, tool calls) within it, then end the session. All events carry a `session_id`.

DSM does **not** provide query/search or vector search; it is an ordered, append-only event log. Agents read recent entries from a shard and interpret them in their own logic.

**Key modules:**

- `dsm_v2` — root package (installable as `dsm-v2`).
- `dsm_v2.core` — `Storage`, `Entry`, `ShardMeta` (models and persistence).
- `dsm_v2.session` — `SessionGraph`, `SessionLimitsManager` (session lifecycle and safeguards).
- `dsm_v2.skills` — skill registry, router, ingestor, usage/success loggers (optional telemetry, separate from the DSM kernel).

---

## 2. How agents should log events to DSM

There are two supported ways to log events: **via SessionGraph (recommended)** or **via Storage + Entry directly**.

### 2.1 Recommended: use SessionGraph for session-scoped events

For any interaction that belongs to a “conversation” or “run,” agents should use **SessionGraph**. It ensures a consistent session lifecycle and writes to the `sessions` shard with the right metadata.

**Pattern:**

1. **Start a session** when an interaction begins (e.g. user message, trigger).
2. **Record snapshots** (e.g. state observations) and **execute actions** (tool calls) during the session.
3. **End the session** when the interaction is finished.

**Example:**

```python
from dsm_v2.session.session_graph import SessionGraph
from dsm_v2.core.storage import Storage

# Optional: custom data_dir; default uses a test path under home
storage = Storage(data_dir="/path/to/memory")
session_graph = SessionGraph(storage=storage)

# 1) Start session
session_graph.start_session(source="telegram")   # or "manual", "moltbook", etc.

# 2) During session: record a state snapshot (e.g. Moltbook home)
session_graph.record_snapshot(snapshot_data={"screen": "home", "items": [...]})

# 3) During session: log an action (tool call)
session_graph.execute_action(action_name="post_reply", payload={"text": "Hello"})

# 4) End session when done
session_graph.end_session()
```

- **`start_session(source)`** — creates a new `session_id`, writes a `session_start` event to the `sessions` shard, and sets the session as “active.”
- **`record_snapshot(snapshot_data)`** — writes a `snapshot` event; may be rate-limited by `SessionLimitsManager` (e.g. home poll cooldown).
- **`execute_action(action_name, payload)`** — writes a `tool_call` event; may be blocked if action limits are exceeded.
- **`end_session()`** — writes a `session_end` event and clears the active session.

All of these return an `Entry` when the write succeeds, or `None` if skipped (e.g. cooldown) or if no session is active.

### 2.2 Alternative: write raw entries via Storage

For events that are **not** part of the session lifecycle (e.g. identity shard, custom shards), agents can use **Storage** and **Entry** directly.

**Entry fields:**

- `id` — unique ID (e.g. UUID string).
- `timestamp` — `datetime` (UTC).
- `session_id` — session ID or a sentinel like `"none"` if not session-scoped.
- `source` — origin (e.g. `"message"`, `"heartbeat"`, `"manual"`).
- `content` — string payload (often JSON-serialized).
- `shard` — shard name (e.g. `"sessions"`, `"default"`, `"daryl_identity"`).
- `hash` — optional; Storage can compute it if left empty.
- `prev_hash` — optional; Storage maintains chain per shard.
- `metadata` — dict (e.g. `{"event_type": "custom"}`).
- `version` — e.g. `"v2.0"`.

**Example:**

```python
from datetime import datetime
from uuid import uuid4
from dsm_v2.core.storage import Storage
from dsm_v2.core.models import Entry

storage = Storage(data_dir="/path/to/memory")

entry = Entry(
    id=str(uuid4()),
    timestamp=datetime.utcnow(),
    session_id="session_123",
    source="agent",
    content='{"type": "observation", "data": "..."}',
    shard="default",
    hash="",
    prev_hash=None,
    metadata={"event_type": "observation"},
    version="v2.0"
)
storage.append(entry)
```

- **Do not move or delete existing files** in the DSM data directory; only append.
- Prefer **one logical event per Entry**; put structured data in `content` (e.g. JSON) and use `metadata` for event type and tags.

---

## 3. How to read memory from DSM

Reading is done via **Storage**. There is no query language or vector search; agents read **recent entries** from a shard and interpret them.

**Main methods:**

- **`storage.read(shard_id, limit=N)`** — returns up to `N` **most recent** entries from the shard (newest first).  
  Example: `entries = storage.read("sessions", limit=50)`.
- **`storage.list_shards()`** — returns a list of `ShardMeta` (shard_id, entry_count, last_updated, etc.).

**Example:**

```python
from dsm_v2.core.storage import Storage

storage = Storage(data_dir="/path/to/memory")

# List shards
for meta in storage.list_shards():
    print(meta.shard_id, meta.entry_count)

# Read last 100 entries from the sessions shard
entries = storage.read("sessions", limit=100)
for e in entries:
    print(e.timestamp, e.session_id, e.metadata.get("event_type"), e.content[:80])
```

- Entries are **ordered newest first** in the list returned by `read`.
- `content` is an opaque string; the agent must parse it (e.g. JSON) and implement its own semantics (e.g. “last user message”, “last tool result”).

---

## 4. How to implement a new skill

Skills are **reusable capabilities** (e.g. “browser search”, “reasoning”) that agents can select and invoke. The DSM skills system provides a **registry**, a **router** (task → skill), and optional **usage/success loggers** (telemetry only; they do not write to the DSM kernel).

### 4.1 Skill model

A **Skill** is defined by:

- `skill_id` — unique string (e.g. `"browser_search"`).
- `domain` — category (e.g. `"web"`, `"reasoning"`).
- `description` — short human-readable description.
- `trigger_conditions` — list of strings; the router matches these against the task description (e.g. `["search", "web", "browser"]`).
- `prompt_template` — optional template for prompts.
- `tags` — optional list of tags.
- `source_type` / `source_path` — optional (e.g. `"json"`, path to definition).

Definition lives in **`dsm_v2.skills.models.Skill`**.

### 4.2 Implementing a new skill

1. **Define the skill** (in code or via JSON in a library directory):
   - Create a `Skill` instance with `skill_id`, `domain`, `description`, `trigger_conditions`, and optionally `prompt_template`, `tags`.
2. **Register it** in a **SkillRegistry** (in memory; no DSM write).
3. **Use the SkillRouter** to map a task description to a skill: `router.route(task_description)` returns a `skill_id`, or `router.route_to(task_description)` returns the `Skill` object.
4. **Execute the skill** in the agent’s own code (DSM does not execute skills; it only stores events and, optionally, usage/success logs).
5. **Optional telemetry**: use **SkillUsageLogger** to log which skill was used for which task, and **SkillSuccessLogger** to log success/failure and duration. These write to separate JSONL files (e.g. `logs/skills_usage.jsonl`, `logs/skills_success.jsonl`), not to DSM Storage.

**Example (minimal in-code skill):**

```python
from dsm_v2.skills import SkillRegistry, SkillRouter
from dsm_v2.skills.models import Skill

registry = SkillRegistry()
router = SkillRouter(registry)

# Define and register
skill = Skill(
    skill_id="my_skill",
    domain="tools",
    description="Does something useful",
    trigger_conditions=["my_skill", "do something"],
)
registry.register(skill)

# Route a task
task = "User asked: do something with my_skill"
matched_skill = router.route_to(task)
if matched_skill:
    # Agent executes the skill logic, then optionally logs usage/success
    pass
```

**Libraries:** Skills can be loaded from directories via **SkillIngestor** (`ingest_from_directory`, `ingest_from_file`). Expected format (e.g. JSON) should include at least `skill_id` and a name/description; the ingestor maps them into `Skill` and registers with the registry. Skill libraries live under `memory/dsm/skills/libraries/` (e.g. `anthropic`, `community`, `custom`).

---

## 5. How agents should structure their interaction with DSM

Recommended structure so that behavior is consistent and replayable:

1. **Single memory root**  
   Use one **Storage** instance (and optionally one **SessionGraph** using it) per process or agent run, with a fixed `data_dir` (e.g. configured from env or project config). Do not mix multiple roots for the same logical “agent” unless by design.

2. **Session lifecycle**  
   - For each user interaction or run: **start_session(source)** at the beginning.  
   - All session-scoped observations and actions: **record_snapshot** / **execute_action**.  
   - When the interaction ends: **end_session()**.  
   - Do not start a new session without ending the previous one if the design is one active session at a time.

3. **Shard usage**  
   - Use the **`sessions`** shard for session lifecycle events (session start/end, snapshots, tool calls) via SessionGraph.  
   - Use other shards (e.g. `default`, `daryl_identity`) for non-session events (identity, heartbeats, custom logs) via **Storage.append(Entry(...))** with the appropriate `shard` and `session_id` (or `"none"`).

4. **Read-before-write (optional)**  
   When the agent needs context, **read** from the relevant shard(s) with a bounded `limit`, then decide what to do and **append** new entries. Do not assume indexes or search; treat memory as a recent-event stream.

5. **Skills and telemetry**  
   - Load skills (registry + router, optionally ingestor) once; route each task to a skill and execute in agent code.  
   - If using usage/success loggers, call them after execution; keep DSM kernel usage to **Storage** and **SessionGraph** only for persistence.

6. **No direct file manipulation**  
   Do not create, move, or delete files under the DSM `data_dir`; only use the **Storage** and **SessionGraph** APIs so that append-only and integrity semantics are preserved.

7. **Determinism and replay**  
   Entries are ordered and chained; trace/replay tools (see `dsm_v2` CLI and replay modules) can verify and replay logs. Agents should not rely on global mutable state for what they write; the source of truth is the stream of entries they append.

---

## Quick reference

| Need | Use |
|------|-----|
| Start/end a session, log snapshots and tool calls | `SessionGraph`: `start_session`, `record_snapshot`, `execute_action`, `end_session` |
| Log a custom event to a specific shard | `Storage.append(Entry(...))` |
| Read recent events | `Storage.read(shard_id, limit=N)` |
| List shards | `Storage.list_shards()` |
| Define/register a skill | `Skill`, `SkillRegistry.register` |
| Match task to skill | `SkillRouter.route` / `SkillRouter.route_to` |
| Optional skill telemetry | `SkillUsageLogger.log_usage`, `SkillSuccessLogger.log_success` |

All of the above assumes the **dsm_v2** package is installed (e.g. `pip install -e .` at repo root) and that the agent runs with the correct `data_dir` (and optional limits/session config) for the environment.
