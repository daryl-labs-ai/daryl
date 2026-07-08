# External R&D Memos — 2026-07-07

**Author:** ZCode (external R&D)
**Scope:** product and interoperability improvements, grounded in code
inspection of `daryl-labs-ai/daryl` @ `a5e56dc`.
**Status:** proposals only. Not patches. Each memo states its proof gate.
**Kernel:** none of these touch `src/dsm/core/`.

Three memos, ordered by leverage. Each is independent and can be evaluated
on its own. A summary table follows the memos.

---

## MEMO P2-01 — Multi-agent handoff is unreachable over MCP

### 1. Problem

Two agents (e.g. Claude Code and Codex) want to coordinate via DSM: Agent A
finishes work, issues a receipt proving what it did, hands the receipt to
Agent B, B verifies the receipt and continues. This is the exact "coordination
with provenance" the project positions itself around.

The primitives to do this exist (`DarylAgent.dispatch_task`,
`issue_receipt`, `receive_receipt`, `verify_external_receipt`,
`attest_compute`). **None of them are exposed through MCP.** An agent
connected via MCP cannot dispatch, issue, receive, or verify a receipt.

### 2. Evidence

- `src/dsm/agent.py:444-535` — `dispatch_task`, `issue_receipt`,
  `receive_receipt`, `verify_external_receipt`, `attest_compute` all exist
  on the facade.
- `src/dsm/integrations/goose/server.py:78-432` — the 11 MCP tools are:
  `dsm_start_session`, `dsm_end_session`, `dsm_log_action`,
  `dsm_confirm_action`, `dsm_snapshot`, `dsm_recall`, `dsm_recent`,
  `dsm_summary`, `dsm_verify`, `dsm_search`, `dsm_status`.
- **Zero** of the receipt/dispatch/attest methods are wrapped as MCP tools.
- A grep for `receipt|attest|dispatch|causal` in `server.py` returns no
  tool definitions.
- The README positions DSM as *"coordination with provenance"* — but the
  coordination layer is invisible to MCP clients.

### 3. Proposed improvement

Expose three additional MCP tools that wrap existing facade methods, no
new logic:

- `dsm_issue_receipt(entry_id, task_description, target_agent_id?)` → wraps
  `DarylAgent.issue_receipt` (+ optional `dispatch_task`).
- `dsm_receive_receipt(receipt_json)` → wraps `receive_receipt`.
- `dsm_verify_external_receipt(receipt_json)` → wraps `verify_external_receipt`.

These are thin adapters from the existing facade to the existing MCP
registration pattern. No kernel change. No new cryptographic surface.

### 4. Canonical impact

- `src/dsm/integrations/goose/server.py` — add 3 tool functions following
  the pattern of the existing 11.
- `src/dsm/integrations/goose/README.md` — document the new tools.
- Possibly rename the package/tool surface from Goose-specific to generic
  MCP (see note below — flagged as scope expansion, not part of this memo).

### 5. Kernel risk

**None.** All three facade methods are above the kernel. The MCP server
already imports `DarylAgent`; this adds tool wrappers, not new logic.

### 6. Proof gate

The canonical repo can verify safely by:
1. Adding the 3 tool wrappers on a branch.
2. Writing an integration test: Agent A (process 1) issues a receipt via
   `DarylAgent`; serialise to JSON; Agent B (process 2) receives via the
   new `dsm_receive_receipt` MCP tool; assert B's stored receipt
   `integrity == INTACT` and `verify_external_receipt` returns CONFIRMED
   against A's shard.
3. Confirm the existing 11 tools and the full test suite still pass.

### 7. User value

This is the difference between "DSM records one agent's work" and
"DSM lets agents hand off work with proof". Real multi-agent workflows
(Claude→Codex, Codex→Gemini verification, OpenAI Agent→human review)
become possible over the standard interop layer. Without this, DSM is a
single-agent memory with multi-agent *aspirations*.

### 8. Priority

