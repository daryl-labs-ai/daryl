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
