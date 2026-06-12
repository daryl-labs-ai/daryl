# P0 Security Remediation — Baseline

**Branch:** `security/p0-tamper-evidence-hardening`
**Reference commit (audited):** `a758bdc`
**Date:** 2026-06-12
**Python:** 3.12.13

This file records the repository state **before** any P0 remediation, so the
effect of each change is measurable. No source was modified to produce it.

## Environment

| Item | Value |
|---|---|
| `python --version` | Python 3.12.13 |
| `git status` | clean (no uncommitted changes) |
| Editable installs | `dsm-primitives`, `daryl-dsm[dev]`, `agent-mesh[dev]` |

## Test & lint baseline

| Command | Result |
|---|---|
| `pytest tests/` (core DSM) | **1296 passed, 52 skipped** |
| `pytest agent-mesh/tests/` | **192 passed** |
| `pytest --cov=src/dsm` | **89.02 %** total (fail_under=75) |
| `ruff check src/ tests/` | All checks passed |
| `bandit -r src/ -ll` | No medium+ findings |
| `bandit -r src agent-mesh/src agent-mesh/workers -ll` | No medium+ findings |

> Note for reviewers: bandit reports **nothing** because the P0 vulnerabilities
> are *architectural* (a verifier that ignores the pinned tip, a binding that
> excludes a field), not syntactic. Static analysis cannot see them. This is
> precisely why adversarial tests are added before the fixes (Step 1).

## Known P0 vulnerabilities targeted by this branch

| ID | Description | Status at baseline |
|---|---|---|
| C1 | Trailing truncation undetected — `verify_shard` ignores the pinned tip/count | **Reproduced** (see `tests/security/test_p0_*`) |
| — | `reconcile_shard` silently rewrites the pin to match a truncated tail | **Reproduced** |
| H5 | Caller-supplied `entry.hash` accepted on write (`if not entry.hash`) | **Reproduced** |
| C2 | agent-mesh API binds `0.0.0.0` with no authentication | Confirmed in `agent-mesh/start.py` / `server/routes.py` |
| H6 | Open agent registration + `submit_task_result` does not check `agent_id == task.assigned_to` | Confirmed |
| H7 | `events.jsonl` has no size cap / rotation; unbounded attacker-controlled writes | Confirmed |

Public-claim issues (README/docs) are tracked separately in Step 6 of the
remediation and corrected only alongside the corresponding code change.
