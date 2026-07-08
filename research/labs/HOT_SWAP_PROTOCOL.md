# The Hot Swap Test — Protocol Specification

**Status:** Protocol design. Not yet executed.
**Position:** This is the test that would demonstrate Daryl's core value
proposition without explaining the architecture. It is the natural next
step after the 5-boucle R&D loop proved the kernel works.

---

## Why this test exists

The 5-boucle loop proved the kernel can serve as common memory. But every
agent in that test was *simulated* — Python functions calling the DSM SDK
directly. No real agent was involved. No real tool adapter existed.

The Hot Swap Test answers a different question:

> **"If I replace the agent mid-project, does the project survive — without
> copy/paste, without shared history between tools, without manual context
> transfer?"**

If yes, that is a demo that explains itself. You don't need to describe
hash chains or append-only logs. You show: Claude works → Claude stops →
Cursor picks up → Cursor stops → GPT picks up → the project continued
seamlessly. The value is immediately visible.

---

## The scenario

```
09:00  Claude works on task A (writes decisions to DSM)
09:15  Claude is closed — its process is gone
09:16  Cursor opens, calls catch_up(), sees task A, continues with task B
09:25  Cursor is closed
09:26  GPT opens, calls catch_up(), sees tasks A+B, continues with task C
09:40  GitHub Action runs, writes a CI receipt to DSM
16:00  Claude reopens, calls catch_up(), sees A+B+C+CI, continues
```

**Constraints:**
- No copy/paste between tools
- No shared filesystem state beyond the DSM data directory
- No manual prompt beyond "continue the project" (the catch_up() call
  provides the context automatically)
- Each tool uses a DSM adapter to read and write

---

## What must exist before this test can run

The test cannot be run today. It requires building three things first.
Each is small. Together they form the **adapter SDK** the prior report
identified as the missing layer.

### 1. `catch_up(project_id)` — the context-recovery primitive

**What it does:** Returns a structured summary of the project state from
DSM, so a new agent can understand "what happened, what's next" in one call.

**What it wraps (all exist today):**
```python
def catch_up(storage, project_id):
    # 1. Verify integrity
    vr = verify_shard(storage, project_id)
    # 2. Read recent decisions
    recent = storage.read(project_id, limit=50)
    # 3. Build summary
    relay = DSMReadRelay(storage=storage)
    summary = relay.summary(project_id)
    # 4. Build provenance
    prov = build_provenance(items=[...], storage=storage)
    # 5. Return structured context
    return {
        "integrity": vr.status,
        "decisions": [...],
        "summary": summary,
        "provenance": prov,
        "next_steps": "infer from last entry",
    }
```

This is a **composition** of existing primitives, not new logic. It is the
product-level API that the Boucle 3 report identified as missing.

**Estimated effort:** Low (1 day). Wraps 4 existing calls into one.

### 2. DSM adapter protocol — the per-tool connector

**What it does:** A minimal interface each tool adapter implements:

```python
class DSMAdapter:
    def catch_up(self, project_id) -> dict
    def remember(self, project_id, agent_id, decision, action) -> str
    def verify(self, project_id) -> bool
    def issue_receipt(self, project_id, entry_id, task) -> dict
    def receive_receipt(self, receipt_json) -> dict
```

Each real tool (Claude, Cursor, GPT, GitHub Action) gets a thin adapter
that calls these. The adapter translates between the tool's native
extension model (Claude commands, Cursor rules, GPT functions, GH Actions)
and the DSM SDK.

**Estimated effort per adapter:** Medium (2-3 days each). The DSM side is
trivial; the tool-integration side depends on the tool's extension API.

### 3. Receipt replay protection — the one security gap

**What it does:** Prevents the same receipt from being accepted twice.

**What Boucle 2 found:** DSM detects mutation, truncation, forgery, and
deletion — but accepts a duplicated receipt without question. Before a
public demo (where someone will probe this), the replay gap should be
closed.

**Minimal fix:** A `seen_receipts` set (or shard) that tracks receipt IDs
that have been received. `receive_receipt` checks the set before accepting.
This is above the kernel — no kernel change needed.

**Estimated effort:** Low (half a day).

---

## What the test proves if it passes

1. **Project survival across agent replacement.** The project's decisions,
   history, and integrity survive the agent being swapped. This is the
   visible value proposition.
2. **No copy/paste.** No human manually transferred context between tools.
   DSM was the sole channel.
3. **Verifiable continuity.** Every transition is receipt-backed. An
   auditor can replay the chain and verify who did what.

## What the test does NOT prove

- It does not prove the agents produce *correct* work (DSM records
  decisions, not correctness).
- It does not prove cross-machine operation (same-machine only until remote
  storage exists).
- It does not prove the adapters are production-ready (they are demo-level
  connectors, not hardened integrations).

---

## Execution plan (if approved)

| Phase | What | Effort | Output |
|-------|------|--------|--------|
| 1 | Build `catch_up()` primitive | 1 day | One-call context recovery |
| 2 | Build receipt replay protection | 0.5 day | Seen-receipts tracking |
| 3 | Build minimal Claude adapter | 2 days | Claude can read/write DSM |
| 4 | Build minimal Cursor adapter | 2 days | Cursor can read/write DSM |
| 5 | Build minimal GPT adapter | 2 days | GPT can read/write DSM |
| 6 | Build GitHub Action adapter | 1 day | GH Action writes CI receipts |
| 7 | Run the Hot Swap Test | 1 day | The demo |
| **Total** | | **~9.5 days** | |

Phases 1-2 are prerequisites. Phases 3-6 can run in parallel. Phase 7 is
the test itself.

---

## Why this is the right next step

The competitive study proved no other product provides verifiable
provenance. The 5-boucle R&D loop proved the kernel works as common memory.
The product gap scan proved Daryl has the primitives but doesn't expose
them. The Hot Swap Test is the convergence point: it takes the proven
kernel, adds the minimal exposure layer (catch_up + adapters), and
demonstrates the value proposition in a scenario anyone can understand.

It is not a benchmark. It is not a simulation. It is the smallest
demonstration that proves *"the project survives the replacement of its
agents"* — and that is the sentence that explains why Daryl exists.

---

## Relationship to prior research

| Prior artefact | What it proved | What this test adds |
|----------------|----------------|---------------------|
| Operational Envelope (2026-OrchestratedMemory) | DSM's measured limits | Tests the limits in a real workflow |
| Competitive study (6 products) | No competitor has provenance | Shows provenance working across tools |
| 5-boucle R&D loop | Kernel works as common memory | Proves it with real tool adapters |
| Product gap scan (P2-01 etc.) | Primitives exist but are hidden | Exposes them via catch_up() + adapters |
| Capability Exposure principle | Every hidden capacity needs a reason | catch_up() is the first deliberate exposure |

The Hot Swap Test is where all prior research converges into a single
demonstration. It is the test that would make Daryl's value visible
without explaining the architecture.
