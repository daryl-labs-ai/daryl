# DSM-RR Integration Specification

This document describes the integration of the **RR index and navigator layer** into the official DSM architecture in the Daryl repository. It is documentation only; no code or kernel changes are required by this spec.

**Validation (verified before writing):**

- ✅ `memory/dsm/rr/relay.py` exists in Daryl.
- ✅ DSM-RR Step 1 exposes `read_recent()` and `summary()`.
- ✅ RR uses only `Storage.read()` (no direct shard file access).
- ✅ No code in `memory/dsm/rr` reads shard files directly (no `read_text`, `rglob`, or raw file open on shards).

---

## 1. Objective

Integrate an optional **index and navigator layer** on top of the existing DSM-RR Step 1 (read relay) so that:

- Agents and tools can **query** shard content by text or metadata without scanning storage manually.
- A **regenerable index** (ShardCatalog, optional stats) supports discovery and caching.
- A **query cache** reduces repeated work.
- **Context packs** (future) can be built from RR results for LLM/agent use.

All of this must be achieved **without modifying the DSM kernel**, using **only the Storage API**, and remaining **compatible with classic and block shards**.

---

## 2. Current State

**Location:** `memory/dsm/rr/`

**Implemented (Step 1):**

- **DSMReadRelay** in `relay.py`: read-only relay over DSM Storage.
- **read_recent(shard_id, limit=100):** returns the most recent entries from a shard. Uses `Storage.read()` only. Expands block-format entries in memory for block shards.
- **summary(shard_id, limit=500):** lightweight activity summary: `entry_count`, `unique_sessions`, `errors`, `top_actions` (from `metadata["action_name"]` via `Counter`).

**Data path:** All shard data is obtained via `Storage.read()`. Block shards are supported by expanding `{"block": true, "entries": [...]}` in memory after read.

**No index, no navigator, no query cache** exist in Daryl today. The laboratory at `/home/buraluxtr/clawd` contains a reference implementation in `dsm_modules/dsm_rr/` (indexer, navigator, cache_store) that currently uses **file-based** reads; the integration spec requires any future index/navigator in Daryl to use **only** the Storage API.

---

## 3. Target Architecture

Target layout for DSM-RR after optional integration of index and navigator:

```
memory/dsm/rr/
├── __init__.py          # Exports DSMReadRelay (+ optional Index, Navigator if added)
├── relay.py             # DSMReadRelay, read_recent(), summary() — unchanged
├── (optional) indexer.py    # Build ShardCatalog from Storage API (list_shards, read metadata)
├── (optional) navigator.py  # Query over entries from Storage.read() per shard
├── (optional) cache_store.py # Query cache, catalog persistence in data/index/
├── (optional) schemas.py    # ShardCatalog, PointerRef, QueryCacheEntry, etc.
└── (optional) cli_rr.py    # CLI: index build, query, cache cleanup
```

**Layering:**

1. **Relay (current):** Uses only `Storage.read()`. No filesystem access to shards.
2. **Index (optional):** Builds catalog from Storage/list_shards and optional metadata from reads. Writes only to `data/index/`.
3. **Navigator (optional):** Runs queries over entries obtained via Relay or Storage.read(); no direct file I/O.
4. **Cache (optional):** Stores query results and catalog in `data/index/`; regenerable.

**Kernel:** Unchanged. No new dependencies from core; RR continues to depend only on `Storage` and `Entry` (and segment manager only if needed via public API).

---

## 4. Public RR API

**Current (Step 1) — stable:**

- **DSMReadRelay**(data_dir=None, storage=None)
- **read_recent**(shard_id, limit=100) → List[Entry]
- **summary**(shard_id, limit=500) → Dict (entry_count, unique_sessions, errors, top_actions)
- **storage** (property, read-only) → Storage

**Future (optional index/navigator):**

