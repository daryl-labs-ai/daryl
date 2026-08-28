# HexaShard Repository Boundary — Freeze Record

Documentation and a mechanical guard. **No production semantics changed.**

| | |
|---|---|
| Base | `main @ 975092f95116714eaf9066b35fe3e2e2c890152a` |
| Branch | `docs/hexashard-repository-boundary` |
| Verdict | **C — keep temporarily, split on a defined trigger**, frozen as ACCEPTED |
| ADR | `docs/architecture/ADR-HEXASHARD-0001-repository-boundary.md` |
| Guard | `scripts/forbid_cross_boundary_imports.py` |
| Guard tests | `tests/test_forbid_cross_boundary_imports.py` (23) |
| CI | step added to `.github/workflows/ci.yml` |

## Verified coupling — measured, not assumed

Against `main @ 975092f` before the ADR was written:

| Direction | Result |
|---|---|
| `hexashard`, `hexashard_adapter` → `dsm`, `prl` | **0 imports** |
| `dsm`, `prl` → `hexashard`, `hexashard_adapter` | **0 imports** |
| `hexashard` mentioned anywhere in `src/dsm`, `src/prl` | **0 files** |
| `dsm`/`prl` mentioned anywhere in the HexaShard trees | **0 files** |

Coupling is zero in both directions, including in prose. Every other fact the
brief expected was also confirmed: Core frozen at `5b6a78e5…`, Adapter and an
8-verb CLI present, Product Seam v0.1.1 merged, HexaShard absent from the
`daryl-dsm` wheel, and **no** standalone HexaShard distribution, release, tag or
repository.

Organization repositories confirmed present: `daryl`, `daryl-mecalabs`,
`dsm-claude-code`, `dsm-grounding`, `dsm-unsloth`. No `daryl-hexashard` exists.

**Nothing in the reviewed assumptions was contradicted by the repository.**

## Guard design

Follows the house pattern set by `scripts/forbid_storage_access.py`: AST parsing,
`--root`, exit codes 0/1/2, a sibling test file. Two deliberate differences,
documented in the script:

- **No allowlist, no tracked-debt list, no per-line escape hatch.** This is a hard
  boundary rather than a migration, so an exception is a repository-architecture
  decision and belongs in a new ADR — not in a list at the top of a lint.
- **`TYPE_CHECKING` imports are not exempt.** The sibling script exempts them
  because they are not a runtime access. Here a type-only import still means the
  package cannot move to its own repository alone, which is precisely the
  coupling being prevented.

Only production trees under `src/` are scanned; tests may legitimately import
both sides, and this guard's own test does.

## Positive result

```
$ python scripts/forbid_cross_boundary_imports.py
OK: 186 files scanned under src/, no cross-boundary imports
    (src/dsm, src/hexashard, src/hexashard_adapter, src/prl).
exit 0
```

## Failure injection — both directions proven

Disposable local mutations, reverted immediately. Nothing artificial was
committed.

**HexaShard → DSM.** Injected `from dsm.core import storage` into
`src/hexashard/tokens.py`:

```
FAIL: 1 cross-boundary import(s):
[FORBID_CROSS_BOUNDARY] src/hexashard/tokens.py:15:0
  -> from dsm.core import storage
  reason: src/hexashard must not import dsm
```

**DSM → HexaShard.** Injected `import hexashard_adapter` into `src/dsm/lanes.py`:

```
exit=1
FAIL: 1 cross-boundary import(s):
[FORBID_CROSS_BOUNDARY] src/dsm/lanes.py:1:0
  -> import hexashard_adapter
  reason: src/dsm must not import hexashard_adapter
```

Injection 1 touched a **Core** module. After reverting, the Core digest was
re-verified as `5b6a78e5…` and `git status src/` was clean, confirming the frozen
Core survived the exercise untouched.

Both directions are also asserted permanently in
`tests/test_forbid_cross_boundary_imports.py`, which additionally pins the edges:
`TYPE_CHECKING` not exempt, relative imports allowed, comments and strings
ignored, `dsm_primitives` not a false positive, and `tests/` and `scripts/` out of
scope.

## Gate results

| | |
|---|---|
| HexaShard suites | **159 passed** |
| boundary + storage guards | **53 passed** |
| full DARYL suite | **2063 passed**, 2 failed, 52 skipped |
| ruff | All checks passed |
| bandit | exit 0 |
| `forbid_storage_access.py` | OK — 510 files, unaffected |
| Core digest before / after | `5b6a78e5…` / `5b6a78e5…` — **unchanged** |
| `daryl-dsm` wheel | `dsm` + `prl`, 164 files, **identical to the pre-HexaShard wheel** |

The 2 failures are the known pre-existing flake in
`tests/prl_pkg/test_consultation_store.py`, unrelated to this change and present
on `main` before it. Test count rose by exactly the 23 guard tests.

## Scope

Changed: one ADR, two documentation pointers, one guard script, one test file,
one CI step.

Not changed: HexaShard Core, Adapter, retrieval, provider behaviour, persistence,
DSM, PRL, packaging semantics.
