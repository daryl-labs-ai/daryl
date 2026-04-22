# Daryl Architecture

> **Version:** 0.8.0 · **Kernel:** frozen since March 2026 · **Tests:** 769 passing (v0.8.0 scope, pre-dating Phase 7 measurement chain — see ADR 0001 §Success criteria item 6 for repo-wide harmonisation plan)

This document describes the architecture of Daryl (DSM). The **kernel is frozen** — see [docs/architecture/DSM_KERNEL_FREEZE_2026_03.md](docs/architecture/DSM_KERNEL_FREEZE_2026_03.md). All v0.8.0 additions (pillars A→E) are above the freeze line.

The canonical read path is governed by **ADR 0001** ([docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md](docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md), Accepted 2026-04-20). ADR 0001 is authoritative for any claim in this document about read path, RR, SessionIndex, or Consumption Layer ; this document reflects that ADR and does not redefine it. In case of divergence of formulation, read the ADR.

---

## Component overview

```
Your Agent(s)
    ↓
DarylAgent facade           ← SDK: 15 facade methods + 7 direct-access properties
    ↓
┌─────────────────────────────────────────────────────────┐
│  Pillars A→E (v0.8.0) — multi-agent collective memory  │
│                                                         │
│  A  IdentityRegistry    identity/identity_registry.py   │
│  B  SovereigntyPolicy   sovereignty.py                  │
│  C  NeutralOrchestrator orchestrator.py                 │
│  D  CollectiveShard     collective.py                   │
│     ShardSyncEngine     collective.py                   │
│     RollingDigester     collective.py                   │
│  E  ShardLifecycle      lifecycle.py                    │
│                                                         │
│  Parallel Lanes:                                        │
│     LaneGroup           lanes.py                        │
│                                                         │
│  Cross-cutting:                                         │
│     ShardFamilies       shard_families.py               │
│     Exceptions          exceptions.py                   │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│  Extension modules (v0.5–v0.7)                          │
│                                                         │
│  Identity         identity/ (IdentityManager, Guard)    │
│  Sessions         session/ (SessionGraph, Limits)       │
│  Pre-commitment   anchor.py                             │
│  Sealing          seal.py                               │
│  Receipts         exchange.py                           │
│  Signing          signing.py (Ed25519)                  │
│  Causal binding   causal.py                             │
│  Attestation      attestation.py                        │
│  Artifacts        artifacts.py                          │
│  Audit            audit.py + policy_adapter.py          │
│  Status enums     status.py                             │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│  Query layers                                           │
│  RR (Read Relay)  rr/ — read-only queries over storage  │
│  ANS              ans/ — skill performance analytics    │
│  Skills           skills/ — registry, router, ingestor  │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│  DSM Core (FROZEN — do not modify)                      │
│  Storage, Entry, ShardMeta, segments, hash chain,       │
│  signing, session, security, replay, runtime            │
└─────────────────────────────────────────────────────────┘
```

---

## DSM Core (frozen kernel)

- **Storage**: Append entries, read by shard, list shards. No update/delete. Append-only by design.
- **Models**: `Entry` (id, timestamp, session_id, source, content, shard, hash, prev_hash, metadata, version), `ShardMeta`.
- **Segments**: Shard segmentation and file layout. Portable locking via `filelock`.
- **Hash chain**: Each entry carries `SHA-256(prev_hash + content)`. Tamper-evident — alter one byte, the chain breaks.

The kernel is frozen since March 2026. Zero modifications in v0.8.0. Do not modify `src/dsm/core/` without explicit approval.

---

## Pillars A→E (v0.8.0) — multi-agent collective memory

Five modules extending DSM from single-agent provable memory to multi-agent collective memory. Full design: [DSM_PILLARS_A_TO_E.md](docs/architecture/DSM_PILLARS_A_TO_E.md).

### Dependency chain

```
A → B → C → D → E
```

Each is a prerequisite for the next. You cannot use C without A and B.

### A — Identity Registry (`identity/identity_registry.py`)

Multi-agent identity governance: register, resolve, revoke, trust score. Coexists with existing `IdentityManager` (single-agent evolution).

- **Shard:** `identity_registry`
- **Key classes:** `IdentityRegistry`, `AgentIdentity`
- **Hot path:** `resolve()` — O(1) via lazy cached index
- **Tests:** 25

### B — Sovereignty Policy (`sovereignty.py`)

Pre-execution access control for the collective. The human owner sets who can contribute, with what trust level, which entry types.

- **Shard:** `sovereignty_policies`
- **Key classes:** `SovereigntyPolicy`, `PolicySnapshot`, `EnforcementResult`
- **Hot path:** `allows()` — O(1) policy lookup + O(1) trust check
- **Schema validation:** types, ranges, non-empty lists (14 validation tests)
- **Complementary to:** `audit.py` (post-hoc) — sovereignty is pre-execution
- **Tests:** 36

### Shard Families (`shard_families.py`)

