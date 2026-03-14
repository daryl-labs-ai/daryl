# LAB → DARYL Migration Plan

**Type:** Analysis and planning only. No code or files are modified in either directory.

**Environments:**
- **Daryl (official):** `/opt/daryl` — clean architecture, DSM core, RR, RM, skills, ANS, block_layer, documentation.
- **Clawdbot laboratory:** `/home/buraluxtr/clawd` — research and experimentation workspace.

---

## 1. Laboratory architecture overview

The laboratory contains a copy or symlink of Daryl’s DSM (`dsm_v2/` → kernel, session, skills, ans, modules) plus **lab-specific** code:

| Layer | Location in lab | Purpose |
|-------|-----------------|---------|
| DSM kernel | `dsm_v2/core/`, `dsm_v2/session/` | Same as Daryl (storage, models, segments, security, replay, SessionGraph). |
| DSM-RR (lab) | `dsm_modules/dsm_rr/` | Index-first read relay: indexer, navigator, cache_store, CLI; builds ShardCatalog, query → pointers; **reads shard files directly** (rglob, read_text). |
| DSM-RM | `dsm_v2/modules/dsm_rm.py` | DSMRecyclingMemory (compaction, archive). Same concept as Daryl’s `memory/dsm/modules/dsm_rm.py`. |
| Storage usage | `dsm_logger.py`, `dsm_analytics.py`, `dsm_bot.py` | Middleware logging to clawdbot_sessions; analytics (Storage.read + Counter); bot entry point. |
| Replay | `dsm_v2/core/replay.py`, `dsm_v2/trace_replay.py` | Same as Daryl. |
| Index | `dsm_modules/dsm_rr/indexer.py`, `cache_store.py`, `data/index/` | ShardCatalog, query_cache.jsonl, heads_manifest. |
| Context Pack | `dsm_modules/dsm_rr/README.md` (roadmap) | Planned: “Summarizer → Context Pack”, no LLM. |
| Memory Sharding | `memory_sharding_with_cache.py`, `memory/shards/`, `MEMORY_INDEX.json` | **Separate system**: SQLite + RAM cache, domains (projects, insights, people, technical, strategy). Not DSM kernel. |
| Analytics | `dsm_analytics.py` | Storage.read(clawdbot_sessions) + action/session/error counts. |
| Agent Skills / ANS | `dsm_v2/skills/`, `dsm_v2/ans/`, `dsm_ans_openclaw/` | Same skills/ANS as Daryl; plus optional openclaw variant. |
| Ingestion | `dsm_ingest.py`, `dsm_ingest_central*.py`, `dsm_ingest_optimized.py`, `dsm_bot.py` | Multiple ingestion pipelines; bot uses DSMIngester. |
| Moltbook / Telegram | `dsm_bot.py`, `dsm_telegram_*`, `moltbook_*`, `FEED_MONITOR_GUIDE.md` | Automation, feeds, monitoring. |
| Block layer | — | Not present in lab. `reconstruct_by_blocks.py` is a **code refactor** script, not DSM block layer. |

---

## 2. Candidate modules for migration

For each concept, files, purpose, and maturity are listed. Comparison with Daryl: **A** = already in Daryl, **B** = better implementation in lab, **C** = experimental prototype, **D** = unrelated.

