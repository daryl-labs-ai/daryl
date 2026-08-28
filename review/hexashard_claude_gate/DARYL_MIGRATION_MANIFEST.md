# DARYL_MIGRATION_MANIFEST

Every candidate file, its digest at source, its destination and the action taken.

## Migrated

| Source | SHA-256 (first 16) | Destination | Action | Reason |
|---|---|---|---|---|
| `Core/hexashard/__init__.py` | `92a1a3582093b3d6` | `src/hexashard/__init__.py` | COPY | byte-identical to frozen v0.1 |
| `Core/hexashard/context.py` | `af4f13280bad5af3` | `src/hexashard/context.py` | COPY | byte-identical to frozen v0.1 |
| `Core/hexashard/ids.py` | `84fcbbd17b18f5bb` | `src/hexashard/ids.py` | COPY | byte-identical to frozen v0.1 |
| `Core/hexashard/metrics.py` | `ff9867adb456b9ea` | `src/hexashard/metrics.py` | COPY | byte-identical to frozen v0.1 |
| `Core/hexashard/models.py` | `e695bc105aaed02a` | `src/hexashard/models.py` | COPY | byte-identical to frozen v0.1 |
| `Core/hexashard/pins.py` | `eae9fcd1dec550cf` | `src/hexashard/pins.py` | COPY | byte-identical to frozen v0.1 |
| `Core/hexashard/project.py` | `ddccda801fdaab2b` | `src/hexashard/project.py` | COPY | byte-identical to frozen v0.1 |
| `Core/hexashard/providers.py` | `70491fd864cf802d` | `src/hexashard/providers.py` | COPY | byte-identical to frozen v0.1 |
| `Core/hexashard/retrieval.py` | `2961e1cb51d883bd` | `src/hexashard/retrieval.py` | COPY | byte-identical to frozen v0.1 |
| `Core/hexashard/store.py` | `4922d905c54dbf59` | `src/hexashard/store.py` | COPY | byte-identical to frozen v0.1 |
| `Core/hexashard/tokens.py` | `2acbc54990ef7be7` | `src/hexashard/tokens.py` | COPY | byte-identical to frozen v0.1 |
| `Core/hexashard/trust.py` | `3595658a80b31c0e` | `src/hexashard/trust.py` | COPY | byte-identical to frozen v0.1 |
| `Adapter/hexashard_adapter/__init__.py` | `a0600d3e67427dc6` | `src/hexashard_adapter/__init__.py` | COPY_AFTER_FIX | Class A fix — see CORRECTIONS.md |
| `Adapter/hexashard_adapter/__main__.py` | `3920f8543bcfdc05` | `src/hexashard_adapter/__main__.py` | COPY | unchanged |
| `Adapter/hexashard_adapter/adapter.py` | `b7437999d5a1bd33` | `src/hexashard_adapter/adapter.py` | COPY_AFTER_FIX | Class A fix — see CORRECTIONS.md |
| `Adapter/hexashard_adapter/config.py` | `5fd4599f01290e3b` | `src/hexashard_adapter/config.py` | COPY | unchanged |
| `Adapter/hexashard_adapter/context.py` | `a2d94d13a33ba1b0` | `src/hexashard_adapter/context.py` | COPY | unchanged |
| `Adapter/hexashard_adapter/core_lock.py` | `adc0345371314704` | `src/hexashard_adapter/core_lock.py` | COPY_AFTER_FIX | Class A fix — see CORRECTIONS.md |
| `Adapter/hexashard_adapter/errors.py` | `100e875542d22d06` | `src/hexashard_adapter/errors.py` | COPY_AFTER_FIX | Class A fix — see CORRECTIONS.md |
| `Adapter/hexashard_adapter/metrics.py` | `d9af8e70f38ddb83` | `src/hexashard_adapter/metrics.py` | COPY | unchanged |
| `Adapter/hexashard_adapter/models.py` | `cca5967a6ec8bbf8` | `src/hexashard_adapter/models.py` | COPY | unchanged |
| `Adapter/hexashard_adapter/provider.py` | `a7b544ab21495451` | `src/hexashard_adapter/provider.py` | COPY_AFTER_FIX | Class A fix — see CORRECTIONS.md |
| `Core/tests/test_architecture.py` | `930a44ac0e9328b1` | `tests/hexashard/test_architecture.py` | COPY_AFTER_FIX | Class B — path rebase |
| `Core/tests/test_core.py` | `239cdecace445d2d` | `tests/hexashard/test_core.py` | COPY_AFTER_FIX | Class B — path rebase |
| `Core/tests/test_failure_modes.py` | `e187314f3c94bc2f` | `tests/hexashard/test_failure_modes.py` | COPY | unchanged |
| `Core/tests/test_integration_long_project.py` | `627ebf138bfbb0ae` | `tests/hexashard/test_integration_long_project.py` | COPY_AFTER_FIX | Class B — path rebase |
| `Core/tests/test_regressions.py` | `e5293cbf04abe5bb` | `tests/hexashard/test_regressions.py` | COPY | unchanged |
| `Core/tests/conftest.py` | `f16e9ec4835df2a2` | `tests/hexashard/conftest.py` | COPY_AFTER_FIX | Class B — path rebase + frozen-Core assertion |
| `Core/fixtures/FIXTURE_LOCK.json` | `3bf4f1e1263baa37` | `tests/hexashard/hexashard_fixtures/FIXTURE_LOCK.json` | COPY | renamed dir — DARYL already has tests/fixtures/ |
| `Core/fixtures/synthetic_project.py` | `57746ae88dd05241` | `tests/hexashard/hexashard_fixtures/synthetic_project.py` | COPY | renamed dir — DARYL already has tests/fixtures/ |
| `Adapter/tests/test_adapter.py` | `51bf3143f5223cb5` | `tests/hexashard_adapter/test_adapter.py` | COPY_AFTER_FIX | Class B — rewritten for in-repo Core identity |
| `Adapter/tests/test_core_immutability.py` | `fecb9c994720aef2` | `tests/hexashard_adapter/test_core_immutability.py` | COPY_AFTER_FIX | Class B — rewritten for in-repo Core identity |
| `Adapter/tests/test_failures.py` | `19cdb08caac501b4` | `tests/hexashard_adapter/test_failures.py` | COPY | unchanged |
| `Adapter/tests/test_smoke.py` | `a664ca2bf9784e46` | `tests/hexashard_adapter/test_smoke.py` | COPY_AFTER_FIX | Class B — rewritten for in-repo Core identity |
| `Adapter/fixtures/smoke.py` | `402d5da98a660a33` | `tests/hexashard_adapter/hexashard_adapter_fixtures/smoke.py` | COPY | renamed dir |
| `Core/integration_results.json` | `94743a6bbbb8d67a` | `docs/hexashard/evidence/core_integration_results.json` | COPY | frozen recorded run |
| `Adapter/results/smoke.json` | `8808b1cfde03f407` | `docs/hexashard/evidence/adapter_smoke.json` | COPY | frozen recorded run |

