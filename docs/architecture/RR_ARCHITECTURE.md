# RR — Read Relay Architecture

This document defines the architecture of the **Read Relay (RR)** system.

RR is the **memory navigation layer** above the DSM kernel. DSM provides deterministic storage; RR provides structured memory access. RR must always remain **read-only with respect to DSM shards**.

---

## 1. Role of RR

RR provides:

- **Memory navigation** — Move through shards, sessions, and timelines without raw file access.
- **Session exploration** — Inspect and reconstruct the event stream of a given session.
- **Timeline reconstruction** — Order and present events along a temporal axis.
- **Context extraction** — Select relevant slices of memory for a given task.
- **Summarization** — Produce lightweight summaries (entry counts, sessions, errors, top actions) from shard data.
- **Query abstraction** — Expose a high-level query interface so agents do not need to know shard layout or segment details.

RR converts raw DSM events into **structured memory views** that agents and upper layers can consume.

---

## 2. Architecture Position

RR sits between the cognition layers and the DSM storage kernel:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  AGENTS                                                                  │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  SKILLS / ANS                                                            │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  CONTEXT PACKS                                                           │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  RR (Memory Navigator)                                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  DSM KERNEL                                                              │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  SHARD STORAGE                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

RR is the boundary between **memory use** (cognition, context, agents) and **memory persistence** (DSM kernel and shard storage). All read access to DSM memory from upper layers should go through RR (or directly through the public Storage API when low-level access is needed).

---

## 3. RR Design Principles

| Principle | Meaning |
|-----------|---------|
| **RR is read-only toward DSM** | RR never writes to shard files or modifies shard content. |
| **RR must use only the Storage API** | All shard data is obtained via Storage.read(), Storage.list_shards(), Storage.get_shard_size(), or other public APIs. |
| **RR must not open shard files directly** | No opening of JSONL segment files; no reliance on filesystem layout. |
| **RR must not modify shard content** | No appends, no edits, no deletes. The kernel remains the single writer. |
| **RR may maintain external indexes or caches** | Indexes and caches live outside the shards (e.g. under a dedicated index directory) and are derived, regenerable data. |

This separation preserves **kernel stability**: the DSM core remains a minimal, frozen storage and integrity layer. All navigation, indexing, and query logic lives in RR, so the kernel contract does not change when RR evolves.

---

## 4. RR Core Components

| Component | Role |
|-----------|------|
| **RRIndex** | Secondary index derived from DSM shards. Stores session references, timestamps, shard pointers, and optional agent identifiers. Enables efficient navigation without scanning full shards. |
| **RRNavigator** | Memory navigation across sessions, timelines, and agents. Reconstructs structure from raw entries and index metadata. |
| **RRQuery** | High-level query interface used by agents. Accepts criteria (session, shard, time range, agent) and returns memory slices or pointers. |
| **RRContextBuilder** | Transforms memory slices (query results) into context packs: selected events, summaries, and references to DSM entries, ready for LLM consumption. |

These components form the RR layer. They depend only on the public Storage API and on RR’s own index/cache storage.

---

## 5. RR Index

The **RR index** allows efficient navigation of large DSM memories without scanning every segment on each request.

The index may include:

- **Session references** — Mapping from session_id to shard and entry references or offsets.
- **Timestamp ordering** — Ordering or ranges of events by time for timeline and time-range queries.
- **Shard pointers** — Which shards exist and optional metadata (counts, last updated).
- **Agent identifiers** — When entries carry agent or source information, index by agent for agent-scoped navigation.

The index is **derived data**. It can always be rebuilt from shards by reading through the Storage API. It is not the source of truth; DSM shards are. If the index is lost or corrupted, RR can regenerate it (possibly with a full or incremental rescan).

**Index storage example:** Index files and caches are stored under a dedicated directory, for example:

```
data/index/
```

This directory is separate from shard storage and from DSM integrity data. RR may write catalog files, query caches, or index segments here—never into shard directories.

---

## 6. RR Navigator

The **RRNavigator** reconstructs memory structure from raw entries and supports operations such as:

- **navigate_session(session_id)** — Return the ordered event stream for a session (from the sessions shard or other shards that record session_id).
- **navigate_shard(shard_id)** — Return a view over a shard (e.g. recent entries, or entries in a range), using Storage.read() and optionally the index.
- **navigate_agent(agent_name)** — Return events or sessions associated with a given agent or source, using metadata and index.
- **timeline(session_id)** — Reconstruct a timeline of events for a session, ordered by timestamp, for display or context building.

