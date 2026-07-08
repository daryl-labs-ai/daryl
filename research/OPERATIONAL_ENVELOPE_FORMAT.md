# Operational Envelope — A reusable evaluation format

**What this is:** the format of an Operational Envelope, extracted from
its first application (DSM) so it can be applied to any agent runtime,
memory system, or coordination layer.

**Why it exists:** architecture documents describe what a system is
*designed* to do. An Operational Envelope describes what a system *does*,
measured. The two answer different questions and should not be confused.

**Status:** format specification. Not tied to DSM. Anyone may apply it.

---

## The problem this format solves

Most evaluation in the agent-tooling space falls into one of three
categories, all inadequate:

1. **"It works on my machine"** — a demo. Not falsifiable, not comparable.
2. **Benchmark scores** — abstract numbers (tokens/sec, queries/sec)
   disconnected from the operational properties users actually rely on
   (durability, handoff, retry semantics).
3. **Architecture documents** — describe intent. Silent on whether the
   implementation delivers it.

An Operational Envelope fills the gap: a structured, falsifiable,
measured description of a system's behaviour, with explicit limits and
explicit confidence. It survives implementation changes because it
describes *observed behaviour*, not *design intent*.

---

## Required structure

An Operational Envelope has exactly six sections. Removing any
destroys the contract the format makes with its reader.

### 1. Identity

```
System:        <name>
Version:       <commit / release>
Measured:      <date>
Measurer:      <who ran the measurements>
Environment:   <hardware / runtime / config one-liner>
```

The envelope is scoped to a specific version. A claim from envelope v1
does not transfer to v2 without re-measurement.

### 2. Operational profile

A table grouped by operational dimension. Every row has five columns,
all mandatory:

| Property | Status | Confidence | Measurement | Scope |
|----------|--------|------------|-------------|-------|

- **Property** — a single, named operational guarantee or limit. Phrased
  as the thing a user would rely on ("cross-agent handoff",
  "idempotent retries"), not as an implementation detail.
- **Status** — `✓`, `partial`, or `✗`. The vocabulary is deliberately
  small; ambiguity here makes the document useless.
- **Confidence** — `High`, `Medium`, or `Low`. Distinguishes the strength
  of the evidence from the direction of the result. A Medium-confidence
  ✓ is not the same claim as a High-confidence ✓.
- **Measurement** — the actual number or observed behaviour, with units.
  Not "fast" — "0.73 ms median". Not "survives crashes" — "50/50 entries
  survived kill+restart".
- **Scope** — the module, config, or precondition under which the
  measurement holds. A row without scope is a row that will mislead.

### 3. At-a-glance

A compact visual of the profile. The point is fast readability — the
reader should absorb the system's character in seconds.

```
✓  <property>
~  <property>  (one-word qualifier)
✗  <property>  (one-word qualifier)
```

### 4. What the envelope means in practice

A Q&A section answering the questions an integrator or architect would
actually ask. Each answer cites the profile rows it rests on. This is
the bridge from raw measurement to usable knowledge.

### 5. What the envelope is NOT

Explicit negations:
- Not a feature list.
- Not static (re-measure on change).
- Not a roadmap.
- Not canonical documentation (unless adopted by the system's owners).

### 6. Provenance

Every row traces to a specific, reproducible experiment. Without
provenance, the envelope is opinion. With provenance, it is falsifiable
— anyone can re-run the experiments and check.

---

## The status vocabulary

Three values. No more.

- **✓** — the system delivers the guarantee named in the Property column,
  under the stated Scope.
- **partial** — the system delivers a weaker form. The gap between the
  property name and the actual behaviour is named in the Measurement
  column. "partial" is not "mostly works" — it is "works differently
  than the name implies, here is how".
- **✗** — the system does not provide this. The consequence is named.

**Forbidden:** "+/-", "yes/no with caveats", "mostly", "should work",
"expected to". If the answer needs a caveat, the property is mis-named
or the status is `partial`. Renaming the property is preferred to
expanding the vocabulary.

---

## The confidence vocabulary

Three values. No more.

- **High** — measured across enough cases that the next measurement is
  very likely to agree; or a structural property unlikely to change
  without an architecture rewrite. The reader may rely on this without
  re-measuring for non-critical decisions.
- **Medium** — measured on a small sample or a narrow scenario. The
  *direction* is reliable; the *number* may shift under wider workload.
  Re-measure before relying on it for a critical decision.
- **Low** — included only when a property must be stated but evidence is
  thin. Should be rare; a Low-confidence row is a prompt to re-measure,
  not a settled claim.

The discipline here matters: a High-confidence ✗ is a much stronger
statement than a Medium-confidence ✗. The first says "we measured this
thoroughly and it does not hold"; the second says "we saw it fail in our
case but have not ruled out that it holds in yours".

---

## The dimensions

An Operational Envelope organises properties into dimensions. The set of
dimensions depends on the system, but the following are near-universal
for agent/memory runtimes:

- **Admission / access control** — who can write, who decides, what is
  logged.
- **Memory and recall** — what is stored, what is reconstructable, what
  is lost.
- **Concurrency and scaling** — what parallelism is real, where
  throughput degrades, where saturation occurs.
- **Reliability under failure** — durability, retry semantics, crash
  windows, corruption containment.

Systems with distinct concerns (federation, payment, real-time sync,
etc.) add their own dimensions. The format does not constrain the
*number* of dimensions; it constrains the *structure* of each row.

---

## How to write one

1. **Pick a version.** Pin a commit or release. An envelope without a
   version is a letter to Santa.
2. **Run real operations.** Not unit tests, not demos. The actual write
   path, the actual read path, the actual failure modes.
3. **Measure, then name.** Do not decide what the system *should* do and
   look for confirmation. Measure what it *does*, then name the property
   that describes it.
4. **Assign confidence honestly.** A 5-sample measurement is Medium, not
   High. Saying High does not make it so; it makes the document lie.
5. **Write the at-a-glance last.** It is a compression of the profile;
   it can only be honest if the profile is complete.
6. **Cite every row.** No row without a reproducible experiment behind
   it.

---

## How to use one

- **As an oracle for change.** Before/after comparison when the system
  is modified. If a row changed status, the change moved the envelope —
  evaluate whether that was intended.
- **As an integration checklist.** An integrator reads the envelope to
  learn whether the system fits their requirements before committing.
- **As a comparison basis.** Two systems' envelopes, placed side by
  side, enable comparison on measured properties rather than on
  marketing. The envelopes need not share dimensions — only shared rows
  are comparable, and that comparability is itself informative.
- **As a research baseline.** A research program that proposes a change
  to the system measures against the envelope to demonstrate impact.

---

## What the format refuses

- **Vague status.** No "mostly", "generally", "should". The vocabulary
  is three statuses and three confidences. Everything else is a
  mis-named property.
- **Unscoped claims.** A row without a Scope column is a row that will
  mislead the reader whose context differs.
- **Unevidenced rows.** A row without provenance is opinion. The format
  does not carry opinions.
- **Aspiration.** The envelope describes what *is*, not what *will be*.
  Roadmaps live elsewhere.

---

## Provenance of this format

This format was extracted from the first Operational Envelope written
for DSM (`research/2026-OrchestratedMemory/OPERATIONAL_ENVELOPE.md`).
That envelope was produced by a research program
(`2026-OrchestratedMemory`) that measured the current orchestrated DSM
across six operational axes and produced seven findings at maturity
level P (measured properties).

The format is broader than its first application. It is published here
so it can be applied to other systems without reference to DSM. The DSM
envelope remains its first instance and its worked example.
