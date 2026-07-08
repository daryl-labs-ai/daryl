# Product Gap Scan #2 — The MCP agent/operator asymmetry

**Author:** ZCode (external R&D, product-first)
**Date:** 2026-07-07
**Scope:** systematic gap scan of `DarylAgent` capacity vs surface exposure.
**Prior memos:** `2026-07-07-product-scan.md` (P2-01, P1-01, P1-02).
This memo extends that work with a quantified scan; it does not repeat
the three prior proposals.
**Status:** proposals only. Not patches.
**Kernel:** untouched.

---

## What this scan did

Compared every public method on `DarylAgent` (82 methods) against three
exposure surfaces: the MCP server (`server.py`, 11 tools), the CLI
(`cli.py`, 47 commands), and the package export (`__init__.py`).

The question answered: **of the things Daryl can already do, what fraction
can an agent actually invoke — and where do humans have capabilities that
agents don't?**

---

## The headline metric

```
DarylAgent public methods:     82
Exposed via MCP:               6   (7%)
Exposed via CLI:              41   (50%)
Exposed via __init__:          0   (0% — DarylAgent not exported)
```

The single number that matters: **an agent connected over MCP can invoke
7% of Daryl's capacity. A human at the CLI can invoke 50%.**

This is not a complaint that MCP is "small". It is the observation that
**Daryl treats agents as second-class operators relative to humans.** The
product positions itself as operational memory *for AI agents*, yet the
interface built for agents exposes an order of magnitude less than the
interface built for humans.

---

## The two distinct gaps

### Gap A — CLI-only capabilities (32 methods)

Capabilities a human operator can invoke today, but an MCP-connected agent
cannot. These are not internal plumbing — they are real product capacities
that already work, already have CLI commands, already have tests. They are
simply not wrapped as MCP tools.

Highest-leverage examples for agents:

| Method | CLI today | Why an agent needs it |
|--------|-----------|----------------------|
| `attest_compute` | — (not CLI either) | Prove "model X produced this output for this input". Agent-native by design (`agent_id`, `model_id`). |
| `issue_receipt` | `receipt-issue` | Hand off work with proof (already proposed in P2-01). |
| `store_artifact` | `artifact-store` | Persist raw input/output the agent references in its reasoning. |
| `retrieve_artifact` | — | Fetch a previously stored artifact by hash during recall. |
| `audit` / `audit_report` | `audit`, `audit-report` | Let an agent verify the memory it's about to trust before acting on it. |
| `find_session` | `session-find` | Recover context: "what did I do in session X". |
| `query_actions` | `session-query` | Recall: "when did I last run action Y". |
| `check_coverage` | `coverage` | Agent self-checks its own memory gaps before claiming completeness. |
| `verify` | `verify` | Agent verifies a shard before relying on its contents. |

### Gap B — fully hidden capabilities (31 methods)

Capabilities built into the facade but not exposed on **any** surface
(not MCP, not CLI). These are stronger candidates for *net-new* exposure
because nothing invokes them today — they are dormant assets.

Notable clusters:

- **Collective memory navigation** (`collective_summary`,
  `collective_recent`, `collective_at_tier`, `read_with_digests`,
  `lane_recent`, `lane_stats`) — the multi-agent shared-memory read path
  exists but is unreachable by either humans or agents. This is the
  Pillar-D surface; it was built but never wired to a consumer.
- **Sovereignty governance** (`set_policy`, `get_policy`,
  `check_sovereignty`) — the pre-execution access-control layer has no
  operator or agent surface. Policies can only be set programmatically.
- **Multi-agent identity** (`register_agent`, `resolve_agent`,
  `list_registered_agents`, `agent_trust`) — the Pillar-A registry is
  invisible to both surfaces. An agent cannot discover other registered
  agents.
- **Lifecycle control** (`lifecycle_state`, `drain`, `archive`,
  `lifecycle_triggers`) — shard lifecycle management is facade-only.

---

## New proposals (this memo)

The three prior memos (P2-01, P1-01, P1-02) remain the priority batch.
The scan below adds proposals that are *net-new* relative to those — i.e.
not already covered. Each follows the 8-section format.

---

## MEMO P2-02 — Expose agent recall over MCP (`find_session`, `query_actions`)

### 1. Problem
An agent connected via MCP can `dsm_search` and `dsm_recall`, but cannot
ask the two highest-value context-recovery questions: *"what did I do in
session X?"* and *"when did I last do action Y?"*. These are the
`find_session` and `query_actions` facade methods — both already
implemented, both already on the CLI (`session-find`, `session-query`),
neither wrapped as an MCP tool.

