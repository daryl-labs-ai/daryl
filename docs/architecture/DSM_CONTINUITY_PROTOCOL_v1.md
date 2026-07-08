# DSM Continuity Protocol v1.0 — Specification

**Status:** SPECIFICATION (pre-implementation)
**Date:** 2026-07-08
**Governs:** every tool that wants to participate in project continuity
**Analogy:** Git clients differ, but all speak the Git protocol. Tools
differ, but all speak the Continuity Protocol.

---

## What this protocol is

The DSM Continuity Protocol defines **how a project maintains its memory
across changing tools, models, and agents**. It is not an LLM API. It does
not answer *"how do I call a model?"*. It answers:

> **"How does a project continue when the model working on it changes?"**

Every tool that implements this protocol — Claude, ChatGPT, Cursor,
Zcode, LM Studio, any future IDE — can participate in project continuity.
The protocol is the standard. The implementations are the providers.

---

## The four primitives

Any tool implementing the Continuity Protocol must provide exactly these
four operations. Nothing more is required for compliance.

### 1. `catch_up(project_id) → ContextBundle`

Recover the full project state from DSM. Called by any actor before
starting work.

Returns:
- project integrity status (verified / tampered)
- total decision count
- all prior decisions (agent, action, content, timestamp)
- activity summary
- catch-up latency

**Contract:** the actor MUST call this before producing any work. If
integrity is not OK, the actor MUST refuse to continue.

### 2. `publish_receipt(project_id, agent_id, task, result) → Receipt`

Write a decision to the project's DSM shard and issue a verifiable receipt.

Returns:
- entry hash (content-addressed)
- receipt (portable proof that this agent produced this work)

**Contract:** the actor MUST publish after completing work. The receipt
is the proof that the actor participated.

### 3. `verify(project_id) → IntegrityReport`

Check the integrity of the project's entire memory.

Returns:
- status (OK / TAMPERED / TRUNCATED)
- entry count
- chain continuity

**Contract:** any actor MAY verify at any time. An auditor SHOULD verify
before trusting the project.

### 4. `project_context(project_id) → ProvenanceBlock`

Get a structured provenance block suitable for inclusion in an LLM prompt
or external report.

Returns:
- entry hashes
- source shards
- integrity assessment
- verification hint

**Contract:** this is the bridge between DSM and the LLM's context
window. It turns raw memory into prompt-ready context.

---

## Compliance levels

| Level | What it means | Example |
|-------|---------------|---------|
| **Full** | All 4 primitives, fully automated | Zcode (SDK), LM Studio (API) |
| **Assisted** | All 4 primitives, but catch_up/publish require human bridge | Claude Desktop (via MCP), ChatGPT (via clipboard) |
| **Read-only** | catch_up + verify + project_context only | An auditor or CI that checks but doesn't write |

A tool at any level participates in continuity. Full is the goal;
Assisted is acceptable for desktop apps without automation APIs.

---

## Naming convention

Implementations of this protocol are called **Continuity Providers**,
not "adapters".

| Name | Not this |
|------|----------|
| Claude Continuity Provider | ~~Claude Adapter~~ |
| LM Studio Continuity Provider | ~~LM Studio Adapter~~ |
| ChatGPT Continuity Provider | ~~ChatGPT Adapter~~ |

Rationale: you don't *connect* a tool to DSM. You make the tool
*compatible with the continuity protocol*. The tool implements the
protocol; DSM does not adapt to the tool.

---

## Protocol invariants

1. **Project-scoped.** All operations are scoped to a `project_id`. No
   cross-project leakage.
2. **Agent-attributed.** Every published receipt identifies its agent.
   No anonymous contributions.
3. **Integrity-checked.** Every `catch_up` verifies integrity before
   returning context. A corrupted project is never silently served.
4. **Receipt-backed.** Every contribution has a portable receipt. The
   receipt is the proof — it works outside the project, outside the
   tool, outside the machine.
5. **Model-agnostic.** The protocol says nothing about which model
   produced the work. It records *what* was done and *who* did it, not
   *which inference engine* was used.

---

## The first release: DSM Continuity Protocol v1.0

This release contains:

| Component | Status | Effort |
|-----------|--------|--------|
| Protocol specification | **This document** | Done |
| SDK (4 primitives) | `catch_up` + `publish_receipt` built and tested | ~1 day to finalize |
| MCP server (exposes primitives over MCP) | Existing server + 2 new tools | ~1 day |
| Claude Continuity Provider | Not built | ~2 days |
| LM Studio Continuity Provider | **Built and tested** (Hot Swap MVP) | Done |
| Zcode Continuity Provider | **Built and tested** (Hot Swap MVP) | Done |
| Hot Swap video (3 real actors) | Not recorded | After Claude provider |

The kernel barely changes. This is a protocol + exposure release, not a
kernel release.

---

## What the protocol standardizes (and what it doesn't)

**Standardizes:**
- How a tool recovers project context
- How a tool publishes its work
- How a tool verifies project integrity
- The receipt format (portable proof of participation)

**Does NOT standardize:**
- How the tool calls its LLM
- How the tool renders its UI
- How the tool stores its own internal state
- Which model the tool uses

The protocol is the narrow waist. Everything above it (model, UI, tool)
is free. Everything below it (kernel, hash chain, storage) is frozen.
The protocol is the contract between them.

---

## The analogy stated explicitly

> Git clients differ (GitHub Desktop, CLI, lazygit, VS Code extension),
> but all speak the Git protocol. You can switch clients mid-project;
> the repository doesn't care.
>
> Continuity Providers differ (Claude, ChatGPT, Cursor, LM Studio), but
> all speak the Continuity Protocol. You can switch tools mid-project;
> the project memory doesn't care.

---

## The ambition

The industry standardized LLM APIs (OpenAI-compatible endpoints). That
solved *"how do I call a model?"*.

The DSM Continuity Protocol standardizes something else:

> **"How does a project continue when the model working on it changes?"**

If the Hot Swap becomes reproducible across Claude, Zcode, LM Studio,
ChatGPT, and Cursor — the protocol is not a Daryl feature. It is an
infrastructure standard for agent continuity.
