# DSM Post-Audit TODO

This document tracks all corrections required after the deep technical audit. It serves as the centralized technical TODO list so the project remains synchronized before implementing fixes.

**Scope:** Architectural issues, runtime bugs, kernel integrity, RR usability, memory correctness, scalability, agent usability, and security hardening identified by the audit.

**Status (updated):** P1 done, P2 done (except segment counter), P3 done (except cursor pagination), P4 done, P5 pending, P6 partial (content_preview + ISO timestamps done), P7 pending.

---

## Priority 1 — Crash-level runtime bugs ✅

* ~~Fix duplicate `score` field in `SkillRecommendation` (ans_models.py)~~ — Done
* ~~Fix `ANSEngine.print_report()` using `.explanation` instead of `.reason`~~ — Done
* ~~Fix `recommend_next_skills()` returning `SkillPerformance` instead of `SkillRecommendation`~~ — Done
* ~~Fix `SkillRegistry.search()` accessing nonexistent `skill.name`~~ — Done

---

## Priority 2 — Kernel integrity and concurrency ✅

* ~~Extend entry hash to include full entry fields (session_id, source, timestamp, metadata, content)~~ — Done
* ~~Add file locking for `_last_hash.json` updates~~ — Done
* ~~Prevent concurrent append race conditions~~ — Done (lock + fsync)
* Replace segment line-count scanning with lightweight segment counter — Future (segment metadata)

---

## Priority 3 — RR usability improvements ✅

* ~~Add `offset` parameter to `Storage.read()`~~ — Done
* ~~Remove RR fallback `limit=50000` logic~~ — Done
* ~~Support paginated RR index building~~ — Done
* ~~Add entry content preview to `RRContextBuilder`~~ — Done
* ~~Allow `resolve=True` option in context builder~~ — Done
* Add cursor-based pagination to `RRQueryEngine` — Pending

---

## Priority 4 — Memory correctness ✅

* ~~Fix `iter_shard_events_reverse()` order~~ — Done
* ~~Fix `entry_count=0` bug in `list_shards()`~~ — Done
* ~~Replace `print()` JSON parse errors with proper logging~~ — Done
* ~~Improve shard metadata tracking~~ — Done

---

## Priority 5 — Scalability improvements

* Implement incremental RR index updates
* Add index warm-start loading
* Consider disk-backed index (SQLite / LMDB) for >1M events
* Add shard partitioning strategy for large datasets

---

## Priority 6 — Agent usability (partial ✅)

* ~~Improve `RRContextBuilder` to include meaningful event content~~ — Done (content_preview + metadata)
* Add semantic summary option — Pending
* ~~Convert timestamps to ISO 8601 strings~~ — Done
* Add session-level context summary — Pending

---

## Priority 7 — Security hardening

* Ensure hash chain verification covers metadata
* Add integrity verification test suite
* Improve security baseline gating logic
* Replace substring path matching with exact path comparison

---

**Next phase:** Systematic bug fixing and architecture hardening. Do not modify source code until tasks are scheduled from this list.

**Stabilization plan:** See [DSM_STABILIZATION_ROADMAP.md](DSM_STABILIZATION_ROADMAP.md) for phased correction order (integrity → performance → concurrency → usability) and kernel-critical rules.