### 2. Evidence
- `src/dsm/agent.py` — `find_session` and `query_actions` exist, both
  documented as RR-index-backed (ADR-0001 Phase 7b).
- `src/dsm/cli.py` — `session-find` and `session-query` commands exist and
  work for human operators.
- `src/dsm/integrations/goose/server.py` — neither is among the 11 MCP
  tools. An agent can `dsm_search` (keyword) but cannot navigate by
  session or action.
- The multi-agent lens (per the R&D charter) explicitly lists "recover
  context" as a primary agent need.

### 3. Proposed improvement
Two MCP tools wrapping existing facade methods:
- `dsm_find_session(session_id)` → `DarylAgent.find_session`
- `dsm_query_actions(action_name?, start_time?, end_time?, limit)` →
  `DarylAgent.query_actions`

No new logic. The CLI already proves the methods work end-to-end.

### 4. Canonical impact
- `src/dsm/integrations/goose/server.py` — 2 tool wrappers, same pattern
  as the existing 11.
- README tool table — 2 rows.

### 5. Kernel risk
**None.** Both methods are above the kernel.

### 6. Proof gate
- Add the 2 wrappers on a branch.
- Integration test: log actions across two sessions via MCP; then call
  `dsm_find_session` on each and `dsm_query_actions` for a specific
  action; assert correct results.
- Existing suite still passes.