| Concept | File(s) | Purpose | Maturity | vs Daryl |
|---------|---------|---------|----------|----------|
| **DSM-RR (index + navigator)** | `dsm_modules/dsm_rr/` (indexer.py, navigator.py, cache_store.py, schemas.py, cli.py, README.md) | ShardCatalog from shards, query → ranked pointers, cache in `data/index/`. Read-only, cache-only. | v0, used (DSM_RR_V0_REPORT) | **C** — Richer than Daryl RR Step 1 (which has only read_recent, summary). Lab RR uses file-based reads; Daryl uses Storage.read() only. |
| **DSM-RR analytics idea** | `dsm_analytics.py` | Storage.read + Counter(action_name), session/error counts. | Small, stable script | **A** — Daryl `rr.summary()` already provides this. Migrate only if we want a standalone CLI script in Daryl. |
| **DSM-RM** | `dsm_v2/modules/dsm_rm.py`, `recycling_test.py` | DSMRecyclingMemory: compaction, archive. | Module + test | **A** — Same as Daryl `memory/dsm/modules/dsm_rm.py`. No migration of code; lab uses Daryl copy. |
| **Index / catalog** | `dsm_modules/dsm_rr/indexer.py`, `cache_store.py` | Build catalog from shards; query cache. | Part of RR v0 | **C** — Concept could move to Daryl as optional RR layer (after refactor to use Storage API). |
| **Context Pack (roadmap)** | `dsm_modules/dsm_rr/README.md` | Planned: concat + dedupe + pointers, no LLM. | Documented only | **A** — Already in Daryl docs (DSM_FUTURE_ARCHITECTURE, RR future capabilities). No code to migrate. |
| **Ingestion pipeline** | `dsm_ingest_central.py`, `dsm_ingest_optimized.py` | Central ingest with MARKER_MAP, refs, shard config; optimized variant. | Multiple variants | **B/C** — Daryl has skills ingestor (skills only). Lab has generic DSM ingest for telegram/bot. Candidate: one canonical ingest design for Daryl (if we want generic ingest in repo). |
| **SessionGraph / Storage / Replay** | `dsm_v2/session/`, `dsm_v2/core/storage.py`, `dsm_v2/core/replay.py` | Same as Daryl. | Frozen in lab (KERNEL_FREEZE) | **A** — Already in Daryl. No migration. |
| **Memory Sharding (with cache)** | `memory_sharding_with_cache.py`, `memory/shards/`, `MEMORY_INDEX.json`, `src/memory_sharding_system.py` | Separate “DARYL Sharding Memory v2” with SQLite cache and domain shards. | Implemented | **D** — Different architecture (own shards, domains). Not DSM kernel. Do not migrate as-is; could be a separate Daryl “memory_sharding” experiment later. |
| **Skills / ANS** | `dsm_v2/skills/`, `dsm_v2/ans/`, `dsm_ans_openclaw/` | Same skills/ANS as Daryl; openclaw = optional variant. | Same as Daryl | **A** — In Daryl. openclaw: **KEEP IN LAB** as experiment. |
| **Block layer** | — | — | — | **A** — Daryl has `memory/dsm/block_layer`. Lab has no block layer. |
| **dsm_logger** | `dsm_logger.py` | Fail-safe middleware: append to clawdbot_sessions (session_start, tool_call, session_end). | Stable, used by dsm_bot | **B** — Useful pattern. Could be a reference for a future “runtime logger” in Daryl (e.g. under `memory/dsm/runtime/` or docs only). |

---

## 3. Modules to keep in lab

These are useful for experimentation or runtime but are **not** part of the canonical DSM architecture in Daryl. They remain in the laboratory.

| Module / area | Location | Reason |
|---------------|----------|--------|
| **Moltbook / observation** | `moltbook_*`, `dsm_v2/moltbook_observation_runner.py`, `moltbook_home_*` | Product-specific automation and observation; not core DSM. |
| **Telegram / bot** | `dsm_bot.py`, `dsm_telegram_*`, `dsm_telegram_buffer_*`, `dsm_telegram_handler.py` | Runtime and integration; keep in lab. |
| **Feed monitor** | `FEED_MONITOR_GUIDE.md`, feed-related scripts | Monitoring and product features. |
| **DSM benchmark (scenarios)** | `dsm-benchmark/` | Research/benchmark scenarios; can stay in lab or be copied later as docs. |
| **dsm_ans_openclaw** | `dsm_ans_openclaw/` | ANS variant; experimental, keep in lab. |
| **Monetization / other** | `monetization_kit/`, non-DSM scripts | Unrelated to DSM architecture. |
| **Daryl-faucet** | `daryl-faucet/` | Separate project or tooling; keep in lab. |

---

## 4. Modules to archive

Classify as **ARCHIVE** (obsolete or superseded). Do **not** delete; only classify for future cleanup.

