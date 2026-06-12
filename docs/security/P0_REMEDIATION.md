# P0 Security Remediation — Report

**Branch:** `security/p0-tamper-evidence-hardening`
**Base commit (audited):** `a758bdc`
**Date:** 2026-06-12
**Scope:** P0 only — the blocking issues that prevented DSM from being
presented as tamper-evident. No MMR/STH/witness/anchoring yet (that is P1).

## Result at a glance

| Suite | Baseline | After P0 |
|---|---|---|
| DSM core tests | 1296 passed | **1304 passed** (+8 adversarial) |
| agent-mesh tests | 192 passed | **203 passed** (+11 adversarial) |
| Coverage (core) | 89.02 % | 89.04 % |
| ruff (`src/ tests/`, `agent-mesh`) | clean | clean |
| bandit `-ll` (`src/`, `agent-mesh/src`) | clean | clean |

Every adversarial test was authored and **verified red on the baseline**
before the corresponding fix, then made green. The full suite is green.

---

## Findings corrected

### C1 — Trailing truncation was undetected
**Before:** `verify_shard()` validated only the internal `prev_hash` chain.
Deleting the last N entries of a shard left a still-valid prefix, so
verification returned `status: OK, tampered: 0, chain_breaks: 0`. Reproduced:
10 entries → delete 4 → still `OK`.
**After:** `verify_shard()` reads the pinned tip (`integrity/{shard}_last_hash.json`)
and compares observed tip hash + entry count against it:
- observed count `<` pinned → `status=TAMPERED`, `mismatch_type=TRUNCATION`,
  `truncation_detected=True`;
- same count, different tip → `TAMPERED` (tail tampering);
- observed count `>` pinned → `AHEAD_OF_PIN` warning (crash window, recoverable;
  not a loss, does not fail verification);
- no pin → `pin_status=UNPINNED` (explicit, never a silent `OK`).
The result now carries structured evidence: `expected/observed_last_hash`,
`expected/observed_entry_count`, `chain_tip_mismatch`, `entry_count_mismatch`,
`mismatch_type`, `warnings`.
Files: `src/dsm/verify.py`. Tests: `tests/security/test_p0_truncation_c1.py`.

### Reconcile could launder a truncated state
**Before:** on any tip divergence, `reconcile_shard()` recomputed the entry
count and **overwrote** the pin — including shrinking it to match a truncated
tail, erasing the only evidence of truncation.
**After:** `reconcile_shard()` classifies divergence by direction:
- **FORWARD** (segment has *more* entries than the pin = K-2 crash window):
  advances the pin, as before. Safe.
- **NON-FORWARD** (truncation or tail tamper): in the default (safe) mode it is
  **REFUSED** — the pin is left intact and a `{shard}_divergence.<ts>.json`
  report is written. Recovery requires the explicit `allow_truncation=True`
  flag, which quarantines the superseded pin
  (`{shard}_last_hash.quarantine.<ts>.json`), logs an audit warning, and only
  then advances. Default behaviour is safe; destructive acceptance is opt-in
  and audited.
Files: `src/dsm/core/storage.py`. Tests: same file as C1.

### H5 — Caller-supplied hash accepted on write
**Before:** `storage.append()` computed the hash only `if not entry.hash`, so a
producer could pre-set an arbitrary hash that DSM persisted and chained.
**After:** `append()` **always** recomputes the canonical hash; a non-empty
mismatching caller hash is dropped and logged as an audit signal.
Files: `src/dsm/core/storage.py`. Tests: `tests/security/test_p0_caller_hash_h5.py`.

### C2 / H6 / H7 — agent-mesh exposed without guards
**Before:** API bound `0.0.0.0` with no auth; `submit_task_result` accepted a
result from any registered agent; `events.jsonl` grew without bound.
**After:**
- **C2** — API-key dependency (`server/auth.py`) on all sensitive endpoints
  (`X-API-Key` or `Authorization: Bearer`, constant-time compare). Enforcement
  activates when `AGENT_MESH_API_KEY` is set; `create_app()` **refuses to start**
  when `APP_ENV=production` and no key is configured.
- **H6** — `submit_task_result` requires `agent_id == task.assigned_to`
  (`403 agent_not_assignee`), after the agent-known check so the existing `422`
  contract is preserved.
- **H7** — `DSMWriter` enforces `max_event_bytes` and `max_log_bytes` (refuse →
  `None`); the result route caps attacker-controlled content (`413`). Config/env
  driven with safe defaults.
Files: `agent-mesh/src/agent_mesh/{config,server/auth,server/app,server/routes,dsm/writer}.py`.
Tests: `agent-mesh/tests/test_p0_hardening.py`.

### D1 — False public claims
Corrected README + the `storage.py` kernel header: removed “frozen since March
2026 / zero modifications” (the repo's first commit is 2026-04-12), softened
“proof of every decision / admissible as evidence / EU AI Act by design”, and
added a **Threat model & limitations** section. Files: `README.md`,
`src/dsm/core/storage.py`.

---

## Guarantees now held

- **Trailing truncation is detected** by `verify_shard` against the pinned tip.
- **Reconcile cannot silently shrink the pin**; truncation acceptance is
  explicit, audited, and preserves the superseded pin.
- **Stored hashes are always DSM-computed**; a caller cannot inject a hash.
- **agent-mesh** is fail-closed in production (no key → no start), authenticated
  on sensitive endpoints, enforces task ownership, and bounds its append log.
- **Public claims match the code**, with an explicit threat model.

## Guarantees still NOT held (residual)

- **Fully-privileged local adversary.** The integrity pin lives on the same host
  as the data. An attacker who rewrites *both* the shard *and* the pin (and any
  divergence reports) in one step can still present a consistent shorter
  history. The pin raises the bar and makes the default tooling fail-closed, but
  it is not a cryptographic anchor.
- **Non-equivocation / split-view.** Nothing yet stops an operator from showing
  different histories to different verifiers.
- **Third-party-verifiable receipts.** Receipts bind to a shard state but are not
  anchored; a later truncation is not provable to an outside party from the
  receipt alone.
- **Cryptographic binding gaps (H1–H4 from the audit) are NOT in P0 scope:** key
  revocation status outside the key-history hash, attestation excluding
  `dispatch_hash`, dispatch excluding agent IDs, unsigned seals. These remain.
- **No rate limiting / RBAC** in agent-mesh — only a single shared API key and
  size bounds. Per-tenant quotas and a real authz model are future work.
- **`startup_check`** logs/writes a divergence report on a refused reconcile but
  does not yet surface it as a hard error status; consumers should check
  `verify_shard` (which does fail) and the divergence reports.

## Next step — P1 (architecture)

The durable fix for the residual items is to replace the ad-hoc proof layer
with a **transparency-log** design (see `DSM_PLAN_EVOLUTION_MAINTAINER.md`):

1. **Merkle Mountain Range** over existing entry hashes → O(log n) inclusion +
   **consistency proofs** (the mathematically correct anti-truncation guarantee).
2. **Signed Tree Head** checkpoints (Ed25519) → completeness provable against a
   signed `{size, root}`.
3. **Witness cosigning** → defeats equivocation/split-view.
4. **MultiversX anchoring** of the STH root → public, third-party,
   non-repudiable timestamp; makes receipts genuinely portable.
5. A single `bind()` primitive (serialize+sign the whole record) → eliminates the
   H1–H4 “field left outside the hash” class by construction.
