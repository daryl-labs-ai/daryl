# Decision Dogfood v0

## Purpose

Decision Dogfood v0 is a manual human-loop method for using Daryl on real
project decisions.

It is not a product feature.
It is not a project database.
It is not a new schema.
It is not a test framework.
It is not an autonomous advisor loop.

The goal is to answer a practical question:

> Does Daryl help a human decide what to do with an AI recommendation?

## Core loop

The advisor proposes once.
DSM audits form, honesty, boundaries, required checks, and limits.
The human decides.
Agent Memory records why.
The outcome is appended later.

The advisor may be ChatGPT, Claude, LM Studio, Ollama, or another provider.

The advisor is never the authority.

## Trust boundary

The provider proposes.
DSM validates boundaries.
DSM assigns status.
The human decides.
Agent Memory records the audit.

DSM does not decide whether the recommendation is true.
DSM does not decide whether the recommendation is strategically correct.
`accepted_for_audit` means auditable, not correct.

## Why no new test

A test would only prove that a project recommendation can be captured.

That is not the current bottleneck.

The current bottleneck is utility: whether the audit helps with a real decision.

Therefore v0 is manual dogfood, not new machinery.

## Local LLM usage

A local LLM may be used as advisor through the already existing provider-live /
gateway machinery (see `tools/agent_proposal_gateway_v0/LIVE_SMOKE.md`). No new
runtime is introduced.

Allowed:

- one advisor proposal
- one DSM audit
- one human decision
- one Agent Memory audit record
- later outcome appended manually

Not allowed:

- retry loop
- autonomous action
- autonomous decision
- self-invoking advisor
- advisory orchestrator
- new connector
- new API
- new MCP
- new dashboard

The LLM output should be treated as a non-authoritative proposal.

The human should explicitly ask:

- Would I have decided the same without the advisor?
- Did the fluency of the answer influence me?
- Did DSM reveal a missing check, overclaim, or uncertainty?
- Did Daryl help, or did it only add ceremony?

## Scope

Apply this method to 1-3 real decisions.

Prefer decisions with concrete required checks.

A meta decision about Daryl may be used once, but it must not become an infinite
self-referential loop.

After the self-dogfood cap, apply the method to one external real decision,
preferably Omari/BTP if a live decision exists.

## Recommended first external decision

Use Omari/BTP if there is a live decision with concrete checks.

Examples:

- Should Omari/BTP build the next workflow manually or automate it now?
- Should the next Omari/BTP report flow add DSM audit before adding dashboard
  features?
- Should an AI-generated construction report recommendation be accepted,
  rejected, or sent to human review?

The decision should have concrete checks, such as:

- context was not re-asked unnecessarily
- missing project facts were surfaced
- required risks were mentioned
- limits were disclosed
- no external fact was invented
- no action was automated
- human decision remained explicit

## Manual capture fields

For each decision, capture:

- decision_id
- project
- decision_question
- current_project_state
- advisor
- advisor_recommendation
- context_used
- required_checks
- checks_covered
- checks_missing
- constraints_respected
- risks
- non_claims
- DSM status
- human_decision: follow / reject / defer / needs_review
- decision_reason
- action_taken
- later_observed_outcome: appended later
- lesson_learned: appended later

## First decision record template

### decision_id

decision-dogfood-001

### project

TBD

### decision_question

TBD

### current_project_state

TBD

### advisor

TBD: ChatGPT / Claude / LM Studio / Ollama / other

### advisor_recommendation

TBD

### context_used

TBD

### required_checks

TBD

### checks_covered

TBD

### checks_missing

TBD

### constraints_respected

TBD

### risks

TBD

### non_claims

This record does not prove that the recommendation is true.
This record does not prove that the recommendation is strategically correct.
This record does not prove Daryl is useful.
This record only captures a bounded recommendation and a human decision.

### DSM status

TBD: accepted_for_audit / needs_human_review / rejected_by_validator

### human_decision

TBD: follow / reject / defer / needs_review

### decision_reason

TBD by Mohamed.

### action_taken

TBD after decision.

### later_observed_outcome

Append later.

### lesson_learned

Append later.

## Stop condition

After 1-3 real decisions, stop and review:

- Did Daryl clarify the decision?
- Did it expose missing context?
- Did it reveal overclaiming?
- Did it identify required checks?
- Did it help Mohamed decide?
- Did it only add ceremony?

If it did not help, record that honestly.

Do not turn this into a project-management system before one external real
decision has been audited manually.
