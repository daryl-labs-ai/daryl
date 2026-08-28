# CORRECTIONS

Every change made to the payload, classified per §19. **No Class C change was made.
Core semantics are untouched and the Core modules are byte-identical.**

## Class A — Adapter-only

### A-1 — Core imported as an installed package (F-01)
- **File:** `src/hexashard_adapter/adapter.py`, `src/hexashard_adapter/__init__.py`
- **Patch:** removed `ensure_core_on_path()` and the deferred-import dance; `hexashard`
  is now imported normally at module top.
- **Behaviour changed:** the package imports without test scaffolding; the CLI runs.
- **Regression test:** `test_f01_adapter_imports_without_path_scaffolding`,
  `test_f01_cli_entrypoint_runs`
- **Impact on past evidence:** none. No runtime code path changed.

### A-2 — Core identity re-expressed for in-repo layout
- **File:** `src/hexashard_adapter/core_lock.py`
- **Patch:** rewritten. The lab version hashed a frozen tree at an absolute path
  outside the package. In-repo it pins the **per-module digests of the frozen v0.1
  Core** and compares them against the installed package.
- **Behaviour changed:** the guarantee is preserved and now travels with the repo;
  it no longer depends on a sibling directory existing on disk.
- **Regression test:** `tests/hexashard_adapter/test_core_immutability.py`, including
  a tamper-detection test.
- **Impact on past evidence:** none. `ARCHIVE_SHA256` and the frozen distribution
  tree digest are retained verbatim for provenance.

### A-3 — repointed pins surfaced (F-02)
- **File:** `src/hexashard_adapter/adapter.py` (`_harden_context`)
- **Patch:** the Adapter adds a warning for any `active_pins` entry whose stored
  status is not `ACTIVE` and which Core did not already flag.
- **Behaviour changed:** `ChatTurnResult.pin_warnings` is no longer empty for a pin
  that supersession repointed. Healthy pins still produce no warning.
- **Regression test:** `test_f02_repointed_pin_is_surfaced_as_a_warning`,
  `test_f02_healthy_pin_produces_no_warning`
- **Impact on past evidence:** none. Additive; Core's own `pin_warnings` is untouched
  and no experiment asserted an empty warning list.

### A-4 — turn context detached from Core state (F-05)
- **File:** `src/hexashard_adapter/adapter.py` (`_harden_context`)
- **Patch:** copies the list-valued keys Core returns by reference.
- **Behaviour changed:** a caller mutating the returned context can no longer corrupt
  Core state.
- **Regression test:** `test_f05_caller_cannot_mutate_core_state_through_the_turn_context`
- **Impact on past evidence:** none. `assemble()` already copied, so no measured path
  changes.

### A-5 — typed error for malformed provider replies (F-04)
- **File:** `src/hexashard_adapter/adapter.py`, `src/hexashard_adapter/errors.py`
- **Patch:** added `MalformedProviderResponse` and a shape check on the provider's
  return value.
- **Regression test:** `test_f04_malformed_provider_reply_raises_typed_error`,
  `test_f04_non_string_text_raises_typed_error`
- **Impact on past evidence:** none. Conformant providers are unaffected.

### A-6 — provider endpoint scheme allowlist (F-06)
- **File:** `src/hexashard_adapter/provider.py`
- **Patch:** `_require_http_endpoint()` rejects anything that is not `http`/`https`
  before `urlopen`. Two narrowly-scoped `# nosec B310` markers point at that guard.
- **Behaviour changed:** a `file:`/`ftp:` endpoint now raises
  `InvalidProviderConfiguration` instead of being opened.
- **Regression test:** `test_f06_non_http_provider_endpoint_is_rejected`
- **Impact on past evidence:** none. The endpoint used in every experiment was
  `http://127.0.0.1:11434/api/generate`.
- **Note:** this was required to pass DARYL's existing `bandit -r src/ -ll` gate. The
  check was fixed, not weakened or skipped.

## Class B — documentation / tests / migration compatibility

### B-1 — test path assumptions rebased
- **Files:** `tests/hexashard/test_architecture.py`, `test_core.py`,
  `test_integration_long_project.py`, `tests/hexashard_adapter/test_adapter.py`,
  `test_smoke.py`
- **Patch:** five sites assumed `tests/` sat beside the package. They now resolve the
  installed package. Left unfixed, `test_architecture.py` would have scanned its own
  test directory and the boundary assertions would have been meaningless.
- **Note:** the Core conftest deliberately does **not** import `hexashard_adapter`.
  Core must not depend on the Adapter, even in tests; Core immutability is asserted
  by the Adapter suite, which is the layer that owns that guarantee.
- **Impact on past evidence:** none — verified by bit-identical MERIDIAN-9 output.

### B-2 — measurement artifacts write to scratch, not the source tree
- **Files:** `tests/hexashard/test_integration_long_project.py`,
  `tests/hexashard_adapter/test_smoke.py`
- **Patch:** results go to `$HEXASHARD_ARTIFACTS_DIR` or the system temp directory.
  The recorded v0.1 runs are frozen under `docs/hexashard/evidence/`.
- **Rationale:** CI must not dirty the working tree.

### B-3 — fixture packages renamed to avoid a collision
- **Patch:** `fixtures/` → `hexashard_fixtures/` and `hexashard_adapter_fixtures/`.
- **Rationale:** **DARYL already has `tests/fixtures/`.** The original name shadowed
  it and broke `tests/integration/test_hash_parity.py`
  (`ModuleNotFoundError: fixtures.canonical_entry`). Caught by running the full suite.

### B-4 — absolute local path removed
- **Patch:** `fixtures/CORE_MANIFEST.json` was **excluded**; its `core_root` field
  held `/Users/<user>/…`. Its content is superseded by the digests embedded in
  `core_lock.py`.

### B-5 — `integration` marker registered
- **File:** `pyproject.toml`
- **Patch:** added `markers = ["integration: ..."]` under `[tool.pytest.ini_options]`.
- **Rationale:** the migrated suite uses `@pytest.mark.integration`; unregistered
  marks warn. No existing configuration was altered.

## Class C — NOT IMPLEMENTED

Two findings would need Core semantic changes. Both are **documented and left alone**:

| Finding | Core change that would be required |
|---|---|
| F-02 | `check_pins`/`resolve` honouring the stored pin status |
| F-05 | `handle_turn` returning copies instead of live references |
| F-03 | transactional turn semantics |

Each is mitigated Adapter-side or documented in LIMITATIONS. **Migration is not
blocked by any of them.**