- **Indexer:** build_catalog() → ShardCatalog; write_catalog(catalog); catalog built from Storage.list_shards() and metadata from Storage.read() where needed.
- **Navigator:** query(terms, top_n, shard_ids=None) → List[Pointer]; implementation must obtain entries via Storage.read() (or Relay.read_recent) per shard, then score/filter in memory.
- **Cache:** get_cached(query_key); set_cached(query_key, result, ttl); cleanup(max_age). Backed by files under `data/index/` only.

All new APIs must be **read-only** toward shards and security/baseline; writes only to `data/index/` (or configurable index directory).

---

## 5. Storage API Rule

**Rule:** DSM-RR must use **only** the following to read shard data:

- **Storage.read(shard_id, limit)** — primary API for recent entries.
- **Segment manager iteration** (if exposed by Storage or public API) — e.g. `iter_shard_events(shard_id)` for full scan when building index or running queries.

**Forbidden:**

- No `Path.read_text()` on shard files.
- No `rglob("*.jsonl")` or direct `open()` on files under `data/shards/` (or equivalent).
- No parsing of segment file paths or filesystem layout.

**Rationale:** Keeps RR compatible with segment layout, block shards, and future storage changes. Single source of truth remains the kernel; RR is a consumer of the public API.

---

## 6. Index Layer

**Purpose:** Optional catalog of shards (identifiers, optional metadata such as entry count or last updated) to support discovery and navigator queries without assuming filesystem layout.

**Source of information:**

- **list_shards()** from Storage (or equivalent public API) to get shard identifiers.
- Optional: bounded **Storage.read(shard_id, limit)** or iteration to compute counts/samples for metadata. No direct file access.

**Output:** ShardCatalog (e.g. shard_id, metadata dict, generated_at). Stored under `data/index/` (e.g. `shard_catalog.json`).

**Properties:**

- Index is **regenerable**: if `data/index/` is removed, RR continues to work (read_recent, summary); index can be rebuilt from Storage API.
- Index is **cache-only**: never used as source of truth for shard content.
- **authoritative** flag (if present) must remain **false** so that RR never claims to replace kernel data.

---

## 7. Navigator

**Purpose:** Answer queries (e.g. text terms) with ranked pointers (shard, ref, evidence) so that agents can find relevant entries without ad-hoc scripts.

**Implementation constraint:** Navigator must obtain entries **only** via:

- Storage.read(shard_id, limit), or
- Relay.read_recent(shard_id, limit), or
- Public iteration over shard events (e.g. iter_shard_events) if available.

Query logic: for each shard (from list_shards or catalog), read entries (via Storage/Relay), score lines/entries in memory, return top N pointers. No direct file I/O.

**Output:** List of pointers (shard_id, ref, score, evidence snippet). May be written to query cache (see below).

**Scoring:** Simple term match, TF-IDF, or similar — all over in-memory content. No kernel change.

---

## 8. Query Cache

**Purpose:** Avoid repeating the same query; store result (e.g. list of pointers) with a key (e.g. hash of query + params) and TTL.

**Storage:** Append-only or overwrite file(s) under `data/index/` only (e.g. `query_cache.jsonl` or a small DB). Never under `data/shards/` or `data/security/`.

**Properties:**

- Cache is **regenerable**: safe to delete; RR and navigator still work.
- Optional **cleanup(max_age)** to remove stale entries.
- Query cache must not be used to **serve** content; it stores pointers/results that refer back to kernel shards. Content is always read via Storage when needed.

---

## 9. Context Packs

**Purpose (future):** Produce a “context pack” for agents: concatenated, deduplicated content plus pointers into DSM, **without** LLM summarization in v0.

**Design:**

- Input: shard_id(s), optional filters (e.g. session_id, time range).
- Data: obtained via **Storage.read()** or Relay.read_recent/summary.
- Output: structured pack (e.g. list of entries or snippets + refs). No writes to shards; optional write to `data/index/` for cache.

