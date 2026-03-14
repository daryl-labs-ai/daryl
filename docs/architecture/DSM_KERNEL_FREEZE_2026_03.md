# DSM Kernel Freeze — March 2026

This document records the **kernel freeze** of the DSM storage kernel following stabilization and two full audits. No kernel logic is to be changed without following the DSM kernel evolution process.

---

## 1) Kernel scope

The following files are part of the frozen DSM storage kernel:

| File | Role |
|------|------|
| `memory/dsm/core/storage.py` | Append/read/list, JSONL append-only, segment coordination |
| `memory/dsm/core/shard_segments.py` | Segment layout, rotation, O(1) active segment resolution |
| `memory/dsm/core/models.py` | Entry, ShardMeta, integrity-related dataclasses |
| `memory/dsm/core/signing.py` | SHA-256 hash chain for append-only integrity |
| `memory/dsm/core/replay.py` | Trace replay and verification (audit-only) |
| `memory/dsm/core/security.py` | Security layer: integrity baseline, audit, protected files |

All are located under **`memory/dsm/core/`**. The kernel is versioned via `memory/dsm/core/KERNEL_VERSION`.

---

## 2) Freeze reason

The kernel has completed stabilization fixes from two audits. The following items have been implemented and verified:

### Critical (C1–C4)

- **C1** — Atomic integrity writes: `_set_last_hash()` and shard metadata updates use temp file + fsync + replace to avoid corruption on crash.
- **C2** — Replay CLI import fix: missing `import sys` added so `sys.exit()` works in replay CLI.
- **C3** — O(1) append using segment metadata: `segment_meta.json` (or equivalent) per shard family; no line counting on each append.
- **C4** — Streaming segmented reads: `_read_segmented()` uses a single-pass streaming approach instead of O(N²) two-pass.

### Critical Replay (CR-1–CR-3)

- **CR-1** — Atomic shard metadata writes for replay-related metadata.
- **CR-2** — Integrity file corruption tolerance: `_get_last_hash()` handles read/parse errors and returns `None` instead of crashing.
- **CR-3** — Replay hash verification fix: step hash is computed from the record **without** the `step_hash` field to avoid self-referential verification failure.

### Important (M-1, M-3)

- **M-3** — Security monitor paths correction: `CRITICAL_FILES` and `PROTECTED_WRITE_FILES` reference `memory/dsm/core/` (and `memory/dsm/cli.py`) instead of `dsm_v2/core/`.
- **M-1** — Replay statistics correction: `verified_records = len(records) - broken_chain_count` (corrupt_count is not subtracted because corrupt records are not in `records`).

---

## 3) Kernel guarantees

The DSM kernel provides the following guarantees:

| Guarantee | Description |
|-----------|-------------|
| **Append-only storage** | Entries are appended to segment files; existing content is never modified or deleted. |
| **Atomic integrity writes** | Last-hash and shard metadata files are written via temp file + fsync + replace to avoid partial writes on crash. |
| **Hash chain integrity** | Each entry carries a hash of its content and `prev_hash`; chains can be verified and replayed. |
| **Segmented log storage** | Shards may be split into segments with rotation; segment metadata enables O(1) active segment resolution. |
| **Crash-safe metadata updates** | Segment and shard metadata updates use atomic write patterns. |
| **Replay verification capability** | Trace logs can be replayed and verified (hash and chain) in audit-only mode. |

---

## 4) Known acceptable limitations

The following are **known design characteristics**, not bugs. They are accepted for the frozen kernel:

- **Micro window between entry fsync and hash commit** — A crash in the short window after appending an entry but before committing the new last hash to the integrity file may create a detectable chain break (e.g. last hash on disk does not match last entry). Recovery or reconciliation may be needed outside the kernel.
- **entry_count metadata may drift under concurrent writers** — If multiple processes append to the same shard, the stored `entry_count` (or equivalent) in metadata may not be exact; it is intended for optimization (e.g. O(1) active segment), not as a single source of truth.
- **Replay tool loads full trace file into memory** — The current replay implementation reads and parses the trace file; very large traces may require future streaming or chunked handling.

---

## 5) Post-freeze roadmap

Future work is expected **outside** the frozen kernel or in separate modules:

- **DSM-RR (Read Relay)** — Query and read-relay layer built on top of the kernel (see RR architecture docs).
- **Higher-level agent memory tools** — Session graphs, agent-facing APIs, and tooling that use the kernel as storage.
- **Improved replay streaming** — Replay that does not load the full trace into memory (e.g. streaming or iterator-based).

Kernel changes themselves will follow the DSM kernel evolution process and must preserve the guarantees listed above.

---

*Freeze date: March 2026. See `memory/dsm/core/KERNEL_VERSION` for version and freeze date.*
