# HEXASHARD — PRE-GITHUB GATE

Independent technical gate on HexaShard Core v0.1 + Adapter v0.1 before entry into the
canonical DARYL repository.

## Verdict

> ### B — READY FOR DARYL BRANCH AFTER MINOR ADAPTER/DOC FIXES

The fixes were identified, classified, applied and regression-tested; the branch in
front of you is the post-fix state. **No Core semantic change was made or is needed.**

## Why B and not A

Four defects had to be fixed before this could responsibly be pushed:

1. **The Adapter package did not import** (F-01). `import hexashard_adapter` raised
   `ModuleNotFoundError`, and the CLI documented in its own docstring had never run.
   The 34 green tests were partly an artefact of `conftest.py` seeding `sys.path`.
2. **A repointed pin was reported as clean** (F-02). `Core.check_pins()` masks a stored
   `NEEDS_REVIEW`, so the structured `pin_warnings` channel was silently empty for a
   stale pinned invariant.
3. **Malformed provider replies raised `AttributeError`** (F-04) instead of a typed
   error, at the one boundary that handles untrusted third-party code.
4. **The provider endpoint scheme was unvalidated** (F-06) — `urlopen` would have
   honoured `file:`. This also **failed DARYL's existing bandit gate**, which the
   baseline passes.

None is architectural. All four are Adapter-side.

## Why not C, D, E, F or G

- **not D (Core issue)** — the Core reproduces completely: 68/68 tests and 20/20
  acceptance criteria on Python 3.10, 3.12 and 3.14, from a fresh extraction of the
  frozen archive.
- **not E (topology unclear)** — it very nearly was. Two different codebases are both
  called "Core v0.1". The ambiguity was resolved from `core_lock.py`,
  `CORE_MANIFEST.json` and a repository-wide import search: the Claude Core is
  canonical, the Cursor Core is an orphan nothing imports. Had that not resolved, the
  correct verdict would have been E.
- **not F (evidence does not support the architecture)** — the surviving architecture
  is *narrower* than the name suggests, and the evidence supports that narrow version.
  Hex agents, six-neighbour routing, packets-as-truth, spatial retrieval priors and DSM
  as working memory were all tested and rejected, and none of them is in this payload.
- **not G (inconclusive)** — every headline figure was independently reproduced.

## Independent reproduction

| Item | Result |
|---|---|
| Frozen archive SHA-256 | **matches** the reported value |
| Five Core working copies vs archive | **all byte-identical** |
| Core suite (3.10 / 3.12 / 3.14) | **68 / 68 / 68 passed** |
| Acceptance verifier | **20/20** on all three |
| MERIDIAN-9 | reproduced **field-for-field** |
| Adapter suite (3.10 / 3.12 / 3.14) | **34 / 34 / 34 passed** |
| Adapter smoke | reproduced (101,627 tokens, ~280x) |
| Paraphrase experiment | reproduced **bit-for-bit** |
| Core unchanged after Adapter suite | **yes** |
| After migration into DARYL | MERIDIAN-9 **still field-for-field identical** |

**§8 — did later experiments run against the same Core?** Yes, cryptographically. This
is the strongest single result in the body of work.

## Verdicts reviewed, not inherited

| Experiment | Recorded | This gate |
|---|---|---|
| Core acceptance | met | **confirmed** |
| Paraphrase | B — BM25 sufficient with caveats | **confirmed, caveats emphasised** (authority accuracy 0.286 under heavy paraphrase) |
| DSM partnership / namespace | D / C — DSM optional | **confirmed**, and nothing DSM-shaped is in the payload |
| Z-depth | B — Z supported, six-port not | **confirmed as directional**; small n |
| Spatial canvas | G — harmful as a retrieval prior | **confirmed as directional**; small n |
| Spatial ports | P-C — not a Core requirement | **confirmed**; the self-reported rounding artefact is real and correctly described |
| LIVE 001 | F — INCONCLUSIVE | **confirmed.** At 250k *both* arms scored 0/48 on HTTP 400s — credit exhaustion, not architecture. Rejecting the machine letter `A` was correct. |
| LIVE 001-L | B | **confirmed, narrowly.** Denominators, pairing and truncation verified fair; no successful-call-only bias. But n=1, one model, and it shows *equal* accuracy at ~1/58th the visible context — not better answers. |

## The §17 investigation

| Question | Answer |
|---|---|
| 1. Is the mutation real? | **Yes.** `handle_turn` increments the turn, records a hint, touches hexes, enforces budget and saves to disk. |
| 2. Intended? | **Yes**, and documented. |
| 3. Do repeated innocent questions accumulate noise? | **Bounded.** Identical questions de-duplicate (25 turns → +10 tokens). 120 distinct questions against an 800-token budget ended at 272 tokens. |
| 4. Can queries alter project context? | **Working state only.** Sources and pins are never altered; objective and summary do not drift. |
| 5. Does it affect session reset? | The state it advances **persists across reload**. |
| 6. Long-term drift? | Active-state tokens do **not** drift. **Epochs do** — 120 read-only questions caused 3 durable rotations. |
| 7. Is Adapter READ_ONLY enough? | **Yes.** Verified zero state change and **zero bytes written** over 30 turns. |
| 8. Can the Adapter avoid mutation without changing Core? | **Yes — already does**, via `Core.retrieve()`. |
| 9. Would fixing it invalidate prior evidence? | Not applicable — nothing was changed. |
| 10. Migration blocker? | **No.** Documented, with a working mitigation. |

The one substantive correction to the existing framing: the caveat is accurate, and the
durable consequence is **epoch advance**, not unbounded context growth.

## Release blockers

**None outstanding.** Three findings would require Core semantic changes (F-02's root
cause, F-03, F-05); all three are Class C, none was implemented, each is either
mitigated Adapter-side or documented in LIMITATIONS.

## Validation in DARYL

```
ruff check src/ tests/     -> All checks passed!
bandit -r src/ -ll         -> exit 0
pytest tests/              -> 1996 passed, 1 failed, 52 skipped
pytest tests/hexashard tests/hexashard_adapter  -> 114 passed (3.10 and 3.12)
```

Baseline on untouched `main` @ 990d378 was **1881 passed, 2 failed**. The single
remaining failure — `tests/prl_pkg/test_consultation_store.py` — is a **pre-existing
flake on `main`**, fails on the untouched baseline, was not touched, and is not claimed
as fixed. **Zero failures are attributable to HexaShard.**

One regression *was* introduced during migration and fixed before commit: the lab's
`fixtures/` directory name shadowed DARYL's existing `tests/fixtures/` and broke
`tests/integration/test_hash_parity.py`. Caught by running the full suite, not just the
new tests.

## What is deliberately not here

Roughly **460 MB** of research trees, raw provider logs, duplicate Core copies and the
orphaned Cursor Core. See DARYL_MIGRATION_MANIFEST.md.

## Requires a human decision

`packages.find` discovers `src/` automatically, so **HexaShard is now inside the
`daryl-dsm` distribution**. Nothing was published and no version bumped, but the next
PyPI release would ship it unless that is decided deliberately. Flagged rather than
silently changed.

## Stop

The branch is pushed and a draft PR is open. **Not merged.** No tag, no release, no
package published, no work started on v0.2. The human reviews next.
