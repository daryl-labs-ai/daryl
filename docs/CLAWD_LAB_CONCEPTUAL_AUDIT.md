# Conceptual Architecture Scan — Clawdbot Laboratory

**Directory analyzed:** `/home/buraluxtr/clawd`  
**Type:** Conceptual audit only. No files were modified in the laboratory.

---

## 1. Core architecture concepts detected

| Concept | Location | Role |
|--------|----------|------|
| **DSM** | `dsm_v2/`, `dsm_logger.py`, `dsm_bot.py`, `dsm_analytics.py`, `KERNEL_FREEZE.md`, `DSM_KERNEL_FREEZE_REPORT.md`, `dsm-benchmark/` | Kernel (storage, models, segments, security, signing), middleware logging, bot entry point, analytics script, benchmark scenarios. |
| **DSM-RR (Read Relay)** | `dsm_modules/dsm_rr/` (indexer, navigator, cache_store, cli, schemas), `DSM_RR_V0_REPORT.md`, `dsm_modules/dsm_rr/README.md` | Index-first, read-only, cache-only navigation: ShardCatalog, query → pointers, cache in `data/index/`. **Reads shard files directly** (rglob `*.jsonl`, `read_text`), not via `Storage.read()`. |
| **DSM-RM (Recycling Memory)** | `dsm_v2/modules/dsm_rm.py` (`DSMRecyclingMemory`), `recycling_test.py` | Session compaction, duplicate detection, archiving. Referred to in one place as "DSM-RR" (see naming inconsistencies). |
| **SessionGraph** | `dsm_v2/session/session_graph.py`, `trace_replay.py`, `moltbook_observation_runner.py`, `KERNEL_FREEZE.md` | Session lifecycle orchestration; coordinates start/end/snapshot; used by replay and Moltbook runner. |
| **Storage** | `dsm_v2/core/storage.py`, `dsm_logger.py`, `dsm_analytics.py` | Append-only JSONL storage; used by logger and analytics for read/write. |
| **Replay** | `dsm_v2/core/replay.py`, `dsm_v2/trace_replay.py` | Trace replay and integrity verification. |
| **Index** | `dsm_modules/dsm_rr/indexer.py`, `cache_store.py`, `data/index/` (shard_catalog.json, query_cache.jsonl, heads_manifest.json) | DSM-RR index: catalog of shards, query cache, heads manifest. |
| **Context Pack** | `dsm_modules/dsm_rr/README.md` (roadmap: "Summarizer → Context Pack", "Context Packs (No LLM)"), `recycling_test.py` (text: "Context Packs (DSM-RR)") | Planned RR feature (concat + dedupe + pointers); mentioned in recycling context. |
| **Memory Sharding** | `memory_sharding_with_cache.py`, `memory/shards/`, `MEMORY_INDEX.json`, `src/memory_sharding_system.py`, `memory_sharding_system.py` | Separate system: "DARYL Sharding Memory v2 avec Cache", SQLite + RAM cache, own shard config (projects, insights, people, technical, strategy). Not the DSM kernel. |
| **Agent Skills** | `dsm_v2/skills/` (ingestor, registry, router, evaluator, cli), `dsm_v2/ans/` (DSM-ANS) | Skill loading, routing, usage/success logs; ANS analyzes skill performance. |
| **Block Layer** | Not found as a named concept in clawd. `reconstruct_by_blocks.py` is a **code refactoring script** (splits `dsm_ingest_central.py` into blocks), not the DSM block aggregation layer. |
| **Navigation Layer** | Implemented as **DSM-RR** in `dsm_modules/dsm_rr` (Navigator, query → pointers). |

---

## 2. Duplicate concept clusters

### Concept: Shard / memory read + analytics

| Files implementing it | Notes |
|------------------------|--------|
| `dsm_analytics.py` | Reads `clawdbot_sessions` via `Storage.read()`, Counter on `action_name`, session/error counts. |
| `dsm_modules/dsm_rr` | Navigator + indexer: reads shards via **file paths** (rglob, `read_text`), builds catalog and query cache, scores lines. |
| Daryl `memory/dsm/rr` (Step 1) | `read_recent()`, `summary()` using **only** `Storage.read()`. |

**Potential duplicates:** Two different “read/navigate shards” approaches: (1) clawd DSM-RR = index + file-based search; (2) Daryl RR Step 1 = Storage.read() + in-memory summary. Plus standalone `dsm_analytics.py` overlapping with “summary” (actions, sessions, errors).

### Concept: Ingestion pipeline

