# `proof/` — the double replay of the pack composition law

This directory holds the evidence produced while testing whether ADR-PACK-0001 and ADR-PRL-0014
determine a resolver, rather than merely describe one. Nothing in it is normative. The ADRs, the two
schemas, the example packs, the compatibility matrix and `resolution-vectors.v0.1.json` are the
specification; everything here is a measurement taken against it, and no measurement was ever allowed
to change what it measures.

Both ADRs remain `Proposed`. `CAPABILITY_REGISTER.md` is unchanged. Nothing has been pushed.

## What is here

| path | what it is |
|---|---|
| `REPLAY-ENVELOPE.md` | the normative result format both implementations emit |
| `replay_a.py`, `results-a.json` | the reference resolver (A, in `../tools/`) replayed over all 19 vectors and all 101 admissible input permutations |
| `implementation-b/` | a second resolver, written from the specification alone, in two variants: `sealed/` as sealed before it had seen anything of A, and `r2/` after its one genuine defect was corrected |
| `comparison/` | the seven-axis A/B comparison, the divergence journal, the verdicts, and the amendments the divergences motivate |
| `cleanroom-kit/` | the self-contained kit for a genuinely external third party to write a third implementation with no access to A, to B, or to any expected output |

Read `comparison/COMPARISON-REPORT.md` first. It carries the two verdicts and the final
recommendation. `comparison/DIVERGENCE-JOURNAL.md` is the working record behind it, written before any
correction was applied; `comparison/AMENDMENT-PROPOSALS.md` is the separate proposal for closing the
specification gaps the comparison exposed, and nothing in it has been applied.

## How to re-run everything

Every step below rebuilds an artefact from source and checks it against a hash recorded before the
comparison. All paths are relative to this directory. None of these commands writes anywhere inside
the repository.

```sh
# B's results, rebuilt in a scratch directory from B's own source and the oracle-free vectors.
# Reads nothing from A and nothing from resolution-vectors.v0.1.json.
sh implementation-b/reproduce.sh sealed     # -> REPRODUCED — byte-identical
sh implementation-b/reproduce.sh r2         # -> REPRODUCED — byte-identical

# The seven-axis comparison. Verifies B's seal by sha256 before reading anything, then VERIFIES the
# committed divergence record rather than overwriting it.
python3 comparison/compare_ab.py sealed     # 49 axis divergences; A/oracle 0, B/oracle 18
python3 comparison/compare_ab.py r2         # 40 axis divergences; A/oracle 0, B/oracle 13

# The clean-room kit tarball, rebuilt deterministically. Verifies KIT-MANIFEST.sha256 while staging.
sh cleanroom-kit/build-tarball.sh /tmp      # -> c60b0b1e…5b831281, 34549 bytes

# Every hash pinned at seal time.
(cd implementation-b && sha256sum -c MANIFEST.sha256)
(cd cleanroom-kit && sha256sum -c KIT-MANIFEST.sha256)
```

`compare_ab.py` refuses to run if any sealed file has moved, and if a re-run produced different
divergence content it would write that run to a temporary file and exit non-zero rather than touch
`divergences-raw.json` or `divergences-r2.json`. Those two files are the record: they were taken at
the moment the two result files were first placed side by side, and they are cited by name in the
divergence journal.

## Paths that changed when this was committed

B was written, sealed and compared under `/tmp/implb/`, outside the repository, precisely so that A
could be removed from the working tree while B was being written. `implementation-b/BRIEF.md`,
`implementation-b/COMMANDS.md` and parts of `DESIGN-JOURNAL.md` therefore quote `/tmp/implb/…` paths.
Those documents are the contemporaneous record and have not been rewritten. The mapping is:

| as written in the record | in this tree |
|---|---|
| `/tmp/implb/resolver_b.py` (sealed source) | `implementation-b/sealed/resolver_b.py` |
| `/tmp/implb/resolver_b.py` (after the D1 fix) | `implementation-b/r2/resolver_b.py` |
| `/tmp/implb/results-b.json` | `implementation-b/sealed/results-b.json` |
| `/tmp/implb/results-b.r2.json` | `implementation-b/r2/results-b.json` |
| `/tmp/implb/replay_b.py` | `implementation-b/{sealed,r2}/replay_b.py` (identical in both) |
| `/tmp/implb/inputs/resolution-vectors.INPUTS-ONLY.json` | `implementation-b/inputs/resolution-vectors.INPUTS-ONLY.json` |
| `/tmp/out/daryl-pack-resolver-cleanroom-v0.1.tar.gz` | rebuild from `cleanroom-kit/` with `build-tarball.sh` |
| `/tmp/implb/kit/…` | `cleanroom-kit/…` |

The hashes quoted in those documents are unchanged and still verify — the files moved, their bytes
did not. `implementation-b/MANIFEST.sha256` pins all seven, and also records that the five spec
documents and five example packs given to B were byte-identical copies of the repository's own files,
which is why they are not duplicated under `implementation-b/`.

One point of history is recorded in `DESIGN-JOURNAL.md` entry E20 rather than hidden: the D1
correction was applied to B's source in place, which left the sealed result file with no source on
disk. The sealed source was recovered byte-exactly from the session's edit record, verified against
the seal hash, and verified again by rebuilding `sealed/results-b.json` bit for bit. Both variants are
now committed as sources, which is why `reproduce.sh` takes a variant argument.

## What this evidence supports, in one paragraph

Two implementations with different internal architectures — A a per-pack fold, B a relational pipeline
— agree on the resolved path completely: same effective manifest by value identity, same canonical
hash, same resolution trace and same trace hash, on all 19 vectors under all 101 permutations. They
cannot be made to agree on the refused path, because the refusal object is hashed and three of its
fields are left undetermined by the specification. That is the finding, and it is why the final
recommendation is `ADR specification still incomplete` rather than `ready for ratification` —
incomplete in its reporting contract, not in its composition law. B's independence is architectural
and documentary; it is explicitly **not** cognitive clean-room independence, since B was written in the
same session as A. Establishing that is what `cleanroom-kit/` is for, and it has not yet been done.

Ratification, the capability register and the push remain three separate decisions. None is taken
here.
