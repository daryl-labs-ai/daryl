# RR Query Engine — Implementation

This document describes how the **RR Query Engine** works: the query pipeline, filter strategy, resolution logic, and limit handling.

**Reference:** RR_ARCHITECTURE.md, RR_IMPLEMENTATION_PLAN.md, RR_NAVIGATOR_IMPLEMENTATION.md.

---

## 1. Role of the Query Engine

The **RRQueryEngine** provides a high-level query interface on top of the RR Navigator. It:

- Accepts optional criteria: **session_id**, **agent**, **shard_id**, **start_time**, **end_time**.
- Translates these into one or more navigator calls (navigate_session, navigate_agent, navigate_shard, timeline).
- When **multiple** criteria are set, returns only records that match **all** of them (intersection by entry_id).
- Optional **sort** by timestamp (`"asc"` or `"desc"`), and **limit** applied after filtering and sorting.
- Optionally **resolves** metadata records to full **Entry** objects via the navigator. Returns `[]` when no filter is provided.

The engine does not touch the DSM kernel or the index directly; it uses only the **RRNavigator** API. RR remains read-only.

---

## 2. Location and dependencies

- **Module:** `memory/dsm/rr/query/rr_query_engine.py`
- **Class:** `RRQueryEngine`

**Dependencies:**

- **RRNavigator** — all lookups and resolution are delegated to the navigator. The engine does not call Storage or the index builder.

No dependency on `memory/dsm/core`; the engine is a thin layer above the navigator.

---

## 3. Query pipeline

The flow of a single **query(...)** call is:

1. **Empty filter check** — If none of session_id, agent, shard_id, start_time, end_time is set, return `[]` immediately (no full scan).
2. **Gather candidate lists** — For each set filter, call the corresponding navigator method:
   - `session_id` → `navigator.navigate_session(session_id)`
   - `agent` → `navigator.navigate_agent(agent)`
   - `shard_id` → `navigator.navigate_shard(shard_id)`
   - `start_time` or `end_time` → `navigator.timeline(start_time=..., end_time=...)`
3. **Combine results** — If only one filter was set, use that list (records without `entry_id` are dropped). If several were set, apply **intersection by entry_id** (see below).
4. **Optional sort** — If `sort` is `"asc"` or `"desc"`, sort records by timestamp (normalized to float).
5. **Apply limit** — Only after filtering and sorting: `records = records[:limit]` if `limit` is not None.
6. **Optional resolution** — If `resolve=True`, call `navigator.resolve_entries(records, limit=limit)` and return the list of **Entry** objects. Otherwise return the list of metadata records.

No Storage.read() is invoked by the engine itself; resolution (when requested) is done inside the navigator.

---

## 4. Filter strategy

### Single filter

- Only one of session_id, agent, shard_id, or time range is set → the result is exactly the list returned by the corresponding navigator method. No intersection.

### Multiple filters (intersection)

- When two or more criteria are set (e.g. `query(agent="planner", session_id="abc")`), the engine computes the **intersection** of the candidate lists so that only records satisfying **all** criteria are returned.
- **Intersection key:** `entry_id`. Records without `entry_id` are excluded before intersection so they do not affect the result. The engine:
  1. Filters each candidate list to records that have `entry_id`.
  2. Builds a set of `entry_id` per list and computes `set.intersection(*id_sets)` for O(n) behaviour.
  3. Keeps only records (from the first filtered list) whose `entry_id` is in the common set.
- Order of the result follows the order of the **first** candidate list (session, then agent, then shard, then timeline when present). So with multiple filters, order is determined by the first applicable navigator call.

### Time range

- **start_time** and **end_time** are passed through to `navigator.timeline(start_time, end_time)`. They accept `datetime` or numeric Unix timestamps. The engine does not interpret them; the navigator normalizes and filters.

---

## 5. Resolution logic

- **resolve=False (default)** — The engine returns the list of **metadata records** (dicts with session_id, timestamp, agent, event_type, shard_id, entry_id, offset). No call to Storage.
- **resolve=True** — The engine calls `navigator.resolve_entries(records, limit=limit)` and returns the list of **Entry** objects. The navigator uses Storage.read() internally to resolve; the engine does not access Storage.

