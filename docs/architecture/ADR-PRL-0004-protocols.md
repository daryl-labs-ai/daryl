# ADR-PRL-0004 — Protocols (the Epistemic Message Protocol)

**Status:** Accepted — ratified-by-Mohamed 2026-06-27 · **Version:** v1 · **Date:** 2026-06-27 · **Regime:** `declared`
**Depends on:** ADR-PRL-0001 (Constitution), ADR-PRL-0002 (Architecture), ADR-PRL-0003 (Vocabulary)
**Nature:** *normative protocol*, not implementation. It defines the **messages** that carry
epistemic standing between producers, consumers, and any materialization — and the rules those
messages obey in transit. It names no wire format, no storage engine, no API. It must stay true if
DSM/PRL is rewritten in Rust, Go, or C++, or distributed across machines.

> **PRL does not make project knowledge true. It makes project knowledge governable.**

**ADR series:** 0001 Constitution · 0002 Architecture · 0003 Vocabulary · **0004 Protocols** ·
0005 Implementation. Protocols precede implementation: 0005 may choose encodings and engines, but
only ones that *carry* these messages and *preserve* these frames intact.

**The inversion (founding choice of this ADR).** 0004 does **not** start from a "Registry Event."
A registry is already a projection toward storage; starting there would anchor the protocol in one
architecture. Instead it starts from the **message** — the smallest epistemic unit in transit. The
**registry is a projection of the protocol** (Chapter 5), one materialization among many (a stream,
a log, a distributed set of nodes). This continues the arc of 0001–0003: knowledge is governed by
*how its standing travels*, not by where it is stored.

**Reading note.** Chapters give a **Definition**, the **Always / Never** clauses that bind, and
**Derives from** (the law, boundary, or vocabulary term it answers). The protocol is described at
the level of *roles and obligations of messages*, never their bytes.

---

## Chapter 1 — Epistemic Messages

**Definition.** An *epistemic message* is the smallest unit that moves epistemic standing between
parties. It is **not** a stored object and **not** a registry entry; it is what travels. Whether it
is ever persisted is a projection concern (Chapter 5), invisible to the protocol.

The message kinds (vocabulary from 0003):

- **Observation** — asserts an Observed fact entered the system, with its acquisition regime
  (Witnessed / Imported / Recovered / Declared). It is *not* an interpretation.
- **Proposal** — offers a Derived interpretation (a Claim) for governance. Always attributed to a
  producer; never asserts truth.
- **Acceptance** — a governance act raising a Proposal's standing to Accepted.
- **Rejection** — a governance act marking a Proposal Rejected.
- **Withdrawal** — a producer retracts its own Proposal.
- **Supersession** — a newer Claim declares it supersedes an older one.

Always: every message carries a Minimal Epistemic Frame (Chapter 2). Never: a message implies that
acceptance equals truth, or that it must be stored to be valid.
Derives from: L5 (no epistemic authority over truth), L6 (write contract = proposals), 0002 Citizens.

## Chapter 2 — Minimal Epistemic Frame (MEF)

**Definition.** The MEF is the **transport contract**: the information that can **never be lost**
when a message crosses *any* boundary, relay, transform, or projection. It answers one question —
*what must survive, always?*

The non-strippable fields:

- **claim_id** — the identity the standing attaches to.
- **regime** — the epistemic regime (Observed sub-regime, or Derived status).
- **confidence** — the producer's stated confidence.
- **contested** — whether a contradiction is on record.
- **producer** — who emitted this standing.

