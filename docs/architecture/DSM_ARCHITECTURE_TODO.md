# DSM — Architecture-to-Code TODO

This document compares the **architecture documentation** (DSM Architecture Map, RR Architecture, RR Implementation Plan, RR Index Spec) with the **actual codebase** and produces a gap analysis and implementation TODO list.

**Scope:** Tracks architecture-to-code alignment. This file is updated as RR components are implemented (Index, Navigator, Query done; Context Builder pending).

---

## 1. Introduction

The architecture docs define:

- **DSM kernel** — Minimal append-only storage (Storage API, models, segments, signing, replay, security). Frozen; no search, index, or query.
- **Session layer** — SessionGraph (start_session, record_snapshot, execute_action, end_session) writing to the sessions shard.
- **Security layer** — Baseline integrity, audit logs, protected files, rate limiting.
- **Block layer** — Optional batching of entries into blocks via Storage API.
- **RR (Read Relay)** — Memory navigation: read_recent, summary (Step 1); plus planned RRIndex, RRNavigator, RRQuery, RRContextBuilder.
- **Context Packs** — Transform DSM memory into LLM-ready context (planned).
- **Skills / ANS** — Skill registry, router, telemetry; ANS learning layer.

This TODO lists what exists in the repo, what is missing, and what work is required to align code with the architecture.

---

## 2. Architecture vs Codebase Analysis

### 2.1 Repository layout (memory/dsm)

