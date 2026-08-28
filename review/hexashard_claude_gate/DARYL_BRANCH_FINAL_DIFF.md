# DARYL_BRANCH_FINAL_DIFF

Exactly what this branch adds, reviewed before push.

**Branch:** `feat/hexashard-v01`
**Base:** `main` @ `990d378` (verified equal to `origin/main` at gate time)

## Shape of the diff

| | |
|---|---|
| files changed | **55** |
| lines added | **8,413** |
| lines deleted | **0** |
| binary files | **none** |
| total payload | **~326 KB** |
| files touched outside HexaShard | **1** (`pyproject.toml`, +3 lines) |

**Nothing existing was modified or deleted.** The only edit to a pre-existing file is
additive:

```diff
 pythonpath = ["."]
+markers = [
+    "integration: HexaShard long-project architecture validation",
+]
```

## Commits

```
    4f86a9a docs(hexashard): record the pre-GitHub independent gate
    3b48e48 docs(hexashard): architecture, evidence and limitations
    aca2e8c feat(hexashard): add chat adapter over the frozen core
    4f6389d feat(hexashard): add bounded project-context core (experimental v0.1)
```

Each is independently green: the Core commit does not depend on the Adapter, in code
or in tests.

## What is committed

| Path | Contents |
|---|---|
| `src/hexashard/` | Core — 12 modules, **byte-identical to the frozen v0.1 archive** |
| `src/hexashard_adapter/` | Adapter — 10 modules, with the Class A fixes |
| `tests/hexashard/` | Core suite (68) + fixtures |
| `tests/hexashard_adapter/` | Adapter suite (34) + gate regressions (12) |
| `docs/hexashard/` | README, ARCHITECTURE, EVIDENCE, LIMITATIONS + 2 recorded runs |
| `review/hexashard_claude_gate/` | the gate record |

## Confirmed absent

- **credentials** — none of any kind
- **absolute local paths** — none; `CORE_MANIFEST.json` was excluded for this reason
- **user email, username, machine identifiers** — none
- **raw provider logs / research data** — none
- **binaries, archives, model files** — none
- **new dependencies** — none; standard library only
- **`__pycache__`, `.pytest_cache`, venvs** — none (covered by `.gitignore`)

Two stray measurement files written into `tests/` by an early test run, before the
artifact-path fix, were caught during this review and removed. The suites now write to
the system temp directory and leave the tree clean, verified with and without
`HEXASHARD_ARTIFACTS_DIR` set.

## Gate results at the pushed commit

```
ruff check src/ tests/                            All checks passed!
bandit -r src/ -ll                                exit 0
pytest tests/hexashard tests/hexashard_adapter    114 passed   (3.10 and 3.12)
pytest tests/                                     1996 passed, 1 failed, 52 skipped
```

The single failure is a pre-existing flake on `main` (`test_consultation_store.py`),
present in the untouched baseline, untouched here, not claimed as fixed.
