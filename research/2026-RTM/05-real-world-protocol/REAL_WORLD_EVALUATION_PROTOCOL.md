# Real-World Evaluation Protocol for DSM — and for RTM

**Status:** Evaluation framework, not an experiment.
**Frozen:** 2026-07-04
**Position:** The laboratory has reached diminishing returns on synthetic
experiments. This document defines the next validation level.

---

## Why this document exists

Six experimental loops on an isolated clone produced a consolidated
hypothesis (RTM v0): DSM has strong local integrity, but its relational
integrity is structurally incomplete (0/25 edges satisfy I/V/C/P).

This hypothesis is internally coherent, falsification-resistant on its core,
and explicitly bounded. But these are **Niveau 1** validations (logical
coherence, reproducibility, counter-examples). They cannot answer the only
question that ultimately matters:

> **Do the relational gaps identified by the laboratory actually cause
> operational harm under real agent workloads — or are they theoretical
> artifacts that real usage never stresses?**

This question cannot be answered by another synthetic experiment. It
requires real agents, real tasks, multi-day runs, and pre-defined metrics.
This document specifies how to run that evaluation.

---

## The five validation levels

Borrowed from scientific software validation, adapted to DSM:

| Level | What it validates | DSM status |
|-------|-------------------|------------|
| **1 — Internal** | Logical coherence, reproducibility, falsification | ✅ Done (6 loops) |
| **2 — Canonical integration** | No regression, invariants preserved, complexity as claimed | ⛔ Not done — Gate G4 of RTM v0 |
| **3 — Real agents** | Workloads of hours/days; observe actual receipt/citation/replay use | ⛔ Not done — defined here |
| **4 — Third-party** | Users unfamiliar with DSM hit the same gaps spontaneously | ⛔ Not done |
| **5 — Comparative** | Same workflow on DSM vs Mem0/Zep/Letta/LangGraph/event log | ⛔ Not done |

The laboratory has extracted maximum value from Level 1. Levels 2–5 are
where RTM either gains operational evidence or gets killed by reality.

---

## The core question this protocol must answer

Stated precisely, so success/failure is decidable:

> **Under multi-day, multi-agent workloads, do the structural properties
> identified by the laboratory manifest as measurable operational cost —
> failed investigations, broken citations, unreplayable traces, audit
> gaps — at a rate that justifies the relational model RTM proposes?**

Three possible outcomes, all acceptable:

- **RTM confirmed by reality.** The gaps cause measurable operational harm
  at a rate that justifies addressing them. RTM graduates from hypothesis
  to candidate architecture.
- **RTM killed by reality.** Real workloads rarely stress the relational
  gaps (e.g., citations are almost always by hash in practice; audit
  policies are rarely shard-scoped; identity re-registration never
  happens organically). RTM is shelved as theoretically correct but
  operationally irrelevant.
- **Partial.** Some gaps matter, others don't. RTM is refined to cover
  only the operationally-relevant subset.

All three outcomes are valuable. The unacceptable outcome is a 7th
synthetic loop.

---

## Evaluation dimensions

The protocol measures DSM along five dimensions. Each dimension maps
directly to a finding from the six loops — so every metric is tied to a
specific architectural claim, not to generic "quality".

### D1 — Receipt lifecycle (loops 4, 5)
Are receipts created, and are they actually consumed?

- count of receipts issued
- count of receipts *verified* by a downstream consumer (not just stored)
- count of receipts whose `entry_id` (unprotected field) was used to resolve
- count of receipts whose `entry_hash` (protected field) was used to resolve
- count of orphan receipts (`verify_receipt_against_storage` → ENTRY_MISSING)
- ratio: receipts verified / receipts issued

**RTM prediction:** if the laboratory's findings are operationally
relevant, the `entry_id`-vs-`entry_hash` resolution ratio will skew
toward `entry_id` (the fragile path), and orphan receipts will be non-zero
under truncation/corruption scenarios.

### D2 — Citation patterns (loop 4, IA2)
How do agents actually cite prior work?

- count of citations by `entry_hash` (robust)
- count of citations by `entry_id` (fragile — Loop 3 finding)
- count of citations by content match (no formal link)
- count of broken citations after replay (target missing or mutated)

**RTM prediction:** if no convention is enforced, citation patterns will
be heterogeneous and the fragile-by-id subset will break under the same
conditions that broke it in the lab.

### D3 — Audit policy activation (loop 3)
Do real workloads exercise the `shard`-based access control?

- count of audit runs with `allowed_shards` policy active
- count of entries whose `shard` field was the *sole* basis of an audit
  decision (allowed or denied)
- count of cases where `shard` mutation would have flipped the audit
  verdict (counter-factual; tested by re-running audit on a copy with
  mutated `shard`)

**RTM prediction:** if shard-scoped audit is rarely used in practice,
the shard-bypass finding (Loop 3) is theoretically correct but
operationally dormant.

### D4 — Replay utility (loops 1, 4)
Is replay actually invoked, and does it complete?

- count of replays invoked
- replay completion rate (full chain verified)
- replay wall-clock under real shard sizes
- count of replays aborted due to broken chain / missing entries
- count of replays where the suffix-deletion gap (Loop 6, F1) would have
  masked a truncation

**RTM prediction:** replays on long-lived shards (weeks of activity) will
approach the O(N²/batch) build cost measured in Loop 1, and the
completeness gap (4 % of edges detect dangling targets) will mask at
least one truncation per N days of workload.

