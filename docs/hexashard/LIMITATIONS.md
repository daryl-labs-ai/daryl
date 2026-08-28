# HexaShard v0.1 — Limitations

Confirmed by independent reproduction at the pre-GitHub gate. Anything measured is
stated with its measurement.

## Retrieval

**Lexical retrieval degrades under paraphrase.** Retrieval is BM25 over fragments.
On the frozen paraphrase bank:

| Paraphrase level | n | retrieval accuracy | Hit@1 | authority accuracy |
|---|---|---|---|---|
| original wording | — | 1.000 | — | 1.000 |
| light (P1) | 13 | 1.000 | 0.846 | 0.714 |
| medium (P2) | 13 | 0.769 | 0.385 | 0.286 |
| heavy (P3) | 13 | 0.692 | 0.385 | 0.286 |

Recall degrades gracefully; **rank-1 authority selection does not**. If a question is
worded very differently from the source that answers it, the right source may not come
first, or at all.

**All CURRENT sources share one authority rank.** Ordering among them is pure lexical
overlap. Supersession status is respected; relative importance of two live sources is
not modelled.

**`claim_key` is opt-in, so contradiction detection is opt-in.** Two CURRENT sources
that contradict each other are only flagged as an authority conflict if both declare
the same `claim_key`. Undeclared contradictions are not detected.

**Identifier-dependent questions are fragile.** Questions that hinge on a literal
token (`V-118`, `ADR-007`) work well when the token is used and poorly when it is
paraphrased away.

## Pins

**A pin can be grounded and still be wrong.** Nothing verifies that a pin's value
actually appears in the source it points at. A pin entered incorrectly stays
incorrect and reports as grounded.

**A repointed pin is not reported through `Core.check_pins()`.** When `supersede()`
repoints a pin, it stamps the stored pin `NEEDS_REVIEW` and keeps the old value — but
`check_pins()` re-resolves against the new pointer and returns `ACTIVE`, so Core's own
`pin_warnings` is empty. The Adapter compensates and reports these, so
`ChatTurnResult.pin_warnings` is correct; **direct Core users should read the pin's
stored `status`, not `check_pins()` alone.** Reconciliation only adopts a new value
when the successor is CURRENT *and* declares a matching `claim_key`/`claim_value`.

## Adapter and state

**NORMAL mode mutates project state on every question, including read-only ones.**
`Core.handle_turn()` increments the turn counter, records a retrieval hint, touches
hexes, enforces the budget and saves to disk. Measured consequences:

- Repeated *identical* questions do not accumulate — hints de-duplicate. 25 identical
  turns moved active state by 10 tokens.
- Distinct questions do accumulate hints, but **active state stays bounded**: 120
  distinct questions against an 800-token budget ended at 272 tokens.
- **Epochs advance from questions alone, durably.** 120 read-only questions produced
  3 epoch rotations, persisted across reload. Epoch number is not a reliable record
  of project activity.
- Sources and pins are never altered by asking questions.

`READ_ONLY` mode avoids all of it: verified zero state change and **zero bytes
written** across 30 turns. It is an Adapter-level wrapper over `Core.retrieve()`, not
a Core mode.

**A provider failure still consumes a turn.** State advances and is saved before the
provider is called, so a failed call spends a turn with no answer.

**`Core.handle_turn()` returns live references into ActiveState.** A caller that
mutates the returned `response_context` mutates Core state, and the change persists.
The Adapter copies defensively, so this affects direct Core users only.

## Measurement

**The token counter is an estimator**, not a provider tokenizer. Every token figure
here is approximate and provider-independent by design.

**Context-reduction ratios are fixture properties, not constants.** 31.7x on
MERIDIAN-9 and ~280x on the Adapter smoke project describe those fixtures. A different
project shape gives a different ratio.

## Live-model evidence

**The external-API experiment (LIVE 001) is inconclusive and supports nothing.** It
ran out of credit mid-run; at the largest checkpoint both arms scored 0/48 on HTTP
400s.

**The local-model experiment (LIVE 001-L) is a single unreplicated run** — n=1, one
model (`qwen3.6:35b-a3b`), one machine. It shows equal accuracy at far smaller visible
context, and completion where the full-context arm could not run. It does **not**
show better answers, and does not generalise to other models.

## Operational

**Single-process assumptions.** Writes are atomic per file (temp file, `fsync`,
`os.replace`, directory `fsync`), but there is no cross-process locking. Concurrent
writers to one project are not supported.

**No migration story.** The on-disk format is v0.1 with no versioning or upgrade path.

**Providers are `mock` and `ollama` only.** The Ollama defaults come from the
LIVE 001-L machine and are not universal.
