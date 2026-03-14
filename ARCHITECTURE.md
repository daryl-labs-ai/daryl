# Daryl Architecture

This document describes the main components of Daryl. The **DSM kernel is frozen** as of March 2026; see [docs/architecture/DSM_KERNEL_FREEZE_2026_03.md](docs/architecture/DSM_KERNEL_FREEZE_2026_03.md) for details.

## Component overview

```
Agents
  ↓
Skills / Sessions
  ↓
RR / ANS
  ↓
DSM Core (append-only, frozen)
```

- **Agents**: Consume memory (via RR) and write events (via Sessions); use Skills for task routing and execution.
- **Skills**: Registry and router for matching task descriptions to skills; optional usage/success telemetry (separate from DSM kernel).
- **Sessions**: `SessionGraph` orchestrates session lifecycle (start, snapshots, tool calls, end) and writes to the `sessions` shard with rate limits and safeguards.
- **RR (Read Relay)**: Read-only layer over DSM storage. Uses only `Storage.read()`; does not write to shards. Provides recent entries and lightweight summaries. Compatible with classic and block shards.
- **ANS (Adaptive Navigation System)**: Analyzes skill performance (usage/success logs), produces rankings and workflow recommendations. Optional RR-based analysis for agent-level insights.
- **DSM Core**: Append-only storage, entry model, shard segments, hash chaining. **Frozen** — no changes without discussion and approval.

## DSM Core (frozen kernel)

- **Storage**: Append entries, read recent entries by shard, list shards. No update/delete.
- **Models**: `Entry`, `ShardMeta` (and related).
- **Segments**: Shard segmentation and file layout.

The kernel is frozen since March 2026. Do not modify `src/dsm/core/` without explicit approval.

## Repository layout

- `src/dsm/core/` — DSM kernel (frozen).
- `src/dsm/session/` — SessionGraph, SessionLimitsManager.
- `src/dsm/rr/` — Read Relay (DSMReadRelay).
- `src/dsm/ans/` — ANS engine and analyzers.
- `src/dsm/skills/` — Registry, router, ingestor, models.
- `tests/` — Test suite.
