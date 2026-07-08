# Daryl Platform M1 — Release Candidate

**Date:** 2026-07-08
**Status:** Release Candidate (not Released)
**Condition for Release:** independent reproduction by an external developer

---

## Summary

M1 demonstrates that a Daryl project maintains verifiable continuity across
heterogeneous tools — cloud assistants, autonomous agents, and local LLMs —
without copy/paste, manual summaries, or shared history between tools.

Three proofs were produced during the M1 cycle, each answering a different
question. All three passed.

---

## The three proofs

### Proof 1 — Hot Swap M1

**Question:** Le projet survit-il au changement d'outil ?

**Result (OBSERVED):**
- 3 real actors: Zcode (SDK), LM Studio (local LLM), Claude Desktop (MCP)
- Claude read Zcode + LM Studio's work via `dsm_catch_up` — no copy/paste
- Claude published its own decision via `dsm_publish_receipt`
- `dsm_dcp_verify` → VerifyStatus.OK, 4 entries, truncation not detected
- 3 unique sessions, 0 errors

**Evidence:** `research/platform/HOT_SWAP_V1_CLAUDE_ZCODE_LMSTUDIO.md`

### Proof 2 — CLI DCP Sprint

**Question:** Peut-on construire un vrai module avec DCP ?

**Result (OBSERVED):**
- A real module (5 CLI commands, 163 lines) was developed collaboratively
- Workflow: plan → implement → review → verify — a development workflow,
  not just agent handoff
- LM Studio produced a genuine technical review from DSM context
- Every transition receipt-backed
- Kernel intact, 1731 tests pass

**Evidence:** `research/platform/COLLABORATIVE_MODULE_SPRINT.md`

### Proof 3 — Replay Protection

**Question:** Une limite observée est-elle corrigée ?

**Result (OBSERVED):**
- The only falsification gap (Boucle 2: receipt replay) is now closed
- `ReplayProtector` class detects duplicates: CONFIRMED → DUPLICATE
- Race condition (identified by LM Studio review) fixed with threading.Lock
- Concurrent `protect()` tested: exactly one True, one False
- 79 lines added to `exchange.py`, no kernel changes

**Evidence:** `research/platform/LONG_RUNNING_PROJECT_CONTINUITY.md`

---

## What is OBSERVED

| Claim | Evidence |
|-------|----------|
| 3 real actors share project memory via DCP | Hot Swap M1 |
| Claude Desktop reads/writes DSM via MCP | M1 (6 steps, all verified) |
| LM Studio participates as a local LLM actor | M1 + sprints |
| A real module can be developed collaboratively via DCP | CLI DCP Sprint |
| Receipt replay is detected and rejected | Replay Protection tests |
| Race condition in concurrent protect() is fixed | Race hardening test |
| Kernel is intact across all changes | `git diff src/dsm/core/` empty |
| 1732 tests pass (1 pre-existing PRL failure, documented) | Test suite |

## What is FEASIBLE

| Claim | Status |
|-------|--------|
| ChatGPT Desktop as a real actor | Needs adapter (no automation API) |
| Cursor as a real actor | Needs adapter |
| Multi-machine operation | Needs remote storage backend |
| Multi-developer collaboration | Needs identity + sovereignty configuration |

## What is NOT TESTED

| Claim | Status |
|-------|--------|
| External developer reproduction | Pending — condition for Release |
| Multi-process concurrent replay at scale | Not tested |
| Claude Desktop in a sprint (not just Hot Swap) | Not tested |
| Large-scale seen-shard performance (10k+) | Not tested |

---

## Code changes in this release candidate

| File | Lines | What |
|------|-------|------|
| `src/dsm/integrations/goose/server.py` | +198 | 5 DCP MCP tools |
| `src/dsm/cli.py` | +163 | 5 DCP CLI commands |
| `src/dsm/exchange.py` | +85 | ReplayProtector + threading.Lock |
| `src/dsm/status.py` | +1 | StorageReceiptStatus.DUPLICATE |
| `src/dsm/core/` | **0** | **Kernel unchanged** |

**Total: 447 lines of platform code. 0 lines of kernel code.**

---

## Governance documents included

| Document | Location |
|----------|----------|
| ADR-0000 (Platform Doctrine) | `docs/architecture/ADR-0000-daryl-platform-doctrine.md` |
| DCP v1.1 Specification | `docs/architecture/DSM_CONTINUITY_PROTOCOL_v1.md` |
| DCP v1.1 Amendment | `docs/architecture/DCP_v1.1_AMENDMENT.md` |
| DCP Compliance | `docs/architecture/DCP_COMPLIANCE.md` |
| Quick Start Guide | `docs/QUICK_START_HOT_SWAP.md` |

---

## Condition for Release

> **A milestone is not Released until someone who did not build it can reproduce it.**

M1 moves from Release Candidate to Released when:
1. One developer outside the core team follows `docs/QUICK_START_HOT_SWAP.md`
2. They reproduce the Hot Swap (at least 2-actor: script + LM Studio)
3. They confirm it works

Until then: Release Candidate.

---

## Phrase

> *Change d'outil quand tu veux. Le projet n'oublie pas.*
