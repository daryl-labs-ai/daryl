# ADR-PRL-0009 — Structured Contributor Attribution (`agent_id` ≠ `model_id`)

**Status:** Accepted — ratified-by-Mohamed 2026-06-28 · **Version:** v1 · **Date:** 2026-06-28 · **Regime:** `declared`
**Depends on:** ADR-PRL-0001 (Constitution), 0002 (Citizens), 0004 (Messages/MEF), 0007 (Adapter Strategy), 0008 (Consultation)
**Axis:** epistemic frame extension — answers *"who contributes?"*. **Nature:** defines **a rule and a
frame structure, not an implementation.** No Pydantic/wire specifics, no registry design, no CLI.

> **Identity is never defined by its carrier.** A logical contributor must survive a change of model,
> provider, adapter, or run.

## Why now
The grounding (`IDENTITY_AGENT_GROUNDING.md`) found the **mirror image** of `claim_id`: contributor
identity today **is** its carrier — `producer = f"{provider}:{model} (adapter)"` — so in practice
**`agent_id == model_id`**, exactly the anti-pattern this ADR forbids. The second identity pillar is
not to be *proven* but to be *established*, and it changes the attribution carried in the **MEF**
(ADR-PRL-0004), so it needs a ratified rule before code.

## Decision (the rule)

> Introduce **structured contributor attribution**. The logical contributor is a **frame-level**
> identity in the MEF; the execution carrier is recorded **alongside** it; the legacy `producer`
> string becomes a **display projection**, not the source of truth.

```
MEF.agent_id        = the stable logical contributor        (frame-level; "who contributes?")
MEF.producer        = legacy display / compatibility projection (NOT source of truth)
carrier.provider    = openai / anthropic / local / human
carrier.model       = gpt-4o / claude-… / llama-…
carrier.adapter     = consult-adapter v1
Entry.session_id    = run_id (already separate)
```

`agent_id` is **frame-level (in the MEF)** — not Extended Frame — because *"who contributes?"* is part
of the epistemic regime of an act, not enrichment metadata.

## The load-bearing invariant

> **`agent_id` is never derived from `provider` / `model` / `adapter` / `run`.** It is a minted/assigned
> logical identity (the contributor's mirror of `claim_id` ∉ storage). The carrier is recorded *next to*
> it — the *carrier-of-record* — never as its source.

## The rules (minimal)

1. **`agent_id` is frame-level and logical.** It lives in the MEF and names the contributor
   (`agent.<role>`, `human:<id>`). It is not computed from the carrier.
2. **Carrier-of-record alongside.** `provider` / `model` / `adapter` are recorded with the act (the
   execution that produced it); `run` stays `Entry.session_id`. They answer *"what executed this"*,
   separately from *"who contributed"*.
3. **`producer` is a display projection.** It remains visible (a projection of `agent_id` + carrier)
   so existing readers keep working, but it is **not** the source of truth.
4. **No read-time inference. Unknown means unknown.** Acts written before this ADR carry only
   `producer` and **no `agent_id`**. They remain **readable**, with `agent_id` **absent/None** — never
   fabricated, never back-derived from the carrier.
5. **MEF stays complete-or-refuse.** The existing required fields are unchanged. `agent_id` is
   type-optional (so legacy acts read) but **producer-required**: new consultation/resolution acts
   MUST set it (enforced at the producer/adapter, not by weakening the frame).
6. **The human is a contributor too.** `human:mohamed` is an `agent_id` (carrier `provider = human`);
   humans get the same structure, not a special case.

## Enforcement (per the 0001 discipline)
- *`agent_id` ∉ carrier* → the producer/adapter assigns `agent_id` independently of `provider`/`model`/
  `adapter`; a test/lint asserts it is not a function of the carrier string.
- *Backward compatibility* → legacy acts (no `agent_id`) parse with `agent_id = None`; a read-path test
  asserts no inference occurs.
- *MEF non-strippable / complete-or-refuse* → unchanged for the existing fields (0004 Ch2).
- *Agent never ratifies* (0008) → unchanged; attribution structure does not touch ratification.

## Open questions (deliberately NOT settled here)
- **How `agent_id` is assigned** — caller-supplied vs an agent registry vs a naming convention. (v1 may
  start caller-supplied, like `producer` today.)
- **Namespace ownership** — who governs `agent.<role>` names; collision/uniqueness rules.
- **Agent reputation / specialization / longitudinal metrics** — these *consume* `agent_id`; they are a
  later frontier, not this ADR.
- **Migration of the 6 existing acts** — they stay `agent_id = None` (no backfill, no fabrication).

## Non-goals
No Pydantic/wire format, no registry implementation, no CLI design, no reputation system, no kernel
change beyond the frame field the implementation strictly needs. `claim_id` minting is untouched.

## Consequences & sequence
- This **extends the epistemic frame** (MEF, ADR-0004), so it is heavier than Identity-across-projections
  (which was additive with `types.py` untouched). Backward compatibility of existing acts is a **hard
  requirement**.
- **Ratification first.** Changing the attribution contract is itself a **governed decision** — this ADR
  must be **human-ratified** before any implementation (the project applies its own governance to its
  own frame).
- **Then:** an implementation issue (frame field + carrier-of-record + producer-as-projection +
  backward-compat read) → **runtime proof**: one `agent_id` (`agent.architect`) across two carriers
  (`openai:gpt-4o` then `openai:gpt-5` or a local/dummy second model), both certified,
  `consultations`/`explain` showing the **same `agent_id`, different carrier**.
- Passing that establishes the **second identity pillar** (`agent_id ≠ model_id`). With two referents
  proven (`claim_id ∉ storage`, `agent_id ≠ model_id`), the transversal principle *"identity is never
  defined by its carrier"* earns its second leg → it may then **incubate** in
  `FABRIC_FRAMINGS_INCUBATING.md` with a gate (a third referent to graduate). A `PROOF_LOG.md` entry on
  proof; a `FRAMING_DECISION_LOG.md` row if the transversal framing guided the call.