The navigator does not open shard files directly. It uses the Storage API (and the index when available) to obtain entries, then orders, filters, and structures them in memory.

---

## 7. RR Query Model

The **RR query** abstraction exposes a high-level interface to agents. Examples:

- **query(session_id=...)** — Return all entries (or pointers) for the given session.
- **query(shard="sessions")** — Return recent entries from the sessions shard, optionally with a limit.
- **query(time_range=...)** — Return entries within a time range (implemented via index and/or Storage.read() plus in-memory filtering).
- **query(agent="clawdbot")** — Return entries or sessions associated with the given agent.

Internally, RR queries rely on the **index** (when present) for fast lookup and on **Storage.read()** to fetch actual entries. The query layer hides segment layout and shard structure from the caller.

---

## 8. RR Context Builder

The **RRContextBuilder** turns RR query results into **context packs** for LLM consumption.

**Input:**

- RR query results (memory slices: lists of entries or pointers).

**Output:**

Structured context including:

- **Selected events** — The entries or snippets relevant to the request.
- **Summaries** — Optional short summaries (e.g. per session or per shard).
- **References to DSM entries** — Stable references (e.g. shard, id, timestamp) so that the agent or LLM can refer back to DSM if needed.

The builder prepares memory for LLM consumption: it does not write back to DSM and does not call LLMs itself in the minimal design; it only shapes the data. Context packs are the output of this process.

---

## 9. RR Data Flow

End-to-end flow from agent request to context pack:

```
Agent request
       │
       ▼
┌──────────────┐
│  RR Query    │
└──────────────┘
       │
       ▼
┌──────────────┐
│ RR Navigator│
└──────────────┘
       │
       ▼
┌──────────────┐
│ RR Index    │
│ lookup      │
└──────────────┘
       │
       ▼
┌──────────────┐
│Storage.read()│
└──────────────┘
       │
       ▼
┌──────────────┐
│Context      │
│Builder      │
└──────────────┘
       │
       ▼
Context Pack
```

The agent (or Context Packs layer) issues a request. RR Query translates it into navigator calls. The Navigator uses the RR Index when available, then calls Storage.read() to obtain entries from the DSM kernel. The Context Builder turns the resulting memory slice into a context pack returned to the caller.

---

## 10. Performance Strategy

RR must support **large memories** without requiring the DSM kernel to grow in complexity.

Strategies may include:

- **Index caching** — Keep index data in memory or in a fast cache so that repeated navigations do not rescan shards every time.
- **Incremental indexing** — Update the index as new entries are appended (by reading only new data via Storage.read() with appropriate limits or by tracking last-seen positions). Avoid full rescan when possible.
- **Lazy shard scanning** — When the index is absent or incomplete, scan shards on demand via Storage.read() and optionally backfill the index.

DSM itself remains simple and does not handle indexing. All indexing and caching logic lives in RR (or in a dedicated indexer component within the RR layer). The kernel continues to expose only append, read, list_shards, and get_shard_size.

---

## 11. Future Extensions

Possible future features for RR (all outside the DSM kernel):

- **Semantic indexing** — Index entries by meaning or topic for semantic search.
- **Vector embeddings** — Store or compute embeddings for entries and support similarity search over memory.
- **Memory graph navigation** — Model relationships between sessions, agents, or events as a graph and navigate along edges.
- **Multi-agent shared memory** — Views or namespaces so that multiple agents can navigate the same DSM store with different perspectives or filters.

These extensions must remain **outside the DSM kernel**. They are implemented in RR (or in layers above RR) and use only the public Storage API to read data. The kernel stays a deterministic, append-only storage and integrity layer.

---

## 12. Summary

- **DSM** = deterministic storage kernel. It provides append-only shards, hash chain integrity, and a minimal API (append, read, list_shards, get_shard_size). It does not provide search, indexing, or query.

- **RR** = memory navigation layer. It provides memory navigation, session exploration, timeline reconstruction, context extraction, summarization, and query abstraction. It is read-only toward DSM and uses only the Storage API.

RR enables agents to **understand and use DSM memory efficiently** without touching the kernel contract. All evolution of navigation, indexing, and context building happens in RR, keeping the DSM core stable and portable.
