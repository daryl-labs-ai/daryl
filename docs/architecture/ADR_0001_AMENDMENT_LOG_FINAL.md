# ADR 0001 — Final Amendment Log

- **Date:** 2026-04-20
- **Status transition:** Proposed → Accepted
- **Branch:** proto/phase-7a-rr-action-name-index @ e570841 (not merged — merge is
  Phase 7b prerequisite, not this phase)

## Documents amended in-place

| Document | Change | Nature |
|---|---|---|
| `ADR_0001_CANONICAL_CONSUMPTION_PATH.md` | Status, Decision reconciliation, Acceptance gate marked satisfied, Open questions marked resolved, Non-actionable observations added, Migration plan notes | Authoritative |
| `ADR_0001_PHASE_7A_5_VERDICT.md` | `## Resolution` section appended | Pointer |
| `ADR_0001_PHASE_7A_5_BIS_VERDICT.md` | `## Resolution` section appended | Pointer |
| `ADR_0001_STORAGE_READ_PROBE.md` | `Strategic implication` section rewritten in-place (replaces hypothetical branches with resolved state) | Update |
| `ARCHITECTURE.md` | Canonical Consumption Path section, RR architecture pointers, test count annotation | Update |

## Documents NOT amended

- `ADR_0001_SESSIONINDEX_CLASSIFICATION.md` — classification remains `duplicative`, verdict intact.
- `ADR_0001_PHASE_7A_VERDICT.md` — PASS intact, prior amendments A/B/C/D intact.
- `ADR_0001_PHASE_7A_5_ROOTCAUSE.md` — decomposition intact.
- `ADR_0001_PHASE_N1A_VERDICT.md` — PASS intact (it is the most recent verdict, no pointer needed).
- `ADR_0001_AMENDMENT_LOG_2026-04-19.md` — prior (mid-chain) log intact.

## Code NOT modified

- `src/dsm/core/` — kernel untouched (frozen 2026-03-14).
- `src/dsm/session/` — SessionIndex untouched.
- `src/dsm/rr/` — no change from N+1A final state.
- `tests/` — no change.
- `benchmarks/` — no change.

Verified by `git diff e570841..HEAD -- src/dsm/ tests/ benchmarks/` = empty at close of this phase.

## Scope declaration

This log is trace-only. It introduces no normative rule not already present in ADR 0001
or the referenced verdict reports. If a future change is needed, it belongs in the ADR
itself, not here.

## Next step

Phase 7b — rebind the 8 live consumers of SessionIndex to RR, and deprecate SessionIndex
on the agreed horizon. Scope defined by ADR 0001 Migration plan > Phase 7b. Not started
by this amendment.
