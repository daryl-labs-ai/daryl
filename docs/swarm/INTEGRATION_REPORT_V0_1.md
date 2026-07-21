# DSM Swarm Grounding Layer v0.1 — Integration Report

Branch: `feat/dsm-swarm-grounding-v0.1` (base: canonical `main` @ `0ec530a`).
Controlled, verification-first transplantation from an out-of-repo candidate
package. Every candidate file was evaluated against this repository's real
contracts; nothing was copied blindly, and the candidate's own test results
were never reused as proof.

## Objective of this slice

Ground multi-agent (swarm) activity in DSM as append-only, tamper-evident
receipts — delegation, work claims, reviews, decisions, observed conflicts —
and derive every stateful reading (standing, supersession, conflict signal,
check coverage) by pure replay. No orchestration, no benchmark execution, no
memory promotion.

## Architecture retained

- **Pure layer** — `src/prl/swarm/` (kernel-free: no `Storage`, no `dsm.core`
  import):
  - `types.py`: pydantic models (`extra="forbid"`), the CLOSED action set
    (`SWARM_ACTION` / `SWARM_ACTIONS` — single definition point), and the
    envelope mapping `to_swarm_entry` / `from_swarm_entry` over the existing
    `EntryDraft` (no second envelope). Canonicalization via `prl._canonical`
    (neither `dcp` nor `rfc8785` was added).
  - `replay.py`: deterministic, read-only projection (`project_run`).
- **Bounded writer** — `PRLStore.commit_swarm_entry` in
  `src/prl/store/dsm_commit.py`, the ONE physical `Storage.append` call site
  for swarm records. `dsm_commit.py` was already in `LEGITIMATE_WRITERS`
  (still exactly 20 entries; the static gate `scripts/forbid_storage_access.py`
  is unchanged). No `src/prl/store/swarm_commit.py` was created.
- **Kernel** — `src/dsm/**` untouched (`git diff main...HEAD -- src/dsm/` is
  empty). `DSM_KERNEL_VERSION = "1.0"` is read from the packaged marker and
  stamped into `metadata['kernel_version']` by the writer, at the kernel
  boundary.

## Actions integrated (closed set, v0.1)

`swarm.run`, `swarm.task`, `swarm.work`, `swarm.review`, `swarm.decision`,
`swarm.conflict`.

Deliberately NOT integrated: `swarm.context_grant`, `swarm.memory_candidate`
(refused by the writer), the benchmark protocol, `SwarmRecorder` /
`NoOpRecorder`, and any orchestrator / scheduler / planner / router / merge
engine. These require separate missions with their own contracts.

## Writer boundary

`commit_swarm_entry` refuses, with `PRLValidationError` and **before any
append** (proved by shard-count assertions):

1. `source != "swarm"`;
2. envelope `version != "swarm.v0.1"`;
3. `metadata['schema_version'] != "swarm.v0.1"`;
4. `action_name` outside the closed `SWARM_ACTIONS` set (PRL and arbitrary
   actions cannot borrow the path);
5. payload failing its swarm model (re-validated via `from_swarm_entry`,
   never trusted);
6. decoded kind not matching the declared `action_name`;
7. `session_id != swarm_run_id` (run-scoped replay integrity).

## RR contracts (as observed in this repository)

- `navigate_action(action_name)` returns the **authoritative order**
  (timestamp ascending, stable insertion tiebreaker).
- `resolve_entries(records)` does NOT preserve caller order (disk order per
  shard) — consumers join record→entry by `entry_id` and replay in the
  records' order. The raw order of `Storage.read` (newest-first) carries no
  swarm semantics.
- `verify_shard(storage, shard)["status"]` is a `VerifyStatus` enum; success
  is `status == VerifyStatus.OK`. Deliberate payload tampering was proved to
  flip it to `VerifyStatus.TAMPERED`.

## Semantics of claims (non-negotiable)

- A `WorkReceipt` is a **claim** of work, not proof the work happened.
- A `ReviewReceipt` is a declared opinion/verification; agreement between
  reviews is corroboration, **never proof**.
- A `DecisionReceipt` records a decision and its declared bases, not world
  truth; stored status never includes `conflicted`.
- A `ConflictRecord` records an observed incompatibility, never its
  resolution (`resolved` requires an explicit `resolution_ref`).
- No record auto-promotes memory or retroactively modifies an earlier record.
- Receipt integrity (hash chain) certifies **storage**, never real-world truth.
- `agent_id` is never derived from `carrier.model`.

## Supersession rule (derived only)

Declared by id (`supersedes`), same run only, closed compatibility matrix
`decision -> decision`. The latest-wins effect is applied by the projection
ONLY when the chain is valid and unambiguous. Self-supersession, missing or
mistyped targets, cycles and concurrent branches are surfaced as diagnostics
(`supersession_ambiguous` withholds the reading) — never silently resolved.
The superseded record is preserved in full history.

## Conflicts

- **Explicit**: `ConflictRecord` (latest-wins per id); an unresolved one is
  surfaced as an observation (`conflict_unresolved`).
- **Derived by replay** (`DERIVED_CONFLICT_KINDS`): `reviews_divergent`,
  `concurrent_supersession`, `supersession_cycle`, `decision_on_superseded`,
  `required_checks_uncovered`. The replay observes; it never appends derived
  conflicts back to DSM.

## Check coverage (computed, never author-supplied)

Per `WorkReceipt`: `required` / `claimed` / computed `missing`, `unrequested`
and `ratio` (`None` when nothing was required — not 1.0). No model field lets
an author supply a coverage number. Coverage measures **declarative
completeness only** — it is not proof that checks ran, nor that the work
happened.

## Limitations of this slice

- Review divergence is derived from verdict polarity only (closed vocabulary
  `approve|reject|inconclusive`); findings are not analyzed.
- Supersession covers decisions only (v0.1 matrix).
- `project_run` is single-run; no multi-run aggregate.
- Reviews attach to tasks via `reviewed_ref` ∈ {task, work}; a review of a
  decision stays run-level.
- `docs/swarm/examples` is a focused selection, not the full candidate corpus.

## Validation commands

```bash
.venv/bin/python scripts/forbid_storage_access.py   # OK, exactly 20 writers
.venv/bin/python -m pytest tests/ -q                # full suite green
.venv/bin/python -m pytest agent-mesh/tests/ -q     # green
.venv/bin/ruff check src/ tests/                    # clean
.venv/bin/bandit -r src/ -ll                        # clean
git diff main...HEAD -- src/dsm/                    # empty (frozen kernel)
git diff main...HEAD -- scripts/forbid_storage_access.py  # empty (allowlist)
```

## Final status

**DSM Swarm semantic core integrated**: real kernel write path proved
(append → chain → RR replay in authoritative order → projection →
`verify_shard` OK → tamper detected), semantic core (work/review/decision/
conflict + derivations) integrated and tested in-repo.

This report does NOT claim: that DSM proves truth; that declared work
actually happened; that Swarm is an orchestrator; that any benchmark was
executed; that the system is production- or live-ready; or that memory
promotion exists.
