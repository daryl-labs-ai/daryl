# Boucle 0 — Préflight Report

**Date:** 2026-07-08
**Kernel:** DSM 1.0 (frozen 2026-03-14)
**Repo:** `a5e56dc` (main), clean except `experiments/`, `research/` (untracked)
**Baseline:** 1732 passed, 1 pre-existing PRL failure, 52 skipped
**Classification:** OBSERVED for all factual claims.

---

## Repo state

- Branch: `main`
- Kernel: **intact** (zero modifications across all prior research)
- Test suite: green (the 1 failure is a pre-existing PRL logic bug, documented
  in prior arcs, unrelated to this mission)
- venv: `.venv-research` (Python 3.12), all packages installed and validated

---

## Primitive inventory — what DSM has TODAY

### Kernel layer (frozen, immutable)

| Primitive | Status | Notes |
|-----------|--------|-------|
| `Storage.append()` | ✓ | Append-only JSONL, hash-chained |
| `Storage.read()` | ✓ | Paginated, newest-first |
| `verify_shard()` | ✓ | Hash chain + tip-pin verification |
| `Entry` model | ✓ | 10 fields; 6 in canonical hash |
| Segment manager | ✓ | Auto-rotation at 10k entries |

### Trust layer (above kernel)

| Primitive | Status | For inter-agent? |
|-----------|--------|------------------|
| **Receipts** (`issue_receipt`, `verify_receipt`, `verify_receipt_against_storage`) | ✓ | **Core inter-agent primitive** — portable proof of work |
| **Causal** (`create_dispatch_hash`, `DispatchRecord`, `verify_causal_chain`) | ✓ | Links Agent A's dispatch → Agent B's work |
| **Attestation** (`create_attestation`, `ComputeAttestation`) | ✓ | Binds input→output + model_id |
| **Identity** (`IdentityRegistry.register/resolve/revoke`) | ✓ | Agent identity with trust score |
| **Ed25519 signing** (`generate_keys`, `sign_entry`, `verify_signature`) | ✓ | Per-agent keypairs |

### Recall layer

| Primitive | Status | For inter-agent? |
|-----------|--------|------------------|
| `DSMReadRelay.read_recent()` | ✓ | Recent entries from a shard |
| `DSMReadRelay.summary()` | ✓ | Lightweight activity summary |
| `build_provenance()` | ✓ | Provenance block for a set of entries |
| RR index (`session`, `agent`, `timeline`, `shard`, `action`) | ✓ | Queryable indexes |

### Exposure surfaces

| Surface | Tools | For inter-agent? |
|---------|-------|------------------|
| **MCP** (goose server) | 11 tools | **Single-agent only** — no receipt/dispatch/attest tools (gap documented in prior memos) |
| **CLI** | 47 commands | Human operator; receipts/dispatch available |
| **SDK** (`DarylAgent`) | 71 methods | Full surface; not exported from `__init__` |

---

## What's MISSING for inter-agent memory (OBSERVED gaps)

1. **MCP has no inter-agent tools.** The 11 MCP tools are single-agent
   (log, confirm, search, verify). An agent connected via MCP cannot
   issue, receive, or verify a receipt. *(Documented in P2-01 memo.)*
2. **No `export_state` / `import_state` primitive.** An agent cannot
   serialize its full context (decisions, receipts, identity) into a
   portable bundle that another agent can reconstruct from.
3. **No "project memory" abstraction.** Shards are flat (`sessions`,
   `identity_registry`, `orchestrator_audit`). There is no "project"
   concept that groups all shards belonging to one codebase/workflow.
4. **Cross-agent context recovery is manual.** An agent arriving fresh
   must call `read_recent` + `summary` + `list_receipts` separately and
   mentally reconstruct the project state. No single "catch up" call.

---

## Assessment for the mission

**Can DSM serve as inter-agent memory with what exists today?**

The primitives are present (receipts, dispatch, verify, identity). The
gaps are in *exposure* and *orchestration*, not in *capability*. Boucles 1–4
will test whether the existing primitives, wired together manually, can
achieve inter-agent project continuity — and where they break.

**Classification:** OBSERVED — all primitives verified present and importable.