| Path | Purpose (from code) |
|------|---------------------|
| **core/** | storage.py, models.py, shard_segments.py, signing.py, replay.py, security.py, session.py, runtime.py, tracing.py, drift_metrics.py, security_listener.py |
| **session/** | session_graph.py (SessionGraph), session_limits_manager.py (SessionLimitsManager) |
| **rr/** | relay.py (DSMReadRelay: read_recent, summary), __init__.py — no index/, navigator/, query/, context/ |
| **block_layer/** | manager.py (BlockManager, BlockConfig), benchmark.py, __init__.py |
| **skills/** | registry.py, router.py, ingestor.py, models.py, skill_usage_logger.py, skill_success_logger.py, skill_graph.py, success_analyzer.py, evaluator.py, cli.py, libraries/ |
| **ans/** | ans_engine.py, ans_analyzer.py, ans_models.py, cli.py, ans_test.py |
| **modules/** | dsm_rm.py (DSMRecyclingMemory) |
| **storage/** | __init__.py (facade: re-exports ShardSegmentManager) |
| **security.py** (root) | Facade to core.security; adds allow_writes/deny_writes/writes_allowed |

### 2.2 DSM kernel API (core)

- **Storage** (core/storage.py): `append(entry)`, `read(shard_id, limit)`, `list_shards()`, `get_shard_size(shard_id)` — **implemented** and match the architecture.
- **Models** (core/models.py): Entry, ShardMeta, IntegrityRecord — **implemented**.
- **Shard segments** (core/shard_segments.py): ShardSegmentManager, get_active_segment, iter_shard_events — **implemented**.
- **Signing** (core/signing.py): compute_hash, verify_chain, chain_entry — **implemented**.
- **Replay** (core/replay.py): TraceRecord, replay_session, verify_chain (trace format) — **implemented**.
- **Security** (core/security.py): SecurityLayer, verify_integrity, baseline gating, audit, protected files, rate limiting — **implemented**.

Kernel boundary (storage, models, shard_segments, signing, replay, security) is present and matches the docs. Other core modules (session.py SessionTracker, runtime, tracing, drift_metrics, security_listener) exist but are not in the “kernel boundary” list in the architecture map; they are supporting or runtime.

### 2.3 Session layer

- **SessionGraph** (session/session_graph.py): start_session, record_snapshot, execute_action, end_session, get_session_id, is_session_active — **implemented**. Writes to shard `sessions` via Storage.append.
- **SessionLimitsManager** (session/session_limits_manager.py): can_poll_home, can_execute_action, mark_*, state file — **implemented**.

Session layer matches the architecture.

### 2.4 Security layer

- **SecurityLayer** (core/security.py): verify_integrity, check_baseline_gate, update_baseline, audit_action, check_protected_write, _verify_chain_integrity, etc. — **implemented**.
- Root **security.py** re-exports core.security and adds contextvars for write gating — **implemented**.

Security layer matches the architecture.

### 2.5 Block layer

- **BlockManager** (block_layer/manager.py): append(entry), flush(), read(shard_id, limit), iter_entries; uses Storage only; block shards with suffix — **implemented**.
- **BlockConfig** (block_size, block_shard_suffix) — **implemented**.

Block layer matches the architecture (experimental, above kernel).

### 2.6 RR (Read Relay)

- **rr/relay.py**: DSMReadRelay with read_recent(shard_id, limit) and summary(shard_id, limit). Uses Storage.read() only; expands block-format entries. — **implemented** (Step 1).
- **rr/index/** — **implemented**. RRIndexBuilder; build/load/ensure_index; sessions.idx, agents.idx, timeline.idx, shards.idx under data/index/; index_version; pagination and atomic writes.
- **rr/navigator/** — **implemented**. RRNavigator(navigator, storage); navigate_session, navigate_agent, timeline(start_time, end_time), navigate_shard; resolve_entries with pagination and set lookup.
- **rr/query/** — **implemented**. RRQueryEngine(navigator); query(session_id, agent, shard_id, start_time, end_time, resolve, limit, sort); intersection by entry_id; optional sort and limit.
- **rr/context/** — **missing**. No RRContextBuilder or context pack construction.

RR Step 1, RR Index, RR Navigator, and RR Query are implemented; RRContextBuilder is not.

### 2.7 Context Packs

- No dedicated Context Packs module or API in the repo. Architecture describes it as “planned”; no code found. — **missing**.

### 2.8 Skills / ANS

- **Skills**: SkillRegistry, SkillRouter, Skill model, ingestor, skill_usage_logger, skill_success_logger, skill_graph, success_analyzer, evaluator, libraries (anthropic, community, custom) — **implemented**. Telemetry to separate JSONL (not DSM shards).
- **ANS**: ANSEngine, ans_analyzer (load_usage_events, load_success_events, compute_skill_performance, compute_transition_performance, recommend_*, detect_weak_*), ans_models, CLI — **implemented**.

Skills and ANS layers are implemented and match the architecture (above kernel, no DSM shard writes for telemetry).

---

## 3. Component Status Table

| Component | Status | Notes |
|-----------|--------|--------|
| **DSM Core** | Implemented | storage, models, shard_segments, signing, replay, security present; API matches. |
| **Session Layer** | Implemented | SessionGraph, SessionLimitsManager; sessions shard. |
| **Security Layer** | Implemented | SecurityLayer in core; root facade; baseline, audit, protected files. |
| **Block Layer** | Implemented | BlockManager, BlockConfig; uses Storage only. |
| **RR (Read Relay)** | Partially implemented | Step 1 (relay) + Index + Navigator + Query implemented. RR Context Builder missing. |
| **RR Index** | Implemented | rr/index/; RRIndexBuilder; sessions.idx, agents.idx, timeline.idx, shards.idx; index_version; rebuild/load/ensure_index. |
| **RR Navigator** | Implemented | rr/navigator/; RRNavigator; navigate_session, navigate_agent, timeline, navigate_shard; resolve_entries (paginated, set lookup). |
| **RR Query** | Implemented | rr/query/; RRQueryEngine; query(session_id, agent, shard_id, time range, resolve, limit, sort); intersection by entry_id. |
| **RR Context Builder** | Not implemented | No rr/context/; no context pack construction from query results. |
| **Context Packs (layer)** | Not implemented | Documented as planned; no dedicated module. |
| **Skills / ANS** | Implemented | Registry, router, ingestor, loggers, graph, ANS engine/analyzer, CLI. |

---

## 4. Gap Analysis

### 4.1 DSM Core

- **Current state:** Implemented. Storage (append, read, list_shards, get_shard_size), models, shard_segments, signing, replay, security.
- **Expected (architecture):** Minimal kernel; no search, index, query; frozen.
- **Required work:** None. Keep kernel unchanged.

### 4.2 Session Layer

- **Current state:** SessionGraph and SessionLimitsManager implemented; write to shard `sessions`.
- **Expected:** start_session, record_snapshot, execute_action, end_session; limits and cooldowns.
- **Required work:** None.

### 4.3 Security Layer

- **Current state:** SecurityLayer in core; baseline, audit, protected files, rate limiting; root facade.
- **Expected:** Baseline integrity, audit logs, protected files, rate limiting.
- **Required work:** None.

### 4.4 Block Layer

- **Current state:** BlockManager, BlockConfig; append, flush, read, iter_entries; block shards; Storage-only.
- **Expected:** Optional batching; no kernel change; separate block shards.
- **Required work:** None.

### 4.5 RR (Read Relay) — Step 1

- **Current state:** DSMReadRelay with read_recent and summary; Storage.read() only; block expansion.
- **Expected:** Read-only; Step 1 read_recent, summary.
- **Required work:** None for Step 1. Validate and document as stable base.

### 4.6 RR Index

- **Current state:** Implemented. rr/index/ with RRIndexBuilder; build/load/ensure_index; sessions.idx, agents.idx, timeline.idx, shards.idx under data/index/; index_version; pagination (when Storage supports offset), atomic writes, timestamp normalization.
- **Expected (RR_INDEX_SPEC, RR_IMPLEMENTATION_PLAN):** Index built from Storage.list_shards() and Storage.read(); metadata stored under data/index/; derived, rebuildable.
- **Required work:** None. Optional: incremental index update strategy when needed.

### 4.7 RR Navigator

- **Current state:** Implemented. rr/navigator/ with RRNavigator(index_builder, storage); navigate_session, navigate_agent, timeline(start_time, end_time), navigate_shard; resolve_entries with pagination, set lookup, shard grouping, limit safety, missing-entry handling; timestamp normalization.
- **Expected (RR_ARCHITECTURE, RR_IMPLEMENTATION_PLAN):** RRNavigator with the four navigation operations; uses index; resolution via Storage.read() only.
- **Required work:** None.

### 4.8 RR Query

- **Current state:** Implemented. rr/query/ with RRQueryEngine(navigator); query(session_id, agent, shard_id, start_time, end_time, resolve, limit, sort); intersection by entry_id (set-based); optional sort by timestamp; empty filter returns [].
- **Expected:** High-level query API delegating to Navigator; returns memory slices or resolved entries.
- **Required work:** None.

### 4.9 RR Context Builder

- **Current state:** No rr/context/ module. No transformation of query results into context packs.
- **Expected:** RRContextBuilder; input = RR query results; output = structured context (selected entries, summaries, references to DSM); for LLM consumption.
- **Required work:** Add rr/context/; implement RRContextBuilder; input: lists of Entry or pointers; output: context pack structure (entries/snippets, summaries, refs); no writes to DSM.

### 4.10 Context Packs (standalone layer)

- **Current state:** No dedicated module. Architecture describes Context Packs as a layer that transforms DSM memory into LLM-ready context (planned).
- **Expected:** Either a thin layer that uses RR (read_recent, summary, future query) to obtain data and shape it, or part of RR (Context Builder). RR_ARCHITECTURE places Context Builder inside RR.
- **Required work:** Either implement as consumer of RR (and optionally RRContextBuilder), or treat RRContextBuilder as the implementation of “Context Packs” for now. No separate Context Packs code required until product needs a distinct layer.

### 4.11 Skills / ANS

- **Current state:** Implemented. Registry, router, ingestor, usage/success loggers, skill graph, success analyzer; ANS engine, analyzer, models, CLI.
- **Expected:** Skill registry, router, telemetry (separate from DSM shards); ANS learning from telemetry.
- **Required work:** None.

---

## 5. Implementation TODO List

### DSM Core

**Status:** Implemented.

**Tasks:** None. Keep kernel frozen.

---

### Session Layer

**Status:** Implemented.

**Tasks:** None.

---

### Security Layer

**Status:** Implemented.

**Tasks:** None.

---

### Block Layer

**Status:** Implemented.

**Tasks:** None.

---

### RR Step 1 (relay)

**Status:** Implemented.

**Tasks:**

- Document rr/relay.py as the stable RR Step 1 API (read_recent, summary).
- Ensure all RR extensions use only Storage.read(), list_shards(), get_shard_size().

---

### RR Index

**Status:** Implemented.

**Tasks:** None. See docs/architecture/RR_INDEX_IMPLEMENTATION.md.

---

### RR Navigator

**Status:** Implemented.

**Tasks:** None. See docs/architecture/RR_NAVIGATOR_IMPLEMENTATION.md.

---

### RR Query

**Status:** Implemented.

**Tasks:** None. See docs/architecture/RR_QUERY_ENGINE_IMPLEMENTATION.md.

---

### RR Context Builder

**Status:** Not implemented.

**Tasks:**

- Create rr/context/ package.
- Implement RRContextBuilder class.
- Input: RR query results (memory slices).
- Output: structured context pack (selected entries/snippets, optional summaries, references to DSM: shard_id, entry id, timestamp).
- No writes to DSM; no LLM calls in minimal version; prepare data for LLM consumption.

---

### RR pipeline (end-to-end)

**Status:** Partially implemented (Step 1 + Index + Navigator + Query; Context Builder missing).

**Tasks:**

- Implement RR Context Builder (rr/context/); then wire: Agent request → RRQueryEngine → RRNavigator → Index → Storage.read() → ContextBuilder → Context Pack.
- Add tests for full pipeline using Storage only (no direct file access).
- Query limits are enforced in RRQueryEngine (limit parameter) and RRNavigator.resolve_entries().

---

### Context Packs (layer)

**Status:** Not implemented (planned).

**Tasks:**

- Option A: Treat RRContextBuilder as the implementation of Context Packs for now; document accordingly.
- Option B: Add a thin Context Packs layer that calls RR (read_recent, summary, query) and RRContextBuilder and exposes a single “build context pack” API for agents. Defer until product requires it.

---

### Skills / ANS

**Status:** Implemented.

**Tasks:** None.

---

## 6. Suggested Development Phases

### Phase 1 — RR foundation (current)

- **Scope:** RR Step 1 (read_recent, summary) already in rr/relay.py.
- **Tasks:** Document as stable base; confirm Storage-only usage; add/update tests.
- **Deliverable:** Stable RR Step 1; no kernel change.

---

### Phase 2 — RR index and session navigation

- **Scope:** RR index build and navigator for sessions/timeline.
- **Status:** Done. rr/index/ (RRIndexBuilder) and rr/navigator/ (RRNavigator with navigate_session, navigate_agent, timeline, navigate_shard, resolve_entries) implemented.
- **Deliverable:** Index can be built and rebuilt from shards; navigation works via index and Storage.read().

---

### Phase 3 — RR query engine and context builder

- **Scope:** High-level query API and context pack construction.
- **Status:** Query engine done; context builder pending. rr/query/ (RRQueryEngine) implemented with query(session_id, agent, shard_id, time range, resolve, limit, sort) and intersection by entry_id. rr/context/ (RRContextBuilder) not yet implemented.
- **Tasks remaining:** Implement rr/context/ (RRContextBuilder); wire Agent request → RRQueryEngine → RRNavigator → Index → Storage.read() → ContextBuilder → Context Pack.
- **Deliverable (when context done):** Agents can query memory by session/shard/time/agent and receive context packs for LLM use.

---

### Phase 4 — Performance and robustness

- **Scope:** Index and query performance; failure handling.
- **Tasks:** Index caching and invalidation; lazy shard scanning and index backfill; query limits; document and test recovery (delete index → rebuild from shards).
- **Deliverable:** RR scales to larger memories; recovery path documented and tested.

---

### Phase 5 — Optional extensions (future)

- **Scope:** Semantic index, vector embeddings, memory graph, multi-agent views (all outside kernel).
- **Tasks:** Design and implement only when needed; always via Storage API and RR index/cache only.
- **Deliverable:** Optional RR extensions without kernel changes.

---

**Summary:** The DSM kernel, session layer, security layer, block layer, and skills/ANS are implemented and aligned with the architecture. RR Index, RR Navigator, and RR Query Engine are implemented; RR Context Builder is the remaining RR gap. The TODO list and phases above track the remaining work (context builder and full pipeline wiring) without modifying the kernel.

---

## Post-Audit Corrections

A deep technical audit has identified additional runtime bugs, kernel integrity issues, RR usability gaps, and security improvements. All audit-driven tasks are tracked in a separate document so the repository stays synchronized before implementing fixes.

**See:** [docs/architecture/DSM_AUDIT_TODO.md](DSM_AUDIT_TODO.md)