| Category | Examples | Reason |
|----------|----------|--------|
| **Fix / patch / rewrite scripts** | `fix_load_all_shards.py`, `fix_extract_refs_*.py`, `patch_*`, `rewrite_extract_refs*.py`, `restore_dsm_ingest_central.py`, `add_debug_ingest.py`, `add_load_all_shards.py` | One-off fixes or variants; superseded by canonical code paths. |
| **Multiple ingest variants** | `dsm_ingest_central_clean.py`, `dsm_ingest_central_simple.py` (plus base and optimized) | Duplicate pipelines; one canonical ingest should be chosen. |
| **Code refactor scripts** | `reconstruct_by_blocks.py`, `rewrite_init_block.py` | Refactor of ingest code into blocks; not DSM block layer. |
| **Old DSM clients** | `dsm_lite.py`, `dsm_lite_fixed.py`, `dsm_lite_v2.2.py` | Likely superseded by dsm_bot + dsm_logger. |
| **CLI / hardening stack** | `dsm_cli_v2.py`, `dsm_cli_v3.py`, `dsm_cli_hardening*.py`, `dsm_hardening*.py`, `dsm_hardening_final.py` | Evolution stack; document current entry point and archive old variants. |
| **Recycling test naming** | `recycling_test.py` (docstring “DSM-RR (DSM Recycling Memory)”) | Naming confusion RR vs RM; correct in docs and keep test in lab or archive. |

---

## 5. Migration strategy

### 5.1 MIGRATE — What to integrate

Only **DSM-RR (lab)** is a strong migration candidate: the **index + navigator + cache** idea. Daryl already has RR Step 1 (read_recent, summary); the lab adds an optional index and query layer.

- **DSM-RR index/navigator (lab)** → extend Daryl’s `memory/dsm/rr/` so that:
  - Index and query are **optional** (no breaking change to existing Step 1).
  - All shard access goes through **Storage.read()** (and segment manager iteration where needed), not direct file reads, so Daryl stays compatible with block shards and kernel contract.
- **dsm_analytics.py** → optional: add a small CLI script in Daryl (e.g. `memory/dsm/rr/analytics_cli.py`) that calls `rr.summary()` and prints; or document `dsm_analytics.py` as a lab reference only. **No obligation to migrate.**
- **Ingestion** → only if Daryl wants a **generic** DSM ingest (non-skills): pick one lab variant (e.g. `dsm_ingest_optimized.py` or `dsm_ingest_central.py`) as reference and design a single Daryl ingest module; leave all current lab variants in lab/archive.

### 5.2 Migration design for DSM-RR (index + navigator)

| Item | Detail |
|------|--------|
| **Concept** | DSM-RR optional index and query (ShardCatalog, Navigator, query cache). |
| **Source** | `/home/buraluxtr/clawd/dsm_modules/dsm_rr/` (indexer.py, navigator.py, cache_store.py, schemas.py, cli.py, README.md). |
| **Target** | `/opt/daryl/memory/dsm/rr/` (extend existing package). |

**Required refactoring (design only; no code change in this plan):**

1. **Replace file-based reads with Storage API**
   - Do not use `shard_dir.rglob("*.jsonl")` or `shard_path.read_text()`.
   - Use `Storage.read(shard_id, limit)` and/or `segment_manager.iter_shard_events(shard_id)` so that classic and block shards are supported and kernel contract is respected.

2. **Index as optional layer**
   - Build ShardCatalog from **list_shards()** and metadata (e.g. from Storage or segment manager), not from walking the filesystem.
   - Optional: build catalog by iterating shards via Storage.read() with a bounded limit to get counts/samples; or keep index as “cache of list_shards + optional stats” that can be regenerated.

3. **Navigator query**
   - Query should run over entries obtained via **Storage.read()** (or iter_entries) per shard, then score/filter in memory. No direct file I/O.

4. **Cache**
   - Keep cache in `data/index/` (or configurable dir) as today; ensure cache is clearly “regenerable” and never used as source of truth.

5. **Compatibility**
   - Preserve append-only and read-only semantics.
   - No writes to shards or security/baseline.
   - Document that RR (including index) is read-only and uses only the public Storage API.

**Risks and mitigations:**

