# DSM / DARYL — Architecture Map

Primary reference for developers and contributors to the Daryl project.

---

## 1. Vision

**DSM (Daryl Sharding Memory)** is a **deterministic, append-only memory kernel** for AI agents.

- Events are written once and never modified or deleted.
- Data is organized by **shards** (logical logs); each shard is an ordered sequence of entries.
- **Hash chaining** per shard enables integrity verification and deterministic replay.
- The kernel does not provide search, indexing, or query engines—it is a minimal persistence and integrity layer. Agents and upper layers build navigation, context, and reasoning on top of it.

---

## 2. High-Level Architecture

The system is organized in **layers**. Upper layers depend only on the APIs of the layers below; the DSM core is the frozen foundation.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  AGENTS                                                                  │
│  Runtime agents (e.g. Clawdbot) that use memory and skills               │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  SKILLS / ANS                                                            │
│  Skill registry, router, usage/success telemetry, learning (ANS)         │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  CONTEXT PACKS                                                           │
│  Transform DSM memory into LLM-ready context (planned)                   │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  RR — READ RELAY                                                         │
│  Read-only memory navigation: read_recent, summary (Step 1)              │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  BLOCK LAYER                                                             │
│  Optional batching of entries into blocks (experimental)                  │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  SESSION LAYER                                                           │
│  SessionGraph: start_session, snapshot, tool_call, end_session            │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  SECURITY LAYER                                                          │
│  Baseline integrity, audit logs, protected files, rate limiting          │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  DSM CORE                                                                │
│  Storage API, models (Entry, ShardMeta), segments, signing, replay       │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  STORAGE                                                                 │
│  Append-only JSONL files per shard family, integrity metadata            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. DSM Core Responsibilities

The **DSM core** is the minimal kernel. Its public storage API is:

| Method | Role |
|--------|------|
| **append(entry)** | Append one entry to a shard. Computes hash, chains prev_hash, writes one JSONL line. |
| **read(shard, limit)** | Return the most recent `limit` entries from the shard (newest first). |
| **list_shards()** | Return metadata for all shards (id, counts, last updated, integrity status). |
| **get_shard_size(shard)** | Return total size in bytes for a shard. |

**DSM intentionally does NOT implement:**

- **Search** — no full-text or semantic search in the kernel.
- **Indexing** — no indexes; readers scan or use upper-layer caches.
- **Query engine** — no SQL, no structured queries; only read-by-shard with limit.
- **LLM logic** — no models, no summarization, no generation inside the kernel.

All of these belong in upper layers (RR, Context Packs, agents).

---

## DSM Kernel Boundary

The **DSM kernel** is strictly limited to the core storage and integrity components.

Kernel modules:

- memory/dsm/core/
  - storage.py
  - models.py
  - shard_segments.py
  - signing.py
  - replay.py
  - security.py

These modules define the deterministic storage system and must remain stable.

The following components are **NOT part of the kernel** and may evolve independently:

- session/
- rr/
- block_layer/
- skills/
- ans/
- modules/

These layers operate above the kernel and must interact with DSM only through the public Storage API.

This boundary ensures long-term kernel stability and prevents feature creep inside the core storage system.

---

## 4. Sharding Model

- Each **shard** is a logical log identified by a shard id (e.g. `sessions`, `default`).
- On disk, a shard is represented by a **family directory** and one or more **segment files**.

**Example structure:**

```
data/shards/sessions/
  sessions_0001.jsonl
  sessions_0002.jsonl
  ...
```

- One line per entry (JSON). Order of lines is the order of appends.
- **Segment rotation**: when the active segment reaches a maximum number of events or a maximum size, the next append creates a new segment file (e.g. `sessions_0003.jsonl`). This keeps individual files bounded and supports efficient sequential read.

---

## 5. Hash Chain Integrity

- **Per entry:**  
  - `hash` = SHA256(`content`).  
  - `prev_hash` = `hash` of the previous entry in the same shard (null for the first entry).

- **Chain:** Entry₁.prev_hash = null → Entry₂.prev_hash = Entry₁.hash → Entry₃.prev_hash = Entry₂.hash → …

- **Verification:** Given a list of entries in order, integrity is checked by:  
  - Recomputing SHA256(content) and comparing to `entry.hash`.  
  - Checking that each `prev_hash` equals the previous entry’s `hash`.

- The kernel stores the **last hash** per shard in integrity metadata so that each new append can set `prev_hash` correctly. Any tampering or truncation breaks the chain and can be detected.

---

## 6. Session Layer

The **Session Layer** models a session lifecycle and writes events to the **sessions** shard:

| Step | API | Event type |
|------|-----|------------|
| 1 | **start_session(source)** | `session_start` |
| 2 | **record_snapshot(data)** | `snapshot` (optional, rate-limited) |
| 3 | **execute_action(name, payload)** | `tool_call` (optional, rate-limited) |
| 4 | **end_session()** | `session_end` |

- Every such event is an **Entry** with `session_id` set to the current session.
- The **sessions** shard is the single stream of session lifecycle events; other shards can be used for identity, heartbeats, or custom logs.
- Limits (e.g. cooldown for snapshots, daily action budget) are enforced by the session layer, not by the kernel.

---

## 7. Replay System

Two replay mechanisms exist:

