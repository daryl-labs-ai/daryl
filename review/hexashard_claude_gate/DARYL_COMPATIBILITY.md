# DARYL_COMPATIBILITY

## DARYL conventions observed

| Aspect | DARYL | HexaShard follows |
|---|---|---|
| layout | `src/` package dir (`src/dsm`, `src/prl`) | `src/hexashard`, `src/hexashard_adapter` |
| tests | `tests/`, `test_*.py`, `testpaths=["tests"]` | `tests/hexashard`, `tests/hexashard_adapter` |
| Python | `>=3.10`; CI matrix 3.10 / 3.12 / 3.13 | verified on 3.10 and 3.12 (and 3.14) |
| lint | `ruff check src/ tests/`, pinned `>=0.15,<0.16` | passes clean |
| security | `bandit -r src/ -ll` | passes, exit 0 |
| coverage | `--cov=src/dsm`, `fail_under=75` | unaffected — not in the coverage source set |
| dependencies | explicit, minimal | **zero new dependencies** — stdlib only |
| licence | repo `LICENSE` | inherited; no third-party code vendored |

**No DARYL convention was weakened, and no existing check was relaxed or skipped.**

## Placement rationale

A top-level `hexashard/` directory was **not** used, despite that being where the work
currently sits in the source working tree. DARYL is a `src/`-layout project with
`[tool.setuptools.package-dir] "" = "src"`; a top-level package would not be
importable or installable the way `dsm` and `prl` are.

Core and Adapter are **sibling packages**, not nested, for two reasons: it matches the
existing `src/dsm` + `src/prl` shape, and it keeps the Core/Adapter boundary visible in
the tree rather than implying the Adapter is part of Core.

## Test results in DARYL

| Run | Result |
|---|---|
| baseline, `main` @ 990d378, before any change | 1,881 passed, **2 failed** |
| after migration | 1,996 passed, **1 failed** |
| HexaShard suites alone (3.12) | **114 passed** |
| HexaShard suites alone (3.10) | **114 passed** |

The delta is exactly **+113 tests** (68 Core + 34 Adapter + 12 gate regressions, less
one replaced immutability test file counted in both).

The remaining failure is `tests/prl_pkg/test_consultation_store.py` — a **pre-existing
flaky test on `main`**, unrelated to HexaShard, which also failed on the untouched
baseline. It was not touched and is not claimed as fixed.

## A regression this migration caused and fixed

DARYL already has `tests/fixtures/`. The first migration attempt kept the lab's
`fixtures/` directory name inside `tests/hexashard/`, which shadowed it and broke
`tests/integration/test_hash_parity.py` with
`ModuleNotFoundError: No module named 'fixtures.canonical_entry'`.

Caught by running the **full** suite rather than only the new tests. Fixed by renaming
to `hexashard_fixtures/` and `hexashard_adapter_fixtures/`.

## Packaging consequence — needs a human decision

`[tool.setuptools.packages.find] where = ["src"]` discovers packages automatically, so
`hexashard` and `hexashard_adapter` are now **included in the `daryl-dsm`
distribution**. The repository has a `publish-pypi.yml` workflow.

Nothing was published and no version was bumped, but **the next PyPI release of
`daryl-dsm` would ship HexaShard unless this is decided deliberately.** The options are
to accept it, or to add an explicit `exclude` to the packages configuration. This was
left as-is rather than changed silently — flagging it is the point.
