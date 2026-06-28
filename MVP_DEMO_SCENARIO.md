# MVP Demo Scenario — the exit criterion

**Status:** Acceptance scenario / operational exit criterion · **Date:** 2026-06-27
**Not a vision, not an ADR.** A *falsifiable* definition of "MVP done": the smallest scenario that
makes the product understood, runnable end-to-end with real agents.

## The reframe

The real MVP of Daryl is **not a set of features** — it is a **demonstrable scenario**. The question
shifts from *"what features are missing?"* to *"what is the smallest scenario that makes the product
understood?"* A reproducible demonstration explains a new product far faster than a manifesto.

## The scenario

1. A **Knowledge Object** is created.
2. **ChatGPT** is consulted → **Observation**, DSM-certified.
3. **Claude** is consulted → **Proposal**, DSM-certified.
4. A **local model** runs a benchmark → **Observation**, DSM-certified.
5. A **human** reviews the contributions → **Resolution** → **Standing**.
6. **Two weeks later**, someone asks *"why this decision?"* — and the system answers with:
   - the **Knowledge Acts**, their **authors**, their **evidence**,
   - the **Resolution**, and **why the decision exists** —
   reconstructed from the certified record, not narrated.

## What it validates — in one demonstration

| Property | Component it exercises |
|---|---|
| Memory | Retrieval (recall the object + its history) |
| Governance | PRL / MEF (every claim carries its standing) |
| Certification | DSM (each Act is a hash-chained, certified Entry) |
| Collaboration | Adapters (different intelligences contribute via the same protocol) |
| Decision | Resolution / Standing (human-ratified, Accepted ≠ True) |
| Continuity | RR readback weeks later (the work resumes, not restarts) |

## The exit criterion

> **The MVP is not done when all features exist. It is done when this scenario runs
> end-to-end with real agents, without cheating.**

After this works, everything else — Knowledge Maps, visualizations, the knowledge compiler,
analytics — becomes a **value multiplier**, not a prerequisite. This is the objective line between
*building foundations* and *building the product*.

## "Without cheating" — what counts

- Each consultation is a **real adapter call to a real model** (not a synthetic answer).
- Each Act is a **real DSM-certified `Entry`** (real `Storage.append` hash + prev_hash), not a stub.
- The Resolution is a **real human / witnessed act** — the agent never ratifies.
- The recall (step 6) goes through the **actual RR read path**, by `action_name`.
- The "why" is **reconstructed from the certified Acts** (authors, evidence, Resolution) — not a
  generated narrative laid over them.

## The two remaining pieces (same scenario, not two projects)

- **R-consult v3 — real adapter invocation** → steps 2–4 (a real agent produces a certified Act).
- **Resolution / Standing** → step 5 (the human-ratified decision that gives step 6 its answer).

Steps 1, and the read/display of 6, already exist (Consult v1 write, v2 read/display, Retrieval v2).
When v3 + Resolution close steps 2–5, the scenario is executable end-to-end — and most of the
manifesto stops being a vision and becomes an **observable property of the system.**
