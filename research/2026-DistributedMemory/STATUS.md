# 2026-DistributedMemory — Program Status

**Program:** Distributed memory for multi-agent software development
**Opened:** 2026-07-04
**State:** **BLOCKED** (per `research/PROGRAM_LIFECYCLE.md`)
**Reason for block:** architectural, not merely environmental. See §"The
honest blocker" below. Phase 0 produced a valid finding (level P) before
the block; it is recorded in §"Finding produced before block".
**Independence:** This program does not cite, reuse, or seek to confirm any
prior program. It is treated as the first.
**Kernel modified:** No.
**Push / PR / canonical contact:** None.

---

## Research question

> Un ensemble d'agents peut-il partager une mémoire durable sans serveur
> mémoire central et sans perdre les propriétés de rappel, de provenance et
> de cohérence nécessaires à un travail de développement logiciel de longue
> durée ?

## Initial hypothesis (assumed false until proven)

> Une mémoire distribuée fondée uniquement sur des échanges append-only et
> des références vérifiables est suffisante pour permettre à plusieurs
> agents de développer ensemble pendant plusieurs jours sans coordinateur
> mémoire central.

---

## What Phase 0 found before any workload was run

The program specification demands real multi-day workloads with real agents
from the start — no synthetic benchmarks, no abstract scenarios. Before
investing in that, Phase 0 asked a cheaper question that could falsify the
premise entirely:

> **Does the current DSM architecture even satisfy the "without central
> memory coordinator" clause of the hypothesis?**

If the answer is no, the hypothesis is untestable on the current codebase
without first building the distribution layer — which is an engineering
project, not a research finding.

### Finding 1 — There is a central coordinator

`ShardSyncEngine` is explicitly *"the only writer to collective shards"*
(`src/dsm/collective.py:287`). Every `push()` to the collective memory
passes through `self._orchestrator.admit()` — a `NeutralOrchestrator` that
applies sovereignty policy, rate limits, and admission rules.

`LaneGroup` (`src/dsm/lanes.py`) removes write contention by giving each
agent its own shard, but each lane still goes through a `ShardSyncEngine`
sharing the same `NeutralOrchestrator` instance.

**Verdict:** the architecture is *concurrent* (parallel writes) but not
*distributed* (no peer autonomy). A single orchestrator gates all writes.

### Finding 2 — Memory is local and singular

`Storage` is strictly local: one `data_dir`, one filesystem, one process.
There is no federation, no peer-to-peer sync, no remote storage adapter, no
network layer (`src/dsm/core/storage.py:81`). The orchestrator's admission
cache and counters are in-memory state of a single process.

**Verdict:** there is no "distributed memory" in DSM today. There is a
single-process, single-host memory with multi-agent *access* patterns.

### Finding 3 — The premise of the hypothesis is not met

The hypothesis posits *"without central memory coordinator"*. The current
architecture has exactly such a coordinator (the orchestrator) and exactly
such a central memory (the single Storage). Therefore the hypothesis
**cannot be tested on the current codebase as stated** — there is nothing
to falsify because the precondition is absent.

---

## The honest blocker

This program's specification is explicit and correct:

> Pas de benchmarks synthétiques. Pas de scénarios abstraits. Les agents
> doivent accomplir un vrai travail.

This laboratory (an isolated clone, a single session) **cannot provide**
that environment. Specifically, it cannot provide:

- multiple real agents (Claude Code, Codex, GPT, Gemini, custom) running
  concurrently for days
- a real codebase under active multi-agent development
- genuine distribution across processes or hosts
- the failure modes that only emerge at multi-day scale
- a DSM *without* its orchestrator, to test the no-coordinator clause

If I proceeded anyway — inventing "simulated agents", "simulated
workloads", "simulated distribution" — I would commit exactly the error
that closed the prior arc: manufacturing apparent relevance instead of
testing for it. Synthetic multi-agent simulation cannot answer *"can agents
develop software together for days without a central memory"*; it can only
beg the question.

---

