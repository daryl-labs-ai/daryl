# DARYL PLATFORM ROADMAP

**Status:** The kernel is proven. The research lab is closed. This is the
platform plan.
**Governing principle:** The Hot Swap is not just a demo — it is the
acceptance test for the entire platform. Every phase exists to make it
pass. Every adapter exists because the Hot Swap requires it.

---

## The two sentences

**For developers (the pitch):**

> Change d'outil quand tu veux. Le projet n'oublie pas.

**For architects (the design):**

> Daryl déplace la continuité du projet hors des outils qui le manipulent.

Both are true. Both describe the same system from different altitudes.
Neither is marketing — both are testable claims that the platform exists
to validate.

---

## Phase sequence

Each phase has exactly **one observable validation criterion**. A phase is
not "done" until its criterion is met. No phase begins until the previous
criterion passes.

### Phase 1 — Kernel ✓ DONE

**Criterion:** The kernel provides append-only, hash-chained, tamper-
detectable storage with receipts, dispatch, attestation, identity, and
verification.

**Evidence:** 1732 tests passing. 6 research arcs. 5-boucle inter-agent
validation. Kernel 1.0 frozen since 2026-03-14. Zero modifications across
all research.

**Status:** CLOSED. The kernel evolves only when an adapter (Phase 5+)
reveals a concrete limit.

---

### Phase 2 — Research ✓ DONE

**Criterion:** Sufficient uncertainty reduced to know that the next
knowledge comes from integrations, not hypotheses.

**Evidence:** 26 research documents across 6 arcs:
- Operational Envelope (measured limits of the real system)
- RTM (falsification-resistant architectural hypothesis, sealed)
- 6 competitive studies (5 categories, 0 provenance layers found)
- 5-boucle inter-agent validation (continuity + tamper detection)
- Capability Exposure principle + product gap scans
- Hot Swap protocol design

**Status:** CLOSED. The lab produced what a lab can: reduced uncertainty
to the point where the remaining questions require real tools, not more
paper.

---

### Phase 3 — Hot Swap Protocol → CURRENT

**Criterion:** A working `catch_up()` primitive + receipt replay protection,
demonstrated via a scripted multi-agent handoff (no real adapters yet, but
the protocol runs end-to-end with simulated tools).

**Deliverables:**
- `catch_up(project_id)` — one-call context recovery (wraps verify + read + summary + provenance)
- Receipt replay protection — seen-receipts tracking
- A runnable Hot Swap script that demonstrates the full cycle

**Effort:** ~1.5 days
**Rule:** This phase defines the API contract that all adapters must implement.
The adapters are built *for* this test, not the other way around.

---

### Phase 4 — SDK

**Criterion:** A clean public API package (`daryl-sdk`) with 4 methods:

```python
daryl.catch_up(project_id)          → structured project context
daryl.remember(project_id, decision) → entry hash (receipt)
daryl.verify(project_id)            → integrity status
daryl.handoff(receipt)              → receipt verification + storage
```

**Deliverables:**
- `daryl-sdk` package (thin wrapper over existing primitives)
- Documentation: 4 methods, one page
- The "Hello World" is the Hot Swap from Phase 3

**Effort:** ~2 days
**Rule:** The SDK exposes only what the Hot Swap needs. Nothing more. If
a method doesn't serve the Hot Swap, it doesn't go in the SDK yet.

---

### Phase 5 — Claude Adapter

**Criterion:** Claude Code can read project context from DSM and write
decisions back, via the SDK.

**Validation:** Claude works on a task → closes → DSM has the decisions →
reopens → Claude reads `catch_up()` and continues.

**Effort:** ~2 days
**Acceptance test:** Does the Hot Swap work with Claude as one of the agents?

---

### Phase 6 — Cursor Adapter

**Criterion:** Cursor can read project context from DSM and write decisions
back, via the SDK.

**Validation:** Same as Phase 5, with Cursor.

**Effort:** ~2 days
**Acceptance test:** Does the Hot Swap work with Claude → Cursor?

---

### Phase 7 — GPT Adapter

**Criterion:** GPT (ChatGPT or API) can read project context from DSM and
write decisions back.

**Validation:** Same as Phase 5, with GPT.

**Effort:** ~2 days
**Acceptance test:** Does the full Hot Swap work? Claude → Cursor → GPT →
GitHub Action → Claude returns.

---

### Phase 8 — Public Demo

**Criterion:** The Hot Swap runs end-to-end with real tools, recorded as a
< 2 minute video that requires zero architecture explanation.

**Validation:** A developer who has never seen Daryl watches the video and
says: "I understand — the project survives changing tools."

**Acceptance test:** Show it to 3 people who don't know Daryl. If they
understand the value proposition without explanation, it passes.

---

## The governing rule

> **Every phase, every adapter, every SDK method must answer one question:
> "Does this make the Hot Swap work?"**
>
> If yes, build it. If no, defer it.

The Hot Swap is not a demo among demos. It is the acceptance test for the
entire platform. It is the "Hello World" that explains Daryl in 60 seconds.
Everything between Phase 3 and Phase 8 exists to make it pass with real tools.

---

## What the kernel freeze means in practice

The kernel (Phase 1) is closed. It does not reopen unless:

1. An adapter (Phases 5-7) hits a concrete limit that cannot be worked
   around at the SDK or adapter layer, AND
2. The limit is demonstrated (not hypothesised), AND
3. The fix is scoped to the minimal change that unblocks the adapter.

No "improvements". No "while we're in there". No opportunistic features.
The kernel served the lab for 6 arcs without modification. It will serve
the platform the same way.

---

## What this document replaces

This document supersedes:
- All research program statuses (they are CLOSED or SEALED)
- All competitive memos (concluded: the gap is universal)
- All product gap scans (the gaps are now exposed via the SDK, not via memos)
- All R&D loop reports (the kernel is proven; the loops are done)

The research artefacts remain in `research/` as an archive of how the
uncertainty was reduced. They are no longer the active steering documents.
This roadmap is.

---

## The transition, stated plainly

The question was: *"Is the kernel sufficient?"*
The answer is: **Yes, observed.**

The question is now: *"Can real tools use it?"*
The answer will come from the Hot Swap, not from more research.
