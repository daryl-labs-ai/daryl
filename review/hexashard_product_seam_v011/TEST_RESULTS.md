# TEST_RESULTS

All runs from a clean environment built by `scripts/setup_dev_env.sh` on this
branch.

## Core freeze

```
core lock assertion: PASS
before: 5b6a78e5c1a821bb17680ec8dfb5871247f2b9dc2cdaa9fd593e94791df726d9
after : 5b6a78e5c1a821bb17680ec8dfb5871247f2b9dc2cdaa9fd593e94791df726d9
CORE UNCHANGED: True

git diff origin/main -- src/hexashard   ->  empty
```

## Suites

| Run | Result |
|---|---|
| `pytest tests/hexashard tests/hexashard_adapter` (3.12) | **159 passed** |
| same, Python 3.10 (CI matrix minimum) | **159 passed** |
| `pytest tests/` — full DARYL suite | **2042 passed, 0 failed**, 52 skipped |
| `ruff check src/ tests/` | All checks passed |
| `bandit -r src/ -ll` | exit 0 |
| `python -m build --wheel` | OK |

Baseline before this change was 1996 passed. The delta is +46: 30 CLI tests, 15
atomicity tests, and one gate test renamed.

The pre-existing PRL flake (`tests/prl_pkg/test_consultation_store.py`) did not
fail in this run; it is unrelated and untouched either way.

## New tests

### `tests/hexashard_adapter/test_cli_authoring.py` — 30 tests

Covers C1–C18. The CLI is exercised as a **subprocess** wherever the point is
user-facing behaviour, because that is what a person runs.

| | |
|---|---|
| C1, C16 | chat unchanged; READ_ONLY still blocks writes and mutates nothing |
| C2 | `--help` exposes every authoring verb and explains project ≠ chat |
| C3–C5 | create, refuse to clobber, add source inline and from file, persists across reopen |
| C6–C7 | pin by title, persists, ungrounded refused unless explicit |
| C8–C9 | supersede; statuses correct; history reachable; **both** claim_key paths |
| C10–C11 | explicit decision persists; **a model recommendation does not** |
| C12 | question opened, listed, resolved; unknown id errors |
| C13 | ambiguous title is **not guessed** — error lists both ids |
| C14 | no internal id ever typed; ids still displayed |
| C15 | missing project and missing content give useful errors |
| C17–C18 | transcript never becomes a source |

`test_c9_ordinary_supersession_surfaces_the_stale_pin` asserts the known
limitation is **reported**, and `test_c9_declared_claim_carries_the_value_forward`
asserts the careful path still reconciles. Both paths are pinned so neither
silently changes.

### `tests/hexashard_adapter/test_turn_atomicity.py` — 15 tests

Covers F1–F15.

| | |
|---|---|
| F1 | typed error surfaces |
| F2–F4 | sources, pins, open questions unchanged across repeated failures |
| F5–F7 | turn counter, ActiveState and epoch unchanged; **no epoch artifacts left** |
| F8 | durable state byte-identical apart from observability |
| F9 | failure **is** recorded — `outcome: failed`, error type, `turn_rolled_back` |
| F10–F11 | retry succeeds and costs exactly one turn |
| F12 | success after 3 failures identical to success with none |
| F13 | READ_ONLY failure remains non-mutating |
| F14 | 20 distinct failing questions accumulate nothing |
| F15 | reload from disk shows clean state |

Plus three beyond the brief: malformed provider replies and context-budget
failures roll back through the same window, and a rollback after a *successful*
rotation preserves that rotation while removing only the failed turn's artifacts.

### One existing test changed

`test_f03_provider_failure_still_consumes_a_turn` asserted the old behaviour, with
the docstring *"This locks the behaviour in so a future change to it is
deliberate."* The change is deliberate and authorised, so the test was rewritten
as `test_f03_provider_failure_no_longer_consumes_a_turn`, keeping the record of
why it changed. **No test was weakened or deleted to get green.**

## Packaging

```
wheel top-level: ['dsm', 'prl']  (164 files)
hexashard excluded: True
```

Identical to the boundary established before this change.

## Mini dogfood

Twelve steps through the real CLI, real local model, real process restarts —
recorded in the final report. Verified from a fresh process reading disk that
three failed turns left `turn 1 → 1` and `active 199 → 199`.
