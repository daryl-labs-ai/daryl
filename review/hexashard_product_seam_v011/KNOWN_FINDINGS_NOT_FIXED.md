# KNOWN_FINDINGS_NOT_FIXED

Everything both dogfoods surfaced that this change deliberately leaves alone.
Recorded so the next decision starts from evidence rather than memory.

## 1. Historical retrieval of a superseded value — FROZEN

Both evaluators, independently, on different projects:

> *"Didn't we originally plan for more than that?"*
> *"Wasn't that number lower before?"*

Neither question shares vocabulary with the source that answers it. Lexical
retrieval returns nothing, and the superseded value stays out of reach. In
evaluator A's run the model then fell back on a stale pin and contradicted its
own previous turn.

**Not addressed.** No BM25 tuning, no embeddings, no semantic layer, no query
rewriting or expansion, no reranking, no `claim_key` redesign, no supersession
redesign, no Core retrieval change, and specifically **no heuristic that searches
superseded sources when it sees words like "before", "previously" or
"originally"**. That last one is tempting and would probably help the two
observed cases, which is exactly why it needs its own experiment rather than a
guess bolted onto a CLI change.

Documented in `docs/hexashard/LIMITATIONS.md`.

## 2. Stale pin value after an ordinary supersession — FROZEN in Core

`supersede()` repoints a pin and marks it `NEEDS_REVIEW` while it keeps its old
value. `Core.check_pins()` re-resolves and returns `ACTIVE`, masking the stored
status, so Core's own `pin_warnings` is empty.

**Core is unchanged.** The Adapter's existing warning is untouched.

One thing did change, and the boundary is worth being precise about: the new
`supersede` command prints the consequence of the operation the user just
performed, naming the pin and the value it still holds. That is required by the
brief's own instruction not to conceal the limitation when exposing supersession,
and it is scoped to the command that causes it.

What was **not** done: `status` still reads `check_pins()`, so it does not report
a repointed pin. Extending stale-pin rendering across the CLI would be the "tiny
Adapter rendering correction" the brief says to stop and classify rather than
smuggle in. **Classified here, not implemented.** It is a real inconsistency —
`supersede` warns, `status` does not — and it deserves a decision of its own.

## 3. READ_ONLY is developer-shaped UX — FROZEN

Both dogfoods found `READ_ONLY` technically correct and awkward: the user must
choose it before opening the CLI, before knowing what the conversation will be,
and choosing wrong is invisible because NORMAL's mutation gives no signal.

**Not redesigned.** No automatic classifier, no LLM deciding mutation mode. The
only change is that `chat --mode READ_ONLY` now says what it is doing, and
`--help` explains it.

## 4. Output truncation is silent — NOT ADDRESSED

`max_output_tokens` defaults to 256 and answers stop mid-sentence. The reported
`truncated` flag describes input assembly, not output. Evaluator A saw this three
times.

Out of scope: neither authorised part covers it.

## 5. No compression at small scale — EXPECTED

Evaluator A measured a project store of ~593 tokens against a mean model-visible
context of ~686 — HexaShard cost context at that size. Expected: bounded context
is a scale mechanism.

**No performance or compression claim is made by Product Seam v0.1.1.** This work
is about continuity, authoring and failure semantics.

## 6. Crash consistency — EXPLICITLY NOT CLAIMED

Part B covers failures the Adapter can observe. A process kill or power loss
partway through Core's writes is a different transaction model and is **not**
addressed. Core's writes are individually atomic (temp file, `fsync`,
`os.replace`, directory `fsync`), which is not the same as a multi-file
transaction.
