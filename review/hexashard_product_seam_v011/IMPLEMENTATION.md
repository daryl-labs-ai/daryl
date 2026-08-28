# IMPLEMENTATION

Two files changed, both Adapter. Core untouched.

```
src/hexashard_adapter/__main__.py   authoring CLI (Part A)
src/hexashard_adapter/adapter.py    turn atomicity (Part B)
```

## Part A — the CLI

The existing `__main__.py` was extended, not replaced. Still argparse, still
stdlib, still no TUI and no new dependency. `chat` keeps its exact prior
behaviour and output format.

| Command | Underlying API |
|---|---|
| `create` | `HexaShardAdapter.create` |
| `status` | `project_status()`, `unresolved_questions()`, `check_pins()` |
| `source add` / `list` / `show` | `add_source(...)` |
| `pin` | `pin(key, value, source_ref, critical=, note=)` |
| `supersede` | `supersede(old, new)` |
| `decision` | `state.note_decision(...)` |
| `question add` / `list` / `resolve` | `state.add_open_question` / `resolve_question` |
| `chat` | unchanged |

The CLI holds no project model of its own. Every command is a pass-through, and
`READ_ONLY` gating is the Adapter's existing `PermissionError`.

### Reference resolution

Sources are addressed by **id or title**. Titles are what a person remembers.

Ambiguity is never guessed — two sources sharing a title produces an error
listing both ids:

```
error: 'Berth licence' matches 2 sources — say which one by id:
    P1.S0001  Berth licence  [CURRENT]
    P1.S0002  Berth licence  [CURRENT]
```

An unknown reference lists what does exist. IDs are still printed everywhere for
auditability — the rule is that they may be *visible*, not that they must be
*memorised*.

Question ids are allocated automatically when omitted.

### Two deliberate refusals

**A pin without a source is refused** unless the user passes `--ungrounded`.
Pins point, sources ground; making the ungrounded case explicit keeps that true
without forbidding it.

**`supersede` reports a pin left holding a superseded value**, naming the pin and
the value. Required so the CLI does not conceal the known `claim_key` limitation.
Scoped to the command that causes it — see KNOWN_FINDINGS_NOT_FIXED.md §2.

## Part B — turn atomicity

### The problem, precisely

`Project.handle_turn` advances state **and persists it** before the caller can
call a provider, because it is what produces the context to send. So by the time
generation fails, a completed-looking turn is already on disk.

Delaying the mutation is impossible: the mutation *is* the context production.
Snapshot and restore is the only Adapter-local option, and discovery confirmed it
is sufficient.

### What is captured

`Project.save()` writes exactly five files, and **never `sources/`**:

```
project.json  active_state.json  hexmap.jsonl  pins.jsonl  relations.jsonl
```

plus, on rotation, three artifacts under `epochs/`.

`_TurnSnapshot` records those five files' bytes and the `epochs/` listing before
`handle_turn`. Cost scales with pins and hexes, **never with the source store**,
so a large project does not pay per turn.

`sources/` is deliberately not copied, because nothing on the failing path writes
it. That invariant is asserted by test rather than enforced by copying.

### What happens on failure

The window from `_harden_context` through provider-result validation is wrapped.
Any failure in it means state advanced and no response exists, so:

1. record the failure in `adapter_metrics.jsonl`;
2. restore the five files and delete epoch artifacts the failed turn created;
3. rebuild the `Project` from disk, preserving `trust`, `provider` and `counter`;
4. re-raise.

Step 3 is necessary: restoring bytes under a live object would leave stale
in-memory state. `Project.open` reconstructs every store and reloads
`ActiveState`, which discovery verified is lossless.

`READ_ONLY` takes no snapshot — it mutates nothing — and its errors simply
propagate.

### Scope of the window

The wrapper covers three failure shapes, because from the project's point of view
they are identical — state advanced, no response produced:

- the provider raising (`ProviderUnavailable`)
- a malformed provider reply (`MalformedProviderResponse`)
- assembled context over the provider limit (`ContextBudgetExceeded`)

Rolling back a provider error but not a context-budget error one line earlier
would have been incoherent, and it is the same code path.

`BaseException` is caught rather than `Exception` so that a `KeyboardInterrupt`
mid-turn also leaves a clean project; it is re-raised untouched.

### What is deliberately NOT rolled back

The metrics row. Observability is not project truth, and a failure that leaves no
trace is worse than one that leaves a record. Failure rows carry `outcome:
failed`, the error type, a truncated detail, and `turn_rolled_back`.

### Verification of the strategy, before it was chosen

On a 13-source project with a 400-token budget:

```
baseline               turn=0  epoch=1
after 40 handle_turns  turn=11 epoch=3   (2 rotations, 6 epoch artifacts)
restore + reopen       turn=0  epoch=1
FINGERPRINT IDENTICAL: True
epoch artifacts after restore: []
```

Fingerprint covered turn, epoch, active-state tokens, retrieval hints, active hex
refs, every pin, every source id, open questions and every hex temperature.

## Successful turns

Unchanged. The snapshot is taken and discarded; nothing on the success path
reads it. `test_f12_successful_turn_behaviour_is_unchanged` asserts that a
success following four failures is identical to a success with no failures at
all — same retrieved source ids, context tokens, active-state tokens, epoch,
turn and pin warnings.

## What was not touched

Core (byte-identical), retrieval, pin semantics, `check_pins()`, supersession
semantics, `claim_key`, READ_ONLY semantics, context assembly, the metrics schema
for successful turns, packaging.
