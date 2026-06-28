# ADR-PRL-0007 — Adapter Strategy (Provider Independence)

**Status:** Accepted — ratified-by-Mohamed 2026-06-27 · **Version:** v1 · **Date:** 2026-06-27 · **Regime:** `declared`
**Depends on:** ADR-PRL-0002 (Architecture — Citizens/Boundaries), ADR-PRL-0004 (Protocols — the epistemic messages & MEF)
**Axis:** **adoption / integration** — how external intelligences come to "speak Fabric." Not
constitutional law (0001), not the recall engine (0006), not implementation encodings (0005).

> **PRL does not make project knowledge true. It makes project knowledge governable.**

**The diffusion risk this ADR answers.** A protocol exists only if it has multiple implementations.
The Knowledge Fabric's value depends on heterogeneous agents — ChatGPT, Claude, Gemini, OpenClaw,
local models — all contributing. The real risk is not internal coherence; it is **adoption**.

## Decision — integrations adopt PRL, models never do

Making an LLM speak PRL natively would be a strategic error: it locks the Fabric to providers willing
to change their models, adds friction, and is impossible to mandate across vendors and across time. So:

> **Models never adopt PRL. Integrations adopt PRL.**

A **Daryl Adapter** sits between an agent and the Fabric. The agent produces its *normal* output; the
adapter maps that output into epistemic messages (ADR-PRL-0004 Ch1) — Observation, Proposal,
Benchmark, Resolution — each carrying a complete MEF; DSM then certifies the act. The model is
entirely unaware of PRL.

```
Claude  ┐
GPT     ┤── normal output ──▶  Daryl Adapter ──▶  Knowledge Act ──▶  DSM (certify)
Gemini  ┤                       (maps to 0004      (MEF, producer)
local   ┘                        messages)
```

This is where the epistemic **ABI** (ADR-PRL-0004) becomes real: the calling convention lives at the
**adapter boundary**, not inside the model.

## Why this is the right boundary

- **Provider independence.** Any agent contributes through its adapter; swapping GPT-5 for GPT-6, or
  adding a 2032 open-source model, touches only that adapter — never the Fabric, never the protocol.
- **Minimal friction.** No model change, no fine-tuning, no vendor cooperation required. An adapter
  is something *Daryl* ships, not something a provider must.
- **The provider lock-in inverts** (see VISION_KNOWLEDGE_FABRIC.md): value accrues in the project's
  Knowledge Objects/Acts, not in any one model's API.

## Citizenship of an adapter (from ADR-PRL-0002)

An adapter is a **Producer / boundary citizen**, with exactly the rights a producer has:

- **May** emit Proposals and Observations on behalf of its agent, always attributing the producing
  model (e.g. "produced by Claude via adapter v2").
- **Never** emits a Resolution by inference — ratification stays human or witnessed (L4).
- **Never** mints standing: every adapter-emitted message carries a complete, non-strippable MEF
  (ADR-PRL-0004 Ch2); an adapter that cannot supply one must refuse, not default.

## Non-goals

- No model is fine-tuned, prompted, or required to "know" PRL.
- Adapters are not governance authorities; they propose, they do not decide.
- Agents are not required to share context or memory — only their adapters' messages meet, in the
  Fabric (the Git-shaped collaboration of the vision).

## Enforcement (per the 0001 discipline)

- An adapter is typed as a Producer: the capability surface makes "adapter emits a Resolution"
  unconstructible (mirrors the 0002 capability matrix → lint).
- Every adapter-emitted message is unconstructible without a complete MEF (the 0004 Ch2 invariant
  applies unchanged at the adapter boundary).
- Each message records the producing model + adapter version (attribution is mandatory).

## Consequences

- The Fabric becomes adoptable without any provider's cooperation — the single most important
  property for diffusion.
- Adapters become the natural unit of the eventual plugin ecosystem (ChatGPT-adapter,
  Claude-adapter, local-model-adapter), each small and provider-specific, all speaking one protocol.
- A future ADR may formalize the **Agent Consultation Protocol** (a live consultation = an
  Observation, or Observation + Proposal) on top of this adapter boundary.
