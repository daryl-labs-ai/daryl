# ADR 0001 — SessionIndex Classification Report

- **Date:** 2026-04-19
- **Parent ADR:** `docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md`
- **Status of parent ADR:** Proposed → (unchanged by this report; parent is amended in-place on the sections enumerated by the classification phase brief)
- **Classification result:** `duplicative`

> **Reconstruction note.** The parent ADR's section `Open questions before Accepted` did not exist in the v1 document. It is created in-place during this phase so that the classification rule (a) / (b) / (c) has an anchor inside the parent ADR, then resolved with a pointer to this report. The rule below is the one supplied in the classification phase brief and is now mirrored verbatim in the parent ADR.

---

## Criterion (a) — Access pattern orthogonality vs RR

### SessionIndex query patterns (from `src/dsm/session/session_index.py`)

Public methods and observed algorithmic behaviour:

- **`build_from_storage(storage)` at `src/dsm/session/session_index.py:44`** — cold full-shard scan. Reads `storage.read(self.shard_id, limit=10**7)` at line 51. Complexity: **O(N)** in total entries of the shard. Persists `sessions.jsonl`, `actions.jsonl`, `meta.json` at lines 102, 107, 118.
- **`find_session(session_id)` at `src/dsm/session/session_index.py:133`** — constant-time lookup via `self._sessions.get(session_id)` at line 140 (Python dict, hash table). Complexity: **O(1)** expected, **O(k)** worst-case for dict lookup.
- **`get_actions(action_name=None, session_id=None, start_time=None, end_time=None, limit=100)` at `src/dsm/session/session_index.py:156`** — linear scan over the pre-built `self._actions` list (flat, timestamp-sorted at line 97). AND-filters on `action_name` (exact match, line 170), `session_id` (line 172), and `start_time`/`end_time` compared as **lexicographic ISO strings** (lines 174, 176). Complexity: **O(N_actions)** worst-case, early-exit on `limit` (line 179). Note: the time comparison is string-based, which is correct for ISO 8601 UTC with `Z` suffix only — the builder normalises this at line 60 (`entry.timestamp.isoformat()`), which prevents the bug in practice but represents a semantic difference from RR's numeric timestamp comparisons.
- **`list_sessions(limit=50)` at `src/dsm/session/session_index.py:183`** — enumerates `self._sessions.values()` at line 186, sorts by `end_time` descending (line 197). Complexity: **O(N_sessions · log N_sessions)**.
- **`is_consistent(storage)` at `src/dsm/session/session_index.py:200`** — re-reads storage and compares `len(entries)` against `self._meta["entries_indexed"]` (lines 205–206). Complexity: **O(N)** due to the read; purely an entry-count check (does not detect edits within the count).

### RR equivalent coverage

From `src/dsm/rr/query/rr_query_engine.py` and `src/dsm/rr/navigator/rr_navigator.py`:

