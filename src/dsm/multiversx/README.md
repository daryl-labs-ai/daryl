# `dsm.multiversx` — MultiversX anchor backend for Daryl's DSM

Scaffold of the adapter that anchors DSM hash-chained logs to the MultiversX
blockchain across the Andromeda → Supernova transition window.

**Status: scaffold only.** Every function raises `NotImplementedError`. Every
test file is guarded by `pytestmark = pytest.mark.skip(...)`. The scaffold is
meant to be validated for architecture and implementability before any
implementation PR lands.

---

## What this package is

A strictly-additive layer above the frozen DSM kernel (`src/dsm/core/`). It
provides:

- **Regime detection** (`regime.py`) — reads `erd_round_duration` from the
  MultiversX Gateway's `/network/config` to decide whether the network is in
  Andromeda (6 s rounds, `inclusion ≡ execution`) or Supernova (600 ms
  rounds, `inclusion ≠ execution`, `ExecutionResult` notarized in a later
  header).
- **Payload anchor builder** (`payload.py`) — DSM01 binary format, encoded
  into the `data` field of a self-addressed EGLD transfer. No smart contract
  required in V1.
- **Three-stage state machine** (`state_machine.py`) — pure function mapping
  (state, event, regime) → (new_state, entry_to_emit). No I/O.
- **Chain watcher** (`watcher.py`) — WebSocket primary, polling fallback.
  Dual-schema reader handles both legacy (`rootHash`/`stateRootHash`) and
  Supernova (`lastExecutionResult`) block shapes during the compatibility
  window.
- **Backend** (`backend.py`) — `MultiversXAnchorBackend` satisfying the
  `AnchorBackend` ABC.
- **Audit CLI** (`audit.py`) — `dsm verify --mvx` regime-aware verification.

## What this package is not

- **Not a kernel change.** `src/dsm/core/` is untouched. The freeze is
  respected.
- **Not a smart contract deployment.** That's V2 (registry contract,
  Merkle batching, cross-agent P6). V1 is payload-only.
- **Not cross-shard-aware.** V1 anchors are always intra-shard
  (sender ≡ receiver). V2 adds cross-shard for P6 receipts.
- **Not ready to run.** Every function raises `NotImplementedError`.

---

## Minimal change required in `src/dsm/anchor.py`

This scaffold defines the `AnchorBackend` ABC in a **separate module**
(`src/dsm/anchor_backend.py`) so that the existing `anchor.py` can adopt it
with a two-line change, in a separate PR after the scaffold is validated:

```diff
--- a/src/dsm/anchor.py
+++ b/src/dsm/anchor.py
@@
 # ... existing imports and P4 pre-commitment logic ...
+from dsm.anchor_backend import AnchorBackend
@@
 class Anchor:
     # ... existing methods ...
+
+    def with_backend(self, backend: AnchorBackend) -> "Anchor":
+        """Register an external anchoring backend (e.g. MultiversX).
+
+        Until a backend is registered, Anchor behaves as before: local
+        pre-commitment only, no external witness. With a backend
+        registered, calls to anchor(shard_id) delegate to
+        backend.submit()/watch()/capabilities() per the three-stage flow
+        described in dsm/multiversx/SPEC.md.
+        """
+        self._backend = backend
+        return self
```

Nothing else in `anchor.py` changes in V0 or V1. Kernel untouched.
Existing tests continue to pass.

---

## Reference documents

- **EXECUTIVE.md** — 1-page thesis; go/no-go gates.
- **SPEC.md** — full technical specification (13 sections, failure matrix,
  schemas, dual-schema reader, operator UX vs audit semantics).
- **BACKLOG.md** — V0/V1/V2 task list, each with module/deps/risk/tests/
  acceptance criteria.

Every `TODO[VX-YY]` comment in this scaffold is traceable to a task ID in
`BACKLOG.md`.

## Module → Backlog ID map

| File | Primary task IDs |
|---|---|
| `schemas.py` | V0-01 |
| `payload.py` | V0-02 |
| `state_machine.py` | V0-03 |
| `regime.py` | V0-04 |
| `errors.py` | V0-05 |
| `backend.py` | V0-06, V1-03, V1-21 |
| `anchor_backend.py` | V0-07 |
| `config.py` | V0-08 |
| `client.py` | V1-01, V1-02 |
| `watcher.py` | V1-05, V1-06, V1-07, V1-08 |
| `audit.py` | V1-20 |

## Test → Failure matrix map

| Test file | Matrix row | Notes |
|---|---|---|
| `test_payload_codec.py` | — | V0-02 pure codec |
| `test_state_machine.py` | — | V0-03 pure state machine |
| `test_regime_detection.py` | F10 | includes Phase A edge case |
| `test_dual_schema_reader.py` | F5 | compatibility window |
| `test_f2_execution_fail.py` | F2 | the critical correctness test |
| `test_audit_cli.py` | — | regime-aware audit semantics |

Additional test files will be added in implementation PRs per BACKLOG.md
V1.C, V1.D.

## Validation step

Before any implementation PR:

```bash
pip install -e .[dev]
# Static validation: every file parses.
python -m py_compile src/dsm/multiversx/*.py src/dsm/anchor_backend.py
# Test discovery: every skipped test is discoverable.
python -m pytest tests/multiversx/ --collect-only
```

Both commands should succeed with zero errors. Tests collect but all skip
(`reason="V0-XX scaffold: ..."`).

## Implementation order

Follow BACKLOG.md strictly. V0 tasks are tightly coupled; do V0-01 through
V0-06 sequentially. V1.C rows (failure matrix coverage) can be parallelized
once V1.A and V1.B are in place. Do not jump ahead to V1.E (Devnet / Battle
Net) without V1.C passing locally.