Always: every message, response, and projection preserves the MEF whole; a relay that cannot carry
it must refuse the message, not drop fields. Never: a component strips, defaults, or silently
synthesizes an MEF field — that is the L8 violation ("no component may silently alter or
misrepresent epistemic standing"). Enforcement (per 0001 discipline): a message/claim is
**unconstructible without a complete MEF** (the type refuses it), so "no naked claim" is mechanical,
not a convention.
Derives from: L7 (read contract / MEF), L8 (no silent standing change).

## Chapter 3 — Extended Frame

**Definition.** Everything else a message *may* carry — rich but **optional**, fetched lazily,
never required for a message to be valid.

Typical contents: provenance, evidence references, ranking explanation (with policy id +
extractor/version), contradiction references, signatures, timestamps of materialization.

Always: when present, the Extended Frame is attributed (each part names its producer/policy) and
referenced from the MEF's claim_id. Never: the Extended Frame carries anything that *changes*
standing — standing lives in the MEF; the Extended Frame only *explains* it. Omitting the Extended
Frame must never change how a claim is interpreted, only how much can be audited right now.
Derives from: L7 (extended frame is lazy), §0002 Contracts, "ranker is a producer."

## Chapter 4 — Protocol Contracts

**Definition.** The conversations the messages form — described as **protocol**, not API. The
protocol knows nothing of HTTP, JSON, or gRPC; 0005 may bind it to those.

The contract messages:

- **Proposal message** — a producer offers a Claim (carries MEF; Extended Frame optional). Never
  modifies state directly.
- **Resolution message** — a governance act *about* a prior Proposal: Acceptance, Rejection,
  Withdrawal, or Supersession. Always attributed; never anonymous; never inferred (ratification is
  human or witnessed, never produced by inference).
- **Query** — a request for claims matching a need. May state a salience policy, which is itself a
  producer (the result will name it).
- **Response** — the answer to a Query. Always a set of claims each carrying its MEF; an empty
  result is **not** silence but an **EmptyClaim** that carries detector + coverage + confidence
  (negative findings are epistemic claims). Never a "naked" list of bodies without frames.

Always: producers emit Proposals; only governance emits Resolutions; rankers may order Responses but
never alter a claim's standing. Never: a Query/Response path that returns a claim without its MEF.
Derives from: L6 (write contract), L7 (read contract), L10 (negative findings are claims),
0002 Citizens capability matrix.

## Chapter 5 — Registry Projection

**Definition.** A **registry is a projection of the protocol** — one way to *materialize* the
message stream so standing can be recalled later. It is deliberately introduced *here*, fifth, not
first: the protocol is complete without it.

A projection:

- **Replays** messages into some durable shape (an append-only log, a distributed set of nodes, an
  index — implementation's choice in 0005).
- **Preserves** every MEF exactly as transported; a projection that mutates an MEF is not a valid
  projection (it would forge standing).
- Is **not authoritative over truth** — it records standing, it does not adjudicate it.

When projected onto **DSM specifically**, messages become hash-chained, append-only entries: this is
where the *DSM Integrity Constitution* (immutability, witnessed-forward integrity) governs the
materialization. But that is one projection. Another runtime could project the same protocol
differently and 0004 would still hold. The integrity regime belongs to the projection; the epistemic
regime belongs to the message.

Always: a projection is recomputable from the messages it replayed (Derived tier discipline). Never:
a projection becomes the source of truth such that losing it loses standing the messages still carry.
Derives from: 0001 two-constitutions split (Integrity vs Epistemic), 0002 Boundaries, 0003 Derived
("recomputable, versioned").

## Chapter 6 — State Machine & Invariants

**Definition.** The legal lifecycle of a Claim's standing, and the transitions a Resolution message
may cause.

States (0003 vocabulary): **Proposed → {Accepted | Rejected | Withdrawn | Superseded}**, with
Observation regimes (Witnessed / Imported / Recovered / Declared) on the Observed tier.

The binding invariants (each stated as a rule a projection/runtime must make impossible to violate,
per the 0001 enforcement discipline):

- **Accepted ≠ True.** No state carries a boolean "truth" field; acceptance raises standing, not
  truth. *(enforcement: the type has no truth field)*
- **Imported ↛ Witnessed.** No transition turns a reconstructed-backward regime into a
  witnessed-forward one; one cannot witness retroactively. *(enforcement: the transition is absent
  from the state machine)*
- **Withdrawal does not erase history.** A Withdrawn Proposal remains on record as withdrawn; the
  message that made it is never deleted. *(enforcement: append-only projection; withdrawal is a new
  message, not a deletion)*
- **Supersession does not erase historical validity.** A Superseded Claim stays valid *as of its
  time*; supersession adds a successor, it does not falsify the past. *(enforcement: supersedes is a
  relation, not an overwrite)*
- **Every transition is an attributed message.** No standing changes except via a Resolution
  message naming its producer; inference never moves a state. *(enforcement: state changes are only
  reachable through Resolution messages)*

Always: the state machine is the *only* path standing may travel. Never: a back-channel that changes
a claim's state without an attributed, recorded message.
Derives from: L1–L4 (regimes, witnessed vs reconstructed, ratification), L8, 0003 Epistemic Standing.

---

## Non-goals

0004 defines no wire format, no serialization, no storage engine, no transport (HTTP/gRPC/queue),
no API surface, and no concrete identifiers' encoding. Those are 0005 (Implementation), which is
free to choose any of them **provided** it carries these messages and preserves these frames.

## Enforcement (per the 0001 discipline)

A protocol rule is real only if a runtime can be built that makes its violation *impossible*, not
merely discouraged. The load-bearing ones — MEF non-strippable, no naked claim, Accepted≠True,
Imported↛Witnessed, transitions only via attributed Resolution messages, EmptyClaim for empty
Responses — must each become a type/lint/test that fails CI when broken, exactly as ADR-0001's
storage law became `forbid_storage_access.py`. 0005 names those tests.

## Consequences

- The registry is demoted from foundation to projection: DSM is *a* materialization, not *the*
  meaning. This buys freedom (rewrite, distribute, re-project) at no cost to standing.
- 0005 (Implementation) is now bounded: it picks encodings/engines/identifiers that *transport*
  these messages and *preserve* these frames — nothing it does may add a way to lose an MEF or move
  a state without an attributed message.
- The MEF is the single most load-bearing artifact in PRL: it is the write-side ("Accepted≠True")
  and read-side ("no naked claim") guarantee fused into one non-strippable frame.
