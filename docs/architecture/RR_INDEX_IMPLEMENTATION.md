# RR Index — Implementation

This document describes how the **RR Index Builder** works: how it scans DSM shards, what index structures it builds, where indexes are stored, and how rebuild works.

**Reference:** RR_ARCHITECTURE.md, RR_IMPLEMENTATION_PLAN.md, RR_INDEX_SPEC.md.

---

## 1. Location and API contract

- **Module:** `memory/dsm/rr/index/rr_index_builder.py`
- **Class:** `RRIndexBuilder`

RR does **not** modify the DSM kernel. It uses only the public Storage API:

- `Storage.list_shards()`
- `Storage.read(shard_id, limit)`
- `Storage.get_shard_size(shard_id)` (available for future use)

No direct access to shard files or segment paths. All data is obtained through these methods.

---

## 2. How the index builder works

### Steps (in order)

1. **List shards** — Call `Storage.list_shards()` to get all shard identifiers and metadata.
2. **Read entries per shard** — For each shard, read in batches. When `Storage.read(shard_id, offset=..., limit=...)` is supported, paginate with `batch_size` (e.g. 5000) until no entries are returned. When `offset` is not supported, a single `read(shard_id, limit=read_limit_fallback)` is used so indexes remain bounded.
3. **Extract metadata** — From each `Entry` returned by `read()`, extract (with safe defaults for missing fields):
   - `session_id` (from `entry.session_id`)
   - `timestamp` (from `entry.timestamp`, serialized as ISO string)
   - `agent` (from `entry.source`)
   - `event_type` (from `entry.metadata.get("event_type")`)
   - `shard_id` (the shard being scanned)
   - `entry_id` (from `entry.id`)
   - `offset` (ordinal position in the read batch for this shard)
4. **Build index structures in memory** — Four Python dicts/lists:
   - **session_index** — `session_id → list of index records`
   - **agent_index** — `agent → list of index records`
   - **timeline_index** — list of all index records, sorted by `timestamp`
   - **shard_index** — `shard_id → list of index records`
5. **Persist to disk** — Write these structures to JSON files under the index directory (see below).

An **index record** is a small dictionary (no entry content). It is a reference to a DSM entry, not the full payload. Content stays in DSM and is read via `Storage.read()` when needed.

---

## 3. How shards are scanned

- The builder calls `list_shards()` once to get the set of shards.
- For each shard, it uses **paginated reading** when the Storage API supports it:
  - `offset = 0`, `batch_size = 5000` (configurable).
  - Loop: `entries = Storage.read(shard_id, offset=offset, limit=batch_size)`; if no entries, break; process entries; `offset += len(entries)`.
  - This guarantees full shard scanning when `offset` is supported.
- If `Storage.read()` does not accept an `offset` parameter (current kernel API), the builder falls back to a single `read(shard_id, limit=read_limit_fallback)` per shard, so at most `read_limit_fallback` entries (default 50,000) are indexed per shard. No kernel change is required; when the kernel adds offset support, the same builder code will use full pagination.
- No direct filesystem access: the builder does not open JSONL segment files or walk shard directories. All data comes from `Storage.read()`.

---

## 4. Index storage

### Location

Index files are stored **outside** DSM shard storage, under:

```
data/index/
```

(or another path passed as `index_dir` to `RRIndexBuilder`). This directory is **not** under `data/shards/` or any DSM integrity path. RR never writes into shard directories.

### Files

| File          | Content                                                                 |
|---------------|-------------------------------------------------------------------------|
| `sessions.idx` | JSON object: `session_id → list of index records` for that session.   |
| `agents.idx`   | JSON object: `agent → list of index records` for that agent.           |
| `timeline.idx` | JSON array: all index records sorted by `timestamp`.                   |
| `shards.idx`   | JSON object: `shard_id → list of index records` for that shard.       |

Format is JSON (human-readable). Each index record contains at least: `session_id`, `timestamp`, `agent`, `event_type`, `shard_id`, `entry_id`, `offset`.

### No modification of DSM

DSM shards and integrity data are **never** modified by the index builder. Only the `data/index/` directory (or the configured index root) is written. The kernel remains the single writer to shard storage.

---

## 5. How rebuild works

Indexes are **derived data**. They can be recreated at any time from DSM.

### When index files are missing

