# INTER_APP_PROJECT_MEMORY — R&D Loop Report

**Date:** 2026-07-08
**Kernel:** DSM 1.0 (frozen 2026-03-14), intact throughout
**Vision tested:** *"Le projet se souvient, quel que soit l'agent ou l'application qui travaille dessus."*
**Classification:** OBSERVED for all factual claims; INFERRED for verdicts.

---

## Executive Summary

DSM **can** serve as a common verified memory across agents and applications — within the scope of what was tested. A 5-agent chain (developer → zcode → claude_code → cursor → gpt) completed successfully with receipt-verified handoffs. A 6-tool inter-app cycle (Claude → GitHub Action → Zcode → Cursor → GPT → Claude) closed the loop with full integrity. A new agent arriving fresh reconstructed the complete project state from DSM alone.

DSM **cannot yet** serve as a *production* inter-app memory without three missing pieces: remote storage (currently same-machine only), per-tool adapters (each tool needs a DSM plugin), and a project-handshake protocol (no standard "catch up" primitive). These are integration gaps, not architectural flaws.

The falsification tests revealed DSM detects 4 of 5 attack classes (mutation, truncation, receipt forgery, entry deletion) but does not detect receipt replay (the same receipt presented twice is accepted both times).

**Verdict: READY_FOR_MORE_R_AND_D** — the core works; the integration layer does not yet exist.

---

## Boucle 0 — Préflight (OBSERVED)

- Repo: `a5e56dc` (main), clean. Kernel 1.0 intact.
- Baseline: 1732 passed, 1 pre-existing PRL failure (unrelated).
- Primitives available: Storage, verify_shard, receipts (issue/verify/verify_against_storage), causal (dispatch), attestation, identity, provenance, RR recall.
- 71 methods on DarylAgent facade. 11 MCP tools (single-agent only).
- **4 gaps identified:** no MCP inter-agent tools, no export/import state, no project abstraction, no catch-up primitive.

---

## Boucle 1 — Inter-agent chain (OBSERVED)

**Scenario:** developer → zcode → claude_code → cursor → gpt. Each agent reads DSM, verifies the predecessor's receipt, produces work, writes to DSM, issues a receipt for the next agent.

**Result:**
- 5/5 agents completed successfully.
- 5/5 receipts verified INTACT + CONFIRMED.
- `verify_shard`: OK.
- Full continuity reconstruction from a fresh read: all 5 decisions recovered with correct attribution.

**Classification: OBSERVED.** DSM can reconstruct inter-agent continuity with the existing primitives.

---

## Boucle 2 — Falsification (OBSERVED + correction)

| Attack | Detected? | Mechanism | Class |
|--------|-----------|-----------|-------|
| F1: mutate entry content on disk | **YES** | `verify_shard` → TAMPERED (hash chain broken) | OBSERVED |
| F2: truncate last entry (suffix deletion) | **YES** | `verify_shard` → truncation_detected=True (pin auto-created on append) | OBSERVED |
| F3: duplicate a receipt (replay) | **NO** | No replay tracking; same receipt accepted twice | OBSERVED |
| F4a: forge receipt with fake entry_hash | **YES** | `verify_receipt` → TAMPERED (receipt_hash covers entry_hash) | OBSERVED |
| F4b: delete entry referenced by receipt | **YES** | `verify_receipt_against_storage` → ENTRY_MISSING | OBSERVED |

**Correction logged:** my initial prediction was that F2 (truncation) would not be detected without a pin. I was wrong — DSM auto-creates an integrity pin on every `append`, so truncation IS detected. This is a stronger property than I expected.

**Classification: OBSERVED.** DSM detects 4/5 attack classes. The gap is receipt replay (no nonce/counter mechanism).

---

## Boucle 3 — Context reconstruction (OBSERVED)

**Scenario:** 8 entries from 4 agents over 4 simulated hours. A new agent arrives with zero native history.

**What works from DSM alone:**
- ✓ All 8 project decisions recovered (content + attribution + timestamp)
- ✓ Chronological order preserved
- ✓ Integrity verified (`verify_shard` OK)
- ✓ Provenance block generated (`build_provenance` → integrity OK, 8 records, 0 broken chains)
- ✓ Activity summary (entry count, sessions, top actions)

**What still requires manual intervention or is missing:**
- ✗ Code artifacts — the actual file contents are not in DSM (only decisions about them)
- ✗ Test results — "all passing" is recorded but the test output is not
- ✗ Rationale — "fix race condition" is recorded but the reasoning is not
- ✗ Agent capabilities — no record of which model/tool each agent used
- ✗ Task dependency graph — no explicit `depends_on` between entries
- ~ Manual prompt needed — DSM provides the data but not the trigger to read it

**Classification: OBSERVED.** A new agent can recover project *decisions* from DSM alone, but not project *artifacts* or *reasoning*. Full automation needs a `catch_up()` primitive.

---

## Boucle 4 — Inter-app loop (OBSERVED)

**Scenario:** Claude → GitHub Action → Zcode → Cursor → GPT → Claude. Each step is a fresh `Storage` handle (simulating a new process/tool).

