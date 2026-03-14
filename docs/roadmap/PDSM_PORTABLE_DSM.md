# PDSM — Portable DSM (Personal / Portable Distributed Sharding Memory)

**This document is a concept document only.** It describes a potential future project idea. It does not introduce implementation tasks or require changes to the DSM kernel.

---

## 1. Concept

A **Portable DSM (PDSM)** is a personal instance of DSM that can be moved between machines and used by multiple agents. It packages the DSM storage structure (shards, integrity data, optional index and session metadata) into a portable layout so that agent memory and context can travel with the user or be shared across environments without rewriting the DSM kernel.

---

## 2. Goals

- **Portable agent memory:** Carry a consistent memory store across devices or runtimes.
- **Persistent context across machines:** Resume work or reasoning with the same history on a different host.
- **Shared memory for multi-agent systems:** Allow several agents to read from (and, where designed, append to) the same portable store.
- **Deterministic replayable history:** Preserve append-only, hash-chain semantics so that history remains verifiable and replayable wherever the portable instance is used.

---

## 3. Basic Structure

Example directory layout for a portable instance:

```
pdsm/
  shards/        # Append-only shard data (segment files or monolithic JSONL per shard)
  blocks/        # Optional block-layer storage if block format is used
  index/         # Optional RR index/cache (catalog, query cache — regenerable)
  sessions/      # Optional session metadata or manifests
  signatures/    # Integrity: hash chain state, optional signatures
  manifest.json  # Descriptor: version, created_at, schema hint, optional checksums
```

**Brief role of each:**

- **shards/** — Core ledger data; append-only entries per shard (same semantics as DSM kernel).
- **blocks/** — Optional block-format storage if the instance uses a block layer; still append-only.
- **index/** — Optional index and query cache (e.g. ShardCatalog, query_cache); regenerable from shards.
- **sessions/** — Optional session manifests or metadata for discovery and replay.
- **signatures/** — Integrity state (e.g. last hash per shard, optional signing metadata); supports verification and replay.
- **manifest.json** — Describes the portable instance (format version, creation time, optional checksums) for validation and tooling.

---

## 4. Use Cases

- **Personal AI memory:** One portable store that follows the user across devices.
- **Migrating agents between machines:** Move the PDSM directory (or a snapshot) to another host and resume with the same history.
- **Multi-agent collaboration:** Several agents share one PDSM instance (read-only or append-only by design) for a common context.
- **Reproducible agent behavior:** Replay or audit agent decisions using the same portable history on different runs or machines.

---

## 5. Relationship with DSM

**PDSM is not a modification of the DSM kernel.**

It is a **portable instance** of the DSM storage structure: the same append-only, shard-based, hash-chain model, packaged so it can be copied or moved. Implementations would consume the existing DSM Storage API (or a compatible reader) and would not change `memory/dsm/core`. PDSM is a packaging and deployment idea, not a kernel redesign.

---

## 6. Status

**Status:** Concept / future project  
**Priority:** Low (after RR integration and kernel stabilization)

No implementation is planned by this document. This is a direction for later consideration.

---

## 7. References

- [DSM_MEMORY_LEDGER.md](../DSM_MEMORY_LEDGER.md) — Long-term vision of DSM as a Memory Ledger for AI agents.
- [DSM_FUTURE_ARCHITECTURE.md](../DSM_FUTURE_ARCHITECTURE.md) — Future architectural ideas (block layer, RR, hashing, compression, index).
- [LAB_TO_DARYL_MIGRATION_PLAN.md](../LAB_TO_DARYL_MIGRATION_PLAN.md) — Lab-to-Daryl migration and RR integration strategy.
