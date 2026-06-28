# ADR-PRL-0008 — Agent Consultation Protocol

**Status:** Accepted — ratified-by-Mohamed 2026-06-27 · **Version:** v1 · **Date:** 2026-06-27 · **Regime:** `declared`
**Depends on:** ADR-PRL-0001 (Constitution), 0002 (Citizens), 0004 (Messages/MEF), 0007 (Adapter Strategy)
**Axis:** protocol / adoption — composes ratified pieces. **Nature:** defines **a rule, not an
implementation.** No runtime types, no wire format, no CLI design, no kernel change.

> **PRL does not make project knowledge true. It makes project knowledge governable.**

**Why now.** The grounding (`AGENT_CONSULTATION_GROUNDING.md`) showed the *insertion surfaces* exist
but the *epistemic surfaces* (Observation/Proposal/Resolution, MEF, producer attribution,
consultation, adapter boundary, no-ratification boundary) are **absent from code**. So a plain
implementation ticket would be premature: the **rule** must be fixed first.

## Decision (the rule)

> A live agent consultation emits an **attributed Knowledge Act** — an **Observation**, or an
> **Observation + Proposal** — **through an Adapter**, **certified by DSM**, and **never ratified by
> the agent**.

## The load-bearing invariant

> **Agent answers are not claims by default. They are Observations unless the adapter explicitly maps
> them into Proposals.**

Without this default, "Claude answered X" silently becomes "X is a governed proposal" — re-creating
exactly the failure 0001/0004 exist to prevent. Promotion from Observation to Proposal is an
*explicit, attributable* act, never implicit.

## The rules (minimal)

1. **Default = Observation.** An agent's answer is recorded as an Observation — a witnessed event
   ("X, consulted on K, answered Y") — *unless* explicitly promoted. It makes no claim on K's standing.
2. **Proposal only by explicit mapping.** An `Observation + Proposal` requires an explicit adapter
   decision; it never arises implicitly from an answer.
3. **Producer attribution is mandatory.** Every consultation act names its producer = model + adapter
   version (0007).
4. **The agent never ratifies.** Only a human or witnessed **Resolution** may accept a Proposal
   (0001 L4, 0004 Ch6). A consultation never changes K's standing by itself.
5. **Every act is certified.** Each consultation message is projected and certified by DSM (a
   receipt); the answer becomes a Knowledge Act, not a transient reply.
6. **MEF is carried.** Every consultation message carries a complete MEF (0004 Ch2); the adapter
   refuses if it cannot supply one.

## Enforcement (per the 0001 discipline)

- *Default = Observation* → the consultation path produces an Observation; reaching `Proposal`
  requires a distinct, attributed mapping step (a type/lint when built makes the implicit path
  impossible).
- *Agent cannot ratify* → the adapter is a Producer citizen (0002); a `Resolution` is unreachable
  from the adapter (capability surface → lint).
- *MEF non-strippable* → the 0004 Ch2 invariant applies unchanged at the consultation boundary.

## Non-goals

No runtime types or schema, no encoding/wire format, no `consult` CLI design, no multi-agent
convergence/merge, no kernel change. The open questions in `AGENT_CONSULTATION_PROTOCOL_PLAN.md` §8
(regime of the consultation event, context passed to the agent, prompt-as-evidence, idempotency, may
an agent read the Fabric) are **not settled here** — they stay open.

## Consequences & sequence

- This is the **first runtime epistemic surface**; the default-to-Observation rule protects the whole
  standing system before any code exists.
- **Next:** a Code grounding pass on the real kernel (`Storage.append` signature, the forbid-storage
  lint, RR resolve), **then** an implementation issue. Adoption gets a `PROOF_LOG.md` entry; if the
  *Knowledge Act* or *"projects augment intelligences"* framing guided the call, a
  `FRAMING_DECISION_LOG.md` row.