Cross-cutting classification: every shard belongs to a family (`agent`, `registry`, `audit`, `collective`, `infra`). Pure function, O(1) dict lookup, no kernel change.

- **Key classes:** `ShardFamily`, `classify_shard()`, `list_shards_by_family()`
- **Used by:** B (policy-by-family), D (read-by-family), E (retention-by-family)
- **Tests:** 21

### C — Neutral Orchestrator (`orchestrator.py`)

Rule-based admission control. Evaluates frozen rules, logs decisions, caches results.

- **Shard:** `orchestrator_audit`
- **Key classes:** `NeutralOrchestrator`, `RuleSet`, `Rule` (ABC), `AdmissionResult`
- **Built-in rules:** `SovereigntyCheckRule`, `MinTrustScoreRule`, `RateLimitRule`, `NoSelfReferenceRule`
- **Hot path:** `admit()` — O(1) cache by entry hash, O(1) admission counter for rate limiting
- **Tests:** 17

### D — Collective Sync (`collective.py`)

Shared memory layer: N agents contribute projections (not copies) to a collective shard. Single writer (SyncEngine) guaranteed.

- **Shards:** `collective_main`, `collective_digests`, `sync_log`
- **Key classes:** `CollectiveShard`, `ShardSyncEngine`, `CollectiveMemoryDistiller`, `RollingDigester`
- **Tiered Resolution:** Tier 0 (~30 tokens) → Tier 1 (~80) → Tier 2 (~300) → Tier 3 (full, on-demand)
- **Rolling digests:** Structural aggregation hourly → daily → weekly → monthly
- **Budget-aware:** `read_with_digests(max_tokens=N)` auto-optimizes coverage
- **Tests:** 31

### E — Shard Lifecycle (`lifecycle.py`)

State machine: `active → draining → sealed → archived`. Auto-drain/seal on configurable triggers.

- **Shard:** `lifecycle_registry`
- **Key classes:** `ShardLifecycle`, `ShardState`, `LifecycleResult`, `VerifyResult`
- **Spot-check:** O(1) verify (first + last hash). Full replay on explicit audit.
- **Tests:** 25

### Parallel Lanes (`lanes.py`)

Scalable multi-agent writes: each agent writes to its own lane shard (`collective_lane_{agent_id}`), eliminating FileLock contention. Cross-lane reads merge all lanes into a unified view sorted by time.

- **Shards:** `collective_lane_{agent_id}`, `collective_merges`
- **Key classes:** `LaneGroup`, `LaneTip`, `MergeEntry`, `LaneWriteResult`
- **Write path:** per-agent lane → zero contention (N agents = N independent locks)
- **Read path:** cross-lane merge → sorted by timestamp → tiered resolution + budget
- **Merge entries:** periodic snapshots referencing all lane tips with SHA-256 merge hash
- **Scaling:** 2.5x at 3 agents → 8.4x at 10 → 42x at 50 → 84x at 100
- **Tests:** 30

### Integration (`agent.py`)

`DarylAgent` exposes A→E + lanes through 21 facade methods and 8 direct-access properties. `end(sync=True)` triggers auto-sync + lifecycle triggers on session end.

- **Tests:** 31 (facade + direct access + end-to-end)

---

## Extension modules (v0.5–v0.7)

| Module | File | Purpose | Tests |
|--------|------|---------|-------|
| Identity | `identity/` | Single-agent genesis + evolution | 20 |
| Sessions | `session/` | SessionGraph lifecycle | varies |
| Pre-commitment | `anchor.py` | Temporal pre-commitment, environment anchoring | varies |
| Sealing | `seal.py` | Shard sealing, cryptographic tombstone | 17 |
| Receipts | `exchange.py` | Cross-agent trust receipts | 17 |
| Signing | `signing.py` | Ed25519 entry signing, key rotation | varies |
| Causal | `causal.py` | Cross-agent causal binding | varies |
| Attestation | `attestation.py` | Compute attestation (input-output binding) | 11 |
| Artifacts | `artifacts.py` | Content-addressable artifact store | varies |
| Audit | `audit.py` | Post-hoc compliance verification | varies |
| Policy adapters | `policy_adapter.py` | OPA, Inkog adapters | varies |
| Status | `status.py` | Enums (Verify, Seal, Receipt, Sovereignty, etc.) | — |

All extension modules are untouched in v0.8.0. Their APIs and tests are preserved.

---

## Query layers

- **RR (Read Relay)**: Read-only layer over DSM storage. Uses only `Storage.read()`. Provides recent entries, summaries, filters. Compatible with classic and block shards.
- **ANS (Adaptive Navigation System)**: Analyzes skill performance (usage/success logs), produces rankings and workflow recommendations.
- **Skills**: Registry and router for matching task descriptions to skills. Optional telemetry separate from DSM kernel.

---

## Canonical Consumption Path

