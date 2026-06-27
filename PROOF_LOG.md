# PROOF_LOG

Append-only record of hypotheses tested and the rule each one fired. One entry per adopted change.

---

## PRL Agent Consultation v1 (ADR-PRL-0008)

- **Hypothesis:** ADR-0008 can be implemented without kernel change.
- **Experiment:** R-consult v1 implementation + tests + RR read + forbid-storage.
- **Change:** Consultation Knowledge Act adopted.
- **Rule fired:** promotion / implementation adoption.

---

## PRL Agent Consultation v2 — read/display (ADR-PRL-0008)

- **Hypothesis:** A certified consultation act can be consumed through the existing RR read path without new writers or kernel changes.
- **Experiment:** R-consult v2 implementation + ConsultationQuery + CLI consultations + RR e2e tests.
- **Change:** Consultation Knowledge Acts are now writable and readable/displayable.
- **Rule fired:** HOLD / evidence added, no conceptual promotion.