**Rules:** No LLM calls in v0; no modification of kernel state; source of truth remains Storage.

---

## 10. Compatibility

**Classic shards:** One entry per line (JSONL). Storage.read() returns list of Entry. RR and any index/navigator use this as-is.

**Block shards:** One entry per line where content may be `{"block": true, "entries": [...]}`. RR already expands these in memory (relay.py). Index and navigator must operate on entries **after** expansion (or use Relay/Storage that returns expanded entries). No direct parsing of block format from disk.

**Segment layout:** Daryl uses segment families (e.g. `shards/sessions/sessions_0001.jsonl`). RR does not depend on path structure; it uses Storage and segment manager API only.

**Kernel:** No changes to core (storage, models, signing, shard_segments, replay, security). RR remains a layer above the kernel.

---

## 11. CLI Integration

**Current:** No RR-specific CLI in Daryl (tests use Python API).

**Optional (future):**

- **index build** — build ShardCatalog from Storage API, write to `data/index/`.
- **query** — run navigator query, print pointers; optional `--show` for evidence.
- **cache cleanup** — remove cache entries older than max_age.

CLI must use only public RR and Storage APIs; no direct file access to shards. CLI may live in `memory/dsm/rr/cli_rr.py` or be subcommands of a main DSM CLI.

---

## 12. Tests

**Existing:** `tests/dsm_rr_test.py` — tests DSMReadRelay, read_recent (empty and classic shard), summary, example usage.

**Requirements for any new code:**

- Tests must not modify `memory/dsm/core`.
- Tests may use temporary directories and Storage; no reliance on lab paths.
- Any index/navigator tests must mock or use Storage only (no raw shard files).

---

## 13. Migration Steps

When implementing the optional index and navigator (not required by this spec):

1. **Add indexer** that builds ShardCatalog from Storage.list_shards() and, if needed, Storage.read() for metadata. Write catalog to `data/index/`. No filesystem walk.
2. **Add navigator** that, for each shard from catalog or list_shards(), calls Storage.read() (or Relay.read_recent), scores in memory, returns pointers.
3. **Add cache_store** for query cache and catalog persistence under `data/index/` only.
4. **Add CLI** (optional) for index build, query, cache cleanup.
5. **Keep relay.py unchanged** — read_recent and summary remain the stable Step 1 API.

No migration of lab code “as-is”: lab’s dsm_rr uses file-based reads; Daryl implementation must use Storage API only.

---

## 14. Safety Rules

- **Do not modify** `memory/dsm/core`.
- **Do not write** to `data/shards/`, `data/security/`, baseline or policy files. RR may write only to `data/index/` (or configured index dir).
- **Do not read** shard data except via Storage.read() or public segment iteration. No direct file access to shards.
- **Append-only:** RR does not change append-only semantics; it only reads. Index/cache are separate, regenerable artifacts.
- **Block shards:** Must be supported via existing expansion in relay (or equivalent) and Storage API; no special-case file parsing in new code.

---

## 15. Final RR Layer

**Final shape of DSM-RR in Daryl:**

- **Step 1 (current):** DSMReadRelay with read_recent() and summary(), using only Storage.read(), compatible with classic and block shards. No direct shard file access.
- **Optional extension:** Index (ShardCatalog from Storage API), Navigator (query over Storage.read() results), Query cache (under data/index/), and optional CLI — all under the same Storage API rule and safety rules above.

**Kernel:** Unchanged. **Storage API:** Sole data path for shard content. **Block shards:** Supported. **Append-only:** Preserved.

---

*This specification is documentation only. It does not require any code or kernel changes by itself. See [DSM_FUTURE_ARCHITECTURE.md](DSM_FUTURE_ARCHITECTURE.md), [LAB_TO_DARYL_MIGRATION_PLAN.md](LAB_TO_DARYL_MIGRATION_PLAN.md), and [HEARTBEAT.md](../HEARTBEAT.md) for context.*
