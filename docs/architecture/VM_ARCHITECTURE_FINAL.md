# VM Architecture — Final Reference

**Phase 2 — Documentation only.** No code changes, no file moves, no refactoring.

Reference documents: VM_STRUCTURE_AUDIT.md, VM_ORGANIZATION_TODO.md, REPO_HYGIENE_REPORT.md.

---

## 1. DSM Repository Structure

The **canonical DSM repository** is located at:

**`/opt/daryl`**

It is the **only** location on the VM that contains the full DSM kernel layout. All development of the official kernel happens here.

### Directory layout

```
/opt/daryl/
├── memory/dsm/
│   ├── core/          # DSM kernel — storage, models, integrity
│   ├── session/       # Session lifecycle (SessionGraph, limits)
│   ├── rr/            # Read Relay — memory navigation
│   ├── block_layer/   # Optional entry batching (experimental)
│   ├── ans/           # Audience / skill performance analysis
│   ├── skills/        # Skill registry, router, telemetry
│   ├── modules/       # Optional modules (e.g. dsm_rm)
│   ├── storage/       # Storage package facade
│   └── moltbook/      # Moltbook integration
├── docs/
├── tests/
├── pyproject.toml
└── ...
```

### Role of each component

| Component | Path | Role |
|-----------|------|------|
| **core** | `memory/dsm/core/` | **DSM kernel.** Append-only storage API (`Storage.append`, `Storage.read`, `list_shards`), models (`Entry`, `ShardMeta`), segment files, hash chaining, signing, replay, security (baseline, audit, protected files). No search, no indexing — minimal persistence and integrity. |
| **session** | `memory/dsm/session/` | **Session layer.** `SessionGraph`: start_session, record_snapshot, execute_action, end_session. Writes to the `sessions` shard. `SessionLimitsManager`: cooldowns, action budgets. Depends only on core Storage API. |
| **rr** | `memory/dsm/rr/` | **Read Relay.** Read-only memory navigation above the kernel. `DSMReadRelay`: read_recent(shard, limit), summary(shard, limit). Uses only `Storage.read()`. No writes to shards. |
| **block_layer** | `memory/dsm/block_layer/` | **Optional batching.** `BlockManager` buffers entries and flushes them as blocks via the Storage API. Uses shards with a `_block` suffix. Experimental; does not modify core. |
| **ans** | `memory/dsm/ans/` | **Audience Neural System.** Analysis of skill usage and success telemetry: load usage/success events, compute skill/transition performance, `ANSEngine`. Consumes skills logs; separate from kernel. |

**Kernel boundary:** Only `memory/dsm/core/` (storage, models, shard_segments, signing, replay, security) is the frozen kernel. Session, rr, block_layer, ans, skills, and modules are **layers above** the kernel and must use only the public Storage API.

---

## 2. Daryl Laboratory

The **Daryl laboratory** is located at:

**`~/clawd`** (e.g. `/home/buraluxtr/clawd`)

### Purpose

This directory is used for:

- **Agent experiments** — Trying new behaviors, integrations, and workflows.
- **Scripts** — One-off and utility scripts (e.g. dsm_*.py, fix_*.py, moltbook_*.py, apply_*).
- **Clawdbot integrations** — Telegram, Moltbook, feeds, and bot runtime.
- **Prototypes** — Early versions of features before they are proposed for the official DSM repo.

### Important

**The laboratory is NOT part of the official DSM repository.**

- `/opt/daryl` is the **single source of truth** for the DSM kernel.
- `~/clawd` may contain a **partial copy** of DSM code (e.g. `dsm_v2/` with core, session, ans, skills — but typically **no** rr, **no** block_layer).
- Experiments, data, and logs under `~/clawd` stay in the lab; they are not committed to `/opt/daryl`.
- The official repo may reference the lab (e.g. `agents/clawdbot/runtime` → `~/clawd`) for agent runtime only; the kernel itself lives only in `/opt/daryl`.

---

## 3. Runtime Memory

Runtime storage for shards, logs, and runtime state is located at:

**`~/memory`** (e.g. `/home/buraluxtr/memory`)

### Rules

- **Shards, logs, and runtime state must always remain outside the repository.**
- `/opt/daryl` must **not** track runtime data: no `data/`, no `memory/dsm/core/data/`, no `*.jsonl` logs in Git (see REPO_HYGIENE_REPORT.md).
- Runtime data may also exist under `~/clawd/data`, `~/clawd/dsm_v2/data`, `~/clawd/dsm_v2/logs`, or `~/clawdbot_dsm_test` for lab and test use; none of these are part of the DSM repo.
- Using a single canonical runtime root (e.g. `~/memory`) for production or shared agents keeps the separation clear.

---

## 4. Development Workflow

| Step | Location | Action |
|------|----------|--------|
| **Edit code** | `/opt/daryl` | All changes to the DSM kernel and official layers (core, session, rr, block_layer, ans, skills) are made in the canonical repo. |
| **Test agents** | `~/clawd` | Run and test agents, scripts, and integrations in the laboratory. Use lab copies or point to `/opt/daryl` (e.g. via `pip install -e /opt/daryl`) as needed. |
| **Runtime memory** | `~/memory` | Shards, logs, and runtime state are written here (or to lab paths) and never committed to the repo. |

Flow:

```
edit code → /opt/daryl
test agents → ~/clawd
runtime memory → ~/memory
```

---

## 5. Final Architecture Map

High-level view of the VM after organization (Phase 1 hygiene applied; documentation finalized in Phase 2).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  VM ARCHITECTURE                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  DSM REPOSITORY (canonical)                                               │
  │  /opt/daryl                                                              │
  │  • memory/dsm: core, session, rr, block_layer, ans, skills, modules      │
  │  • docs, tests, pyproject.toml                                           │
  │  • Single source of truth for the DSM kernel                             │
  │  • No tracked runtime: data/, logs/, caches ignored                       │
  └─────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  DARYL LABORATORY                                                       │
  │  ~/clawd                                                                │
  │  • Agent experiments, scripts, Clawdbot, Moltbook, prototypes           │
  │  • Optional partial DSM copy (dsm_v2, dsm_modules)                      │
  │  • NOT part of the official DSM repository                              │
  └─────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  RUNTIME MEMORY                                                         │
  │  ~/memory                                                               │
  │  • Shards, logs, runtime state                                          │
  │  • Always outside the repository                                        │
  └─────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  EXPERIMENTAL PROJECTS                                                  │
  │  ~/dsm_staging_repo_2 (and similar)                                     │
  │  • Separate repos (e.g. slot normalizer, custom dsm_kernel/dsm_modules) │
  │  • Different layout; not the canonical DSM                               │
  └─────────────────────────────────────────────────────────────────────────┘
```

### Summary table

| Zone | Path | Role |
|------|------|------|
| **DSM Repository** | `/opt/daryl` | Canonical kernel and layers; edit and version here. |
| **Daryl Laboratory** | `~/clawd` | Experiments, scripts, agents; not the official repo. |
| **Runtime Memory** | `~/memory` | Shards and logs; never in Git. |
| **Experimental Projects** | `~/dsm_staging_repo_2` | Other projects; separate from Daryl DSM. |

---

*This document is the final architecture reference for the VM. It does not replace VM_STRUCTURE_AUDIT.md or VM_ORGANIZATION_TODO.md; it consolidates the target view and workflow for daily use.*