| Files implementing it | Notes |
|------------------------|--------|
| `dsm_ingest.py` | Base ingester. |
| `dsm_ingest_central.py` | Central ingest (MARKER_MAP, refs, shard config). |
| `dsm_ingest_central_clean.py` | Variant (larger). |
| `dsm_ingest_central_simple.py` | Simpler variant. |
| `dsm_ingest_optimized.py` | Optimized variant. |
| `dsm_bot.py` (DSMIngester) | Uses `dsm_ingest_central` for telegram_save. |
| `add_debug_ingest.py`, `add_load_all_shards.py`, `fix_load_all_shards.py`, etc. | Many fix/add scripts around ingest. |

**Potential duplicates:** Several ingestion entry points and variants (central, central_clean, central_simple, optimized) plus numerous one-off fix/restore scripts.

### Concept: Index / catalog over shards

| Files implementing it | Notes |
|------------------------|--------|
| `dsm_modules/dsm_rr/indexer.py` | Builds ShardCatalog from `data/shards/**/*.jsonl`. |
| `dsm_modules/dsm_rr/cache_store.py` | Writes/reads catalog and query_cache. |
| `memory_sharding_with_cache.py` | QueryCache (SQLite), different shard layout (`memory/shards/`, domains). |

**Potential duplicates:** Two indexing ideas: (1) DSM-RR index (catalog + query cache for kernel shards); (2) memory_sharding cache (SQLite for a different “memory” sharding system).

### Concept: “RR” vs “Recycling”

| Files | Issue |
|-------|--------|
| `dsm_v2/recycling_test.py` | Docstring: "Test du module **DSM-RR** (DSM **Recycling** Memory)". Final print: "DSM-RR - Recycling Memory (SESSION READY)". |
| `dsm_v2/modules/dsm_rm.py` | Correctly named **DSM-RM** (Recycling Memory). |

**Potential duplicate:** RR (Read Relay) and RM (Recycling Memory) are distinct; recycling_test conflates them by labeling recycling as "DSM-RR".

---

## 3. Naming inconsistencies

| Concept | Names used | Where |
|--------|------------|--------|
| Read Relay | **DSM-RR**, **Read Relay**, **Navigation** (layer), **Navigator** (class) | dsm_rr README: "DSM Read Relay", "navigation layer", "Navigator Query". |
| Recycling | **DSM-RM**, **Recycling Memory**, **DSM-RR** (incorrect) | dsm_rm.py: DSM-RM; recycling_test.py: "DSM-RR (DSM Recycling Memory)". |
| Session orchestration | **SessionGraph** (orchestrator) vs **SessionTracker** (core/session.py heartbeat) | KERNEL_FREEZE: "SessionGraph is Orchestrator". Daryl ARCHITECTURE: SessionTracker = heartbeat; SessionGraph = event logging. |
| Sharding | **Memory Sharding**, **Sharding Memory**, **shards** (kernel) | memory_sharding_with_cache.py: "DARYL Sharding Memory v2"; kernel: "shards" (segment files). |
| Context pack | **Context Pack**, **Context Packs** | dsm_rr README: "Context Pack"; roadmap: "Context Packs (No LLM)". |

---

## 4. Experiments vs official architecture (HEARTBEAT.md)

- **HEARTBEAT.md (Daryl)** defines DSM-RR as **planned**, with a **minimal Step 1** in `memory/dsm/rr` (`read_recent`, `summary`), using only `Storage.read()`.

- **Clawd laboratory** contains a **different, fuller DSM-RR** in `dsm_modules/dsm_rr`:
  - Index-first (ShardCatalog, index build/rebuild).
  - Navigator (query → pointers), cache (query_cache.jsonl).
  - **Reads shard files directly** (rglob `*.jsonl`, `read_text`), not via `Storage.read()`.
  - Roadmap: Context Packs, Drift Scout, etc.

So:

| Aspect | HEARTBEAT / Daryl Step 1 | Clawd dsm_modules/dsm_rr |
|--------|---------------------------|---------------------------|
| Status | Step 1 of planned RR | Implemented v0 (index + navigator + cache) |
| Read path | Storage.read() only | Direct file read (rglob, read_text) |
| Scope | read_recent, summary | Index build, query, cache, catalog |
| Alignment | Aligned with “no kernel change, Storage only” | Implements a richer RR but bypasses Storage API |

Conclusion: The lab’s DSM-RR is an **experimental, pre-architecture** implementation (index-first, file-based). The **official** “Step 1” is in Daryl’s `memory/dsm/rr` (Storage.read() only). They are two different designs; aligning them would require either (a) making clawd’s RR use `Storage.read()` and optional index on top, or (b) explicitly documenting clawd’s RR as an alternate/legacy experiment.

---

## 5. Conceptual map (high level)