- **Session lookup.** `RRQueryEngine.query(session_id=…)` at `src/dsm/rr/query/rr_query_engine.py:83–84` → `RRNavigator.navigate_session(session_id)` at `src/dsm/rr/navigator/rr_navigator.py:70–78` → `self._index_builder.session_index.get(session_id, [])` (line 77). Complexity: **O(k)** where k is the count of records in the session (dict.get + list copy). Returns individual index records, not a pre-aggregated summary. `SessionIndex.find_session` returns the aggregate `{session_id, source, start_time, end_time, entry_count, entry_ids, actions}` (lines 147–153). Aggregating from RR's per-record output is **O(k)** on the returned list — not an orthogonal operation, a derived view.
- **Time-range query.** `RRQueryEngine.query(start_time=…, end_time=…)` at `src/dsm/rr/query/rr_query_engine.py:89–91` → `RRNavigator.timeline(...)` at `src/dsm/rr/navigator/rr_navigator.py:90–119`. Linear scan over the full `timeline_index` at line 110 with numeric-timestamp filtering (line 111 normalises via `_to_timestamp`). Complexity: **O(N_all_entries)**. Same cost class as `SessionIndex.get_actions` with only a time filter; slightly different comparison semantics (numeric vs lexicographic ISO).
- **Agent filter.** `RRQueryEngine.query(agent=…)` at `src/dsm/rr/query/rr_query_engine.py:85–86` → `RRNavigator.navigate_agent(agent)` at `src/dsm/rr/navigator/rr_navigator.py:80–88` → `self._index_builder.agent_index.get(agent, [])` (line 87). **O(k)** dict lookup. SessionIndex has no agent filter — not a gap on RR's side.
- **Action-name filter.** **RR has no action-name index.** Confirmed by reading `_entry_to_index_record` at `src/dsm/rr/index/rr_index_builder.py:34–66`: the record exposes `session_id`, `timestamp`, `agent`, `event_type`, `shard_id`, `entry_id`, `offset` (lines 58–65). The metadata key `action_name` is **not promoted into any index structure** — `RRIndexBuilder` stores `event_type` only (line 55). `RRQueryEngine.query` accepts no `action_name` parameter (signature lines 47–57). The RR context builder does include `action_name` in its `METADATA_KEYS_WHITELIST` at `src/dsm/rr/context/rr_context_builder.py:18`, but that only forwards the value *when an entry is already resolved*; it is not a reverse index. To emulate `SessionIndex.get_actions(action_name="X")` through RR today, you would have to call `RRNavigator.timeline(...)` to get candidate records, then `resolve_entries(records)` at `src/dsm/rr/navigator/rr_navigator.py:131–214` (which calls `Storage.read` in 5000-entry batches per shard at lines 176–181), then inspect each resolved `Entry.metadata["action_name"]` — that is **O(N_range) Storage reads for a query that SessionIndex answers in O(N_actions) in-memory**.
- **`list_sessions` enumeration.** `RRNavigator` exposes no method that enumerates all known `session_id` keys. The data is present (`self._index_builder.session_index` is a dict at `src/dsm/rr/navigator/rr_navigator.py:76`) but there is no public iterator. A caller would have to reach into `navigator.index_builder.session_index.keys()` manually, which breaks encapsulation. Not orthogonal — a missing trivial accessor.

### Verdict on (a)

**`covered by RR at materially worse cost`** — specifically for the action-name filter path, which has no RR index equivalent and would require O(N) Storage reads via `resolve_entries`. Session, agent, and timeline filters are **covered at comparable cost**. The SessionIndex patterns are not orthogonal to RR — they are a superset that RR fails to cover because RR did not index one metadata key (`action_name`) that SessionIndex chose to promote to a first-class index. A ~30-line extension of `_entry_to_index_record` and `RRIndexBuilder` adding an `action_index: Dict[str, List[record]]` would close the cost gap entirely. This is a missing RR filter, not an orthogonal access pattern — the rule requires "matériellement orthogonal", not "answerable with less RR plumbing today". **Not met.**

**Fichiers examinés :** `src/dsm/session/session_index.py`, `src/dsm/rr/query/rr_query_engine.py`, `src/dsm/rr/navigator/rr_navigator.py`, `src/dsm/rr/index/rr_index_builder.py`, `src/dsm/rr/context/rr_context_builder.py`.

---

## Criterion (b) — Invalidation / freshness model

### SessionIndex invalidation model

- **Build:** cold rebuild via `build_from_storage(storage)` at `src/dsm/session/session_index.py:44`. Clears in-memory state implicitly (reassigns `self._sessions` at line 121 and `self._actions` at line 122), writes three files on disk: `sessions.jsonl` (line 102), `actions.jsonl` (line 107), `meta.json` (line 118).
- **Load-cold behaviour:** `_load_if_exists()` at `src/dsm/session/session_index.py:210`, called from `__init__` at line 40. Reads `meta.json` first, then streams JSONL files if they exist. **Never auto-rebuilds** — if files are missing or stale, queries return empty results.
- **Staleness detection:** `is_consistent(storage)` at `src/dsm/session/session_index.py:200` — compares `len(entries)` to `self._meta["entries_indexed"]`. Detects only *count* divergence, not content edits. Does not trigger a rebuild; it is a boolean check.
- **Called by:** `DarylAgent.index_sessions` at `src/dsm/agent.py:620–623` (only production rebuild trigger), CLI `dsm session-index` at `src/dsm/cli.py:570–580` (`_cmd_session_index`). `is_consistent` is invoked only by tests (`tests/test_session_index.py:173, 183, 192`) — no production caller.
- **Operational reality:** explicit, operator-triggered rebuild. No read-time invalidation. Stale reads are possible and silent.

