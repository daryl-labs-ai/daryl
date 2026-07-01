# Capability Register — what Daryl owns, must prove, and must build

**Status:** Living register · **Date:** 2026-06-28 · **Regime:** `declared` · **Supersedable:** yes

```
──────────────────────────────────────────────

  CAPABILITY REGISTER

  Proven assets          5
  Robustness frontiers   9   (8 proven · 1 idea)
  Product surfaces      10
  Canonical law         11

  Current focus 🔥
  → free

  PROOF VELOCITY
  Last proof       2026-07-01  Governance layer v0 — a governance posture derives read-only above latest-wins
  Previous proof   2026-06-30  Object coherence visibility v1 — incoherence across a subject's claims surfaced
  Recent cadence   2026-06-27 → 2026-07-01 : 5 assets + 8 frontiers proven
  (the date is the datum; days elapsed is a view — let Git compute it)

──────────────────────────────────────────────
```
*(Counts and velocity mirror the tables below — update them in the same edit as any row move. The
last-proof **date** is the datum; elapsed time is a view (Git computes it). A long gap is a health
signal, not a failure. 🔥 marks the single item under active work — one focus at a time.)*

Most projects keep a roadmap (what they intend to build). This is the rarer, more honest artifact:
a register of capabilities **by level of proof**, split by **what Daryl already owns** vs **what it
must still prove** vs **what it must still build**. It does not say how *much* is done — percentages
age badly — it says, for each item, **how strongly it is established**. A row moves only with the
same discipline as the rest of Daryl: nothing reaches 🟢 without a real transcript, nothing reaches
🏛 without entering the law.

## Proof levels (Daryl's own epistemic ladder)

| Level | Meaning |
|---|---|
| ⚪ **Idea** | named; no design yet |
| 🟡 **Designing** | grounding / issue / ADR in progress; not implemented |
| 🔵 **Implemented** | code merged + tests green; not yet proven under real conditions |
| 🟢 **Proven (runtime)** | demonstrated end-to-end with a **real transcript** (real agent / real gate), receipt-backed |
| 🏛 **Canonical** | promoted into the law — an Accepted ADR or a graduated manifesto property |

The load-bearing distinction is **🔵 Implemented vs 🟢 Proven**: code that runs in tests is not the
same as a capability shown to hold in real conditions.

---

## 1 · Proven assets — what Daryl owns

Capabilities demonstrated end-to-end under real conditions. These are acquired; they do not regress
without a recorded demotion.

| Status | Asset | Proven | Proof | Notes |
|---|---|---|---|---|
| 🟢 | Retrieval v2 | 2026-06-27 | through-prod benchmark (15-Q, eval↔prod parity) · Evidence Book Proof #1 | policy `chunk_primary gate10` frozen in ADR-0006 |
| 🟢 | Agent Consultation (write · read · real agent) | 2026-06-27 | PRs #71/#73/#75 · real **gpt-4o** transcript, receipt `v1:d1df9eda…2470779` write↔read identical | ADR-0008; Observation default, Proposal explicit |
| 🟢 | Resolution / Standing | 2026-06-28 | PR #77 · real gate `claim_7c765d2988fd` → Resolution receipt `v1:b9901b…214a` | human governance; standing **derived**, never stored |
| 🟢 | Explain ("why this decision?") | 2026-06-28 | PR #78 · real gate reconstructed the chain, receipt-per-line | MVP step 6; projection over certified acts |
| 🟢 | MVP Demo Scenario (end-to-end) | 2026-06-28 | PR #79 · full KO-7 chain Proposal `v1:97d271…` → Resolution `v1:b9901b…` → standing ACCEPTED → explain | steps 1–6, real agent, without cheating |

## 2 · Robustness frontiers — what Daryl must prove

Not features — **tests of whether the proven invariants survive at scale** (see
`SECOND_EPOCH_OPEN_QUESTIONS.md`). A frontier graduates to a Proven asset only with a real transcript.