**P2 — Multi-Agent Coordination.** Highest leverage of the three memos:
it unlocks the product positioning. The work is small (3 wrappers) because
the hard part (receipts, dispatch, causal binding) already exists.

---

## MEMO P1-01 — The facade (`DarylAgent`) is not importable

### 1. Problem

A new user runs `pip install daryl-dsm`, opens a REPL, and types
`from dsm import DarylAgent`. It fails. The facade that abstracts the
entire system exists (`src/dsm/agent.py`) but is not in the public import
surface. The README quickstart doesn't use it either — it shows
`Storage` + `SessionGraph` + `SessionLimitsManager` directly, which is the
internal construction path, not the user path.

### 2. Evidence

- `src/dsm/__init__.py` exports ~40 names (`Storage`, `Entry`,
  `IdentityRegistry`, `SovereigntyPolicy`, `NeutralOrchestrator`,
  `CollectiveShard`, `LaneGroup`, …) — **`DarylAgent` is not among them**.
- `README.md:226-242` — the Quick Start constructs memory from
  `dsm.core.storage.Storage` + `SessionGraph` + `SessionLimitsManager`,
  three low-level pieces. It never mentions `DarylAgent`.
- `src/dsm/agent.py:1-600` — `DarylAgent` exposes `start`, `end`,
  `snapshot`, `intend`, `confirm`, `verify`, `audit`, `dispatch_task`,
  `issue_receipt`, etc. — i.e. exactly the ergonomics a user wants, already
  implemented.

### 3. Proposed improvement

Two smallest-useful changes:

1. Add `DarylAgent` to `src/dsm/__init__.py` `__all__` and import.
2. Replace the README Quick Start with a `DarylAgent`-based 5-line recipe:
   ```python
   from dsm import DarylAgent
   agent = DarylAgent(agent_id="my-agent", data_dir="~/.dsm-data")
   agent.start()
   agent.intend("write_file", {"path": "foo.py"})
   agent.confirm(intent_hash, result={"bytes_written": 42})
   agent.end()
   ```

No code logic change. Pure surface correction.

### 4. Canonical impact

- `src/dsm/__init__.py` — one import, one `__all__` entry.
- `README.md` — Quick Start section rewrite (~20 lines).

### 5. Kernel risk

**None.** `DarylAgent` is above the kernel; re-exporting it changes no
behaviour.

### 6. Proof gate

1. `python -c "from dsm import DarylAgent"` works after the change.
2. The 5-line README recipe runs end-to-end on a fresh `data_dir`.
3. Full test suite still passes (the import is purely additive).

### 7. User value

The first 60 seconds of adoption. Today a user who installs the package
hits either a missing import or a quickstart that asks them to compose
three internal classes. After this, the documented happy path is one
import and five lines. This is the difference between "I have to read the
source to start" and "I have a working example in 30 seconds".

### 8. Priority

**P1 — Product UX.** Lowest effort, highest first-impression impact.

---

## MEMO P1-02 — MCP integration is named and framed for one consumer (Goose)

### 1. Problem

The MCP server is the primary way external agents connect to DSM. But it
is named, packaged, and documented as a Goose integration: the package is
`dsm-mcp` with entrypoints `dsm-mcp` and `dsm-serve-goose`, and the README
is titled "DSM Goose Integration" with a Goose-specific config block.
An engineer evaluating DSM for Claude Desktop, Cursor, or Cline sees a
Goose product and may stop reading.

### 2. Evidence

- `packages/dsm-mcp/pyproject.toml` —
  `name = "dsm-mcp"`,
  entrypoints `dsm-mcp` and `dsm-serve-goose`.
- `src/dsm/integrations/goose/README.md:1` — title "DSM Goose Integration".
- The diagram in that README is `Goose UI → MCP stdio → DSM Goose server`.
- The MCP standard itself is transport- and consumer-agnostic (that is the
  point of MCP). The current framing narrows the addressable ecosystem to
  one consumer while the protocol serves all of them.

