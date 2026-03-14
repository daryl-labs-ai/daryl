# RR — Index Specification

This document defines the structure of the **RR memory index**.

The RR index enables efficient navigation of DSM memory without scanning all shard files for every query. The index is **derived data** and can always be rebuilt from DSM shards. **DSM shards remain the source of truth.**

---

## 1. Role of the RR Index

The RR index allows:

- **Fast navigation across sessions** — Resolve a session_id to its entries without reading every segment of the sessions shard.
- **Timeline reconstruction** — Order events by timestamp for a session or shard without a full sequential scan each time.
- **Agent activity lookup** — Find entries or sessions associated with a given agent (or source) without filtering entire shards in memory.
- **Efficient query resolution** — Answer queries (by session, time range, agent) by consulting the index first, then fetching only the relevant entries via Storage.read().

**Without the index**, RR would need to scan shards repeatedly: each navigation or query would require reading large portions of one or more shards and filtering in memory. The index reduces I/O and latency by storing lightweight metadata and references, so RR can target reads and reconstruct views efficiently.

---

## 2. Index Principles

Core rules for the RR index:

| Principle | Meaning |
|-----------|---------|
| **Never modify DSM shards** | The index does not write to shard directories or segment files. RR is read-only toward DSM. |
| **Contain only derived metadata** | The index stores references and metadata (session_id, timestamp, shard_id, agent, event_type, etc.), not full entry content. Content lives only in DSM. |
| **Be rebuildable at any time** | The index can be regenerated from shards by listing shards, reading entries via Storage.read(), and rebuilding index structures. No unique state is lost if the index is deleted. |
| **Remain independent from DSM storage** | Index format, location, and update strategy are chosen by RR. DSM does not depend on the index. |
| **Be stored outside the shard directories** | Index files live in a dedicated directory (e.g. data/index/), not inside data/shards/ or any shard family directory. |

**If the index is deleted**, it can be **regenerated** by running the index build process again. DSM shards are unchanged; RR re-reads them through the Storage API and reconstructs the index. No kernel recovery is required.

---

## 3. Index Storage Location

Index data is stored in a **dedicated directory**, separate from DSM shards and integrity data.

**Example structure:**

```
data/index/
  sessions.idx      # Session index: session_id → entries / references
  agents.idx        # Agent index: agent_name → entries / references
  timeline.idx      # Timeline index: ordered by timestamp
  shard_catalog     # Optional: shard metadata (counts, last updated)
```

- **sessions.idx** — Maps session_id to the list of index entries (or pointers) belonging to that session. Used for navigate_session and timeline(session_id).
- **agents.idx** — Maps agent name (or source) to entries. Used for navigate_agent and agent-scoped queries.
- **timeline.idx** — Orders entries by timestamp (e.g. global or per-session). Used for timeline reconstruction and time-range queries.
- **shard_catalog** — Optional catalog of shards (identifiers, entry counts, last updated). Can be built from Storage.list_shards() and optional reads.

These files are **RR-managed artifacts**. They are not part of the DSM kernel or shard storage. RR may choose different formats (e.g. JSON, JSONL, or binary) and naming; the important point is that they live under data/index/ (or a configured index root) and are never mixed with shard segments.

---

## 4. Index Entry Structure

An **index entry** is a lightweight record that points to a DSM entry and holds metadata for navigation. It does not store the full content of the DSM entry.

**Example structure:**

```json
{
  "session_id": "session_1734567890_abc12345",
  "timestamp": "2026-03-15T10:30:00.000Z",
  "shard_id": "sessions",
  "segment": "sessions_0003.jsonl",
  "offset": 421,
  "agent": "clawdbot",
  "event_type": "tool_call"
}
```

**Field meanings:**

