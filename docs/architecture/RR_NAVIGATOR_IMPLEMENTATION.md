# RR Navigator — Implementation

This document describes how the **RR Navigator** works: how navigation uses the RR Index, how lookups are performed, and how full entries are resolved via the Storage API.

**Reference:** RR_ARCHITECTURE.md, RR_IMPLEMENTATION_PLAN.md, RR_INDEX_IMPLEMENTATION.md.

---

## 1. Role of the Navigator

The **RRNavigator** provides memory navigation on top of the RR Index. It:

- Returns **metadata records** (session_id, timestamp, agent, event_type, shard_id, entry_id, offset) from index lookups.
- Does **not** scan shards directly; it uses only the indexes produced by **RRIndexBuilder**.
- Resolves to full **Entry** content only when requested, via **Storage.read()**.

Navigation is therefore fast (index-only) and read-only toward DSM.

---

## 2. Location and dependencies

- **Module:** `memory/dsm/rr/navigator/rr_navigator.py`
- **Class:** `RRNavigator`

**Dependencies:**

- **RRIndexBuilder** — provides `session_index`, `agent_index`, `timeline_index`, `shard_index`. The navigator does not build indexes; it uses an already-built builder (call `index_builder.ensure_index()` or `build()` before use).
- **Storage** — used only for **resolve_entries()** when full Entry content is needed. The navigator never writes to Storage.

No dependency on `memory/dsm/core` beyond the public Storage API (read only).

---

## 3. How navigation works

Navigation is **index-only**. Each method reads from one of the four in-memory index structures on the index builder:

| Method | Index used | Behaviour |
|--------|------------|-----------|
| **navigate_session(session_id)** | `session_index` | Returns all metadata records whose `session_id` matches. Order is that of the index (session-scoped). |
| **navigate_agent(agent)** | `agent_index` | Returns all metadata records whose `agent` (source) matches. |
| **timeline(start_time, end_time)** | `timeline_index` | Returns metadata records in timeline order, optionally filtered by `start_time` and/or `end_time` (inclusive). Accepts `datetime` or Unix timestamp (float/int); normalized internally. |
| **navigate_shard(shard_id)** | `shard_index` | Returns all metadata records for the given shard. |

No **Storage.read()** is called in these four methods. They only perform dict/list lookups and, for `timeline()`, a filtered pass over the sorted list. The navigator does not open shard files or touch DSM storage for navigation itself.

---

## 4. How index lookups work

- **session_index** and **agent_index** are dictionaries: `session_id → list of records`, `agent → list of records`. Lookup is a single dict get and a copy of the list.
- **shard_index** is a dictionary: `shard_id → list of records`. Same pattern.
- **timeline_index** is a list of records already sorted by `timestamp` (numeric). **timeline(start_time, end_time)** walks this list and keeps records where `start_ts ≤ record["timestamp"] ≤ end_ts` (if bounds are given). Time bounds are converted to Unix timestamp via a small helper so both `datetime` and numeric values are supported.

Index records are plain dicts with at least: `session_id`, `timestamp`, `agent`, `event_type`, `shard_id`, `entry_id`, `offset`. The navigator returns these as-is; it does not modify them.

---

## 5. How entries are resolved

When the caller needs full **Entry** content (e.g. for context building or display), it uses:

**resolve_entries(records, limit=None)**

- **Input:** A list of metadata records (e.g. from `navigate_session`, `timeline`, etc.).
- **Behaviour:**
  1. **Group records by shard_id** into `records_by_shard` so each shard is read at most once per resolution pass.
  2. For each shard, build a **set of requested entry_ids** for O(1) lookup.
  3. **Paginated read:** call **Storage.read(shard_id, offset=offset, limit=batch_size)** in a loop; when offset is not supported by the API, fall back to a single read with a bounded limit. Stop when all requested ids for that shard are resolved or no more entries are returned.
  4. For each batch, match entries by **entry_id in requested set** (O(1) per entry); append to result and track seen ids. **Stop as soon as limit** (if set) is reached.
  5. If an **entry_id** cannot be found in the shard, skip it and log at debug level; no exception is raised.
- **Output:** List of **Entry** objects. Optional `limit` caps the number returned; resolution stops once that count is reached.

---

## 6. Usage example

```python
from dsm_v2.core.storage import Storage
from dsm_v2.rr.index import RRIndexBuilder
from dsm_v2.rr.navigator import RRNavigator

storage = Storage(data_dir="/path/to/data")
builder = RRIndexBuilder(storage=storage, index_dir="/path/to/data/index")
builder.ensure_index()

navigator = RRNavigator(index_builder=builder, storage=storage)

# Metadata only (no Storage.read)
session_records = navigator.navigate_session("session_abc")
agent_records = navigator.navigate_agent("clawdbot")
shard_records = navigator.navigate_shard("sessions")
recent = navigator.timeline(end_time=datetime.utcnow())

# Full entries when needed
entries = navigator.resolve_entries(session_records, limit=50)
```

---

## 7. Navigator robustness improvements

The implementation keeps the navigator index-driven, read-only, and kernel-independent while improving resilience and performance.

### Pagination in resolution

- **resolve_entries()** no longer relies on a single **Storage.read(shard_id, limit)** per shard, which can miss entries in large shards.
- For each shard, entries are read in a loop: `offset = 0`; while True: `batch = read(shard_id, offset=offset, limit=batch_size)`; process batch; `offset += len(batch)`; stop when no batch or all requested ids for that shard are found.
- When **Storage.read()** does not accept `offset` (current kernel), a single read with a fallback limit is used so behaviour remains bounded. When the kernel supports offset, the same code path performs full shard scanning until requested ids are resolved.

### Set-based lookup

- For each shard, **requested_ids = set(record["entry_id"] for record in recs if record.get("entry_id"))**.
- Matching is done with **entry.id in requested_ids** (and **in still_needed**) so lookup is O(1) per entry instead of O(n) list search. This avoids O(n²) behaviour when resolving many records over large shards.

### Shard grouping

- Before any **Storage.read()**, records are grouped by **shard_id**: `records_by_shard = { shard_id: [records...] }`.
- Resolution then runs **shard-by-shard**, so each shard is read only once (or once per batch in the pagination loop). This avoids repeated reads for the same shard and keeps I/O predictable.

### Limit safety

- When **resolve_entries(records, limit=N)** is called, the navigator stops as soon as **N** entries have been collected.
- The limit is checked after each entry append and causes an immediate return. No further shards are scanned once the limit is reached, avoiding unnecessary work.

### Missing entry handling

- If a record references an **entry_id** that is never found in the shard (e.g. index/storage inconsistency or entry evicted from the read window), the navigator **does not crash**.
- Such entries are skipped. A **debug** log line is emitted (e.g. "RR Navigator: entry_id X not found in shard Y") so operators can detect inconsistencies without affecting callers.

### Timestamp normalization in timeline()

- **timeline(start_time, end_time)** accepts both **datetime** and **int/float** Unix timestamps.
- A helper **\_to_timestamp()** normalizes all inputs to a numeric (float) timestamp before filtering. Record timestamps in the index are already numeric; any string or other type in a record is coerced to float for comparison so the filter is consistent and type-safe.

---

## 8. Summary

- **Navigation** = index lookups only (session, agent, timeline, shard). No direct shard access.
- **Index lookups** = dict/list access on the builder’s in-memory indexes; timeline supports optional time-range filter with normalized timestamps (datetime or int/float).
- **Entry resolution** = optional step using **Storage.read()** with pagination, set-based matching, and shard grouping; limit is enforced; missing entries are skipped with debug logging. RR remains read-only and does not modify DSM shards.
