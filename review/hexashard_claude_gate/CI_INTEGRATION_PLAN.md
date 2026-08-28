# CI_INTEGRATION_PLAN

**No new CI universe. No workflow file was added or modified.**

HexaShard runs under DARYL's existing `.github/workflows/ci.yml` unchanged, because it
was placed where the existing steps already look:

| Existing CI step | Picks HexaShard up because |
|---|---|
| `ruff check src/ tests/` | code is under `src/` and `tests/` |
| `bandit -r src/ -ll` | packages are under `src/` |
| `pytest tests/ --cov=src/dsm` | suites are under `tests/`, and `testpaths=["tests"]` |
| matrix 3.10 / 3.12 / 3.13 | Core and Adapter verified on 3.10 and 3.12 |

## Verified locally with the CI commands

```
ruff check src/ tests/            -> All checks passed!
bandit -r src/ -ll                -> exit 0
pytest tests/                     -> 1996 passed, 1 pre-existing flake
pytest tests/hexashard tests/hexashard_adapter  -> 114 passed (3.10 and 3.12)
```

## Runtime and dependency impact

- **Zero new dependencies.** Core and Adapter are standard library only.
- Suite runtime ≈ **2.4 s** for all 114 tests.
- Coverage thresholds are unaffected: `--cov=src/dsm` does not measure these packages,
  so `fail_under=75` cannot regress because of them.

## One pyproject change

`markers = ["integration: ..."]` was added under `[tool.pytest.ini_options]` so the
migrated `@pytest.mark.integration` does not emit an unknown-mark warning. No existing
setting was altered.

## Test artifacts

The Core integration and Adapter smoke tests record measurements. They write to
`$HEXASHARD_ARTIFACTS_DIR`, defaulting to the system temp directory, so CI never
dirties the working tree. The frozen v0.1 runs are committed under
`docs/hexashard/evidence/` for comparison.
