# HEXASHARD_PACKAGING_DECISION

Final packaging gate: should HexaShard ship inside the `daryl-dsm` distribution?

> ## Verdict — B: EXCLUDE HEXASHARD FROM `daryl-dsm`
>
> HexaShard stays in the DARYL monorepo, developed and tested there. It is
> deliberately not part of the `daryl-dsm` distribution.

**Answer to the central question: NO.**

---

## 1. Packaging facts

I did not assume the answer. The repository settles it.

### DARYL is already a multi-distribution monorepo

Four distributions, each with its own `pyproject.toml`, its own name and its own
`src/` layout:

| Distribution | Location | Version | Ships |
|---|---|---|---|
| `daryl-dsm` | repo root | **1.0.2** | `dsm`, `prl` |
| `dsm-mcp` | `packages/dsm-mcp/` | 0.1.1 | MCP server integration |
| `dsm-primitives` | `packages/dsm-primitives/` | 0.1.0 | shared serialization/hashing/signing |
| `agent-mesh` | `agent-mesh/` | 0.1.0 | mesh runtime |

This is decisive. `daryl-dsm` is **not** the umbrella for the DARYL Python namespace —
if it were, `dsm-mcp`, `dsm-primitives` and `agent-mesh` would not exist as separate
distributions. DARYL's established convention is **narrow, purpose-scoped
distributions built from one monorepo**, and `dsm-primitives` documents that boundary
explicitly in its own description ("Shared … primitives for daryl-dsm and agent-mesh
(ADR-0002)").

### `daryl-dsm` is a cohesive DSM distribution, not a grab-bag

It ships two packages, and they are not unrelated:

```
prl -> dsm    13 files import dsm
dsm -> prl     0 files
```

PRL is a layer built **on** DSM. Both expose console scripts (`dsm`,
`dsm-serve-goose`, `daryl`), both are in the coverage source set, and the distribution
description is specifically about DSM: *"Deterministic Sharding Memory for AI agents —
append-only, hash-chained, tamper-evident event log."* The publish workflow's own
acceptance check is `import dsm; import dsm_primitives`.

So the existing contents are coherent and intentional. HexaShard is not part of that
unit.

### Discovery was unbounded

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

Every directory under `src/` is discovered automatically, so adding
`src/hexashard/` silently changed what a published `daryl-dsm` contains.

---

## 2. Wheel evidence

Built, not inferred. Both wheels built clean (a stale `build/lib` masked the first
attempt and was caught by comparing file lists rather than trusting the build log).

| Wheel | Top-level packages | Files |
|---|---|---|
| `main` @ 990d378 | `dsm`, `prl` | 164 |
| branch, before this change | `dsm`, `hexashard`, **`hexashard_adapter`**, `prl` | 186 |
| branch, after this change | `dsm`, `prl` | **164** |

**The PR wheel did contain HexaShard** — 22 module files, both Core and Adapter.

Installed-wheel behaviour after the change is identical to `main`:

```
dsm                  present
prl                  present
hexashard            ABSENT
hexashard_adapter    ABSENT
```

### §15 regression check — the real risk

| Check | Result |
|---|---|
| files on `main` missing after the change | **NONE** |
| files added versus `main` | **NONE** |
| entries removed by the change | 22, **all** `hexashard*` |
| non-HexaShard entries removed | **NONE** |

The corrected wheel's file list is **identical to main's**. Nothing pre-existing was
dropped.

### §25 security inspection

The wheel contains no research data, raw provider output, `.tar.gz` lab artifacts,
fixtures, local paths or credentials. (`dsm/attestation.py`, `dsm/ans/ans_test.py` and
`dsm/skills/browser/browser_test.py` match a naive "test" substring scan but are
pre-existing DSM modules, present on `main`.)

---

## 3. Dependency direction

| Direction | Result |
|---|---|
| HexaShard → DSM | **none** — zero imports |
| HexaShard → PRL | **none** |
| DSM → HexaShard | **none** |
| PRL → HexaShard | **none** |

Verified, not assumed, and consistent with the frozen architectural boundary: DSM is
optional for audit/provenance and is not HexaShard working memory.

**Packaging them together creates no code dependency, but it does create conceptual
coupling** — and that is precisely the problem. `pip install daryl-dsm` delivering an
experimental context runtime would imply a relationship the evidence says does not
exist. Reporting it separately, as required: the coupling risk here is reputational and
semantic, not technical.

---

## 4. User-facing consequence

Before this change, `pip install daryl-dsm` would have delivered HexaShard.

That is **ARCHITECTURALLY WRONG**, for three compounding reasons:

1. **It contradicts the stated boundary.** DSM and HexaShard were established as
   separate concerns, with HexaShard explicitly not requiring DSM.
2. **Maturity mismatch.** `daryl-dsm` is **1.0.2** — a stable, published distribution.
   HexaShard is **experimental v0.1** with documented limitations. Shipping v0.1 code
   inside a 1.0 distribution silently inherits a stability promise it cannot keep.
3. **It happened by accident.** No one chose it; unbounded `packages.find` chose it.
   That is the failure mode this gate exists to prevent.

A secondary hazard: the branch built a wheel with the **same version string, 1.0.2**,
but different contents than the released 1.0.2.

---

## 5. Namespace versus distribution

Kept distinct, as required:

- **Repository location** — `daryl-labs-ai/daryl`. HexaShard stays. Not in question.
- **Import namespace** — `hexashard`, `hexashard_adapter`, unchanged by this decision.
- **Distribution** — `daryl-dsm`. HexaShard leaves.

A package can live in the DARYL repo and namespace without belonging to the DSM
distribution. That is exactly the situation.

---

## 6. Options

| Option | Architecture | User clarity | CI/release complexity | Coupling risk | Recommendation |
|---|---|---|---|---|---|
| **A — inside `daryl-dsm`** | Wrong. Contradicts the four-distribution convention and puts v0.1 inside a 1.0 product | Poor — DSM users receive an unrelated experimental runtime | None added | **High** — permanent conceptual coupling, silently created | **Reject** |
| **B — monorepo, excluded** | Correct. Matches how `dsm-mcp` / `dsm-primitives` / `agent-mesh` already work | Good — DSM ships DSM; HexaShard is source-available and tested | None — no new job, no new workflow | **None** | **ADOPT** |
| **C — extra `daryl-dsm[hexashard]`** | Doesn't work. **Extras gate dependencies, not module inclusion** — the modules would still ship in the wheel. Delivering this genuinely requires a separate distribution, i.e. option D | Misleading — implies opt-in that isn't real | Adds an extra that does nothing useful | High — false sense of separation | **Reject — technically unsound** |
| **D — future `daryl-hexashard`** | Correct long-term shape *if* HexaShard is ever published | Good | Adds a distribution, workflow job and version line | None | **Not yet** — identical action today; premature to commit to a release nobody has decided on |

B and D require the **same change today**. They differ only in whether a future
standalone release is declared. That is a product decision, not a packaging one, so
this gate makes the correction and does not presume the release.

---

## 7. The change

One addition to `pyproject.toml`, plus one line keeping tests robust:

```toml
[tool.setuptools.packages.find]
where = ["src"]
# The daryl-dsm distribution ships DSM and the PRL layer built on it, and
# nothing else. HexaShard is developed and tested in this monorepo but is a
# separate, experimental concern with no dependency in either direction, so it
# is deliberately not part of this distribution. Listed positively rather than
# by exclusion so a new package under src/ cannot be published by accident.
include = ["dsm*", "prl*"]
```

```toml
# "src" keeps the source tree importable for tests independently of how the
# editable install happens to expose it, now that packages.find is scoped.
pythonpath = [".", "src"]
```

**Why `include` rather than `exclude`:** an allowlist states the distribution's
contents positively and closes the whole bug class — the next package added under
`src/` cannot leak into a release either. Same one-line cost.

**Why the `pythonpath` line:** editable installs of this layout emit a `.pth` holding
the whole `src/` directory, so `import hexashard` keeps working from source even
though it is no longer a declared package — verified in a clean CI-equivalent
environment. But that is a setuptools *strategy* detail that could change with a
future version. Naming `src` explicitly makes the test import path independent of it.
Confirmed not to alter resolution: the editable install already points at the same
`src/`.

Core semantics untouched. Adapter semantics untouched. No renames, no moved code, no
new build tooling, no workspace machinery.

---

## 8. Tests

Run in a **fresh** CI-equivalent environment built by `scripts/setup_dev_env.sh`:

```
ruff check src/ tests/                            All checks passed!
bandit -r src/ -ll                                exit 0
pytest tests/hexashard tests/hexashard_adapter    114 passed   (3.10 and 3.12)
pytest tests/                                     1995 passed, 2 failed, 52 skipped
python -m build --wheel                           OK
```

The two failures are the pre-existing flake in `tests/prl_pkg/test_consultation_store.py`,
which the untouched `main` baseline also produced (2 failed there). Not touched, not
claimed as fixed. **CI was not weakened.**

Developer workflow is unchanged: `pip install -e ".[dev]"` then
`pytest tests/hexashard tests/hexashard_adapter`.

---

## 9. Required answers

1. **Is `daryl-dsm` DSM-specific or an umbrella?** DSM-specific — it ships DSM plus
   the PRL layer built on it. The monorepo publishes three other distributions
   alongside it.
2. **Did the PR wheel contain HexaShard?** **Yes** — 22 module files, Core and Adapter.
3. **Does HexaShard depend on DSM?** No. Zero imports.
4. **Does DSM depend on HexaShard?** No. Zero imports.
5. **Would `pip install daryl-dsm` shipping HexaShard be honest?** **No.** It would
   imply a relationship that does not exist and put experimental v0.1 code inside a
   1.0.2 distribution.
6. **Do Core and Adapter belong in the same distribution?** Yes — but that question is
   moot today, since neither is distributed. They share an import namespace, the
   Adapter is useless without Core, and both are stdlib-only with no dependency
   footprint. If HexaShard is ever published, the Adapter is small enough and
   dependency-free enough to ship alongside Core rather than as a second artifact —
   though its provider surface is the least mature part and could reasonably be held
   back. Not decided here.
7. **Smallest clean packaging boundary today?** `daryl-dsm` = `dsm` + `prl`.
   HexaShard = repo-resident, source-available, not distributed.
8. **Does this affect existing DARYL consumers?** **No.** The resulting wheel's file
   list is identical to `main`'s. Consumers of `daryl-dsm` 1.0.2 see no change.
9. **A future standalone HexaShard release?** If ever, `daryl-hexashard` built from
   this monorepo, following the `dsm-mcp` pattern: its own `pyproject.toml`, its own
   version line, its own publish job. It must not be folded into `daryl-dsm` later
   either. **Nothing has been created, versioned or tagged for this.**
10. **Is PR #137 safe to merge after this decision?** From a packaging standpoint,
    yes — the accidental inclusion is closed, no existing consumer is affected, and the
    boundary is now explicit and self-defending. Merge remains a human decision; the
    architectural and evidentiary review is recorded separately in this directory.

---

## 10. Status

| | |
|---|---|
| Branch | `feat/hexashard-v01` |
| Packaging commit | `1242f5b` |
| Draft PR | [#137](https://github.com/daryl-labs-ai/daryl/pull/137) — updated, still **draft** |
| `main` | untouched at `990d378` |
| Published | nothing — no tag, no release, no PyPI upload, no version bump |
