# DSM Future Architecture

## Purpose

This document records **future architectural ideas** for DSM (Daryl Sharding Memory). It is a roadmap of potential enhancements and long-term vision. **No current implementation is changed** by this document; it exists so that ideas are not forgotten while development continues on the stable kernel and experimental layers.

---

## Current DSM Architecture

- **Kernel**: `memory/dsm/core/`
  - Storage (append-only JSONL, segment manager), models (Entry, ShardMeta), signing/hash chain, session tracking, replay, security.
- **Storage API**: One entry per append; hash chain per shard; segments by size/count.
- **Stable**: The core must remain unchanged for production and compatibility.

---

## Experimental Block Layer

An **experimental block aggregation layer** already exists at:

**`memory/dsm/block_layer`**

It provides:

- **BlockManager**: Buffers multiple `Entry` objects and, when the buffer reaches a configurable block size, flushes them as **one** record through the DSM Storage API.
- **No core changes**: It uses only the public Storage API (`Storage.append`, `Storage.read`, segment manager iteration). The core remains untouched.
- **Append-only semantics**: Each block is appended as a single `Entry` whose `content` is JSON: `{"block": true, "entries": [...]}`. The existing hash chain and append-only guarantees are preserved.
- **Separate shards**: Block mode writes to shards with a `_block` suffix (e.g. `sessions_block`), so classic (one entry per line) and block mode can coexist and be compared.

See `memory/dsm/block_layer/README.md` for usage and design details.

---

## Benchmark Strategy

- **Classic mode**: One `Storage.append(entry)` per entry.
- **Block mode**: Buffer N entries, then one `Storage.append(block_entry)` per block (N entries per append).
- The script `memory/dsm/block_layer/benchmark.py` compares both modes (e.g. 500 entries, varying block sizes). Run with:
  ```bash
  PYTHONPATH=/opt/daryl python3 -m dsm_v2.block_layer.benchmark
  ```
- Benchmarking validates that block aggregation improves throughput while preserving semantics, and guides future block-related work.

---

## DSM Read Relay (DSM-RR)

A **read-only relay layer** exists at:

**`memory/dsm/rr`**

### Current DSM-RR capabilities

- **Read-only**: Uses only the DSM Storage API (`Storage.read()`). No writes; no modifications to the core.
- **DSMReadRelay**:
  - **`read_recent(shard_id, limit=100)`**: Returns the most recent entries from the shard. Works with both classic shards and block shards (expands block-format entries in memory after reading).
  - **`summary(shard_id, limit=500)`**: Lightweight activity summary:
    - `entry_count`: number of entries (after expanding blocks)
    - `unique_sessions`: number of distinct `session_id`
    - `errors`: count of entries where `metadata["error"]` is set
    - `top_actions`: top 10 most frequent `metadata["action_name"]` (via `collections.Counter`)
- **Compatibility**: Relies only on `Storage.read()`, so it works with classic shards and future block shards without parsing storage files directly. Block shards are supported by expanding block payloads in memory.
- **Integration test**: `tests/dsm_rr_test.py`.

Example:

```python
from dsm_v2.rr import DSMReadRelay
rr = DSMReadRelay(data_dir="/path/to/data")
summary = rr.summary("clawdbot_sessions")
print(summary)
entries = rr.read_recent("clawdbot_sessions", limit=100)
```

This is **Step 1 of DSM-RR evolution**: minimal read relay for reading shards and summarizing activity, without touching the DSM kernel.

### DSM-RR Implementation Status

DSM-RR is **planned** in HEARTBEAT.md as part of the Daryl/DSM architecture. A **minimal experimental implementation** already exists and lives in **`memory/dsm/rr`**. It provides basic navigation capabilities as **Step 1** toward the full DSM-RR module, not the complete module.

**Current capabilities:**

- `read_recent(shard_id, limit)` — return the most recent entries from a shard.
- `summary(shard_id, limit)` — lightweight activity summary (entry count, unique sessions, errors, top actions).

**Purpose:**

- Inspect shard activity without parsing storage files manually.
- Generate simple summaries for monitoring and debugging.
- Rely only on the Storage API.

**Future capabilities planned (not yet implemented):**

- `reconstruct_session(session_id)` — rebuild a session from entries.
- RR query engine — structured queries over shard data.
- Minimal index — faster lookups by session or time range.
- Context pack generation for agents — prepared context from DSM for LLM/agent use.

**Important:** This implementation is **read-only** and uses only **`Storage.read()`**. It does not write to shards or modify the DSM core.

---

## Possible Future Enhancements

The following are **ideas only**. They would be implemented in layers above the core (e.g. in `block_layer` or new packages), not inside `memory/dsm/core`.

### Block Hashing

- **block_hash**: Hash of the entire block payload (e.g. serialized entries).
- **entries_hash**: Aggregate hash of all entry hashes in the block (e.g. hash of concatenated entry hashes).
- **previous_block_hash**: Link each block to the previous one, forming a **block-level hash chain** in addition to the existing entry-level chain.
- Purpose: Integrity at block granularity; fast verification of block order and content without expanding entries.

### Merkle Trees

- Build a **Merkle tree** over the entries in a block; store or derive the **merkle root** (e.g. in block metadata).
- **Purpose**: O(log n) verification — prove inclusion of a single entry in a block without reading the whole block; support proofs and sparse verification.

### Block Compression

- **msgpack**: Serialize block payload with MessagePack instead of JSON to reduce size and parsing cost.
- **zstd**: Compress the block payload (e.g. after msgpack or JSON) before appending; decompress when reading. Reduces I/O and storage.
- Both would be optional and implemented in the block layer; the core would still see opaque content if needed, or the layer would decompress before exposing entries.

### Block Index

- **block_id → file offset**: Maintain an index (e.g. separate file or sidecar) mapping block identifiers to byte offsets in the segment files.
- Purpose: Random access to a block by ID without scanning; faster range reads and verification.

---

## Long Term Vision

- **Stable kernel**: `memory/dsm/core` remains the single source of truth for storage, models, signing, and replay. All new features (blocks, compression, indexing, Merkle proofs) live in **layers above the core**.
- **Pluggable layers**: Block layer, compression, and indexing as optional layers that use the Storage API and, where useful, build on each other (e.g. block layer + block hashing + block index).
- **Verification and audit**: Block hashes and Merkle roots enable efficient integrity checks and entry-inclusion proofs without changing core replay or storage format.
- **Performance and scale**: Block aggregation, compression, and indexing aim to improve throughput and reduce I/O while preserving append-only semantics and compatibility with existing tooling.

---

## Important Rule

**`memory/dsm/core` must remain unchanged.**

All experimental and future work (block aggregation, block hashing, Merkle trees, compression, block index) must be implemented in **layers above the core**. The core API (Storage, Entry, segment manager, hash chain) is the contract; layers consume it and do not modify it.

---

## Current Priority

- Keep the DSM kernel stable and in production use.
- Develop and benchmark the existing block layer (`memory/dsm/block_layer`) without changing the core.
- Use the DSM Read Relay (`memory/dsm/rr`) for read-only shard access and summaries; extend RR in layers above the core.
- Use this document and the roadmap to revisit future enhancements (block hashing, Merkle trees, compression, index) when capacity allows.

---

*See also: [Roadmap index](roadmap/README.md) for references to this and other planning documents. [DSM_MEMORY_LEDGER.md](DSM_MEMORY_LEDGER.md) — long-term vision of DSM as a Memory Ledger for AI agents.*