## Finding produced before block (level P)

Despite being blocked, Phase 0 produced one valid finding. It is recorded
here at maturity level **P** (demonstrated property, scoped to the current
architectural contract) per `research/MATURITY.md`.

### P-finding — Distribution is not an emergent property of current DSM

**Statement:** In the current DSM architecture, multi-agent memory sharing
is *orchestrated*, not *distributed*. A single authority
(`NeutralOrchestrator` via `ShardSyncEngine`) gates every write to the
collective memory, and a single `Storage` (one `data_dir`, one process)
holds all state. Parallelism of writes exists (via `LaneGroup`), but no
agent has autonomous write access that bypasses the orchestrator, and no
storage backend is federated, replicated, or remote.

**Evidence:**
- `src/dsm/collective.py:287` — `ShardSyncEngine` is *"the only writer to
  collective shards"*.
- `src/dsm/collective.py:329` — every `push()` calls
  `self._orchestrator.admit()`.
- `src/dsm/lanes.py:113-119` — `LaneGroup` shares one orchestrator
  instance across all lanes.
- `src/dsm/core/storage.py:81` — `Storage` takes one local `data_dir`;
  no federation/peer/network adapter exists.

**Scope:** this is a property of the *current* architecture
(commit `a5e56dc`). A future DSM with a federated storage backend or a
peer-to-peer sync layer would not satisfy the premise of this finding and
would require re-measurement.

**Implication for the program:** the hypothesis *"without central memory
coordinator"* cannot be tested on this codebase, because the precondition
is absent. This is what blocks the program. The finding itself is
independent of the block and stands on its own.

**This finding is NOT a critique.** An orchestrated architecture is a
legitimate design choice (it provides admission control, sovereignty
enforcement, and a single-writer invariant). The finding only says: do
not call this architecture "distributed", because it is not. Calling it
distributed would be a category error, and testing a distributed-memory
hypothesis on it would test the wrong thing.

---

## What this program is NOT doing

- It is **not** building a distributed memory layer for DSM. That is
  engineering work for the canonical repo, gated by its own review. This
  laboratory does not add features.
- It is **not** running a degraded/synthetic substitute for the specified
  workload and presenting it as evidence. The program's value depends on
  the workload being real; faking it destroys the value.
- It is **not** testing the orchestrator's *quality* (that is a different
  question, answerable in isolation, and not what this program asks).

---

## The fork in the road

The program specification is sound. The environment cannot deliver it.
There are two legitimate paths forward, and the choice is **not the
laboratory's to make** — it depends on resources only the integration team
or product owner controls.

### Path A — Defer until a real distributed environment exists

Build (or wait for) a DSM deployment that actually runs across multiple
processes/agents/hosts, with the orchestrator removed or federated. Then
run the specified workload (Axes 1–5) and collect the mandatory measures.
The program resumes there, untouched.

**Cost:** engineering work to build the distribution layer first.
**Fidelity:** full — the hypothesis is tested as specified.
**This is the honest path.**

### Path B — Reframe the question to what this environment can honestly test

If the no-coordinator clause is relaxed, a different, smaller, *honestly
answerable* question emerges:

> In the *current* (orchestrated, single-process) DSM, what are the
> measurable limits of multi-agent memory sharing — and at what scale do
> they break?

This is a question about the *existing* system's ceilings, not about a
hypothetical distributed one. It is answerable by measurement. But it is
**not the question this program was opened to answer** — it is a
substitution, and should only be adopted if the owner explicitly chooses to
redefine the program.

---

## Status

**Program: OPEN, BLOCKED at Phase 0.**

Phase 0 produced one valid finding (the architecture is not distributed),
which itself is useful: it tells the owner that testing the hypothesis
requires building infrastructure that does not yet exist.

The program does not proceed to Axes 1–5 until the environment blocker is
resolved — by Path A (real distribution) or by Path B (explicit reframe).
The laboratory will not paper over the gap with simulation.

This is the discipline this program inherits: **stop before faking it.**