### RR invalidation model

- **Build:** full rebuild via `RRIndexBuilder.build()` at `src/dsm/rr/index/rr_index_builder.py:119`. Clears in-memory indexes explicitly (lines 131–134), scans all shards (lines 136–173), sorts timeline (line 175), writes four files atomically using `tempfile.mkstemp` + `os.replace` (lines 192–201): `sessions.idx`, `agents.idx`, `timeline.idx`, `shards.idx`.
- **Load:** `load()` at `src/dsm/rr/index/rr_index_builder.py:209` — returns False if any of the four files is missing (lines 221–225). Does not rebuild.
- **Load-or-build convenience:** `ensure_index()` at `src/dsm/rr/index/rr_index_builder.py:241` — calls `load()`, and if it returns False, calls `build()`. This is the RR analogue of SessionIndex's `_load_if_exists` + manual `build_from_storage`, bundled into one call.
- **Staleness detection:** none. RR has no equivalent of `is_consistent`. Once loaded, the index is trusted until the next explicit `build()`.
- **Called by:** `ensure_index()` is called from navigator/tools wiring paths rather than from routine queries; `build()` is called explicitly by operator-triggered maintenance.
- **Operational reality:** explicit, operator-triggered rebuild. No read-time invalidation.

### Verdict on (b)

**`same model as RR`** — both are derived indexes produced by a cold full-shard scan, persisted as read-only artefacts, rebuilt only on explicit operator command, with no read-time staleness detection or auto-refresh. Incidental differences (JSONL vs JSON-wrapper file format, `is_consistent` present in one and absent in the other, `ensure_index` present in the other and absent in the first) are operational niceties, not a materially distinct model. They would share the same runbook entry: "when a shard grows meaningfully, rebuild the index". **Not met.**

**Fichiers examinés :** `src/dsm/session/session_index.py`, `src/dsm/rr/index/rr_index_builder.py`, `src/dsm/agent.py`, `src/dsm/cli.py`, `tests/test_session_index.py`.

---

## Criterion (c) — Consumer count

### Live consumers of SessionIndex

Exhaustive grep across `src/` (tests excluded per the rule below):

- **`DarylAgent.index_sessions`** at `src/dsm/agent.py:620–623` → `SessionIndex.build_from_storage` (rebuild trigger).
- **`DarylAgent.find_session`** at `src/dsm/agent.py:625–628` → `SessionIndex.find_session`.
- **`DarylAgent.query_actions`** at `src/dsm/agent.py:630–644` → `SessionIndex.get_actions`.
- **CLI `dsm session-index`** at `src/dsm/cli.py:570–580` (`_cmd_session_index`) → `SessionIndex.build_from_storage`. Registered at `src/dsm/cli.py:1093–1097`.
- **CLI `dsm session-find`** at `src/dsm/cli.py:583–595` (`_cmd_session_find`) → `SessionIndex.find_session`. Registered at `src/dsm/cli.py:1099–1104`.
- **CLI `dsm session-query`** at `src/dsm/cli.py:598–617` (`_cmd_session_query`) → `SessionIndex.get_actions`. Registered at `src/dsm/cli.py:1106–1114`.
- **CLI `dsm session-list`** at `src/dsm/cli.py:620–633` (`_cmd_session_list`) → `SessionIndex.list_sessions`. Registered at `src/dsm/cli.py:1116+`.
- **MCP tool `dsm_search`** at `src/dsm/integrations/goose/server.py:378–402`, via `agent.query_actions(...)` at `src/dsm/integrations/goose/server.py:396`.

Total: **8 live consumers** spanning **3 surfaces** (Python agent facade, CLI subcommands, MCP tool).

### Is the API surface fully consumed ?

- `build_from_storage` — consumed by `DarylAgent.index_sessions` and CLI `dsm session-index`.
- `find_session` — consumed by `DarylAgent.find_session` and CLI `dsm session-find`.
- `get_actions` — consumed by `DarylAgent.query_actions` (and indirectly by `dsm_search`) and CLI `dsm session-query`.
- `list_sessions` — consumed by CLI `dsm session-list`. **No Python facade consumer** (no `DarylAgent` method delegates to `list_sessions`) — but the CLI route alone is live production.
- `is_consistent` — **dormant** in production. Called only from `tests/test_session_index.py:173, 183, 192`. No `DarylAgent` or CLI or MCP caller.

