# DISCOVERY

Established from the merged code at `24629c1`, not from prior reports. Written
before any implementation.

## 1. The existing CLI

`src/hexashard_adapter/__main__.py`, argparse, stdlib only. One subcommand:

```
python -m hexashard_adapter chat <project> [--provider mock|ollama] [--mode NORMAL|READ_ONLY]
```

It can only `open` an existing project and chat. It has **no verb for creating a
project, adding a source, pinning, superseding, recording a decision, or
resolving a question**. This is the whole of finding "authoring requires Python".

The seam therefore extends this file. No new framework, no new dependency.

## 2. Authoring API already available

All of it exists on `Project`, re-exported through the Adapter:

| Operation | API | Notes |
|---|---|---|
| create | `Project.create(root, name=, mission=, **cfg)` | via `HexaShardAdapter.create` |
| open | `Project.open(root)` | config restored from `project.json` |
| add source | `project.add_source(source_type, title, content, *, status, tags, claim_key, claim_value, hex_id, …)` | returns `Source` with an **allocated** `source_id` |
| pin | `project.pin(key, value, source_ref, *, critical, note)` | `source_ref` may be `None` (ungrounded) |
| supersede | `project.supersede(old_id, new_id, *, reconcile_pins=True)` | adds a `SUPERSEDES` relation, reconciles pins |
| decision | `state.note_decision(hex_id, title, source_ref=None)` | deterministic, not model prose |
| questions | `state.add_open_question(qid, text)`, `state.resolve_question(qid)`, `state.unresolved_questions()` | single store |

The Adapter already gates all writers behind `READ_ONLY` (`PermissionError`).

**Source IDs are allocated by the store**, so the CLI never has to invent one.
Referring to an existing source is the only place a user currently needs an ID.

## 3. NORMAL turn lifecycle — exact ordering

From `HexaShardAdapter.chat`:

```
1  mode == READ_ONLY ?  _prepare_readonly()   -> project.retrieve() + check_pins(), NO mutation
   else                 project.handle_turn() -> MUTATES AND PERSISTS
2  _harden_context(ctx)
3  assemble(...)                              -> may raise ContextBudgetExceeded
4  provider.generate(...)                     -> may raise ProviderUnavailable
5  _require_provider_result(...)              -> may raise MalformedProviderResponse
6  build ChatTurnResult
7  _commit_turn()                             -> append_metric + _persist_config + project.save()
```

**The mutation at step 1 is already durable before step 4 runs.** `handle_turn`
ends with `self.save()`, and `rotate_epoch` explicitly persists "before the turn
returns". So a provider failure at step 4 leaves a completed-looking turn on disk
with no response ever produced.

Steps 3–5 all share this property: they occur after the state has been advanced
and before any response exists.

### What `handle_turn` mutates

| Mutation | Class |
|---|---|
| `state.turn += 1` | CONVERSATIONAL |
| `state.add_hint(user_message[:120])` | CONVERSATIONAL |
| `state.touch_hex(...)` for retrieved hexes | CONVERSATIONAL |
| `state.sync_pins(pins)` | CONVERSATIONAL (mirror of pin truth) |
| `enforce_budget()` — may drop hints/refs/decisions | CONVERSATIONAL |
| `retemper()` — hex temperatures | CONVERSATIONAL |
| `rotate_epoch()` — epoch + 3 files under `epochs/` | CONVERSATIONAL |
| `metrics.observe_*` | OBSERVABILITY (in-memory only) |
| `save()` | persists the above |
| Sources | **untouched** |
| Pins (the store) | **untouched** by `handle_turn`; only `pin()`/`supersede()` write them |
| Open questions | **untouched** |

**No PROJECT TRUTH is mutated by a chat turn.** That is the key structural fact:
everything a failed turn can dirty is conversational state.

### Durable footprint of a turn

`Project.save()` writes exactly:

```
project.json      (carries epoch)
hexmap.jsonl
pins.jsonl
relations.jsonl
active_state.json
```

plus, on rotation only, three files under `epochs/`.

It does **not** write `sources/`. Source content is written at `add_source` time.
This bounds the rollback problem: the state a turn can dirty is a small fixed set
of files whose size scales with pins and hexes, never with the source store.

## 4. Is rollback possible without touching Core?

Yes, and it was verified before being chosen.

`Project.__init__` builds every store as a fresh reader over the files and loads
`ActiveState` from `active_state.json`; `ProjectConfig` comes from `project.json`.
Nothing is cached across construction. So restoring those files and calling
`Project.open(root)` reconstructs the exact prior object.

Verified empirically on a 13-source project with a 400-token budget:

```
baseline               turn=0  epoch=1
after 40 handle_turns  turn=11 epoch=3   (2 rotations, 6 epoch artifacts written)
restore + reopen       turn=0  epoch=1
FINGERPRINT IDENTICAL: True
epoch artifacts after restore: []
```

The fingerprint compared turn, epoch, active-state tokens, retrieval hints,
active hex refs, every pin (id/value/source_ref/status), every source id, open
questions, and every hex temperature.

**Delaying the mutation is not an option**: `handle_turn` *produces* the context
that is sent to the provider, so it cannot run after generation. Snapshot and
restore is the only Adapter-local strategy, and it is sufficient.

## 5. Consequences for the design

- Snapshot the five state files plus the `epochs/` listing before `handle_turn`;
  restore them if the turn fails to produce a response. Cost is bounded and
  independent of store size.
- `sources/` is deliberately **not** snapshotted, because nothing on the failing
  path writes it. That invariant is asserted by test rather than enforced by
  copying, which keeps per-turn cost flat.
- Rollback must rebuild the `Project` object, since restoring bytes under a live
  object would leave stale in-memory state. `Project.open` with the existing
  `trust`/`provider`/`counter` preserves construction parameters.
- Observability must **survive** the rollback: `adapter_metrics.jsonl` and
  `adapter_config.json` are excluded from the snapshot.
- `READ_ONLY` mutates nothing, so it needs no rollback — only that the error
  still propagates.

## 6. Scope boundary found during discovery

Steps 3, 4 and 5 are indistinguishable from the project's point of view: state
advanced, no response produced. Scoping the rollback to "the turn produced no
response" rather than "the provider raised" is the same code path, is simpler to
state, and avoids the incoherence of rolling back a provider error but not a
context-budget error one line earlier.
