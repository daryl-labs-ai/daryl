# DOGFOOD_EVIDENCE

Why this change exists. Summary only — no raw transcripts are copied here.

Two frozen dogfoods ran independently against `main @ 24629c1`, on different
projects, and reached the same verdict: **B / UX-B**.

| | Evaluator A | Evaluator B |
|---|---|---|
| project | NORTHSTAR PRODUCT LAUNCH | KITEWHARF Hub-7 |
| result | technical B, UX-B | technical B, UX-B |

## What both confirmed works

Continuity survives process restart; an empty visible chat destroys nothing;
transcript replay is unnecessary; current facts stay recoverable; unknown facts
are not fabricated; model suggestions do not become authority; explicit decisions
persist; provider switching does not own persistence.

None of that is touched by this change.

## The two problems both found independently

### 1. Authoring required leaving the product

Neither evaluator could maintain a project from the CLI. The shipped CLI had one
verb — `chat`. Adding a source, pinning a fact, superseding, recording a decision
or resolving a question all required writing Python against the Adapter API.

Both recommended, in their own words, a boring authoring CLI.

Two independent users hitting the same wall on different projects is what
authorises Part A. It is the gap between *the runtime works* and *a person can
use it*.

### 2. A failed provider call still looked like a conversation

Both reproduced: `provider.generate()` fails, no response is produced, and yet
the turn counter has advanced and been persisted. Evaluator A measured it
directly — turn 12 → 13 on a dead endpoint, with sources and pins intact and the
error surfaced cleanly.

Not corruption, and not data loss. But the project records a conversation that
never happened, and that is the kind of quiet inaccuracy the whole design exists
to avoid.

That is Part B.

## Found by both, deliberately NOT repaired here

Both evaluators independently hit a natural-language historical retrieval
failure:

> A: *"Didn't we originally plan for more than that?"*
> B: *"Wasn't that number lower before?"*

In both cases the superseded value was hard or impossible to recover. Evaluator A
recorded the sharper version: the question retrieved neither budget source,
because it shares no vocabulary with either — it does not contain the word
*budget* at all — and the model then fell back on a pin still asserting the old
number, contradicting its own previous turn.

This is important, and it is explicitly out of scope. Repairing it means changing
retrieval, and retrieval changes need their own experiment. See
KNOWN_FINDINGS_NOT_FIXED.md.

## Scope discipline

This change implements **only** what two independent users independently
demonstrated they needed. Everything else both dogfoods surfaced — retrieval,
stale-pin rendering, READ_ONLY ergonomics, output truncation — is recorded and
left alone.
