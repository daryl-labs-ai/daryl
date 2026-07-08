# 2026-RTM — Research Program Status

**Program:** Relational Trust Model (RTM)
**Opened:** 2026-07-04
**Status:** **CLOSED — frozen, awaiting real-world evidence**
**Integration right:** **NONE.** Do not open a PR. Do not document in the
canonical repo. RTM has not earned that right.
**Kernel modified:** No.
**Push / PR / canonical contact:** None.

---

## One-line position

> **DSM a une intégrité locale forte ; RTM explore l'intégrité relationnelle
> authentifiée. C'est une hypothèse unificatrice, pas une architecture.**

---

## What this program produced

A knowledge chain, in the strict order that distinguishes research from
opinion:

```
Observation   (Loops 1–4)
    ↓
Measurement   (Loops 1–4)
    ↓
Property      (Loops 2–4: hash perimeter, trust boundary, inter-agent gaps)
    ↓
Hypothesis    (Loop 5: the implicit Relation Graph; I/V/C/P; 0/25 edges complete)
    ↓
Falsification (Loop 6: minimal, no counter-example, no regression; boundary A found)
    ↓
Evaluation protocol (this program: pre-defined metrics, pre-defined decision rule)
```

Stopping at "we think that…" is the norm. This program stopped at "here is
precisely what would make us abandon the hypothesis." That is a different
level of maturity.

---

## The five gates RTM must pass before any canonical proposal

No gate has been passed. All five are explicit and blocking.

| Gate | Requirement | Status |
|------|-------------|--------|
| G1 | Prove A (Authenticity) independent of {I,V,C/P} | ⛔ Not done |
| G2 | Define a concrete key→identity binding mechanism for A | ⛔ Not done |
| G3 | Re-measure the matrix on current `main`, confirm 0/25 | ⛔ Not done |
| G4 | Integration prototype, full test suite, no regressions | ⛔ Not done |
| G5 | Demonstrate a non-trivial relation composition with proof | ⛔ Not done |

**Until G1–G5 are passed, RTM is a hypothesis. No integration.**

---

## The decision rule for real-world evaluation

Pre-defined in `05-real-world-protocol/REAL_WORLD_EVALUATION_PROTOCOL.md`.
Fixed before execution, not after — to prevent post-hoc rationalisation.

- **3+ dimensions show signal** → promote RTM to Gate G4 (integration prototype)
- **0–1 dimensions show signal** → shelve RTM (theoretically correct, operationally dormant)
- **2 dimensions show signal** → refine RTM to the operationally-relevant subset, re-run

---

## Directory structure

```
research/2026-RTM/
├── STATUS.md                       ← this file (program seal)
├── 01-observations/                (findings folded into 02-experiments)
├── 02-experiments/                 ← Loops 1–5 scripts (21 files)
├── 03-falsification/               ← Loop 6 scripts (4 files)
├── 04-hypothesis/
│   ├── RTM_v0.md                   ← frozen hypothesis (authoritative)
│   └── RELATIONAL_TRUST_MODEL_draft.md  ← Loop 5 draft (superseded, kept for traceability)
└── 05-real-world-protocol/
    └── REAL_WORLD_EVALUATION_PROTOCOL.md  ← Level-3 evaluation framework
```

All scripts are reproducible with the project venv (Python 3.12). No network.
No canonical-repo access. No kernel modification.

---

## Why this program is closed, not continued

The laboratory reached diminishing returns on synthetic experiments. Loops
5–6 produced theory from theory. The next question — *"is RTM operationally
relevant?"* — cannot be answered by isolated-clone methodology. It requires:

- real agents (Claude Code, Codex, GPT, Gemini, custom)
- multi-day workloads (≥ 72 h continuous, ≥ 3 agents)
- pre-defined metrics (D1–D5 in the protocol)
- controlled failure injection
- a decision rule fixed in advance

None of this belongs in a research clone. It belongs to integration and
product work. The laboratory's role is finished.

---

## What the canonical repository should NOT do

1. **Do not integrate RTM.** Not as code. Not as documentation. Not as an ADR.
   The protocol explicitly forbids laboratory→documentation→terrain; it
   requires terrain→measures→decision.
2. **Do not advertise RTM.** Mentioning it to users would bias the third-party
   validation (Niveau 4) that the protocol depends on.
3. **Do not refactor around RTM.** The kernel is intact; the 0/25 finding is
   a structural property of the *current* architecture, not a defect requiring
   immediate fix.

---

## What an integration team CAN do, if they choose

- Run the protocol (`05-real-world-protocol/`) against a real DSM deployment.
- Apply the decision rule.
- If signal is sufficient, attempt Gate G4 (integration prototype on a branch,
  full test suite, no kernel modification).
- Report back measurements; the laboratory's hypothesis stands or falls on
  that evidence.

The laboratory does not pre-judge the outcome. Both confirmation and
refutation are acceptable results.

---

## Closing

The strongest outcome of this research arc is not "RTM is true." It is:

> A falsification-resistant hypothesis, with an honest boundary, and a
> pre-defined protocol that will either promote it or kill it based on
> evidence the laboratory cannot manufacture.

That is what this program constitutes. The laboratory has done what an
isolated clone can do. The next step belongs to a real environment — and
until that environment speaks, RTM remains exactly what it is: a
well-evidenced, unfalsified, **unintegrated** hypothesis.

**Program status: CLOSED.**
