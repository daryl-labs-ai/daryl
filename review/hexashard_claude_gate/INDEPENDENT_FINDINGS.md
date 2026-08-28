# INDEPENDENT_FINDINGS

Findings raised by this gate, not inherited from any prior audit. Each was
reproduced before being written down. Classification follows §9/§19.

| ID | Severity | Area | Summary |
|---|---|---|---|
| F-01 | SHOULD FIX BEFORE GITHUB | Adapter packaging | `import hexashard_adapter` fails cold; the documented CLI never ran |
| F-02 | SHOULD FIX BEFORE GITHUB | Adapter / pins | A pin repointed by supersession is reported as clean |
| F-03 | KNOWN LIMITATION | Adapter / Core | A provider failure still consumes a turn |
| F-04 | SHOULD FIX BEFORE GITHUB | Adapter / provider boundary | Malformed provider reply surfaces as `AttributeError` |
| F-05 | KNOWN LIMITATION (Core) | Core / aliasing | `handle_turn` returns live references into ActiveState |
| F-06 | SHOULD FIX BEFORE GITHUB | Adapter / security | Provider endpoint scheme unvalidated; also fails DARYL's bandit gate |
| F-07 | KNOWN LIMITATION | Retrieval | BM25 authority accuracy falls to 0.286 under paraphrase |
| F-08 | NON-ISSUE (documented) | Evidence | LIVE 001 supports no claim; LIVE 001-L is n=1 |
| F-09 | RESOLVED AT GATE | Topology | Two different codebases are both called "Core v0.1" |

---

## F-01 — the Adapter package did not import

`hexashard_adapter/context.py` imports `hexashard` at module scope, but the
`sys.path` insertion that makes `hexashard` findable lived in `adapter.py`, which
imports `context` first. The package therefore only imported under pytest, because
`tests/conftest.py` seeded `sys.path` before collection.

Observed directly:

```
$ python -c "import hexashard_adapter"
ModuleNotFoundError: No module named 'hexashard'

$ python -m hexashard_adapter --help        # the entrypoint in its own docstring
ModuleNotFoundError: No module named 'hexashard'
```

This matters beyond tidiness: the 34-test green result was partly an artefact of
test scaffolding, and the one documented user-facing entrypoint had never been
executed. This is exactly the "report-only acceptance" §15 warns about.

**Fixed by migration** — both packages are installed siblings under `src/`, so the
imports are ordinary. Locked down by `test_f01_*`, which shells out to a clean
interpreter and runs the CLI.

## F-02 — a repointed pin was reported as clean

`supersede()` correctly repoints a pin at the successor, keeps the old value, and
stamps the stored pin `NEEDS_REVIEW`. But `check_pins()` **re-resolves** the pin
against its *current* pointer, sees a CURRENT source, and returns `ACTIVE`:

```
stored pin:      ('P1.S0002', '6.1 TB', PinStatus.NEEDS_REVIEW)
check_pins():    (PinStatus.ACTIVE, 'grounded in a CURRENT source')
pin_warnings:    []
```

`handle_turn` builds `pin_warnings` from `check_pins()`, so the structured warning
channel reports nothing while the pin asserts `6.1 TB` and the source it cites says
`9.9 TB`. Calling `reconcile_pins()` does not change this.

Two things keep this from being a blocker. The model-visible block does carry the
stored status, and the correct source is retrieved alongside it:

```
CRITICAL PINS:
- downlink = 6.1 TB (source P1.S0002, status NEEDS_REVIEW)
...
[SOURCE P1.S0002 | CURRENT] Budget rev2
The downlink budget per pass is 9.9 TB.
```

So the contradiction is visible and labelled. The defect is that a *programmatic*
consumer of `pin_warnings` — the documented channel for exactly this — sees nothing.

The Core's own report claims "F1c — stale pins surface as warnings in the turn
context: pass". That is true for a pin left pointing at a superseded source, and
false for a pin the supersession repointed. The claim is narrower than it reads.

**Fixed Adapter-side, no Core change.** The Adapter derives warnings from
`active_pins` for any pin whose stored status is not `ACTIVE`.