When `resolve=True`, the same `limit` used for the record list is passed to `resolve_entries`, so the number of entries returned is consistent with the applied limit.

---

## 6. Limit handling

- **Limit is applied only after all filtering and sorting.** The engine first combines results (with intersection if needed), then optionally sorts, then applies `records[:limit]` if `limit` is not None. This avoids applying limit too early and keeps behaviour predictable.
- If **resolve=True**, the limit is also passed to `navigator.resolve_entries(records, limit=limit)` so that resolution stops once enough entries have been collected.

---

## 7. Query engine robustness improvements

The implementation keeps the engine navigator-only and read-only while improving performance and safety.

### Set-based intersection

- Intersection of candidate lists is done via **sets of entry_id** and **set.intersection(*id_sets)** instead of iterating over one list and checking membership in others.
- This reduces complexity from O(n²) to O(n): one pass per list to build id sets, then a single set intersection, then one pass to filter the base list by `common_ids`.

### entry_id safety

- Before intersection, **records without entry_id are filtered out**: each candidate list is reduced to `[r for r in recs if r.get("entry_id")]`.
- This prevents `None` or missing `entry_id` from entering the id sets and keeps the intersection meaningful. Single-filter results are also filtered so only records with `entry_id` are returned.

### Optional sorting

- **query(..., sort="asc" | "desc")** sorts the result by timestamp before applying limit.
- Default (sort=None) keeps the original order (navigator order or first-candidate order after intersection). With `sort="asc"` or `"desc"`, records are sorted by normalized timestamp (ascending or descending).

### Timestamp normalization for sorting

- A helper **\_normalize_timestamp(value)** converts timestamps to a comparable float: **datetime** → `value.timestamp()`, **int/float** → `float(value)`, **None** or invalid → `0.0`.
- This matches the logic used in the navigator’s timeline and ensures consistent ordering regardless of how the timestamp was stored in the index.

### Limit handling

- **Limit is applied only after filtering and sorting.** The pipeline is: combine (and intersect) → optional sort → then `records[:limit]`. This avoids cutting the result before sort and keeps the contract clear: “first N records in the final order.”

### Empty filter safety

- If **query()** is called with **no** filter (all of session_id, agent, shard_id, start_time, end_time are None or not set), the engine returns **[]** immediately.
- This prevents accidentally scanning the full timeline (or all shards) when the caller meant to pass a filter. No navigator call is made when there is no filter.

---

## 8. Usage example

```python
from dsm_v2.core.storage import Storage
from dsm_v2.rr.index import RRIndexBuilder
from dsm_v2.rr.navigator import RRNavigator
from dsm_v2.rr.query import RRQueryEngine

storage = Storage(data_dir="/path/to/data")
builder = RRIndexBuilder(storage=storage, index_dir="/path/to/data/index")
builder.ensure_index()
navigator = RRNavigator(index_builder=builder, storage=storage)
engine = RRQueryEngine(navigator=navigator)

# Metadata only
records = engine.query(session_id="session_abc", limit=50)

# With time range and resolution
entries = engine.query(
    agent="clawdbot",
    start_time=start_ts,
    end_time=end_ts,
    resolve=True,
    limit=100,
)

# Intersection: session AND agent
records = engine.query(session_id="s1", agent="planner")

# With sort and limit
records = engine.query(agent="clawdbot", sort="desc", limit=20)
```

---

## 9. Summary

- **Query pipeline:** empty filter → `[]`; otherwise navigator calls → optional intersection by entry_id → optional sort by timestamp → limit → optional resolution.
- **Filter strategy:** single filter → one list (records without entry_id dropped); multiple filters → set intersection by `entry_id`; time range passed to `timeline()`.
- **Robustness:** set intersection (O(n)), entry_id filtering, optional sort with normalized timestamp, limit after filtering/sorting, no full scan when no filter.
- **Resolution:** when `resolve=True`, the engine delegates to `navigator.resolve_entries()`; otherwise it returns metadata records. RR stays read-only and kernel-independent.
