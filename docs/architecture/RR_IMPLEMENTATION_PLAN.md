# RR — Implementation Plan

This document describes the **implementation strategy** for the Read Relay (RR) system.

RR is the **memory navigation layer** above the DSM kernel. The document explains how RR will be implemented **without modifying the DSM kernel**. RR must operate **strictly through the public Storage API**.

---

## 1. Objectives

The goals of RR implementation are:

- **Memory navigation** — Allow agents and upper layers to move through shards, sessions, and timelines without raw file access.
- **Timeline reconstruction** — Order and present events along a temporal axis for a given session or shard.
- **Session exploration** — Inspect and reconstruct the full event stream of a session from DSM entries.
- **Query abstraction** — Expose a high-level query interface (by session, shard, time range, agent) so callers do not depend on shard layout.
- **Context construction for agents** — Build structured context packs (selected entries, summaries, references) ready for LLM consumption.

RR transforms **raw DSM entries** into **structured memory views**. The kernel continues to store append-only entries; RR adds navigation, indexing, and context shaping on top.

---

## 2. Implementation Principles

Core implementation rules:

| Rule | Meaning |
|------|---------|
| **Use only the DSM Storage API** | All shard data is obtained via Storage.read(), Storage.list_shards(), Storage.get_shard_size(), or other public APIs. No internal kernel APIs. |
| **Remain read-only toward DSM shards** | RR never writes to shard files. No appends, no edits, no deletes. |
| **Never open shard JSONL files directly** | No open() on segment files; no reliance on filesystem paths or segment naming. |
| **Keep all derived data outside DSM storage** | Indexes, caches, and catalogs live in a dedicated directory (e.g. data/index/), not inside shard directories or integrity paths. |
| **Keep the DSM kernel unchanged** | No changes to memory/dsm/core/ or dsm_v2/core/. RR is a separate layer. |

This preserves **kernel stability**: the DSM contract (append, read, list_shards, get_shard_size) remains fixed. All new behavior (indexing, navigation, query, context building) is implemented in RR and does not require kernel evolution.

---

## 3. RR Module Structure

A possible module layout for RR:

```
rr/
  __init__.py
  relay.py           # Existing Step 1: read_recent, summary
  index/             # RR index building and lookup
  navigator/         # Session, shard, agent, timeline navigation
  query/             # High-level query interface
  context/           # Context builder (query results → context packs)
```

**Responsibility of each module:**