## F-03 — a provider failure still consumes a turn

In NORMAL mode `handle_turn()` runs, advances state and saves *before* the provider
is called. If the provider then fails, the turn is spent and persisted with no
answer produced.

Not corruption, and not fixable without transactional turn semantics in Core, which
would be a Class C change. Documented, and pinned by a test so a future change to it
is deliberate. `READ_ONLY` mode does not have this behaviour.

## F-04 — malformed provider replies were untyped

A provider returning the wrong shape produced a bare `AttributeError` from inside
result assembly, which reads as an Adapter bug rather than a provider one. Providers
are ordinary third-party code. Now raises `MalformedProviderResponse`.

## F-05 — `handle_turn` returns live references into ActiveState

`response_context["active_pins"]`, `active_hex_refs` and `recent_decisions` are the
**same list objects** as Core's state, not copies:

```
rc["active_pins"] is p.state.active_pins    ->  True
rc["active_pins"].append({...})             ->  Core state polluted, and persisted
```

A caller editing the context it was handed corrupts Core state, and the corruption
survives the next `save()`.

The shipped Adapter never triggers this — `assemble()` copies at every boundary — so
this is latent, not live. A Core fix would be Class C. The Adapter now detaches the
context defensively, which closes the exposure without touching Core semantics.

## F-06 — unvalidated provider endpoint scheme

`config.endpoint` is caller-supplied and went straight to `urllib.request.urlopen`,
which honours `file:` and other local schemes — a provider endpoint could be turned
into a local file read. DARYL's own `bandit -r src/ -ll` flags this (B310) and
**exits 1**, so it would have failed CI. Baseline `bandit` on `src/dsm src/prl` exits
0, so the failure was entirely attributable to this payload.

Fixed with an explicit `http`/`https` allowlist rather than by silencing the check.

## F-07 — paraphrase weakness is real

Authority accuracy: 0.714 (light paraphrase) → 0.286 (medium and heavy). Retrieval
recall holds up much better than rank-1 authority selection. The mechanism is that
all CURRENT sources share one authority rank, so among CURRENT competitors the
ordering is pure BM25 overlap.

Verdict B stands, but "sufficient with caveats" should not be read as "solved".
Documented in LIMITATIONS. No embeddings were added, per scope.

## F-08 — what the live evidence can and cannot carry

LIVE 001 is inconclusive and supports nothing. LIVE 001-L is a single unreplicated
run of one local model. Neither licenses a general performance claim. The public
docs were written to this constraint.

## F-09 — the two-Core ambiguity

Resolved before migration; see EVIDENCE_INVENTORY.md. Had it not been resolvable
from `core_lock.py`, `CORE_MANIFEST.json` and an import search, the correct verdict
would have been **E — canonical artifact unclear**.

---

## Checked and found sound

Worth recording, because these are the places this kind of work usually fails:

- **Persistence is genuinely atomic.** `atomic_write_text` writes to a temp file in
  the same directory, `fsync`s it, `os.replace`s, then `fsync`s the directory. Not
  the usual naive `write_text`.
- **Repeated identical questions do not accumulate.** `add_hint` de-duplicates; 25
  identical turns moved active state by 10 tokens.
- **ActiveState stays bounded.** 120 distinct innocent questions against an 800-token
  budget ended at 272 tokens; `enforce_budget` trims hints first, as designed.
- **`READ_ONLY` is genuinely non-mutating.** 30 turns produced zero state change and
  **zero bytes written to disk**, verified by hashing the project directory.
- **Sources and pins are never touched by querying.** Only working state moves.
- **No credentials anywhere.** The live harness reads `ANTHROPIC_API_KEY` from the
  environment or the keychain and never persists it.
- **The Core is stdlib-only.** No vendor SDK, no DSM, verified by the architecture
  tests and an import audit.
- **Cursor's own evidence handling was honest.** It rejected its own machine-computed
  verdict `A` for LIVE 001 on denominator grounds, and self-reported a rounding
  artefact in the spatial-ports runner. Both hold up.
