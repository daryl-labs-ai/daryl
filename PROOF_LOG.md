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

---

## PRL Agent Consultation v3 — real agent invocation (ADR-PRL-0008)

- **Hypothesis:** a real agent produces a DSM-certified Knowledge Act without knowing PRL.
- **Experiment:** R-consult v3 + OpenAIClient + real `prl consult` transcript (gpt-4o, real receipt `v1:d1df9edab5ed4d0e00e82c433ba03e00da27a856ee47c8972de1c3dde2470779`).
- **Change:** external commercial model contributed a certified, retrievable project act.
- **Rule fired:** PROMOTION / first real-agent certified act.

---

## Resolution / Standing v1 — first governed decision from a real agent Proposal (ADR-PRL-0008)

- **Hypothesis:** Human ratification can turn a certified agent Proposal into a *governed decision* — with the claim's standing **derived by replay** — **without mutating** the original claim.
- **Experiment:** Real gate (no credentials for the governance chain — ratification is human): gpt-4o `consult --propose` on KO-7 → `claim_7c765d2988fd` → `human:mohamed resolve --decision accepted` → `standing` read via RR.
- **Change:** The chain *certified Proposal → human Resolution → derived Standing* is closed in runtime. The Proposal was DSM-certified (receipt `v1:97d271…0c6e`); a human Resolution was DSM-certified (`decision = accepted`, receipt `v1:b9901b…214a`); the claim's standing read back as `ACCEPTED`, derived from the Resolution (same receipt) — no stored standing field, no mutation. Step 5 of `MVP_DEMO_SCENARIO.md` passes.
- **Rule fired:** PROMOTION / first governed decision from a real agent Proposal. Merged: PR #77 (`2e28245`); `LEGITIMATE_WRITERS` = 20 unchanged, `types.py` on `prl._canonical`, kernel untouched; latest-wins ordering fix guarded by a kernel regression test.

---

## R-explain v1 — MVP Demo Scenario completed end-to-end (ADR-PRL-0008)

- **Hypothesis:** "Why this decision?" can be answered by **reconstruction from certified acts**, not narration above them — closing the MVP scenario (*real agent → certified Proposal → human Resolution → derived Standing → reconstructed explanation*), end-to-end.
- **Experiment:** Real gate: `prl explain --claim claim_7c765d2988fd` over the merged KO-7 chain (gpt-4o Proposal `v1:97d271…` → `human:mohamed` Resolution `v1:b9901b…` → derived Standing).
- **Change:** `explain` reconstructed the chain from the certified acts alone — each line backed by a DSM receipt (`proposal.receipt` / `resolution.receipt` == the `commit_act` tip hashes), standing from `standing_of` (single source), no Proposal fabricated, **no LLM, no summarization**. Output: `why claim_7c765d2988fd is ACCEPTED` / proposal `v1:97d271…` / resolution `resolver=human:mohamed v1:b9901b…` / `standing ACCEPTED (derived)`. The **MVP Demo Scenario is now complete end-to-end** (steps 1–6).
- **Rule fired:** PROMOTION / MVP scenario completed end-to-end. Merged: PR #78 (`859aa30`); `LEGITIMATE_WRITERS` = 20 unchanged, `types.py` untouched, no new `action_name`. Consequence: framing #7 graduates (a contribution becomes a governed project asset) — the manifesto/framings corpus changes (`VISION_KNOWLEDGE_FABRIC.md`, `FABRIC_FRAMINGS_INCUBATING.md`) are deferred to a dedicated manifesto-port PR (not yet on `main`).

---

## Identity across projections v1 — identity survives a second read projection (Second epoch #3)

- **Hypothesis:** the existing identity model survives a **second registry projection** — the same `claim_id` threads Proposal → Resolution → Standing → Explanation **identically** whether read via RR or via another projection, *without* designing new identity.
- **Experiment:** real gate on the merged KO-7 chain (no credentials): `explain --claim claim_7c765d2988fd` via **RR**, then `project-sqlite` (materialize a second projection), then `explain … --projection sqlite`.
- **Change:** the two explanations are **byte-identical** — `claim_7c765d2988fd` → proposal `v1:97d271…0c6e` → resolution `v1:b9901b…214a` (`human:mohamed`) → `ACCEPTED (derived)`; the SQLite projection materialized 2 acts. The same `StandingQuery`/`ExplainQuery` code runs on both backends (one derivation by construction); `claim_id` stays in `content` (never re-minted) and DSM receipts are carried **verbatim**. **Reserve:** the certification *substrate* stays DSM — receipts are **projection-relative** (a substrate swap would re-issue them, not carry them); identity-retrieval is still a linear scan over an action bucket (scale-tension #1). Both out of scope here.
- **Rule fired:** PROMOTION / first robustness invariant proven (read projection). Merged: PR #82 (`0a0d5ee`); `LEGITIMATE_WRITERS` = 20 unchanged, `types.py` untouched, no new `action_name`, `projections/` imports no `Storage` (reads via RR, ADR-0001).