The canonical read path for agent-facing consumers is governed by [ADR 0001](docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md) (Accepted 2026-04-20, status authoritative).

- **Option C retained by ADR 0001** : RR is **designated** by ADR 0001 as the canonical read backend over `Storage`. The Consumption Layer (`src/dsm/recall/`, `src/dsm/context/`, `src/dsm/provenance/`) is reoriented to read through RR. Designation is governance, not a statement about current code state — consumer rebinding across `DarylAgent`, CLI, and MCP is scoped to **Phase 7b** of the ADR 0001 migration plan and is not yet executed ; until Phase 7b completes, SessionIndex and RR coexist operationally.
- **SessionIndex** (`src/dsm/session/session_index.py`) : classified `duplicative` by [ADR_0001_SESSIONINDEX_CLASSIFICATION.md](docs/architecture/ADR_0001_SESSIONINDEX_CLASSIFICATION.md) on 2026-04-19. It continues to serve its 8 live consumers (`DarylAgent.index_sessions` / `find_session` / `query_actions`, CLI `dsm session-*` commands, MCP `dsm_search`) until Phase 7b rebinds them. Its classification is not weakened by this coexistence ; deprecation is scoped, not imminent.
- **Storage layout — Acceptance condition 1 of ADR 0001** : production deployments use **segmented** layout, produced automatically by `Storage.append()` via `ShardSegmentManager`. Phase 7a.5 measured a FAIL on a monolithic fixture ; that verdict applies to monolithic-layout deployments only and is not retracted. The Acceptance of ADR 0001 is conditional on segmented layout — any deployment that bypasses segmentation is outside the scope of that Acceptance and should re-check against `ADR_0001_PHASE_7A_5_VERDICT.md`.
- **RR action_name index** : the extension promoting `metadata["action_name"]` to a first-class RR index key has been **validated on the proto branch** `proto/phase-7a-rr-action-name-index` at commit `58d7789` (Phase 7a PASS architectural, Phase 7a.5-bis PASS on gates (i) and (iii) under segmented, Phase N+1A PASS on gate (ii) top after the navigator fix at commit `e570841`). It is part of the Accepted target architecture. Merge into `main` is a Phase 7b prerequisite and has not been performed ; a consumer of `main` does not yet see this extension.
- **RR navigator `navigate_action` limit kwarg** (Phase N+1A fix) : validated on the proto branch at commit `e570841`. Part of the Accepted target architecture. Not present in `main`.

For the full chain of measurement verdicts and Acceptance conditions, see [ADR 0001](docs/architecture/ADR_0001_CANONICAL_CONSUMPTION_PATH.md) `Reconciliation of phase verdicts` and `Condition Satisfaction Map` sections.

---

## Repository layout

```
src/dsm/
  core/                  # FROZEN kernel — storage, models, hash chain, segments
  session/               # SessionGraph, SessionLimitsManager
  identity/              # IdentityManager (v0.5) + IdentityRegistry (v0.8.0)
  rr/                    # Read Relay
  ans/                   # Analytics
  skills/                # Skill registry, router
  agent.py               # DarylAgent facade (v0.3 + v0.8.0 A→E)
  sovereignty.py         # B — pre-execution access control
  orchestrator.py        # C — rule-based admission
  collective.py          # D — collective memory + sync + digests
  lanes.py               # Parallel shard lanes — scalable multi-agent writes
  lifecycle.py           # E — shard lifecycle state machine
  shard_families.py      # Cross-cutting shard classification
  exceptions.py          # A→E shared exceptions
  anchor.py              # Pre-commitment
  seal.py                # Shard sealing
  exchange.py            # Cross-agent receipts
  signing.py             # Ed25519 signing
  artifacts.py           # Content-addressable store
  causal.py              # Causal binding
  attestation.py         # Compute attestation
  audit.py               # Post-hoc audit
  policy_adapter.py      # OPA/Inkog adapters
  status.py              # Status enums (including A→E)

tests/                   # 769 tests — 0 failures (v0.8.0 scope count — repo-wide
                         # harmonisation of test counts across README.md,
                         # docs/CONSUMPTION_LAYER.md, and this file is a scheduled
                         # Phase 6 deliverable of the ADR 0001 migration plan,
                         # not executed by the current Acceptance)
docs/architecture/       # DSM_PILLARS_A_TO_E.md, kernel freeze doc
```

---

## Invariants

These properties hold across the entire codebase:

1. **Append-only** — no entry is ever modified or deleted
2. **Hash-chained** — each entry carries `SHA-256(prev_hash + content)`
3. **Single writer per shard** — one writer, many readers. SyncEngine is sole writer to collective shards
4. **Kernel frozen** — `src/dsm/core/` has zero modifications since March 2026
5. **Projections, not copies** — collective entries contain hashes + summary, not full content
6. **Lazy indexes** — O(1) reads via cached indexes, rebuilt on first access, invalidated on write
7. **DSM eats its own cooking** — every A→E decision is logged in a DSM shard