**Ecosystem fact (marked, please verify):** as of 2026-07, MCP is adopted
by Claude (Anthropic), Cursor, Cline, Goose, and others. Naming an MCP
server after a single consumer is a positioning tax, not a technical
requirement. *(Source: my training data + the MCP spec; the canonical team
should confirm current adoption before acting.)*

### 3. Proposed improvement

Reframe without rewriting:

1. Keep the package name `dsm-mcp` (stable identifier, no breakage).
2. Add a top-level README for `dsm-mcp` titled "DSM Memory MCP Server"
   with consumer-agnostic config examples for at least Claude Desktop and
   Goose. The Goose-specific README moves to a sub-section.
3. Keep `dsm-serve-goose` as a backward-compat alias; make `dsm-mcp` the
   documented primary entrypoint in all new material.

No code change to the server itself.

### 4. Canonical impact

- `packages/dsm-mcp/README.md` — new top-level, consumer-agnostic.
- `src/dsm/integrations/goose/README.md` — demoted to a Goose-specific
  subsection or moved under a `docs/integrations/goose.md`.
- Documentation links from the root `README.md`.

### 5. Kernel risk

**None.** Pure documentation/positioning. The server binary is unchanged.

### 6. Proof gate

1. The `dsm-mcp` entrypoint still starts the server identically.
2. A Claude Desktop MCP config pointing at `dsm-mcp` connects and lists
   the same 11 (or 14, after P2-01) tools.
3. The Goose config still works unchanged (backward-compat alias).

The canonical team should verify the Claude Desktop config shape against
the current MCP client spec before publishing.

### 7. User value

Engineers evaluating DSM for any MCP-capable agent (which is now most of
them) see a general-purpose memory server, not a Goose plugin. This widens
the top of the adoption funnel without changing any code.

### 8. Priority

**P1 — Product UX.** Low effort, high positioning impact. Should be done
*together with* P2-01 if possible, so that the reframe advertises the new
handoff tools.

---

## Summary table

| Memo | Priority | Effort | Kernel? | Leverage |
|------|----------|--------|---------|----------|
| **P2-01** Multi-agent handoff over MCP | P2 | Small (3 wrappers) | No | **Highest** — unblocks the core positioning |
| **P1-01** Export `DarylAgent` + README recipe | P1 | Trivial | No | High first-impression |
| **P1-02** Reframe MCP from Goose-specific to generic | P1 | Trivial (docs) | No | Widens adoption funnel |

**Recommended sequencing:** P1-01 and P1-02 are independent and trivial;
ship them first to fix the front door. P2-01 is the substantive one — it
makes the product positioning true. Doing P1-02 and P2-01 together means
the reframe advertises capabilities that actually exist over MCP.

---

## What was considered and *not* proposed (with reasons)

- **Rewrite the MCP tool layer to auto-reflect facade methods.** Would
  reduce the hand-wrapping duplication, but it's a refactor with no user
  evidence of pain yet. Defer until the surface is stable.
- **A new Python SDK package.** Unnecessary — `DarylAgent` already is the
  SDK; it just needs exporting (P1-01). A new package would duplicate.
- **Operational Envelope as canonical docs.** Produced in a prior research
  arc; valuable, but its adoption into the canonical repo is a decision
  for the canonical team, not a proposal from here. Mentioned for
  traceability, not re-proposed.
- **Theattractive theoretical work on relational trust (prior arc).**
  Out of scope by explicit instruction: this is a product-first pass.
  That work lives under `research/2026-RTM/` (sealed) and is not cited
  here.

---

## Uncertainty labels

- **P2-01**: high confidence on the gap (verified by grep), medium
  confidence on the wrapper count (3 may grow once the canonical team
  decides which attest/dispatch calls deserve their own tool).
- **P1-01**: high confidence — direct file inspection.
- **P1-02**: the ecosystem claim (MCP adoption breadth) is marked for
  canonical-team verification; the code/doc facts are high confidence.
