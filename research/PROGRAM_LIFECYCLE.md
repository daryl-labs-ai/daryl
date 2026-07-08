# Program Lifecycle

**Applies to:** all research programs under `research/`.
**Purpose:** distinguish a program's state from its findings' maturity.
A program can be healthy while blocked; a finding can be sealed while the
program that produced it is closed. These are independent axes.

---

## Program states

| State | Meaning | What it permits |
|-------|---------|-----------------|
| **OPEN** | Program is actively producing experiments | new hypotheses, new experiments, new findings |
| **BLOCKED** | The question is legitimate but the environment cannot test it as specified | document *exactly* why it is blocked, and what would unblock it; **no degraded substitution** |
| **CLOSED** | Program reached a natural endpoint (finding demonstrated, hypothesis falsified, or diminishing returns) | the findings stand at their earned maturity level; the program does not continue |
| **SEALED** | Program archived; no evolution without a new mandate | nothing — not citation, not extension, not "v2" — without an explicit re-opening decision |

---

## What each state is NOT

- **BLOCKED is not failure.** It is a finding: "we know precisely why this
  cannot be tested here, and what would have to change." That is knowledge,
  not abandonment. A blocked program is healthier than a program that
  faked its way past the block.
- **CLOSED is not abandonment.** It means the program produced what it
  could and stopped at the right point. The findings retain their maturity
  level indefinitely.
- **SEALED is not deletion.** The reasoning is preserved as an archive.
  The seal forbids *use* (citation, extension) without a new mandate — it
  does not forbid *reading*.

---

## The transitions

```
OPEN ──► CLOSED          natural endpoint reached
OPEN ──► BLOCKED         environment cannot test the question as specified
BLOCKED ──► OPEN         environment changed; the question becomes testable
                            (requires explicit re-opening decision)
CLOSED ──► SEALED        archive; no evolution without new mandate
SEALED ──► OPEN          only via a new, explicit mandate — never by drift
```

A program may **never** transition OPEN → CLOSED merely because the
laboratory wants to stop. It closes only when a stop condition from its
own specification is met (finding demonstrated, hypothesis falsified,
two iterations with no new knowledge, or kernel modification required).

A program may **never** transition BLOCKED → OPEN by silently relaxing
the specification. The unblock requires either (a) the environment to
gain the missing capability, or (b) an explicit decision to redefine the
question — which is, in effect, opening a different program.

---

## Relationship to the maturity hierarchy

The maturity hierarchy (`research/MATURITY.md`: O/P/H/F/R/C) classifies
**findings**. Program states classify **programs**. They are orthogonal:

- A **CLOSED** program may contain findings at any maturity level.
- A **BLOCKED** program may still contain valid findings produced before
  the block (the 2026-DistributedMemory Phase 0 finding is one).
- A **SEALED** program's findings retain their maturity level; the seal
  governs *use*, not *truth*.

---

## Current registry

| Program | State | Since | Reason |
|---------|-------|-------|--------|
| 2026-RTM | SEALED | 2026-07-04 | Arc complete; falsification-resistant hypothesis frozen; awaits real-world evidence or independent rediscovery |
| 2026-DistributedMemory | BLOCKED | 2026-07-04 | Question requires a distributed environment (no central coordinator, multi-process, multi-day); current DSM architecture is orchestrated and single-process; the premise is not met |
| 2026-OrchestratedMemory | OPEN | 2026-07-04 | Testing the real (orchestrated, single-process) system. Six axes tested, seven P-level findings produced. Hypothesis holds in qualified form; limits measured and named. |

---

## The discipline this enforces

The most important transition rule is the one that is easiest to violate
under pressure to produce:

> **BLOCKED → OPEN requires an explicit decision, never a silent relaxation.**

When a program is blocked because the environment cannot honestly test
the question, the temptation is to redefine the question into something
the environment *can* test, and continue as if nothing changed. That
temptation is the failure mode. Redefining the question is legitimate —
but it is opening a *new* program, with a new name, a new specification,
and an honest statement of how it differs from the blocked one. It is not
unblocking the old one.

This is the rule that keeps "stop before faking it" durable.
