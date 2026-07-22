# DSM Swarm Benchmark — How to read B1–B4 (one page)

Three rules. Every other document in this directory is subordinate to them.

## 1. This validates an instrument, not DSM as a technology

Phases B1–B4 built and validated a **measurement instrument**: pre-registered
protocol and parity thresholds, typed contracts, a 12-case planted-fault
corpus, a deterministic runner with a FakeProvider, three recorders behind one
interface, and a mechanical campaign in which the instrument was turned on
itself. The campaign's headline result — condition A's symmetric rubric
detects exactly the same mechanical fault set as condition B's replay in the
deterministic regime — is a **validity check of the benchmark**, not a verdict
on DSM: when a log already contains all the structured information, DSM
invents no extra capability, and the benchmark is able to conclude "no
difference" where none should exist. An instrument that could not say "no
difference" could not be trusted to say "difference".

## 2. B1–B4 permit no conclusion about production performance

Everything in B1–B4 runs on a deterministic FakeProvider with scripted
agents, complete and well-formed logs, and planted faults. Nothing here
measures real models, degraded or unstructured logs, live coordination, cost
at scale, or user value. The measured overheads (grounding-block tokens,
record counts, shard bytes) are real but regime-specific. The 0-confounded
parity result is an instrument control, not a scientific finding — in live
runs, confounded pairs are *expected* to appear; their total absence there
would suggest the thresholds are too permissive, not that instrumentation is
free. No claim of the form "DSM improves/does not improve agents" can be
grounded in B1–B4, in either direction.

## 3. B5/B6 are the first phases able to observe real models

The live smoke (B5) and the multi-seed campaign (B6) are the first phases
whose observations bear on real model behavior — under explicit budget
authorization, hard caps, the pre-registered live parity thresholds, and
hypotheses (H1–H6) stated before the data. Even then, the standing
non-claims of the Swarm layer hold: a benchmark score is not universal
product proof; receipts certify storage integrity, never content truth; a
work claim is never proof the work happened.
