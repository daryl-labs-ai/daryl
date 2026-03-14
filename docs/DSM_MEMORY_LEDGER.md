# DSM Memory Ledger — Vision Document

**Status:** Concept note / long-term vision. This document is for **architectural memory only**. It does not define implementation tasks or require changes to the DSM kernel.

---

## Purpose

DSM (Daryl Sharding Memory) can be thought of, in the long term, as a **Memory Ledger** for AI agents: a durable, append-only record of what happened, with integrity and replay guarantees, on which agents and humans can rely.

This vision document is a **reminder for future architecture discussions**. It does not propose modifications to the current DSM kernel or mandate any implementation.

---

## Vision: DSM as a Memory Ledger

- **Ledger:** An append-only, tamper-evident record. Entries are ordered; the hash chain preserves integrity. No rewriting of history.
- **Memory:** The ledger holds agent and system events (sessions, tool calls, snapshots, decisions) in shards. Shards can be segmented and scaled.
- **For AI agents:** Agents (and operators) read from the ledger to understand context, replay traces, and build summaries or context packs—without ever modifying the kernel. The kernel remains the single source of truth.

Principles that this vision preserves and that the current architecture already reflects:

- **Kernel stability:** The DSM core (`memory/dsm/core`) is the stable foundation. New capabilities (RR, RM, block layer, index, context packs) are built as **layers above** the core, using only the public Storage API.
- **Append-only:** Shards are never rewritten. Append-only semantics are preserved for the lifetime of the ledger.
- **Read-only layers:** DSM-RR and any future navigation, index, or context-pack logic **read** from the ledger; they do not write to shards or alter kernel state. Optional caches (e.g. under `data/index/`) are regenerable and never replace the ledger.

---

## Long-Term Ideas (Concept Only)

- **Multi-agent ledger:** Multiple agents or runtimes appending to the same or different shards, with clear attribution (session_id, source).
- **Verifiable history:** Hash chain and optional Merkle structures (as in DSM_FUTURE_ARCHITECTURE.md) support verification and audit without kernel change.
- **Context and recall:** RR, context packs, and optional indexing allow agents to “recall” relevant slices of the ledger for reasoning—always via the Storage API, never by bypassing the kernel.

None of these ideas require changing the DSM kernel. They are directions for layers and tooling built on top of the existing Storage API and append-only model.

---

## Important Reminders

- This document is **not** an implementation specification. It is a **vision** for long-term architectural memory.
- The DSM kernel (`memory/dsm/core`) must remain **unchanged** by this vision. All evolution happens in layers above the core.
- Append-only and kernel stability are **non-negotiable** principles of the DSM Memory Ledger.

---

*See also: [DSM_FUTURE_ARCHITECTURE.md](DSM_FUTURE_ARCHITECTURE.md), [RR_INTEGRATION_SPEC.md](RR_INTEGRATION_SPEC.md), [Roadmap](roadmap/README.md).*
