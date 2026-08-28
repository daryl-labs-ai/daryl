# EVIDENCE_INVENTORY

Every HexaShard artifact found, hashed at gate time, before any judgement was formed.

**Source working tree:** `/Users/mohamedazizi/Documents/DARYL/evidence-fieldops-review/daryl`
**Repository:** https://github.com/daryl-labs-ai/daryl — branch `review/evidence-fieldops-v0` @ `990d378`

> **Git status at gate time:** *zero* HexaShard files were tracked in git. The whole
> body of work — Core, Adapter, every lab — existed only as untracked files in one
> working tree. There is no HexaShard commit history to preserve or import.

The machine-readable form, with full digests, absolute paths and file counts, is
[`EVIDENCE_INVENTORY.json`](EVIDENCE_INVENTORY.json).

| Artifact | SHA-256 (first 16) | Frozen | Canonical | Role |
|---|---|---|---|---|
| `HexaShard Core v0.1 — Claude immutable archive` | `268f0f08362982c2` | yes | **yes** | The frozen Core all downstream labs ran against. Reported hash re-verified at this gate. |
| `Core v0.1 working copy — zdepth control (Adapter's declared CORE_ROOT)` | `2bbc2d4fc6afa429` | yes | **yes** | Byte-identical copy of the frozen Core; verified at this gate. |
| `Core v0.1 working copy — cross-audit immutable_from_tgz` | `2bbc2d4fc6afa429` | yes | no | Byte-identical copy of the frozen Core; verified at this gate. |
| `Core v0.1 working copy — cross-audit extracted` | `2bbc2d4fc6afa429` | yes | no | Byte-identical copy of the frozen Core; verified at this gate. |
| `Core v0.1 working copy — cross-audit work` | `2bbc2d4fc6afa429` | yes | no | Byte-identical copy of the frozen Core; verified at this gate. |
| `Core v0.1 working copy — paraphrase core` | `2bbc2d4fc6afa429` | yes | no | Byte-identical copy of the frozen Core; verified at this gate. |
| `HexaShard Core v0.1 — Cursor build (ORPHAN, superseded)` | `2f5367e3290d4afe` | no | no | A second, independent Core v0.1 with a different module set and 13 tests. No downstream lab imports it. EXCLUDED from migration. |
| `HexaShard Adapter v0.1` | `4982acfc325030a9` | no | **yes** | Chat runtime over the frozen Core. Migrated with Class A/B fixes. |
| `HEXASHARD_CURSOR_INDEPENDENT_REPLICATION.md` | `ec0fc6752d2d064e` | yes | no | B — sharding supported; hex-agent architecture not supported |
| `HEXASHARD_DSM_PARTNERSHIP_REPORT.md` | `ef47456db15134c9` | yes | no | D — pins+retrieval reproduce DSM's operational benefit |
| `HEXASHARD_DSM_NAMESPACE_FINAL_REPORT.md` | `641cecb968ee2662` | yes | no | C — DSM optional, audit/provenance only |
| `HEXASHARD_CORE_V01_CROSS_AUDIT.md` | `cbfe42577affb129` | yes | no | Independent cross-audit of the Claude Core |
| `HEXASHARD_CORE_V01_PARAPHRASE_REPORT.md` | `70754f2ddffca9a7` | yes | no | B — BM25 sufficient with caveats; reproduced bit-for-bit at this gate |
| `HEXASHARD_6PORT_ZDEPTH_REPORT.md` | `961f0ccc091984f4` | yes | no | B — Z-depth supported, six-port not supported |
| `HEXASHARD_SPATIAL_CANVAS_REPORT.md` | `5efa97888ea53676` | yes | no | G — spatial model harmful as a default retrieval filter |
| `HEXASHARD_SPATIAL_PORTS_REPORT.md` | `26c1e4eb08a02313` | yes | no | P-C — ports not a Core requirement; self-reported rounding artefact |
| `HEXASHARD_LIVE_LLM_001_REPORT.md` | `47a6a7db7e96b810` | yes | no | F — INCONCLUSIVE; confirmed at this gate |
| `HEXASHARD_LIVE_LLM_001_LOCAL_REPORT.md` | `532f0c441682a22b` | yes | no | B — Normal saturates at scale, HexaShard completes; confirmed narrowly |
| `eval_rows.json` | `1d9020ef9ba3c8d3` | yes | no | LIVE 001 raw rows (288). 170 HTTP 200 / 118 HTTP 400. |
| `eval_rows.json` | `7413000cdacc9915` | yes | no | LIVE 001-L raw rows (240), 120/arm, paired. |
| `summary.json` | `2e064b629abd9b95` | yes | no | Paraphrase summary; regenerated identically at this gate. |
| `smoke.json` | `8808b1cfde03f407` | yes | no | Adapter smoke measurements. |

## Two things are called "Core v0.1"

This is the single most important topology fact, and it is not visible from the
reports alone.

| | Claude Core | Cursor Core |
|---|---|---|
| location | `research/hexashard_zdepth_experiment/control/hexashard_core_v01_claude` | `hexashard/` (repo root) |
| modules | `context, ids, metrics, models, pins, project, providers, retrieval, store, tokens, trust` | `epochs, hexmap, io, metrics, models, pins, project, provider, relations, retriever, sources, state, tokens, trust, types` |
| tests | 68 | 13 |
| acceptance verifier | yes (20 criteria) | no |
| frozen archive | yes | no |
| imported by any downstream lab | **yes — all of them** | **no — none** |

The Adapter's own `core_lock.py` and `fixtures/CORE_MANIFEST.json` name the Claude
Core explicitly, by absolute path and by digest. A repository-wide import search
found no consumer of the Cursor Core's distinctive modules.

**Resolution:** the Claude Core is canonical. The Cursor Core is an orphaned parallel
build and is excluded from migration.