### 7. User value
An agent that cannot recover "what I did in this session" or "when did I
last run this action" is forced to re-derive context from raw `dsm_recent`
output — which is unindexed. This is the difference between *browsing
entries* and *navigating memory*. It is also a prerequisite for sane
cross-agent handoff (the receiving agent must be able to inspect the
prior agent's session).

### 8. Priority
**P2 — Multi-Agent Coordination.** Pairs naturally with P2-01 (receipts):
the same agent that receives a receipt should be able to inspect the
session that produced it.

---

## MEMO P2-03 — Expose self-verification over MCP (`verify`, `check_coverage`)

### 1. Problem
The product positions DSM as *"coordination with provenance"* and the R&D
charter lists "justify claims" and "coordinate without hallucinating
shared state" as core agent needs. Yet an agent connected via MCP **cannot
verify the memory it is about to act on**. It can read entries and search,
but it cannot run integrity verification or coverage checks before
trusting what it read. A human can (`verify`, `coverage` CLI commands); an
agent cannot.

### 2. Evidence
- `src/dsm/cli.py` — `verify` and `coverage` commands exist.
- `src/dsm/integrations/goose/server.py` — `dsm_verify` exists but is
  scoped to shard-level integrity only. There is no
  `dsm_check_coverage`. An agent cannot detect gaps in its own memory.
- The prior Operational Envelope research (`research/2026-OrchestratedMemory`)
  measured that corruption is *well-contained* (19/20 entries survive a
  corrupted line) — but only if someone runs verify. If agents can't
  invoke it, that property goes unused on the agent path.

### 3. Proposed improvement
One new MCP tool, one clarification:
- `dsm_check_coverage(indexed_ids?, indexed_hashes?)` → wraps
  `DarylAgent.check_coverage`. Lets an agent detect memory gaps before
  claiming a task complete.
- Clarify in docs that `dsm_verify` (already present) is the integrity
  gate an agent should run before trusting recalled context.

### 4. Canonical impact
- `src/dsm/integrations/goose/server.py` — 1 new tool wrapper.
- README/docs — one paragraph on "agent self-verification before acting".

### 5. Kernel risk
**None.**

### 6. Proof gate
- Add the wrapper on a branch.
- Test: agent logs 10 actions, then `dsm_check_coverage` against a partial
  index reports the missing entries.
- Existing suite still passes.

### 7. User value
Agents that verify before acting are the difference between "memory that
looks right" and "memory an agent is willing to bet on". For high-stakes
workflows (code changes, deploys, financial actions) this is the
trust-before-act primitive. Today only human operators have it.

### 8. Priority
**P2.** Lower urgency than P2-01/P2-02 but high symbolic value: it makes
the "provenance" in the product positioning actually usable by agents,
not just by auditors.

---

## MEMO P3-01 — Collective memory read-path is built but has no consumer

### 1. Problem
The Pillar-D collective memory layer (`collective_summary`,
`collective_recent`, `collective_at_tier`, `read_with_digests`,
`lane_recent`, `lane_stats`) is implemented on `DarylAgent`, tested, and
documented in `ARCHITECTURE.md` as the multi-agent shared-memory read
path. **None of it is exposed on MCP or CLI.** It is a finished module
with no consumer.

### 2. Evidence
- `src/dsm/agent.py` — 8 collective/lane read methods exist.
- `src/dsm/cli.py` — `collective` keyword: 0 commands. `lane` keyword:
  0 commands.
- `src/dsm/integrations/goose/server.py` — no collective or lane tool.
- `docs/architecture/DSM_PILLARS_A_TO_E.md` describes the layer as
  production.
- The prior `2026-OrchestratedMemory` research (Axe 2) measured that the
  collective read path *works* — B reconstructs A's full work via
  `lanes.recent()` — but that experiment was the first time anyone
  invoked it.

### 3. Proposed improvement
**Smallest useful change:** expose `collective_summary` and
`collective_recent` as MCP tools. This gives an agent the ability to read
the shared multi-agent memory — the core of the "shared operational
memory" positioning.

```python
dsm_collective_summary()  → DarylAgent.collective_summary
dsm_collective_recent(limit?) → DarylAgent.collective_recent
```

The remaining 6 collective methods (tiered reads, digests, lane stats) are
candidates for a follow-up; do not expose all 8 at once before the first
two have consumers.

### 4. Canonical impact
- `src/dsm/integrations/goose/server.py` — 2 tool wrappers.
- README — 2 rows + a "Collective memory" subsection.

### 5. Kernel risk
**None.** Collective is above the kernel.

### 6. Proof gate
- Add the 2 wrappers on a branch.
- Integration test: agent A pushes to a lane; agent B (separate process,
  same storage) calls `dsm_collective_recent` and sees A's projection.
- Existing suite still passes.

### 7. User value
This is what makes DSM *shared* operational memory rather than
*per-agent* operational memory. Until these are exposed, the multi-agent
read path is theoretical — it works in tests and in the research lab, but
no agent in the field can invoke it. Exposing just summary + recent is
the minimum viable surface; it lets a team of agents actually share a
memory view.

### 8. Priority
**P3 — SDK / API / Integration** with strong P2 overlap. It is marked P3
rather than P2 because the *write* side (`push_to_collective`) also needs
exposure for the read to be useful, and that combination is a larger
batch. Recommend: expose read+write together in a single "collective
memory over MCP" batch rather than dribbling them out.

---

## What was considered and *not* proposed

- **Bulk-expose all 32 CLI-only methods over MCP.** Tempting (high
  coverage in one PR) but violates the smallest-useful-change principle.
  Each MCP tool needs its own arg-shape decision and integration test.
  Propose them in themed batches (recall, verification, multi-agent) so
  each can be reviewed on its merits.
- **Expose sovereignty/lifecycle methods over MCP now.** These are
  operator actions more than agent actions (set policy, drain shard,
  archive). Expose them when there's an operator MCP client, not before.
- **Auto-generate MCP tools from the facade via reflection.** Would
  eliminate the wrap-twice problem, but it's a refactor with no user
  evidence of pain yet. Defer until the manual surface is stable and the
  duplication is actually hurting.
- **A second Python SDK.** Unnecessary — `DarylAgent` is the SDK (per
  prior memo P1-01).

---

## Uncertainty labels

- **Coverage ratios (7% / 50%)**: high confidence on the method/surface
  counts (mechanical grep). The exact *categorisation* of a method as
  "agent-relevant" vs "operator-only" is judgement; the memos above
  argue each case individually rather than relying on the aggregate.
- **P2-02, P2-03, P3-01**: high confidence that the gap exists (verified
  by grep of both surfaces). Medium confidence on the exact tool
  signatures — the canonical team may prefer different arg shapes.
- **The "no consumer" claim for collective read methods**: high
  confidence from grep; the canonical team should confirm no internal
  caller exists that the scan missed.

---

## Relationship to the prior memo batch

| Memo | Surface | Status |
|------|---------|--------|
| P2-01 (receipts over MCP) | multi-agent write | prior — highest leverage |
| P1-01 (export DarylAgent) | package import | prior — trivial |
| P1-02 (MCP naming reframe) | positioning | prior — trivial |
| **P2-02 (recall over MCP)** | agent navigation | **this memo** |
| **P2-03 (self-verify over MCP)** | agent trust-before-act | **this memo** |
| **P3-01 (collective read over MCP)** | shared memory surface | **this memo** |

The pattern across all six: **Daryl's internal capacity far exceeds its
agent-facing surface.** Each memo exposes a different slice of already-
built capability. None adds new logic. None touches the kernel.

The recommended batch order: P1-01 + P1-02 (front door) → P2-01 + P2-02
(receipts + recall: the multi-agent coordination pair) → P2-03 + P3-01
(trust + shared memory). Each batch is independently shippable.