Dormant surface: one method (`is_consistent`). Per the rule, dormant API does not argue for `canonical-supporting`.

### Verdict on (c)

`shared across 3 surfaces: DarylAgent facade (agent.py), CLI (cli.py), MCP (integrations/goose/server.py)`. Not a unique consumer.

**Fichiers examinés :** `src/dsm/session/session_index.py`, `src/dsm/agent.py`, `src/dsm/cli.py`, `src/dsm/integrations/goose/server.py`, `tests/test_session_index.py`, `tests/test_agent_coverage.py`, `src/dsm/recall/__init__.py`, `src/dsm/recall/search.py`.

---

## Classification rule (from ADR 0001)

> SessionIndex est `canonical-supporting` si
> (a) démontre un pattern d'accès matériellement orthogonal à RR,
> **ou**
> (b) démontre un modèle opérationnel matériellement distinct.
> Sinon il est `duplicative`.
> L'API dormante ou l'usage hypothétique futur ne comptent pas.

---

## Classification result

**SessionIndex is classified as: `duplicative`.**

### Justification

Criterion (a) is not met: every SessionIndex query pattern maps to an RR primitive at comparable cost (`find_session` ↔ `navigate_session`, `list_sessions` ↔ `session_index.keys()` enumeration, timeline ↔ `timeline`) except the action-name filter, which fails only because RR chose not to index `action_name` — a ~30-line addition to `src/dsm/rr/index/rr_index_builder.py:34` (`_entry_to_index_record`) closes the gap. A missing RR filter is not access-pattern orthogonality. Criterion (b) is not met: both indexes rebuild cold on explicit operator command, with no read-time invalidation — identical runbook. Criterion (c) is informational: 8 live consumers across 3 surfaces means the deprecation phase is non-trivial blast-radius, but per the rule consumer count is not an argument for `canonical-supporting`. With neither (a) nor (b) met, the classification is `duplicative`.

### Implications

- SessionIndex is **included in the scope of ADR 0001's migration plan** with a deprecation horizon.
- Consumers to rebrand/rebranch onto RR (with action-name index extension as a prerequisite):
  - `DarylAgent.index_sessions` (`src/dsm/agent.py:620`) — replace with `agent.rebuild_indexes()` that triggers `RRIndexBuilder.build()`.
  - `DarylAgent.find_session` (`src/dsm/agent.py:625`) — replace with a thin wrapper over `RRNavigator.navigate_session(...)` + aggregation.
  - `DarylAgent.query_actions` (`src/dsm/agent.py:630`) — replace with `agent.search_memory(action_name=...)` once RR indexes `action_name`, or route through RR + a new `RRQueryEngine.query(action_name=...)` filter.
  - CLI `dsm session-index`, `dsm session-find`, `dsm session-query`, `dsm session-list` (`src/dsm/cli.py:570–633`) — re-point at the RR-backed implementations. Keep the CLI command names stable.
  - MCP `dsm_search` (`src/dsm/integrations/goose/server.py:378–402`) — migration already listed in ADR 0001 "Required MCP changes", now re-grounded in a single canonical backend rather than a cross-stack shuffle.
- SessionIndex module itself (`src/dsm/session/session_index.py`, 243 L) is marked `deprecated` with a six-month removal horizon starting when Phase 7 of the ADR 0001 migration plan lands. Tests in `tests/test_session_index.py` (242 L) retire alongside the module.
- The "4th-path tail" caveat in ADR 0001's original `Consequences > Négatives` and `Non-goals` lines becomes obsolete; those bullets are amended in-place in the parent ADR.

**Fichiers examinés :** `src/dsm/session/session_index.py`, `src/dsm/rr/query/rr_query_engine.py`, `src/dsm/rr/navigator/rr_navigator.py`, `src/dsm/rr/index/rr_index_builder.py`, `src/dsm/rr/context/rr_context_builder.py`, `src/dsm/rr/relay.py`, `src/dsm/agent.py`, `src/dsm/cli.py`, `src/dsm/integrations/goose/server.py`, `src/dsm/recall/__init__.py`, `src/dsm/recall/search.py`, `tests/test_session_index.py`, `tests/test_agent_coverage.py`, `docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md`.