- Lab RR uses a different **shard layout** (e.g. flat `data/shards/*.jsonl` vs Daryl’s segment families). Migration must use Daryl’s segment manager and Storage API so layout is abstracted.
- Query performance: moving to Storage.read() may require more I/O than raw file read; optional index/catalog helps avoid full scans when only metadata is needed.

### 5.3 What not to migrate

- **DSM-RM:** Already in Daryl (`memory/dsm/modules/dsm_rm.py`). Lab’s `dsm_v2/modules/dsm_rm.py` is the same or a copy; no second migration.
- **Memory Sharding (with cache):** Different system; do not migrate into DSM core. Could be a separate “experiment” or doc in Daryl later.
- **Moltbook, Telegram, feeds, monetization, daryl-faucet:** Keep in lab.
- **All ARCHIVE** items: Do not migrate; keep in lab and classify as archived.

---

## 6. Proposed final architecture (Daryl after migration)

Target tree for **Daryl** after optional RR index/navigator migration (and no change to core):

```
/opt/daryl/
├── memory/dsm/
│   ├── core/                    # Unchanged (storage, models, signing, replay, security, session, …)
│   ├── storage/                 # Facade to core.shard_segments (unchanged)
│   ├── session/                 # SessionGraph, session_limits_manager (unchanged)
│   ├── rr/                      # DSM-RR
│   │   ├── relay.py             # Existing: DSMReadRelay, read_recent(), summary()
│   │   ├── __init__.py
│   │   ├── (optional) indexer.py   # Migrated: build catalog from Storage API
│   │   ├── (optional) navigator.py  # Migrated: query over Storage.read()
│   │   ├── (optional) cache_store.py
│   │   ├── (optional) schemas.py
│   │   └── (optional) cli_rr.py     # CLI for index build, query, cache
│   ├── modules/
│   │   └── dsm_rm.py            # DSM-RM (unchanged)
│   ├── skills/                  # Unchanged
│   ├── ans/                     # Unchanged
│   ├── block_layer/             # Unchanged
│   ├── security.py             # Facade to core.security (unchanged)
│   └── cli.py                  # Main CLI (unchanged)
├── docs/
│   ├── LAB_TO_DARYL_MIGRATION_PLAN.md   # This document
│   ├── CLAWD_LAB_CONCEPTUAL_AUDIT.md
│   ├── DSM_FUTURE_ARCHITECTURE.md
│   └── …
├── tests/
│   └── dsm_rr_test.py          # Existing RR tests (unchanged)
└── HEARTBEAT.md
```

**Optional placement for migrated RR index/navigator:**

- **Option A:** Same package `memory/dsm/rr/`: add `indexer.py`, `navigator.py`, `cache_store.py`, `schemas.py`, and a small `cli_rr.py` (or subcommands in a shared CLI). Public API stays `DSMReadRelay`; index/navigator are used internally or via CLI.
- **Option B:** Subpackage `memory/dsm/rr/index/` for index + cache + navigator, and keep `relay.py` as the main read_recent/summary API so that “RR Step 1” stays minimal and index is clearly optional.

**No new top-level concepts:** Block layer, RM, skills, ANS remain as today. Only RR may gain an optional index/navigator layer.

---

## 7. Summary

| Action | Items |
|--------|--------|
| **MIGRATE** | DSM-RR index + navigator (refactored to use Storage API only); optionally a small analytics CLI or ingest design from lab. |
| **KEEP IN LAB** | Moltbook, Telegram, feeds, dsm_bot, benchmark scenarios, dsm_ans_openclaw, monetization, daryl-faucet. |
| **ARCHIVE** | fix_*, patch_*, rewrite_*, restore_*, add_* scripts; multiple ingest variants; dsm_lite*; old CLI/hardening stack; recycling_test naming. |
| **Do not migrate** | DSM core, RM (already in Daryl), Memory Sharding (different architecture), block layer (already in Daryl). |

**Rules respected:** No code or files modified; no changes to DSM core; planning only.

---

*See also: [CLAWD_LAB_CONCEPTUAL_AUDIT.md](CLAWD_LAB_CONCEPTUAL_AUDIT.md), [DSM_FUTURE_ARCHITECTURE.md](DSM_FUTURE_ARCHITECTURE.md), [HEARTBEAT.md](../HEARTBEAT.md).*
