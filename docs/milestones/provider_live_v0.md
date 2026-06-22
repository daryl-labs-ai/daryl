# Provider-live v0 — Internal Milestone Note

Closed after PR #43 (`provider-output-normalization-v0`) and PR #44
(`docs-live-accepted-smoke-v0`). Internal note only; not a product claim.

## Status

Provider-live v0 is CLOSED as `PROVEN REACHABLE`.

This means the live provider path has been observed to reach both:

- safe rejection;
- accepted-for-audit.

It does not mean repeatability or reliability.

## What was proven

### Live rejection path

A weak or invalid live provider output can be rejected as
`rejected_by_validator` without crashing, while still producing an audit trail.

### Live accepted path

A sufficiently structured and honest live provider output can be normalized,
validated, persisted, and accepted as `accepted_for_audit`.

The accepted path was observed after PR #43, which added fenced JSON
normalization without loosening validation.

## Trust boundary

The provider remains an untrusted proposer.

DSM keeps authority over:

- validation status;
- accepted/rejected/review classification;
- audit persistence;
- Agent Memory explanation.

The provider does not get to assign truth, status, or business decision
validity.

## Semantics of accepted_for_audit

`accepted_for_audit` means:

- the proposal is structured enough to audit;
- the proposal is honest enough about its limitations;
- DSM can persist and explain the decision.

It does not mean:

- factual truth;
- reasoning validity;
- business decision approval;
- external verification;
- external anchoring;
- repeatability;
- reliability.

## Why the accepted run was considered merited

The accepted live run was considered merited because:

- substantive coverage was claimed for three checks:
  - `bug_before_feature`
  - `known_context_not_reasked`
  - `persistence_failure_checked`
- `external_evidence_limit_disclosed` was not falsely claimed as covered;
- missing or limited external evidence was surfaced through coverage and
  limitations;
- `truth_claim` was false;
- no candidate rule was auto-promoted;
- no provider-supplied DSM status was accepted;
- anti-echo behavior remained tested and intact.

## What must not be claimed

Do not claim:

- provider-live is reliable;
- provider-live is repeatable;
- `accepted_for_audit` proves truth;
- `accepted_for_audit` proves business correctness;
- `accepted_for_audit` proves external evidence;
- the system is production-ready from this milestone alone.

## Stop condition

This milestone is complete.

Do not continue building on momentum.

Next work must be opened as a separate decision and justified by a concrete
need, such as:

- repeatability;
- deterministic end-to-end coverage gap;
- deployment requirement;
- second domain/skill requirement;
- product integration requirement.

## Safety

No raw provider output, dogfood artifacts, or local smoke data are committed as
part of this milestone note.