| Status | Frontier | Notes |
|---|---|---|
| 🟢 Proven | Identity across projections | PR #82 · real gate KO-7: `explain` RR ≡ `--projection sqlite` · read projection (reserve: certification substrate stays DSM, receipt projection-relative) |
| 🟢 Proven | Concurrent resolutions — conflict **visibility** (#2 v1) | PR #92 · functional in-suite (no credential): `detect_conflict` (D3 — two distinct `agent_id` opposite `accepted`/`rejected`; legacy fallback surfaces unknown-author opposites) read **alongside** latest-wins · standing **unchanged**, conflict a **derived** flag (`⚠ CONFLICT`), never stored (`StandingIndex` inherits; drop/rebuild identical) · **Daryl does not yet govern conflict** — it now guarantees an incompatible human resolution **cannot stay invisible**. **Open (step c):** contested-as-standing / authority / required supersession — `MEF.contested` still unread, no ADR |
| 🟢 Proven | Derived standing at scale (#1) | PR #90 · measured kernel: `StandingIndex` 1 scan (build) vs `StandingQuery` N scans (per-query), identical standing, droppable · `O(N)/query` → `O(N)`-once + `O(k)`/query, *standing never stored* survives the optimization |
| 🟢 Proven | Object referent — `subject_id` read-gather (#4a) | PR #94 · functional in-suite + live smoke: `standings_of_subject` walks `subject → consultation.claim_id → standing_of(claim)` — **gather, not compile** (N claims side by side, no "object standing" field) · `subject_id` reaches the **governed layer read-only**, **no `object_id` / no new field** (not added to resolutions), `#1`/`#2` reused · the *referent* is settled, the compiler is **#4b** |
| 🟢 Proven | Object coherence — visibility (#4b v1) | PR #96 · functional in-suite + live smoke: `detect_coherence` (rule C-d — over **live governed** claims, `superseded`/`withdrawn` excluded) derives `aligned` / `divergent` / `unsettled` read **alongside** the #4a gather · `divergent` surfaces both claim_ids, **claims stay side by side, the subject gets NO standing** (the view has no `standing` field) · per-claim #2 conflict orthogonal · **make visible before governing**, like #2 · **Reserve:** *visibility, not governance* — reconciling claims into one coherent Object (object-standing / authority) is the deferred **object-scale step (c)**; the real *compiler* (one coherent evolution) and `subject_id` F4/F5 stay open |
| 🟢 Proven | Governance of divergence — read-only seam (step (c) v0) | PR #98 · the convergent step (c) of #2 + #4b · functional in-suite + live smoke: `governance_read` derives a posture `clear` / `contested` / `divergent` (rule G-1, precedence `divergent > contested > clear`) **above latest-wins**, consolidating the #2/#4b signals · **governs nothing** — standing byte-identical, no write blocked, `MEF.contested` still unread (0 consumers), distinct vocabulary (never a standing) · **Reserve:** the seam only — what `contested`/`divergent` should **do** ((i) contested standing / (ii) authority / (iii) required supersession) is the **first governing rule = the project's first governance ADR**, deferred |
| 🟢 Proven | Organization identity — the referent (#5a) | PR #88 (ADR-0010) · real gate: same `org.acme` across `openai:gpt-4o`/`gpt-5`, `consultations --org` returns exactly them · `org_id` ≠ carrier (3rd identity referent) |
| ⚪ Idea | Distributed certification — the substrate (#5b) | deferred · can DSM certification survive no single registry? kernel-shaped, heavy — separate from #5a |
| 🟢 Proven | Agent identity across providers and runs | PR #84 (ADR-0009) · real gate: same `agent_id` `agent.architect` across `openai:gpt-4o` / `gpt-5`, both certified · `agent_id` ≠ `model_id` |

## 3 · Product surfaces — what Daryl must build

Engineering / industrialization. Not assets and not invariants — the surfaces a daily-use product
needs. Not yet started.

| Status | Surface | Notes |
|---|---|---|
| ⚪ Idea | Knowledge Objects (first-class entities) | the unit a user manipulates; today a projection of acts |
| ⚪ Idea | Knowledge Maps | views / navigations into the Fabric |
| ⚪ Idea | Organization model (permissions, security, multi-org) | enterprise prerequisite |
| ⚪ Idea | Public API | — |
| ⚪ Idea | Public SDK(s) | — |
| ⚪ Idea | User interface | — |
| ⚪ Idea | Product-facing search | distinct from the internal recall engine |
| ⚪ Idea | Analytics / observability | — |
| ⚪ Idea | Packaging / deployment | — |
| ⚪ Idea | Developer documentation | — |

## 4 · Canonical law — what is now binding

Governed properties the assets rest on; changed only by superseding ADR or manifesto movement.

| Status | Property | Anchor |
|---|---|---|
| 🏛 | Epistemic Registry Constitution | ADR-PRL-0001 |
| 🏛 | Registry Architecture | ADR-PRL-0002 |
| 🏛 | Vocabulary | ADR-PRL-0003 |
| 🏛 | Protocols + MEF (never strippable) | ADR-PRL-0004 |
| 🏛 | Retrieval v2 policy (frozen) | ADR-PRL-0006 |
| 🏛 | Adapter Strategy (integrations adopt PRL, not models) | ADR-PRL-0007 |
| 🏛 | Agent Consultation Protocol | ADR-PRL-0008 |
| 🏛 | Structured Contributor Attribution (`agent_id` ≠ `model_id`) | ADR-PRL-0009 |
| 🏛 | Organization Referent (`org_id` ≠ carrier) | ADR-PRL-0010 |
| 🏛 | "A contribution becomes a governed project asset" | manifesto (graduated 2026-06-28) |
| 🏛 | "Identity is never defined by its carrier" (3 referents) | manifesto (graduated 2026-06-28) |

---

## How to update
Move a row only on a real movement, and cite its proof: 🔵→🟢 needs a real transcript (receipt or
gate output); 🟢→🏛 needs entry into the law (an Accepted ADR or a graduated manifesto property,
recorded in `PROOF_LOG.md`). In the same edit, update the **dashboard counts** and the **proof
velocity** (last/previous proof + date). Never promote on intention. This register is the dashboard;
the dated evidence lives in `PROOF_LOG.md` and `EVIDENCE_BOOK.md`.

**Regression rule.** A capability may move **🟢 → 🔵** (or lower) if a contradicting real transcript
invalidates the previous proof. A backward move requires a `PROOF_LOG.md` entry explaining why, and a
demotion note on the row. Demotion is not failure — it is the system correcting a belief, the same
mechanism that lets it promote one.

---

## Capability lifecycle

```
  Idea  →  Designing  →  Implemented  →  Proven  →  Canonical

  Regression is allowed.
  A capability may move backwards when new evidence contradicts a previous proof.
  Every backward movement requires a PROOF_LOG entry.
```