- **rr/relay.py** — Current RR Step 1: read_recent(shard_id, limit), summary(shard_id, limit). Uses only Storage.read(). Stays as the stable entry point for simple reads.
- **rr/index/** — Builds and maintains the RR index from shard metadata and entries. Reads via Storage.list_shards() and Storage.read(). Writes only to the index directory.
- **rr/navigator/** — Implements navigate_session, navigate_shard, navigate_agent, timeline. Uses the index when available and Storage.read() to fetch entries. Reconstructs structured views in memory.
- **rr/query/** — High-level RRQuery: accepts criteria (session_id, shard, time_range, agent) and returns memory slices. Delegates to Navigator and Index; calls Storage.read() for content.
- **rr/context/** — RRContextBuilder: takes query results (lists of entries or pointers) and produces context packs (selected entries, summaries, references to DSM memory) for agents and LLMs.

This structure keeps relay.py backward-compatible and adds new capabilities in separate subpackages.

---

## 4. RR Index Building

The index is built **from DSM** using only the public API.

**Steps:**

1. **List shards** using Storage.list_shards() to obtain all shard identifiers.
2. **Read entries** using Storage.read(shard_id, limit) per shard (and optionally iterate with larger limits or via segment manager if exposed by the API) to obtain entries.
3. **Extract metadata** from each entry: session_id, timestamp, shard_id, source/agent, event_type from metadata, etc. Do not store full content in the index; store only what is needed for navigation and lookup.
4. **Update RR index** by writing to the index directory (e.g. catalog files, session index, timestamp index). The index contains **references** to DSM entries (e.g. shard_id, entry id, timestamp), not the full content.

**Example metadata stored in the index:**

- session_id
- timestamp
- shard_id
- agent_name (or source)
- event_type (from entry.metadata)

The index is **derived data**. It can be **rebuilt at any time** by re-running the build process from step 1. DSM shards remain the source of truth; the index is a cache for efficient navigation.

---

## 5. Incremental Index Update

To keep the index up to date without full rescans, strategy options include:

- **Periodic scanning** — On a schedule, re-read recent entries from each shard (Storage.read with a limit), extract new metadata, and merge into the index. Simple but may duplicate work.
- **Append detection** — Use Storage.list_shards() (and optional metadata such as last_updated or entry_count if available) to detect when a shard has grown; then read only the additional entries (e.g. by tracking last-seen entry id or count per shard). Requires a way to read “new” entries; if the API only offers read(shard, limit), then periodic reads of the most recent N entries and diffing against the index is one approach.
- **Incremental indexing** — After each index build or update, persist a cursor (e.g. last processed entry id or timestamp per shard). Next run reads from Storage and processes only entries after that cursor. Depends on being able to order entries and detect new ones via the public API.

Index updates must **not interfere with DSM writes**. RR only reads. Writes by agents or SessionGraph to DSM continue as usual; RR’s index runs in the background or on demand and does not lock or modify shards.

---

## 6. RR Navigator Implementation

The navigator implements operations that reconstruct **structured memory views** from raw entries:

- **navigate_session(session_id)** — Use the index to find entries for the session (or scan via Storage.read() and filter by session_id). Return entries in order (e.g. by timestamp). Reconstruct the session event stream.
- **navigate_shard(shard_id)** — Call Storage.read(shard_id, limit) and optionally use the index for larger or paginated views. Return a view over the shard (recent entries or a slice).
- **navigate_agent(agent_name)** — Use the index to find entries where source or agent matches; or read from relevant shards and filter. Return events or sessions associated with that agent.
- **timeline(session_id)** — Same as navigate_session but with explicit ordering by timestamp and optional formatting for timeline display. Return ordered events for the session.

In all cases, the navigator **reconstructs** structure in memory: it does not open files; it uses Storage.read() (and the index when available) to get entries, then sorts, filters, and groups them. The result is a structured view (lists of entries, or pointers + metadata) for the caller.

---

## 7. RR Query Pipeline

End-to-end flow from agent request to context pack:

```
Agent request
       │
       ▼
  RRQuery          ← Parse criteria (session_id, shard, time_range, agent)
       │
       ▼
  RRNavigator      ← Resolve to memory slices (which shards, which entries)
       │
       ▼
  RRIndex lookup   ← Use index for fast resolution (if available)
       │
       ▼
  Storage.read()   ← Fetch actual entries from DSM (only public API)
       │
       ▼
  ContextBuilder   ← Turn entries into context pack (selection, summaries, refs)
       │
       ▼
  Context Pack     ← Output to agent / LLM
```

**Each step:**

1. **Agent request** — The caller asks for memory (e.g. “last 10 events of session X”, “sessions shard recent 100”, “events for agent clawdbot in last hour”).
2. **RRQuery** — Translates the request into navigator calls (e.g. navigate_session(session_id), navigate_shard("sessions") with limit, or navigate_agent + time filter).
3. **RRNavigator** — Decides which shards and which entry set to use; consults RR Index for pointers or ranges.
4. **RRIndex lookup** — Returns references (shard_id, entry ids, timestamps) so the navigator can request only needed data.
5. **Storage.read()** — DSM kernel returns the requested entries. No direct file access.
6. **ContextBuilder** — Selects, summarizes, and formats the entries; adds references to DSM memory. Produces the context pack.
7. **Context Pack** — Returned to the agent for LLM consumption or further processing.

---

## 8. Context Builder

The **context builder** turns RR query results into context packs.

**Input:**

- RR query results: one or more memory slices (lists of Entry or pointers with metadata).

**Output:**

Structured context including:

- **Selected entries** — The entries (or their content/snippets) that are relevant to the request. Optionally truncated or summarized.
- **Summaries** — Short summaries (e.g. “Session X: 5 tool calls, 2 snapshots”) when useful.
- **References to DSM memory** — Stable references (shard_id, entry id, timestamp) so the agent or LLM can refer back to the source in DSM if needed.

The context builder **prepares memory for LLM consumption**: it does not call the LLM and does not write to DSM. It only shapes the data (selection, ordering, formatting, references) so that the agent can pass a clean context pack to an LLM or use it for reasoning.

---

## 9. Performance Strategy

RR must handle **large DSM memories** without changing the DSM kernel.

Possible strategies:

- **Index caching** — Keep the RR index in memory or in a fast local store so that repeated navigations and queries do not rescan shards every time. Invalidate or refresh on a policy (e.g. TTL or on-demand rebuild).
- **Incremental indexing** — Update the index only with new entries (see Section 5) to avoid full rescans. Reduces I/O and keeps index build time bounded.
- **Lazy shard scanning** — When the index is missing or incomplete, scan shards on demand via Storage.read() with a limit. Optionally backfill the index after the first scan so that later requests are faster.
- **Query limits** — Enforce default and maximum limits on the number of entries returned per query (e.g. read_recent(..., limit=100)). Prevents unbounded reads and keeps response size and latency predictable.

**DSM itself remains simple** and does not implement indexing, caching, or query optimization. All of that lives in RR. The kernel continues to expose only append, read, list_shards, and get_shard_size.

---

## 10. Failure and Recovery

**If the RR index is corrupted or lost:**

1. **Delete the index** — Remove or clear the index directory (e.g. data/index/).
2. **Rebuild from shards** — Run the index build process again (Section 4): list shards, read entries via Storage.read(), extract metadata, write the new index.

**DSM shards remain the source of truth.** RR’s index is derived data. No recovery of the kernel is needed; only RR’s derived state is rebuilt. Agents can continue to use Storage.read() directly (or RR’s read_recent/summary) even while the index is down; they may lose only the benefits of fast navigation and query until the index is restored.

---

## 11. Future Extensions

Possible extensions (all **outside** the DSM kernel):

- **Semantic search** — Index entries by meaning or topic; support natural-language or keyword queries over memory. Implemented in RR (or an RR extension) using Storage.read() and optional external indexes.
- **Vector embeddings** — Compute or store embeddings for entries; support similarity search. Embeddings and vector index live in RR’s index directory; content still comes from Storage.read().
- **Memory graph navigation** — Model sessions, agents, or events as a graph; navigate along relationships. Graph structure is derived from entries and stored in RR; kernel unchanged.
- **Multi-agent memory exploration** — Views or namespaces so multiple agents can query the same DSM store with different filters or permissions. Implemented in RR’s query and navigator layers.

These extensions **remain outside the DSM kernel**. They use only the public Storage API and write only to RR’s own index/cache storage. The kernel stays a minimal, frozen storage and integrity layer.

---

## 12. Implementation Phases

Staged implementation reduces risk and keeps each deliverable testable.

**Phase 1 — RR basic navigation (current / Step 1)**

- read_recent(shard_id, limit)
- summary(shard_id, limit)
- Uses only Storage.read(); no index. Already present in rr/relay.py. Validate and document as the stable base.

**Phase 2 — RR index and session navigation**

- Implement RR index: build from list_shards() and read(); store metadata (session_id, timestamp, shard_id, agent, event_type) in data/index/.
- Implement navigate_session(session_id) and timeline(session_id) using index + Storage.read().
- Optional: incremental index update strategy.

**Phase 3 — RR query engine and context builder**

- Implement RRQuery: query(session_id=...), query(shard=...), query(time_range=...), query(agent=...).
- Implement RRContextBuilder: query results → context pack (selected entries, summaries, references).
- Wire the pipeline: Agent request → RRQuery → RRNavigator → Index lookup → Storage.read() → ContextBuilder → Context Pack.

**Phase 4 — Performance optimization**

- Index caching and invalidation policy.
- Lazy shard scanning and backfill.
- Query limits and tuning.
- Optional: incremental indexing and append detection.

Each phase keeps the DSM kernel unchanged and uses only the public Storage API. RR evolves in layers above the kernel.
