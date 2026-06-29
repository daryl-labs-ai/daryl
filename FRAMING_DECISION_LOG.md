# FRAMING_DECISION_LOG

Append-only record of framing decisions: the decision, the framings it drew on, and its outcome. One entry per adopted change.

---

## PRL Agent Consultation v1 (ADR-PRL-0008)

- **Decision:** Agent Consultation v1 via Adapter + Knowledge Act.
- **Framings:** Adapter Strategy, Knowledge Act.
- **Outcome:** validated / adopted.

---

## PRL Agent Consultation v3 — real agent invocation (ADR-PRL-0008)

- **Decision:** real agent behind a provider-independent `AgentClient` interface; the adapter maps the model's native answer to a Knowledge Act.
- **Framings:** Adapter Strategy (provider-behind-interface), Knowledge Act.
- **Outcome:** validated / adopted (real gpt-4o transcript, receipt `v1:d1df9eda…2470779`).

---

## Structured contributor attribution (ADR-PRL-0009) — 2026-06-28

- **Decision:** separate `agent_id` (frame-level, the logical contributor) from the carrier-of-record (provider/model/adapter); `agent_id` ≠ `model_id` as the contributor's mirror of `claim_id` ∉ storage.
- **Framings:** "Identity is never defined by its carrier" (incubating, `FABRIC_FRAMINGS_INCUBATING.md` #8).
- **Outcome:** incubating — 2nd proven referent (`claim_id` ∉ storage, `agent_id` ≠ `model_id`); needs a 3rd to graduate to the manifesto.