- **load()** — Reads `sessions.idx`, `agents.idx`, `timeline.idx`, `shards.idx` from the index directory. If any of these files is missing, `load()` returns `False` and does not change the in-memory state.
- **ensure_index()** — Calls `load()`. If loading fails (e.g. files absent), it calls **build()** to rescan shards and write new index files.

### Rebuild process

1. Clear existing in-memory indexes (`session_index.clear()`, `agent_index.clear()`, `timeline_index.clear()`, `shard_index.clear()`).
2. Call `Storage.list_shards()`.
3. For each shard, read in batches (paginated when offset is supported, or single read with fallback limit).
4. Extract metadata from each entry (skip only if timestamp is missing); build the four index structures.
5. Sort `timeline_index` explicitly by `timestamp` for deterministic ordering.
6. Create the index directory if missing, then write index files atomically (temp file + rename).

No kernel state is altered. If the index directory is deleted or corrupted, running `build()` (or `ensure_index()`) again restores indexes from the current shard contents. DSM remains the source of truth.

---

## 6. Usage summary

| Method            | Purpose                                                                 |
|-------------------|-------------------------------------------------------------------------|
| **build()**       | Scan all shards via Storage API, build indexes in memory, write to index_dir. |
| **load()**        | Load indexes from disk if all four files exist; return True/False.      |
| **ensure_index()**| Load from disk; if not possible, rebuild from shards.                   |

Example:

```python
from dsm_v2.core.storage import Storage
from dsm_v2.rr.index import RRIndexBuilder

storage = Storage(data_dir="/path/to/data")
builder = RRIndexBuilder(storage=storage, index_dir="/path/to/data/index")
builder.ensure_index()  # load if present, else rebuild

# Use in-memory indexes
for session_id, records in builder.session_index.items():
    ...
```

---

## 7. Robustness improvements

The implementation includes the following safeguards.

### Pagination

- **Goal:** Avoid incomplete indexes for large shards when the Storage API supports offset-based reading.
- **Behaviour:** The builder uses a loop: `offset = 0`; while True: `entries = read(shard_id, offset=offset, limit=batch_size)`; if not entries, break; process; `offset += len(entries)`.
- **Fallback:** If `Storage.read()` does not accept `offset` (current kernel), a single `read(shard_id, limit=read_limit_fallback)` is used so behaviour remains bounded without kernel changes. When the kernel gains `offset`, the same code path performs full shard scanning.

### Timeline ordering

- After building `timeline_index`, it is explicitly sorted: `timeline_index.sort(key=lambda x: x["timestamp"])`.
- Ensures deterministic ordering regardless of shard or batch order. All index consumers see a stable timeline.

### Safe metadata extraction

- Entries may have missing or null fields. Extraction uses safe access: `getattr(entry, "field", None)` and defaults (`""`, `"unknown"`, etc.).
- **session_id**, **agent** (source), **event_type**: missing values are stored as `""` or `"unknown"`; the entry is still indexed.
- **timestamp**: if missing, the entry is **skipped** (no index record). This avoids invalid or non-sortable timeline entries.
- No exception is raised on malformed or partial entries; only entries without a timestamp are omitted.

### Index rebuild safety

- At the start of `build()`, existing in-memory indexes are **cleared** (`session_index.clear()`, `agent_index.clear()`, `timeline_index.clear()`, `shard_index.clear()`).
- Prevents duplicate or stale entries when rebuilding. Each build starts from a clean state.

### Index directory creation

- Before writing any file, the index directory (e.g. `data/index/`) is created with `Path.mkdir(parents=True, exist_ok=True)`.
- Ensures the directory exists so writes do not fail due to a missing path.

### Atomic index writes

- Index files are written **atomically** to avoid corruption on crash or interrupt:
  1. Write content to a temporary file in the same directory (e.g. `.sessions.idx.xxxx.tmp`).
  2. Close the file, then `os.replace(temp_path, final_path)` to replace the final file in one step.
- Readers either see the previous complete file or the new one; never a half-written file.

---

## 8. Design choices

- **Bounded scan / pagination:** When the Storage API supports offset, the builder uses paginated reads (batch_size) for full shard scanning. When it does not, a single read with a configurable fallback limit keeps the implementation safe and avoids unbounded I/O.
- **JSON storage:** Simple and debuggable; can be replaced later by a more compact or incremental format without changing the builder’s contract (build/load/ensure_index).
- **No kernel changes:** All logic lives under `memory/dsm/rr/`. The DSM core is not modified; RR remains a read-only layer over the Storage API.