| Field | Meaning |
|-------|---------|
| **session_id** | The session this entry belongs to (from Entry.session_id). Used for session-scoped navigation and queries. |
| **timestamp** | Event time (from Entry.timestamp). Used for ordering and time-range queries. |
| **shard_id** | The DSM shard that contains this entry. Used to call Storage.read(shard_id, ...) or to know which shard to read from. |
| **segment** | Optional: the segment file name (e.g. sessions_0003.jsonl). Used only if RR needs segment-level granularity; if the Storage API does not expose segments, this may be omitted or derived. |
| **offset** | Optional: position or offset within the segment (e.g. line number or byte offset). Enables precise targeting when the storage layer supports it; otherwise RR may rely on entry id and read + filter. |
| **agent** | Agent or source identifier (from Entry.source or metadata). Used for agent index and navigate_agent. |
| **event_type** | Type of event (from Entry.metadata.event_type), e.g. session_start, snapshot, tool_call, session_end. Used for filtering and summaries. |

Additional fields (e.g. entry id, hash) may be stored if useful for validation or deduplication. The index entry is a **reference** to the DSM entry; the full content remains in the shard and is read via Storage.read() when needed.

---

## 5. Index Types

Different **index views** support different navigation patterns.

**Session Index**

- **Maps:** session_id → list of index entries (or references) for that session.
- **Use:** navigate_session(session_id), timeline(session_id), query(session_id=...).
- **Built from:** Entries read from the sessions shard (and optionally others) with session_id extracted; grouped by session_id.

**Agent Index**

- **Maps:** agent_name (or source) → list of index entries for that agent.
- **Use:** navigate_agent(agent_name), query(agent=...).
- **Built from:** Entries with source or metadata.agent extracted; grouped by agent/source.

**Timeline Index**

- **Maps:** Ordered list of entries (or references) by timestamp (global or per session).
- **Use:** Timeline reconstruction, time-range queries, “recent N events”.
- **Built from:** All index entries (or per-shard) sorted by timestamp. May be stored as a sorted file or as pointers into session/agent indexes.

**Shard Index**

- **Maps:** shard_id → segment list and optional metadata (counts, last updated).
- **Use:** Know which shards exist; optionally which segments to read; avoid listing filesystem. Can be built from Storage.list_shards() plus optional Storage.read() for counts.
- **Built from:** Storage.list_shards() and, if needed, bounded Storage.read() per shard to compute or refresh counts.

These index types are **views** over the same underlying DSM data. They can be implemented as separate files (sessions.idx, agents.idx, timeline.idx, shard_catalog) or as different projections of a single index store; the spec does not mandate a single implementation.

---

## 6. Index Building

The index is **created** from DSM using only the public Storage API.

**Steps:**

1. **List shards** using Storage.list_shards() to obtain all shard identifiers.
2. **Read entries** using Storage.read(shard_id, limit) for each shard. For a full build, repeat with appropriate limits or use iteration (if exposed) until all entries are processed.
3. **Extract metadata** from each entry: session_id, timestamp, shard_id, source/agent, event_type from metadata. Optionally segment/offset if the API provides them. Build in-memory structures (session map, agent map, sorted timeline).
4. **Build index structures** — Session index, agent index, timeline index, and optionally shard catalog from the extracted metadata.
5. **Write index files** to the index directory (e.g. data/index/). Do not write to shard directories.

This process can be run **at startup** (e.g. when RR starts and the index is missing or stale), **on demand** (e.g. via an explicit “rebuild index” command), or **periodically** (e.g. a background job). Index building is read-only toward DSM; it only calls Storage.read() and Storage.list_shards().

---

## 7. Incremental Index Update

When new entries are appended to DSM, the index can be updated without a full rebuild.

**Possible strategies:**

- **Periodic shard scanning** — On a schedule, call Storage.read(shard_id, limit) for recent entries (e.g. last N). Compare with the index (e.g. by entry id or timestamp) and append only new entries to the index. Simple but may re-read some entries.
- **Incremental append detection** — Use Storage.list_shards() (and any metadata such as entry_count or last_updated) to detect when a shard has grown. Then read only the “tail” of the shard (e.g. entries after the last indexed timestamp or id) and merge into the index. Requires a way to request entries after a cursor; if the API only supports read(shard, limit), then “read recent limit” and diff against the index is one approach.
- **Update during RR reads** — When RR serves a read (e.g. read_recent or a query), optionally add the returned entries to the index if they are not already present. Index grows lazily as RR is used. May leave the index incomplete until all shards have been read at least once.

**DSM writes must remain independent.** Agents and SessionGraph continue to append to DSM without waiting for the index. Index updates run asynchronously or on demand; they only read from DSM and write to the index directory. No locking or coordination with DSM writers is required.