**Result:**
- 6/6 steps completed.
- Integrity verified OK at every step.
- Loop closure: Claude at the end can see Claude at the beginning (same shard, same chain).
- Cross-tool continuity: all 5 distinct tools read and wrote to the same shared memory.

**Gap analysis for real inter-app deployment:**
- ✓ Same storage file = shared memory (works on same machine)
- ✗ Different machines = needs file sync or remote storage backend
- ✗ Each tool needs a DSM adapter/plugin to read/write
- ✗ No standard "project handshake" protocol between tools
- ✗ Authentication: any process with file access can write (no auth layer)

**Classification: OBSERVED.** DSM works as common memory across tools on the same machine. Cross-machine deployment needs infrastructure that does not yet exist.

---

## Boucle 5 — Architecture Verdict

### 1. DSM peut-il servir de mémoire vérifiable commune ?

**YES** (OBSERVED). The core primitives — append-only storage, hash chain, verify_shard, receipts, dispatch, provenance — compose into a working common memory. Multiple agents and tools can read, write, verify, and reconstruct project state. Integrity is maintained and tamper-detectable across the full chain.

### 2. Les agents deviennent-ils réellement interchangeables ?

**PARTIALLY** (OBSERVED + INFERRED). Any agent that can call the DSM API can read the project state and contribute to it. But "interchangeable" implies the agent needs zero project-specific context — and today, the agent still needs:
- a manual prompt to trigger reading DSM ("you are joining a project")
- knowledge of the shard name ("project_memory")
- the ability to interpret free-text decision entries (no structured task graph)

Agents are interchangeable *at the memory layer* but not *at the workflow layer*.

### 3. Quelles primitives manquent pour une vraie orchestration ?

| Missing primitive | Why it's needed | Difficulty |
|-------------------|-----------------|------------|
| `catch_up(project_id)` | One-call context recovery for a new agent | Low — wraps existing read_recent + summary + provenance |
| `export_state(project_id)` → portable bundle | Serialize project state for cross-machine transfer | Medium |
| Task dependency graph (`depends_on` field) | Structured task ordering beyond free-text | Medium |
| Receipt replay protection (nonce/counter) | Prevent the same receipt from being accepted twice | Low |
| Remote storage backend | Cross-machine shared memory | High |
| Per-tool DSM adapters | Let Claude/Cursor/GPT/GitHub Actions natively read/write DSM | High (per tool) |
| MCP inter-agent tools | Let MCP-connected agents issue/verify receipts | Low (documented in P2-01 memo) |

### 4. Est-on prêt pour une démo privée ?

**YES** (INFERRED). The 5-boucle scenario demonstrates:
- inter-agent handoff with receipts ✓
- tamper detection ✓
- context reconstruction from scratch ✓
- multi-tool loop closure ✓

A private demo can be built on what exists today, with the caveat that each "agent" is simulated via the Python SDK (not a real LLM agent). The demo proves the *memory layer*; it does not prove *agent integration*.

### 5. Est-on prêt pour une démo publique ?

**NO** (INFERRED). A public demo would need:
- At least one real tool integration (e.g., a Claude Code plugin or a GitHub Action that writes to DSM)
- The `catch_up()` primitive so the demo doesn't require manual SDK calls
- Receipt replay protection (a public demo will be probed for weaknesses)
- Documentation of what the demo proves and what it does not

---

## Verdict

### **READY_FOR_MORE_R_AND_D**

**Justification:**

The core memory layer works. Inter-agent continuity, tamper detection, context reconstruction, and multi-tool loops are all OBSERVED and functional. The kernel is intact and sufficient.

But the *integration layer* — the thing that makes DSM usable by real agents in real tools — does not yet exist. No tool adapter, no MCP inter-agent tools, no remote storage, no `catch_up()` primitive. These are not architectural flaws; they are the next development phase.

The honest position: **DSM proves it can be a common verified memory. The next step is proving real agents can use it.** That requires building adapters, not writing more lab simulations.

---

## What this mission discovered (honest summary)

| Discovery | Class |
|-----------|-------|
| DSM can reconstruct 5-agent inter-agent continuity with receipt verification | OBSERVED |
| DSM detects content mutation, truncation, receipt forgery, entry deletion | OBSERVED |
| DSM does NOT detect receipt replay (same receipt accepted twice) | OBSERVED |
| A new agent can recover project decisions from DSM alone | OBSERVED |
| A new agent CANNOT recover code artifacts, test outputs, or rationale from DSM | OBSERVED |
| DSM works as common memory across 6 tools on the same machine | OBSERVED |
| Cross-machine deployment requires infrastructure that does not exist | INFERRED |
| The integration layer (adapters, MCP tools, catch-up primitive) is the bottleneck, not the kernel | INFERRED |

---

## Final correction

My initial prediction in Boucle 2 that truncation would not be detected without a pin was **wrong**. DSM auto-creates an integrity pin on every `append()`, making suffix deletion detectable. This is a stronger tamper-detection property than I expected, and it should be documented as a guaranteed property of the system.

**Classification of the correction: OBSERVED.** The pin exists; truncation IS detected. My prediction was falsified by the experiment — which is exactly how this mission was supposed to work.