### D5 — Identity stability (loop 4, IA3)
Do agent identities stay stable, or do they get re-registered?

- count of `register` events per `agent_id` (distribution)
- count of re-registrations with a *different* `owner_id` (the forgery
  vector from IA3)
- count of `resolve()` calls that returned a different owner than the
  original registration

**RTM prediction:** in multi-agent workloads with key rotation or agent
restart, re-registration will happen organically; if the registry has
no owner-continuity check, at least one agent will lose its identity
silently.

---

## Workload specification

The protocol is workload-agnostic in shape but constrains the workloads
along four axes, so the evaluation is comparable across runs.

### W1 — Duration
Minimum: **72 hours continuous** per workload. Below this, shard sizes
do not reach the regime where Loop 1's performance properties and Loop
6's completeness properties become measurable.

### W2 — Agent count
Minimum: **3 distinct agents** per workload, with at least one
cross-agent handoff (dispatch + receipt) per hour. Single-agent
workloads do not exercise the relational graph meaningfully.

### W3 — Task classes
At least two of the following, to stress different edges of the graph:

- **software development continuous** — stresses entries, replays,
  citations (cross-session code references)
- **multi-agent coordination** — stresses dispatch, receipts, causal
  chains
- **document research / synthesis** — stresses citations, provenance
- **ticket / issue processing** — stresses audit policy, identity
  stability

### W4 — Failure injection (controlled)
The protocol includes *controlled* failure injection at known points,
to test whether the gaps identified by the laboratory manifest under
realistic fault conditions:

- **disk mutation**: mutate one entry's `id` and one entry's `shard`
  on disk, mid-workload. Observe whether downstream consumers
  (queries, audits, receipts) detect it.
- **truncation**: truncate one shard's suffix (simulating a partial
  write failure). Observe whether replays and `verify_shard` detect
  the loss.
- **re-registration**: re-register one agent with a different owner.
  Observe whether downstream identity resolution reflects the change
  and whether the original owner can recover.

Failure injection is the bridge between synthetic experiment (Level 1)
and organic observation (Level 3): it forces the conditions the
laboratory studied, under real workload, to see if real consumers
break the way the model predicts.

---

## Metrics dashboard

Pre-defined, computed automatically from the workload's DSM storage:

```
D1_receipt_verified_ratio        = receipts_verified / receipts_issued
D1_orphan_receipt_rate           = orphans / issued
D2_citation_by_hash_ratio        = hash_citations / total_citations
D2_broken_citation_rate          = broken / total
D3_audit_shard_decision_count    = # entries where shard was decisive
D3_shard_mutation_flip_count     = # counter-factual flips
D4_replay_completion_rate        = completed / invoked
D4_replay_abort_break_rate       = aborted_broken_chain / invoked
D5_reregistration_diff_owner    = # re-registrations with new owner
D5_identity_loss_events         = # resolve() diverged from original
```

Each metric has a threshold for "RTM-relevant signal" defined *before*
the run, not after — to prevent post-hoc rationalisation.

---

## What this protocol does NOT do

- It does not prove RTM is correct. It tests whether RTM is
  *operationally relevant*.
- It does not compare DSM to other memory systems (that is Level 5).
- It does not require modifying the kernel or any existing DSM API.
  The metrics are read-only over the workload's storage.
- It does not require the RTM prototype to be deployed. The protocol
  measures the *current* DSM, and asks whether the gaps RTM names
  show up in practice.

---

## Decision rule

After running the protocol on at least one workload meeting W1–W4:

- If **3 or more dimensions** show non-trivial signal
  (e.g., D2 broken-citation-rate > 5 %, D3 shard-flip-count > 0,
  D5 identity-loss-events > 0), then RTM has operational evidence.
  Promote to Gate G4 of RTM v0 (integration prototype).

- If **0–1 dimensions** show signal, RTM is theoretically correct but
  operationally dormant. Shelve the relational layer; keep the
  documentation as a known structural property that may activate under
  future workloads.

- If **2 dimensions** show signal, refine RTM to cover only the
  operationally-relevant subset of edges, and re-run.

The decision rule is fixed in advance. The whole point of pre-defining
it is to prevent the laboratory from "discovering" relevance after
the fact.

---

## Position of this protocol in the research arc

```
Loop 1  ─┐
Loop 2   │
Loop 3   │  Level 1 — synthetic, internal validation
Loop 4   │  (DONE — diminishing returns reached)
Loop 5   │
Loop 6  ─┘
         │
         ▼
RTM v0  ── frozen hypothesis (I/V/C/P + A boundary)
         │
         ▼
   THIS PROTOCOL ── Level 3 evaluation framework
         │           (defines how to test RTM against reality)
         ▼
   [ execution by integration team, not laboratory ]
         │
         ▼
   decision: promote RTM / shelve RTM / refine RTM
```

The laboratory's role ends here. What remains is engineering work
(integration prototype — RTM Gate G4) and product work (running the
workloads, collecting the metrics, applying the decision rule). Neither
is well-suited to an isolated-research-clone methodology.

---

## Closing

The strongest possible outcome of this research arc is not "RTM is
true." The strongest outcome is:

> A falsification-resistant hypothesis, with an honest boundary,
> and a pre-defined protocol that will either promote it or kill it
> based on evidence the laboratory cannot manufacture.

That is what this document, together with RTM v0, constitutes. The
laboratory has done what an isolated clone can do. The next step
belongs to a real environment.
