# HEXASHARD — PRODUCT SEAM v0.1.1

> ## Verdict — A: READY FOR INDEPENDENT REVIEW

Two independent dogfoods, on different projects, independently found the same two
problems. Both are now fixed, Adapter-side, with Core byte-identical.

A user can maintain a project entirely from the CLI, and a provider failure no
longer leaves the project pretending a conversation happened.

Nothing else was changed. The retrieval finding both evaluators also hit is
recorded and deliberately untouched.

---

## Provenance

| | |
|---|---|
| Base | `main @ 24629c1729f953bcbe4313cacc23edafa9d06a36` |
| Branch | `feat/hexashard-product-seam-v011` |
| Core before | `5b6a78e5c1a821bb17680ec8dfb5871247f2b9dc2cdaa9fd593e94791df726d9` |
| Core after | `5b6a78e5c1a821bb17680ec8dfb5871247f2b9dc2cdaa9fd593e94791df726d9` |
| Core modified | **No** — lock asserts, `git diff origin/main -- src/hexashard` empty |
| Files changed | 2 (`__main__.py`, `adapter.py`), both Adapter |
| New dependencies | **none** |

## The twenty questions

**1. Did Core change?** No. Identical digest before and after; the lock assertion
passes; the diff against main under `src/hexashard` is empty.

**2. What exact friction was removed?** Two things, and only these. Project
authoring no longer requires writing Python. A provider failure no longer records
a conversational turn that never happened.

**3. Can a user author a project without Python?** Yes. The mini dogfood built a
grounded project — sources, pins, a supersession, a decision, a resolved question
— across several separate processes, entirely from the CLI, without typing a
single internal id.

**4. Which operations are available?** `create`, `status`, `source add|list|show`,
`pin`, `supersede`, `decision`, `question add|list|resolve`, `chat`. All are
pass-throughs to existing APIs; the CLI holds no project model of its own.

**5. Are internal IDs mandatory?** No. Sources are addressed by title or id, and
question ids are allocated when omitted. IDs remain *visible* for auditability.
Ambiguity is never guessed — a duplicate title errors and lists both candidates.

**6. Does assistant prose remain non-authoritative?** Yes, unchanged and
regression-tested. A mock model answering *"I recommend delaying the second
carrier until June"* leaves `recent_decisions` untouched and creates no source;
two chat turns leave the source set byte-identical.

**7. Does explicit decision persistence still work?** Yes, through
`state.note_decision`, verified across a reopen.

**8. What happens after `provider.generate()` fails?** The failure is recorded in
`adapter_metrics.jsonl`; the five state files `Project.save()` writes are restored
and any epoch artifact the failed turn created is deleted; the `Project` is
rebuilt from disk; the typed error is re-raised.

**9. Does a failed generation consume a durable turn?** No. Turn counter
unchanged, verified in-process and after reload from a separate process.

**10. Does ActiveState change?** No — tokens, retrieval hints, active hex refs and
recent decisions are all identical, including after 20 consecutive failures.

**11. Can epoch advance because of a failed generation?** No. Tested with a budget
small enough that a turn *would* rotate: epoch unchanged and no epoch artifacts
left behind.

**12. What observability survives?** The metrics row: `outcome: failed`, error
type, truncated detail, `turn_rolled_back`, mode, provider. Deliberately not
rolled back — observability is not project truth.

**13. Can the request be retried cleanly?** Yes, and it costs exactly one turn.

**14. Did successful-turn semantics change?** No. A success after four failures is
identical to a success with none: same retrieved source ids, context tokens,
active-state tokens, retrieved tokens, epoch, turn and pin warnings.

**15. Did retrieval change?** No.

**16. Did stale-pin semantics change?** Core's did not. The `supersede` command
now reports when it leaves a pin holding a superseded value — required so the CLI
does not conceal the limitation, and scoped to the command that causes it.
`status` still reads `check_pins()` and does not report it; that inconsistency is
classified, not patched.

**17. Did historical retrieval change?** No. Frozen deliberately.

**18. Does `daryl-dsm` still exclude HexaShard?** Yes — wheel is `dsm` + `prl`,
164 files, no `hexashard` entries.

**19. Did all Core hashes remain frozen?** Yes.

**20. Strongest remaining UX limitation?** The historical retrieval failure. A
user can now *record* a correction easily, but a question like *"wasn't that
number lower before?"* still may not find the superseded value. That is the next
thing worth an experiment, and it is not a patch.

## Results

| | |
|---|---|
| HexaShard suites (3.12 and 3.10) | **159 passed** each |
| Full DARYL suite | **2042 passed, 0 failed** |
| ruff / bandit | clean / exit 0 |
| wheel | `dsm` + `prl`, HexaShard excluded |

Baseline was 1996; the delta is 30 CLI tests + 15 atomicity tests + 1 renamed.

One existing test changed: the gate test that locked in the old provider-failure
behaviour, whose own docstring asked that any future change be deliberate. It was
rewritten to the new invariant with the reason recorded. Nothing was weakened or
deleted to get green.

## Mini dogfood

Twelve steps, real CLI, real local model, real process restarts:

```
create → 2 sources → 2 pins by title → open question   (no ids typed)
NEW PROCESS → supersede with claim_key → decision → resolve question
NEW PROCESS → chat (ollama) → 3 provider failures → NEW PROCESS status
```

The claim_key supersession carried the pin forward to the new value. The ordinary
supersession printed:

```
warning   pin berths still reads '3 and 4 only' and is marked NEEDS_REVIEW
          — confirm it against P1.S0004
```

The model, asked about berths, surfaced the conflict rather than hiding it.

After three failed turns, a **new process reading from disk** reported `turn 1`
and `active 199` — exactly the values from before the failures.

## Boundary, stated precisely

This covers failures the Adapter can observe: the provider raising, a malformed
reply, or the assembled context exceeding the provider limit. **It is not crash
consistency.** A process kill or power loss partway through Core's writes is a
different transaction model and is not addressed. Core's individual writes are
atomic; that is not the same as a multi-file transaction.

**No performance claim is made.** One dogfood measured a store smaller than the
context sent. This work is continuity, authoring and failure semantics.

## Not fixed, on purpose

Historical retrieval of superseded values; Core stale-pin semantics; `status`
not reporting repointed pins; READ_ONLY ergonomics; silent output truncation.
All in KNOWN_FINDINGS_NOT_FIXED.md.

## Next

Independent review. Not merged, not tagged, not released, no version bumped.