## Not migrated

| Artifact | Action | Reason |
|---|---|---|
| `hexashard/` (repo root) — Cursor Core v0.1 | EXCLUDE | Orphaned parallel build. No downstream lab imports it. Superseded by the Claude Core. |
| `research/hexashard_adapter_v01/fixtures/CORE_MANIFEST.json` | EXCLUDE | Contains an absolute `/Users/<user>/…` path. Superseded by digests in `core_lock.py`. |
| `research/hexashard_core_v01_claude.tar.gz` | EXCLUDE | 72 KB binary; also matched by `.gitignore` `*.tar.gz`. Its digest is pinned in `core_lock.py`. |
| `research/hexashard_core_v01_audit/` (29 MB) | DOC_SUMMARY | Three duplicate Core copies + probes. Summarised in EVIDENCE.md. |
| `research/hexashard_cursor_lab/` (41 MB) | DOC_SUMMARY | Original replication lab. Verdict summarised. |
| `research/hexashard_dsm_partnership/` (11 MB) | DOC_SUMMARY | Includes DSM stores. Verdict summarised. |
| `research/hexashard_live_llm_001/raw/` | DOC_SUMMARY | Raw provider call logs. Verdict INCONCLUSIVE; summarised, not shipped. |
| `research/hexashard_live_llm_001_local/raw/` | DOC_SUMMARY | 240 raw rows incl. local `/var/folders/...` paths. Table summarised. |
| `research/hexashard_zdepth_experiment/` (1.1 MB) | DOC_SUMMARY | Retains a Core copy. Verdict summarised. |
| `research/hexashard_spatial_canvas/`, `hexashard_spatial_ports/` | DOC_SUMMARY | Summarised in ARCHITECTURE.md ('tested and rejected'). |
| `research/hexashard_core_v01_paraphrase/` | DOC_SUMMARY | Reproduced bit-for-bit at the gate; table in EVIDENCE.md. |
| `research/hexashard_dsm_namespace_test/` | DOC_SUMMARY | Verdict summarised. |
| `research/{symbolic,audio,visual}_memory_lab/`, `warm_selector_lab/`, others (~380 MB) | EXCLUDE | Unrelated or superseded research trees. |
| `.venv/`, `__pycache__/`, `.pytest_cache/` | EXCLUDE | Build and environment artifacts. |

## Total excluded

Roughly **460 MB** of research trees stayed out. What shipped is the runtime, its
tests, and a documented evidence summary — no raw provider logs, no duplicate Core
copies, no absolute paths, no binaries.
