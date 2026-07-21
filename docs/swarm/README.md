# DSM Swarm Grounding Layer — v0.1 (semantic core)

Grounds multi-agent runs in DSM as **append-only, tamper-evident receipts**,
then derives every stateful reading by replay. Transplanted under control from
the out-of-repo Swarm v0.1 candidate package, reconciled file by file against
this repository's real contracts (kernel frozen, `LEGITIMATE_WRITERS`
unchanged at 20).

## Where things live

| Concern | Location |
|---|---|
| Pure models + envelope (`to_swarm_entry` / `from_swarm_entry`) | `src/prl/swarm/types.py` |
| Closed action set (`SWARM_ACTION` / `SWARM_ACTIONS`) | `src/prl/swarm/types.py` — the ONLY definition point |
| Replay & derivations (projection, supersession, conflicts, coverage) | `src/prl/swarm/replay.py` — pure, kernel-free |
| The one physical `Storage.append` call site (bounded writer) | `PRLStore.commit_swarm_entry` in `src/prl/store/dsm_commit.py` (registered writer; no new `LEGITIMATE_WRITERS` entry) |
| JSON schemas generated from the final models | `src/prl/swarm/schemas/` (concordance enforced by test) |
| Focused examples (valid / invalid / diagnostic scenarios) | `docs/swarm/examples/` |

Integrated actions (closed set, v0.1): `swarm.run`, `swarm.task`, `swarm.work`,
`swarm.review`, `swarm.decision`, `swarm.conflict`.
**Deferred deliberately**: `swarm.context_grant` (authority/context
distribution) and `swarm.memory_candidate` (the memory-promotion frontier stays
closed until a promotion policy is designed).

## Write path (proved against the real kernel)

- Every swarm append goes through `commit_swarm_entry`, which refuses — before
  any append — wrong `source`, wrong contract version, any `action_name`
  outside the closed set, any payload that fails its model (re-validated, not
  trusted), any kind/action mismatch, any `session_id != swarm_run_id`.
- The writer stamps the real `DSM_KERNEL_VERSION` (`"1.0"`) into
  `metadata['kernel_version']` at the kernel boundary.
- Reads: RR only. `navigate_action("swarm.*")` provides the **authoritative
  order** (timestamp ascending); entries are resolved by **join on
  `entry_id`** — the raw order of `resolve_entries` / `Storage.read` carries no
  swarm semantics.

## Semantic invariants (non-negotiable)

- A `WorkReceipt` is a **work claim**, not proof the work happened
  (`work claim != verified work`).
- A `ReviewReceipt` is a **declared opinion/verification**, not objective
  truth; agreement between reviews is corroboration, **not proof**
  (`review agreement != proof`).
- A `DecisionReceipt` records a decision and its declared bases, not the truth
  of the world (`decision != truth`). Stored status never includes
  `conflicted` — conflict is a derived overlay.
- A `ConflictRecord` records an observed incompatibility, **never its
  resolution**; `state='resolved'` requires an explicit `resolution_ref`.
- No record auto-promotes memory; no record retroactively modifies an earlier
  record. Supersession is **declared by id** and its effect (latest-wins) is a
  **derived projection**, applied only when the chain is valid and unambiguous
  (same run, closed compatibility matrix `decision -> decision`, no
  self-supersession, no cycle, no concurrent branches — those are surfaced as
  diagnostics, never silently resolved).
- `required_checks`, `claimed_checks` and `actual_checks` are three distinct
  axes; **coverage is computed by the projection and never trusted from the
  author**. It measures declarative completeness, not truth of the work.
- `agent_id` stays distinct from `carrier.model` — identity is never defined
  by its carrier (ADR-PRL-0009).
- The replay **observes; it never writes**: derived conflicts and diagnostics
  live only in the projection (derived, droppable, never a second source of
  truth).
- Integrity of a receipt (hash chain, `verify_shard`) certifies **storage**,
  never real-world truth.

## Status

Kernel write path proved and semantic core integrated on a real DSM store
(append → chain → RR replay → projection → `verify_shard` OK → tamper
detected). Benchmark protocol NOT integrated; no live/paid runs.