---

## 8. Index Consistency

RR maintains index consistency by treating the index as **derived state** and DSM as **authoritative**.

- **If inconsistencies are detected** (e.g. an index entry points to a non-existent or changed DSM entry, or the index is out of date with the shard), RR can:
  - **Rebuild the index** — Delete index files and run the full build process (Section 6). Guarantees a consistent index matching current shards.
  - **Rescan shards** — Re-read the affected shards via Storage.read(), update the index structures, and write the index again. Partial rebuild when only some shards are suspect.
  - **Validate references** — When serving a query, optionally verify that referenced entries still exist (e.g. by reading and checking). If not, remove stale index entries or trigger a rescan.

**DSM remains authoritative.** The index may be stale or wrong; the shards are not. Recovery always involves re-reading from DSM and rebuilding or updating the index. RR never “repairs” DSM from the index.

---

## 9. Index Performance

For **large memory** scenarios, performance considerations include:

- **Index caching** — Keep the index (or hot parts of it) in memory so that repeated navigations and queries do not hit disk for every lookup. Invalidate or refresh on a policy (e.g. TTL, or when index files change).
- **Partial index loading** — Load only a subset of the index at startup (e.g. session index for the last N days, or only the sessions shard). Load more on demand when a query touches other shards or time ranges. Reduces startup time and memory.
- **Lazy reconstruction** — For timeline or session views, reconstruct on demand from the index entries (and Storage.read() for content) instead of pre-materializing every possible view. Trade memory for compute.
- **Shard-level partitioning** — Partition the index by shard (e.g. one sessions.idx per shard or one file per shard). Enables updating only the partition for a shard that changed and reduces the size of each index file.

DSM itself does not implement indexing or caching; it only exposes read, append, list_shards, and get_shard_size. All index performance strategies are implemented in RR and do not require kernel changes.

---

## 10. Failure and Recovery

**Recovery from index corruption or loss:**

1. **Delete the index** — Remove or clear the index directory (e.g. data/index/).
2. **Rebuild from shards** — Run the index build process (Section 6): list shards, read entries via Storage.read(), extract metadata, build index structures, write index files.

This is **safe** because:

- **DSM storage is append-only.** Shards are never overwritten or deleted by RR. All data needed to rebuild the index is still in the shards.
- **The index is derived data.** No unique information is stored only in the index; everything can be re-derived from DSM.
- **No kernel state is affected.** Recovery is entirely within RR. DSM continues to serve read and append as usual.

Until the index is rebuilt, RR can still serve requests using Storage.read() directly (e.g. read_recent, summary, or full-scan navigation), possibly with higher latency. Agents can continue to use DSM; they temporarily lose only the performance benefits of the index.

---

## 11. Future Extensions

Possible future extensions to the RR index (all **outside** the DSM kernel):

- **Semantic index** — Index entries by topic or meaning (e.g. keywords, categories). Enables semantic or keyword search over memory. Implemented in RR; content still from Storage.read().
- **Vector embeddings** — Store or compute embeddings for entries; maintain a vector index for similarity search. Embeddings and vector index live in the index directory; DSM stores only the original entries.
- **Memory graph index** — Model relationships (e.g. session → events, agent → sessions) as a graph; store graph structure in the index for graph-based navigation. Built from entries read via Storage.read().
- **Multi-agent correlation index** — Index that correlates activity across agents (e.g. shared sessions, cross-references). Used for multi-agent memory exploration. Derived from entries; no change to DSM.

These extensions **remain outside the DSM kernel**. They are built and updated by RR using only the public Storage API. The kernel stays a minimal, append-only storage and integrity layer.

---

## 12. Summary

- **DSM shards** = immutable source of truth. They store all entries; they are never modified by RR; they are append-only and hash-chained.

- **RR index** = derived navigation layer. It stores metadata and references to DSM entries; it is stored outside shard directories; it can be deleted and regenerated at any time from shards.

RR uses the index to provide **efficient memory access**: fast session and agent lookup, timeline reconstruction, and query resolution without scanning every shard on every request. When the index is absent or stale, RR falls back to reading directly from DSM via the Storage API, preserving correctness at the cost of performance.
