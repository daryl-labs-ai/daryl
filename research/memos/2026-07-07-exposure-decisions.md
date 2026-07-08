# Exposure decisions — applying the 4-criteria filter to the 6 memos

**Applies:** the Capability-first exposure principle
(`research/CAPABILITY_EXPOSURE.md`) to the six proposals in
`research/memos/2026-07-07-product-scan.md` and
`research/memos/2026-07-07-product-gap-scan-2.md`.

**Purpose:** force an explicit exposure decision on each proposal rather
than leaving it as "proposed". This is the first operational use of the
principle.

---

## The four criteria (recap)

A capability is exposed only if **all four** hold:

1. Solves an observed friction.
2. Fits an identified product workflow.
3. Has contracts and tests.
4. Does not add unnecessary surface complexity.

---

## Decisions

### P1-01 — Export `DarylAgent`, rewrite README quickstart

| Criterion | Verdict |
|-----------|---------|
| 1. Observed friction | ✓ — `from dsm import DarylAgent` fails; README teaches internals |
| 2. Product workflow | ✓ — the 30-second onboarding path |
| 3. Contracts/tests | ✓ — `DarylAgent` is stable, tested; pure re-export |
| 4. Surface complexity | ✓ — reduces complexity (one import vs composing 3 classes) |

**Decision: `expose`.** Priority P1. Ship first.

---

### P1-02 — Reframe MCP from Goose-specific to generic

| Criterion | Verdict |
|-----------|---------|
| 1. Observed friction | ✓ — Goose-named surface narrows the addressable ecosystem |
| 2. Product workflow | ✓ — the evaluation path for any MCP-capable agent client |
| 3. Contracts/tests | ✓ — server binary unchanged; docs/positioning only |
| 4. Surface complexity | ✓ — no new surface; reframes existing |

**Decision: `expose` (reframe).** Priority P1.
Caveat: ecosystem claims marked for canonical-team verification before
publishing.

---

### P2-01 — Receipts over MCP (`issue_receipt`, `receive_receipt`, `verify_external_receipt`)

| Criterion | Verdict |
|-----------|---------|
| 1. Observed friction | ✓ — agents cannot hand off work with proof over MCP |
| 2. Product workflow | ✓ — Claude→Codex handoff, the core positioning |
| 3. Contracts/tests | ✓ — all three methods exist, tested above the kernel |
| 4. Surface complexity | ✓ — 3 tools, themed (handoff); coherent with existing 11 |

**Decision: `expose`.** Priority P2. Highest leverage.
Pairs with P1-02 so the reframe advertises real multi-agent capability.

---

### P2-02 — Recall over MCP (`find_session`, `query_actions`)

| Criterion | Verdict |
|-----------|---------|
| 1. Observed friction | ✓ — agents cannot answer "what happened before me" |
| 2. Product workflow | ✓ — handoff recovery: the receiving agent inspects the prior session |
| 3. Contracts/tests | ✓ — both methods exist, CLI-proven (`session-find`, `session-query`) |
| 4. Surface complexity | ✓ — 2 tools, themed (navigation); compose with `dsm_search` |

**Decision: `expose`.** Priority P2. M3.0 candidate.
The natural pair to P2-01: the same agent that receives a receipt should
be able to inspect the session that produced it.

---

### P2-03 — Self-verify over MCP (`check_coverage`)

| Criterion | Verdict |
|-----------|---------|
| 1. Observed friction | ✓ — agents cannot check memory completeness before claiming a task done |
| 2. Product workflow | ✓ — trust-before-act: the "honest reconstructive" signature |
| 3. Contracts/tests | ✓ — method exists, CLI-proven (`coverage`) |
| 4. Surface complexity | ✓ — 1 tool; arguably the *most* agent-defining single tool |

**Decision: `expose`.** Priority P2.
Strategically the strongest single tool: it makes "provenance" usable by
agents, not just by auditors. Could become a Daryl signature primitive.

---

### P3-01 — Collective read over MCP (`collective_summary`, `collective_recent`)

| Criterion | Verdict |
|-----------|---------|
| 1. Observed friction | ~ — no agent has yet asked for it (no consumer exists) |
| 2. Product workflow | ~ — "shared memory" is the positioning, but no field workflow proven |
| 3. Contracts/tests | ✓ — methods exist, tested in `tests/test_collective.py` and the research lab |
| 4. Surface complexity | ~ — adds a *new abstraction* (collective memory) to the surface |

**Decision: `defer`.**
Criteria 1, 2, 4 are conditional on usage signal that does not yet exist.
Valid proposal — but expose only after M3.0 lands and we observe how
agents actually use ask / navigate / receipt / recall / coverage. The
collective layer is powerful and easy to misuse; do not expose a new
abstraction before the simpler surfaces have consumers.

This is the principle working as intended: a capability that *could* be
exposed is held back not because it's broken, but because its exposure
should follow evidence of need, not precede it.

---

## Summary table

| Memo | Decision | Priority | Batch |
|------|----------|----------|-------|
| P1-01 export façade | **expose** | P1 | 1 — front door |
| P1-02 MCP reframe | **expose** (reframe) | P1 | 1 — front door |
| P2-01 receipts MCP | **expose** | P2 | 2 — coordination |
| P2-02 recall MCP | **expose** | P2 | 2 — coordination |
| P2-03 self-verify MCP | **expose** | P2 | 3 — trust |
| P3-01 collective read MCP | **defer** | — | post-M3.0, evidence-gated |

---

## What this exercise demonstrates

Five of six proposals pass all four criteria and earn `expose`. One
(P3-01) fails criteria 1, 2, and 4 *under current evidence* and is held
back — not killed, deferred. That is the discipline in action: the
default is not "expose everything built", and the default is also not
"block everything new". Each capability gets a decision, with a reason.

The net effect on the MCP surface, if batches 1–3 ship:
- MCP exposure rises from 7 % to ~25 %.
- The 25 % is the *deliberate* slice — each tool has a named workflow,
  a proof gate, and no kernel risk.
- The remaining ~75 % is not "missing"; it is `operator-only`,
  `internal`, or `deferred` *by decision*, not by neglect.

That is the difference between a growing surface and an accumulating one.