```
DSM Core (frozen in clawd: dsm_v2/core/)
├── Storage, Entry, ShardSegmentManager, Signing, Security, Replay, Tracing
├── SessionGraph (dsm_v2/session/) — orchestrator
└── SessionTracker (core/session.py) — heartbeat (if present)

DSM-RR (Read Relay)
├── Clawd lab: dsm_modules/dsm_rr — Indexer, Navigator, Cache (file-based read)
└── Daryl official Step 1: memory/dsm/rr — read_recent, summary (Storage.read() only)
    └── Planned: reconstruct_session, query engine, index, context packs

DSM-RM (Recycling Memory)
└── dsm_v2/modules/dsm_rm.py — DSMRecyclingMemory (compaction, archive)
    └── Mislabeled in recycling_test as "DSM-RR"

Memory Sharding (separate from DSM kernel)
└── memory_sharding_with_cache.py, memory/shards/, MEMORY_INDEX.json
    └── Own domains (projects, insights, people, technical, strategy), SQLite cache

Agent Skills / DSM-ANS
├── dsm_v2/skills/ — ingestor, registry, router, evaluator
└── dsm_v2/ans/ — Audience Neural System (skill performance, transitions)

Ingestion (multiple variants)
├── dsm_ingest*.py, dsm_ingest_central*.py, dsm_ingest_optimized.py
└── dsm_bot.py (DSMIngester)

Feed / Moltbook / Telegram
├── dsm_bot.py, dsm_logger.py, dsm_telegram_*, moltbook_*
└── FEED_MONITOR_GUIDE.md, moltbook_observation_runner.py

Analytics (overlap with RR summary)
├── dsm_analytics.py — Storage.read + Counter (action_name, sessions, errors)
└── DSM-RR summary (Daryl) — same idea, in rr layer
```

---

## 6. Obsolete or superseded experiments (classification only)

- **fix_* / patch_* / rewrite_* / restore_* / add_*** scripts (e.g. `fix_load_all_shards.py`, `fix_extract_refs_*.py`, `rewrite_extract_refs*.py`, `restore_dsm_ingest_central.py`, `add_debug_ingest.py`): One-off fixes or variants; likely superseded by a smaller set of canonical scripts. Classify as **maintenance/legacy**; do not delete without product owner decision.

- **Multiple dsm_ingest_central variants** (`_clean`, `_simple`, plus `_optimized`, base `dsm_ingest.py`): **Superseded by** a single maintained ingest path (which one is canonical is unclear from names alone). Classify as **duplicate ingestion pipelines** until one is chosen as reference.

- **reconstruct_by_blocks.py**: Refactors `dsm_ingest_central.py` into code blocks; **not** the DSM block aggregation layer. Classify as **code refactor script**, not architecture.

- **dsm_lite*.py, dsm_lite_fixed.py, dsm_lite_v2.2.py**: Likely earlier or simplified DSM clients. Classify as **superseded by** dsm_bot + dsm_logger + dsm_v2 unless still in use.

- **dsm_cli_v2, dsm_cli_v3, dsm_cli_hardening*, dsm_hardening***: Multiple CLI/hardening versions. Classify as **evolution stack**; current entry point should be documented.

- **recycling_test.py** importing `dsm_recycling_memory` / `DSMRecyclingMemory`: In Daryl the class lives in `dsm_v2/modules/dsm_rm.py`; clawd may have a different path or copy. Classify as **test with naming confusion (RR vs RM)** and possible broken import.

---

## 7. Potential conceptual cleanup recommendations

1. **Terminology**
   - Reserve **DSM-RR** for Read Relay (read/navigate shards). Use **DSM-RM** only for Recycling Memory in docs and comments (e.g. fix `recycling_test.py` docstring and final print so they do not say "DSM-RR" for recycling).

2. **Two RR implementations**
   - Document clearly: (a) **Daryl Step 1** = `memory/dsm/rr` (Storage.read(), read_recent, summary); (b) **Clawd lab** = `dsm_modules/dsm_rr` (index, navigator, file-based). Decide whether clawd’s RR should evolve to use only `Storage.read()` for alignment with HEARTBEAT and block shards.

3. **Ingestion**
   - Choose one canonical ingestion entry point (e.g. `dsm_ingest_central.py` or `dsm_ingest_optimized.py`) and document it; treat others as legacy or deprecated to reduce “duplicate pipelines” confusion.

4. **Memory Sharding vs DSM**
   - In docs, distinguish **DSM kernel shards** (append-only, segment manager, `data/shards/`) from **memory_sharding_with_cache** (separate system with its own shard config and SQLite cache) to avoid “two sharding systems” confusion.

5. **Index**
   - Clarify: DSM-RR index (`data/index/`) is for the kernel shards and query cache; memory_sharding cache is for the other system. Optionally use distinct names (e.g. “DSM-RR index” vs “memory sharding cache”) in docs.

6. **Block layer**
   - Do not treat `reconstruct_by_blocks.py` as the DSM block layer. Document the real block layer (e.g. in Daryl `memory/dsm/block_layer`) separately if/when it is used in clawd.

---

*Audit performed without modifying any files in `/home/buraluxtr/clawd`. Classification and recommendations are conceptual only.*
