# P1 → P2 Roadmap — From Spec to Implementation

- **Status:** Proposed (P1, spec-only)
- **Date:** 2026-06-12
- **Companion to:** [ADR-0003](../adr/ADR-0003-transparency-log.md) and `docs/spec/*`

This roadmap sequences the move from **P1 (specification, this branch)** to **P2
(implementation)**. P1 ships *only* documents. P2 writes code — and is explicitly
**not started** here.

---

## 1. Phase boundary (what is P1 vs P2)

| | P1 (now) | P2 (later) |
|---|---|---|
| Deliverables | ADR-0003, P1 security model, 5 specs, model-test plan, this roadmap | `src/` code, runtime tests, SDK verifier |
| Touches `src/` / `agent-mesh/` | **No** | Yes (new modules, additive) |
| Output | reviewed, internally-consistent design | a behind-flag transparency log + migration |
| Gate to advance | ADR-0003 §7 acceptance criteria met | P2 modules pass `P1_MODEL_TESTS` |

## 2. P2 work breakdown (sequenced, each its own branch/PR)

1. **`dsm-primitives`: `bind()`** (`BIND_PRIMITIVE.md`).
   New pure function + property tests. Lowest-risk, unblocks everything. No
   behavioural change to existing records yet.
2. **MMR core module** (`MMR_SPEC.md`).
   Append, peaks, root, inclusion + consistency proofs, over existing entry hashes.
   Pure, side-effect-free; node store is a recomputable cache.
3. **STH issuance + checkpoints log** (`STH_SPEC.md`).
   Operator signs STHs via `bind()`; append-only checkpoints log per origin.
4. **Verifier (portable)** — inclusion/consistency/STH verification as a small,
   dependency-light module mirrored in at least one non-Python language
   (JS/Go/Rust) so third parties can verify receipts trivially.
5. **Witness service** (`WITNESS_SPEC.md`).
   Reference witness (cosign-on-consistency) + verifier-side quorum policy.
6. **MultiversX anchoring** (`MULTIVERSX_ANCHORING.md`).
   Reuse `src/dsm/multiversx`; anchorer job + anchor-ref resolution; fixtures only
   in tests.
7. **Receipt v2** — assemble `{entry, inclusion_proof, witnessed STH, anchor_ref}`;
   deprecate the P0/P1 ad-hoc receipt behind a version flag.
8. **H1–H4 migration** — move key-history/attestation/dispatch/seal onto `bind()`
   (`BIND_PRIMITIVE.md` §3); re-run the audit attacks as regression tests.

Ordering rationale: 1→2→3→4 builds the trust spine; 5 and 6 add distribution and
public anchoring; 7 exposes it; 8 retires the legacy binding bugs.

## 3. Interaction with the P0 kernel (compatibility plan)

- **Pinned tip stays.** The P0 tip/`reconcile` remain the cheap first-line check.
  The MMR root is the *cryptographic* completeness check layered above it; the two
  MUST agree on `entry_count`.
- **`reconcile` + MMR.** Forward reconcile (crash window) also advances the MMR by
  replaying the orphan leaf. A NON-FORWARD divergence stays refused (P0 behaviour);
  recovery additionally requires the new tree to be consistency-provable or it is
  rejected — recovery can never produce an MMR that fails `σ`.
- **No entry rewrite, ever.** All P2 work reads existing entry hashes; the
  append-only invariant is preserved.

## 4. Migration & versioning

- **SemVer:** P2 lands as **v2.0.0** (breaking receipt/verification format).
- **Backfill:** build each shard's MMR from existing entry hashes; issue and anchor
  a **genesis STH**. Pre-genesis history is provable only relative to genesis
  (stated honestly — `P1_SECURITY_MODEL.md` §6).
- **Dual-read window:** verify accepts legacy `v0/v1` receipts (read-only) and new
  `v2` for two minor versions, then legacy is dropped.
- **Capability flag:** the transparency log ships disabled by default until the
  verifier and ≥ `k` witnesses are operational; enabling is opt-in per deployment.

## 5. Acceptance gates

- **P1 → review:** ADR-0003 §7 met (specs consistent; model tests enumerated;
  security model explicit).
- **P2 module gate:** each module passes its `P1_MODEL_TESTS` section before the
  next depends on it.
- **P2 → v2.0.0:** end-to-end receipt verification (`P1_MODEL_TESTS` §7) passes with
  a live reference witness + devnet anchor; external crypto review booked.

## 6. Explicit non-goals (now)

- No MMR/STH/witness/anchoring **code** in P1.
- No P2 start in this branch.
- No GitHub Release, no PyPI publish.
- No changes to `src/` or `agent-mesh/` in P1.

## 7. Beyond P2 (parking lot, not committed)

- Multi-shard aggregated checkpoints (one STH covering many shards).
- Public witness network / log list (à la CT log list).
- Formal model (TLA+/Alloy) of monotonicity + non-equivocation.
- Independent third-party cryptographic audit and published report.