1. **Trace replay**  
   - Input: a **trace file** (e.g. JSONL with trace_id, session_id, action_type, step_hash, prev_step_hash).  
   - The replay module verifies step hashes and the chain of prev_step_hash → step_hash.  
   - Output: a report (OK / DIVERGENCE / CORRUPT). Used for auditing execution traces.

2. **Session replay**  
   - Input: a **session_id** and access to the **sessions** shard.  
   - The replayer reads all events for that session, orders them by timestamp, and verifies the **hash chain** (prev_hash → hash) and event sequence.  
   - Used to validate that a session’s event stream is consistent and unaltered.

Both support **deterministic** verification: same inputs yield the same integrity result.

---

## 8. Security Layer

- **Baseline integrity:** A set of critical files (kernel code, CLI, security config) has their hashes stored in a baseline. Any change is detected and reported. Shard data is **not** in the baseline; it is protected by the hash chain.

- **Audit logs:** Security-relevant events (baseline updates, protected write attempts, rate limit exceeded) are appended to an audit log (e.g. JSONL). Read-only for normal operation.

- **Protected files:** Certain files (e.g. security policy, core security module) cannot be overwritten by default; overwrite requires an explicit override (e.g. environment variable or policy).

- **Rate limiting:** Optional limits on API calls and file writes per cycle to reduce abuse risk.

---

## 9. RR — Read Relay

**RR (Read Relay)** is the **memory navigation layer** above the kernel.

- It is **read-only** with respect to shard data: it does not write to shards or modify the DSM core.
- **Step 1** provides:
  - **read_recent(shard_id, limit)** — most recent entries from a shard (via Storage.read).
  - **summary(shard_id, limit)** — lightweight stats: entry count, unique sessions, error count, top action names.

- RR uses **only** the public Storage API (read, list_shards, etc.). It does not open shard files directly. This keeps RR compatible with segment layout and block shards.

- Future extensions (index, navigator, query cache) must follow the same rule: read-only toward shards, and only through the Storage API.

**RR access rule:** RR must access DSM memory **only through the public Storage API**. Direct shard file access (opening JSONL files manually) is forbidden. All reads must go through:

- Storage.read()
- Storage.list_shards()
- Storage.get_shard_size()

This guarantees compatibility with shard segmentation and future storage changes.

---

## 10. Context Packs

**Context Packs** (planned) transform DSM memory into **LLM-ready context**.

- **Input:** Shard(s), optional filters (e.g. session_id, time range). Data is obtained via Storage or RR (read_recent, summary).
- **Output:** A structured pack: selected entries or snippets plus references into DSM. No summarization by an LLM in the minimal version; just selection and formatting.
- **Rules:** No writes to shards; no modification of kernel state. The source of truth remains the Storage layer.

---

## 11. Skills / ANS Layer

- **Skills:** A **registry** of skills (e.g. code_review, task_decomposition) with descriptions and trigger conditions. A **router** maps a task description to a skill. **Ingestors** load skill definitions from libraries. Usage and success are logged to **separate** JSONL files (telemetry), not to the DSM kernel shards.

- **ANS (Audience Neural System):** A **learning layer** that analyzes skill telemetry (usage, success, duration) and produces recommendations (e.g. workflow improvements, weak skills). It reads telemetry logs and does not write to DSM shards.

- Both layers sit **above** the kernel and do not require changes to the DSM core.

---

## 12. Architectural Principles

| Principle | Meaning |
|-----------|---------|
| **DSM core must remain frozen** | No new features inside the kernel; new capabilities are implemented in upper layers. |
| **Append-only storage** | Entries are never updated or deleted in place; only append and read. |
| **Deterministic replay** | Hash chains and optional trace replay allow verification and reproducible audit. |
| **Clear layer separation** | Each layer has a well-defined API; dependencies point downward only. |
| **Minimal kernel surface** | The core exposes only append, read, list_shards, get_shard_size (and models); no search, index, or query. |

---

## 13. Future Components

Planned or optional components (not part of the frozen kernel):

- **RR indexing** — Optional catalog of shards (e.g. counts, last updated) built from the Storage API, stored in a separate index directory, regenerable.
- **Navigator** — Query over entries obtained via Storage.read (or RR); returns pointers/references; no direct file access to shards.
- **Context Engine** — Builds context packs from RR/Storage for agents and LLMs.
- **Portable DSM (PDSM)** — A portable or embeddable variant of DSM for use outside the main repository (see roadmap docs).

All of these must use only the public Storage API and remain read-only toward shard data.

---

## 14. Final Architecture Summary

The architecture can be summarized in **three conceptual layers**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  COGNITION LAYER                                                         │
│  Agents / Skills / ANS                                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  NAVIGATION LAYER                                                        │
│  RR (Memory Navigator)                                                  │
│  Context Packs                                                           │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  STORAGE LAYER                                                           │
│  DSM Kernel                                                              │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Storage layer:** DSM kernel guarantees persistence, order, and integrity.
- **Navigation layer:** RR (Memory Navigator) and Context Packs — memory shaping for LLMs.
- **Cognition layer:** Agents and Skills/ANS consume memory and telemetry to act and improve.

This map is the primary architecture reference for Daryl / DSM. For implementation details, see the full system audit and the other architecture and roadmap documents.
