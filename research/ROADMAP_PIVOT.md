# Daryl — Platform Pivot Record

**Date:** 2026-07-08
**Trigger:** the 5-boucle R&D loop proved the kernel is no longer the
bottleneck. The frontier moved from *kernel vs features* to
*infrastructure vs connectors*.
**Status:** decision record, not a research document. The laboratory's
role is ending; the platform team's role is beginning.

---

## The pivot in one sentence

> **Stop building kernel. Start building connectors.**

The kernel is proven (6 research arcs, 5 boucles, 1732 tests, tamper-
detection verified, inter-agent continuity demonstrated). Continuing to
add kernel features before connecting it to real tools would be
optimising the engine without building the wheels.

---

## The four-module split

```
daryl-kernel          ← effectively frozen (kernel 1.0)
daryl-sdk             ← public API: catch_up, publish, verify, receipt
daryl-adapters        ← Claude, Cursor, GPT, Goose, GitHub, MCP
daryl-demo            ← Hot Swap, multi-machine, multi-developer
```

### Evolution rule

> The kernel evolves **only** when an adapter reveals a real limit.

No more kernel-first development. No more "wouldn't it be nice if the
kernel could X". Every kernel change must be traced to a concrete adapter
need, demonstrated in a real tool integration.

---

## The message evolution

**Architecture-level (what we built):**
> Le projet survit au remplacement de ses agents.

**Developer-level (what they feel):**
> Change d'outil quand tu veux. Le projet n'oublie pas.

Both are true. The first is the thesis. The second is the pitch. They
work at different altitudes for different audiences.

---

## The "Hello World" of Daryl

Not `print("Hello World")`. Not a 5-line quickstart.

The Daryl Hello World is the **Hot Swap**:

```
Claude works 10 min → Claude closed
Cursor opens → continues automatically → Cursor closed
GPT opens → continues automatically
GitHub Action → writes a receipt
Claude reopens → continues without being told the history
```

If a developer sees this in 60 seconds, they understand the value
without reading a single ADR. This is the demo that explains itself.

---

## The demo roadmap (proofs, not documents)

The era of R&D memos is ending. The era of demonstrations is beginning.

| Demo | Question it answers | Dependencies |
|------|---------------------|--------------|
| **#1 Hot Swap** | Does the project survive agent replacement? | catch_up() + Claude/Cursor/GPT adapters |
| **#2 Multi-machine** | Does it work across computers? | Remote storage backend |
| **#3 Multi-developer** | Alice → Bob → Agent — shared project memory? | Identity + sovereignty + adapters |
| **#4 LangGraph + DSM** | Verifiable checkpoints under a workflow engine? | LangGraph checkpoint saver adapter |
| **#5 MCP + DSM** | Agents over MCP can hand off with receipts? | MCP inter-agent tools (P2-01 memo) |
| **#6 GitHub Actions + DSM** | CI writes verifiable receipts? | GH Action adapter |

Each demo:
- answers exactly one question
- is reproducible
- runs in a few minutes
- requires no architecture explanation to understand

---

## The central question Daryl answers

Not: *"How do we make agents smarter?"*

But:

> **"Comment faire en sorte que l'intelligence reste attachée au projet
> plutôt qu'à l'outil qui l'a produite ?"**

This is the proposition that distinguishes Daryl from every product in
the competitive study. Mem0, Letta, LangGraph, Unsloth, DSPy — all bind
intelligence to their own substrate. Daryl binds intelligence to the
*project*, independent of which tool produced it.

That idea doesn't depend on a specific model, editor, or framework. It
depends on a verifiable, append-only, hash-chained memory that survives
every tool change. That is what the kernel provides. The connectors make
it real.

---

## Laboratory closure

This document marks the transition from research to platform building.

**What the laboratory produced (6 arcs, 30+ documents):**
- A proven, measured Operational Envelope
- A falsification-resistant architectural hypothesis (RTM, sealed)
- 6 competitive product studies across 5 categories
- A 5-boucle inter-agent validation
- The Capability Exposure governance principle
- The Hot Swap Test protocol

**What the laboratory does NOT do next:**
- Write more competitive memos (concluded: 5 categories, 0 provenance layers)
- Write more falsification arcs (RTM sealed, awaits terrain)
- Simulate more agent workflows (the kernel is proven; simulations add nothing)

**What happens next:**
- Build `catch_up()` (1 day)
- Build receipt replay protection (0.5 day)
- Build the first adapter (Claude or Cursor, ~2 days)
- Run Demo #1: the Hot Swap
- If it passes: the platform era begins

The laboratory's final contribution is this record: a clean handoff from
*"is the kernel sufficient?"* (yes, OBSERVED) to *"can real tools use
it?"* (unknown, requires building adapters).
