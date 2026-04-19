# ADR 0001 — Canonical Consumption Path: Consumption Layer vs RR

- **Status:** Proposed
- **Date:** 2026-04-19
- **Deciders:** Mohamed Azizi (@daryl-labs-ai)
- **Supersedes:** —
- **Related:** `docs/CONSUMPTION_LAYER.md`, `docs/architecture/RR_ARCHITECTURE.md`, `docs/architecture/DSM_STABILIZATION_ROADMAP.md`, `docs/roadmap/PDSM_PORTABLE_DSM.md`

> **Convention note.** This is the first ADR in the repository. It therefore fixes the convention: ADR files live under `docs/architecture/`, are named `ADR_NNNN_SHORT_SLUG.md`, must expose a `Status:` header whose initial value is `Proposed`, and are promoted to `Accepted` only via a distinct review PR. An ADR is never self-approving.

---

## Context

Daryl currently exposes **two agent-facing read stacks** sitting on top of the frozen DSM kernel, plus a third semi-hidden one. This ADR exists because that state is unstable and the next three features on the roadmap (PDSM, onboarding packs, handoff between agents) will each inherit the choice of canonical read path, whether we make it explicit or not.

**Voie A — Consumption Layer.** Three modules introduced in v1.1.0: `src/dsm/recall/search.py` (444 L, `search_memory`), `src/dsm/context/builder.py` (380 L, `build_context`, `build_prompt_context`), `src/dsm/provenance/builder.py` (364 L, `build_provenance`), plus `src/dsm/summarizer.py` (259 L). Heavily documented (`README.md` §"Consumption Layer" at line 194 ; `docs/CONSUMPTION_LAYER.md` claims "77 tests, 0 regressions against the existing 1153" on line 5) yet **has zero agent-facing consumers**: `DarylAgent` exposes 82 public methods (`grep -c '^    def [a-z]' src/dsm/agent.py`) and **none** import `dsm.recall`, `dsm.context`, or `dsm.provenance` (`grep -rn 'from ..recall\|from ..context\|from ..provenance' src/dsm/ → only two hits, both internal to the CL itself`). The MCP server in `src/dsm/integrations/goose/server.py` does not reference these modules. The only live callers are `demo_consumption_layer.py` and `tests/{recall,context,provenance}/`. Test density is **1 test file per module** (307 + 268 + 391 L) for 1 188 L of CL code — light for something the README positions as a flagship.

**Voie B — RR (Read Relay).** `src/dsm/rr/relay.py` (136 L), `src/dsm/rr/index/rr_index_builder.py` (246 L), `src/dsm/rr/navigator/rr_navigator.py` (214 L), `src/dsm/rr/query/rr_query_engine.py` (138 L), `src/dsm/rr/context/rr_context_builder.py` (195 L). Documented in seven files totalling ~92 KB under `docs/architecture/RR_*`, and mentioned in `ARCHITECTURE.md:191`. **RR is the de facto production read path**: `src/dsm/integrations/goose/server.py:239,322,347` import `DSMReadRelay` directly for `dsm_recall` (fallback branch), `dsm_recent`, and `dsm_summary`. The happy path of `dsm_recall` goes through `agent.read_with_digests()` (`src/dsm/agent.py:846`) which hits `RollingDigester` (`src/dsm/collective.py:521`), not RR — but that is still not the Consumption Layer. RR carries one known defect, **I4** in `docs/architecture/DSM_STABILIZATION_ROADMAP.md:37,98`: `RRContextBuilder.build_context` has `resolve: bool = False` as default (`src/dsm/rr/context/rr_context_builder.py:56`), so `content_preview` is empty unless callers opt in.

**The entanglement nobody advertised.** `src/dsm/recall/search.py:18` imports `DSMReadRelay` and `src/dsm/recall/search.py:264` — the inner `_iter_entries` helper — calls `relay.read_recent(sid, limit=…)`. Voie A is therefore **already built on voie B for its read primitive**. The two stacks are not parallel peers, they are partially stacked. Any "coexist as peers" framing is code-contradicted before the ADR starts.

**Hidden third path.** `dsm_search` in `src/dsm/integrations/goose/server.py:379` does not use RR at all. It calls `agent.query_actions` (`src/dsm/agent.py:630`), which instantiates `SessionIndex` (`src/dsm/session/session_index.py:24`) and reads pre-built JSONL index files. This is a third, orthogonal read surface — derived from storage but queried outside both CL and RR. The audit brief labelled `dsm_search` as "voie B"; the code says otherwise. The fact that a third path already exists, silently, is the strongest argument that the anti-redundance driver of this ADR is not theoretical.

**Kernel.** `src/dsm/core/KERNEL_VERSION` pins `DSM_KERNEL_VERSION = "1.0"` with `FREEZE_DATE = "2026-03-14"`. Nothing under `src/dsm/core/` is in scope for this ADR. All moves happen above the kernel.

**Doc incoherence that shows the drift is not purely technical.** `README.md:25` advertises a "1230 passing" badge; `ARCHITECTURE.md:3,226` says "769 passing"; `docs/CONSUMPTION_LAYER.md:5` references "1153" as the baseline; a current measurement on this HEAD (`6d76943`, `2026-04-17`) reports **1 138 passed / 1 failed** (a `K3` filesystem race, probably environmental). `ARCHITECTURE.md` does not list `recall/`, `context/`, or `provenance/` at all in its repository-layout section (lines 197–228). The Consumption Layer is a product claim in one surface and a ghost in another.

**Fichiers examinés :** `src/dsm/recall/search.py`, `src/dsm/context/builder.py`, `src/dsm/provenance/builder.py`, `src/dsm/summarizer.py`, `src/dsm/agent.py`, `src/dsm/integrations/goose/server.py`, `src/dsm/rr/relay.py`, `src/dsm/rr/index/rr_index_builder.py`, `src/dsm/rr/navigator/rr_navigator.py`, `src/dsm/rr/query/rr_query_engine.py`, `src/dsm/rr/context/rr_context_builder.py`, `src/dsm/session/session_index.py`, `src/dsm/core/KERNEL_VERSION`, `src/dsm/collective.py`, `README.md`, `ARCHITECTURE.md`, `docs/CONSUMPTION_LAYER.md`, `docs/architecture/RR_ARCHITECTURE.md`, `docs/architecture/DSM_STABILIZATION_ROADMAP.md`, `docs/architecture/DSM_KERNEL_FREEZE_2026_03.md`, `tests/recall/test_search.py`, `tests/context/test_builder.py`, `tests/provenance/test_builder.py`.

---

## Decision drivers

1. **Anti-redundance.** The chosen path must make a third read stack *structurally harder to introduce*, not merely socially discouraged. The `SessionIndex` case above is proof that "documented convention" is not enough.
2. **Cohérence produit.** `README.md`, `ARCHITECTURE.md`, MCP tool docstrings, and `CONSUMPTION_LAYER.md` must tell the same story about what "reading DSM" means.
3. **Compatibilité MCP.** Eleven tools ship today (`dsm_status`, `dsm_start_session`, `dsm_end_session`, `dsm_log_action`, `dsm_confirm_action`, `dsm_snapshot`, `dsm_recall`, `dsm_recent`, `dsm_summary`, `dsm_search`, `dsm_verify`). Breaking their output shape breaks every downstream agent. Prefer additive migrations.
4. **PDSM readiness.** `docs/roadmap/PDSM_PORTABLE_DSM.md` describes a portable packaging that MUST NOT introduce a fourth read path. The canonical path chosen here defines what PDSM depends on.
5. **Stabilité du kernel.** Zero modification to `src/dsm/core/`. Frozen since `2026-03-14`.
6. **Coût de migration.** Measured in engineer-days for a single implementer with full context. Graded coarsely (1 = weeks, 5 = hours).
7. **Testability.** Count of new or significantly-adapted test files needed to cover the migration.
8. **Operational cost.** Who rebuilds RR index, who invalidates CL-side caches, how many scheduled jobs must an operator understand to keep reads consistent.
9. **Debuggability.** When an agent receives surprising context, how many layers must be inspected, and is the call chain serial or parallel.
10. **Réversibilité.** If the decision proves wrong in six months, how expensive is the rollback (measured in PRs to revert, migrations to re-run).

---

## Options considered

### Option A — Consumption Layer canonical, RR = infra couche indépendante

**Description.** Agents and MCP consume `search_memory`, `build_context`, `build_prompt_context`, `build_provenance`. RR continues to exist as a low-level read/index/navigator/query stack used only for tooling (trace replay, audit drilldown, raw shard inspection). Both stacks read `Storage` directly; the CL stops re-using `DSMReadRelay.read_recent` inside `_iter_entries`.

**Avantages.** Matches the product narrative in `README.md:194` and `docs/CONSUMPTION_LAYER.md`. Scoring / `still_relevant` / `superseded` semantics stay first-class. `DarylAgent` gains three obvious facade methods that map 1-to-1 with the README claims.

**Inconvénients.** Formalizes the duplication it tries to hide. `_iter_entries` (`src/dsm/recall/search.py:259`) would have to stop using `DSMReadRelay` and iterate `Storage` directly, *adding* a read-path rather than removing one. Two independent scan paths to maintain, two places where filter semantics can drift.

**Migration.** ~3–5 j. Rewire MCP tools `dsm_recall`, `dsm_search` to the CL facade; add facade methods on `DarylAgent`; de-couple `_iter_entries` from RR.

**Risque 3e chemin.** High. Nothing forces `SessionIndex` (`src/dsm/session/session_index.py`), digester reads (`src/dsm/collective.py:736`), or any future shortcut to route through CL. The operator has to *choose* CL every time.

**Lisibilité produit.** Good on the README surface, still confusing under the hood because RR remains prominent in `ARCHITECTURE.md:191,204` and in `docs/architecture/RR_*` (seven files, 92 KB).

**Compat PDSM.** Medium. PDSM would consume CL, which would itself re-read `Storage`. PDSM never touches RR, but RR is still shipped and documented — more surface to explain.

**Compat MCP.** Three tools change (`dsm_recall`, `dsm_recent`, `dsm_summary`), additive schema possible; `dsm_search` migrates from `SessionIndex` to `search_memory` (behavior shift, semantics similar).

**Fichiers examinés :** `src/dsm/recall/search.py`, `src/dsm/integrations/goose/server.py`, `src/dsm/agent.py`, `src/dsm/session/session_index.py`, `src/dsm/rr/relay.py`, `README.md`, `ARCHITECTURE.md`.

### Option B — RR canonical, Consumption Layer dépréciée

**Description.** Agents and MCP consume `DSMReadRelay` + `RRQueryEngine` + `RRContextBuilder`. `src/dsm/recall/`, `src/dsm/context/`, `src/dsm/provenance/` are marked `deprecated` with a six-month removal horizon. `docs/CONSUMPTION_LAYER.md` is archived. `DarylAgent` exposes `recall_via_rr` / `context_via_rr` thin facades. `summarizer.py` stays as a lone utility or is folded into RR.

**Avantages.** One read stack. Lowest operational cost (one index to keep warm, `rr_index_builder`). Cleanest debuggability — a single serial call chain from MCP to `Storage`. Smallest immediate refactor effort since MCP is *already* RR-backed today on `dsm_recent` and `dsm_summary`.

**Inconvénients.** Kills the feature `README.md:194` currently headlines. Drops `still_relevant` / `superseded` / `outdated_possibility` semantics (`src/dsm/recall/search.py:40–48`) and the query-scoring logic — RR returns raw records, not scored matches. `build_provenance` (`src/dsm/provenance/builder.py:173`) has no RR equivalent; its verification logic would either be lost or relocated into a new module (which by driver 1 is exactly the 3rd-path risk). Around 1 450 L of CL code and tests become landfill.

**Migration.** ~3–5 j of work, but most of it is deletion + doc archival + README rewrite. The real cost is reputational: Daryl v1.1.0 shipped the CL publicly.

**Risque 3e chemin.** Medium. Single path today, but the first downstream consumer (PDSM, onboarding packs, handoff) that needs *ranked* or *verified* recall will have to reinvent it somewhere, and nothing prevents that reinvention from landing outside RR.

**Lisibilité produit.** Regression. Requires retracting a public claim.

**Compat PDSM.** Good operationally (one stack to port). Weak semantically — PDSM would ship raw entries without scoring or provenance, which is exactly what `PDSM_PORTABLE_DSM.md` lists under "use cases" (verifiable replay, reproducible agent behaviour).

**Compat MCP.** Near-zero churn. Most tools already call RR. `dsm_search` migrates from `SessionIndex` to `RRQueryEngine`.

**Fichiers examinés :** `src/dsm/rr/relay.py`, `src/dsm/rr/query/rr_query_engine.py`, `src/dsm/rr/context/rr_context_builder.py`, `src/dsm/recall/search.py`, `src/dsm/provenance/builder.py`, `src/dsm/summarizer.py`, `src/dsm/integrations/goose/server.py`, `README.md`, `docs/CONSUMPTION_LAYER.md`.

### Option C — RR canonical en lecture, Consumption Layer réorientée au-dessus de RR

**Description.** RR becomes the **only** module allowed to read from `Storage`. `build_context`, `build_provenance`, and `search_memory` are rewritten to consume `RRQueryEngine` / `RRNavigator` instead of `Storage` or `DSMReadRelay` directly. `search_memory`'s scoring (keyword match, `_recency_boost`, enum classification in `src/dsm/recall/search.py:274–300`) stays, but feeds off an `RRQueryEngine` iterator instead of its own `_iter_entries`. `RRContextBuilder` keeps its role as a low-level context primitive used internally by the CL's `build_context`. `SessionIndex` either becomes a specialization of RR's index or is rewired to consume `RRQueryEngine` (separate follow-up).

**Avantages.** Structurally enforces the "one read path" invariant: `grep -rn 'Storage(\|storage.read(' src/dsm/ | grep -v '^src/dsm/rr/\|^src/dsm/core/'` becomes an empty set (CI-enforceable). Preserves all public CL APIs referenced by `README.md:194` and `docs/CONSUMPTION_LAYER.md`. Matches the direction already latent in the code: `src/dsm/recall/search.py:18,264` already imports and uses `DSMReadRelay` — Option C is **the completion of a move the code is halfway through**.

**Inconvénients.** Highest migration cost. `_iter_entries` must be rewritten; `build_provenance` must be audited for any direct `storage.read` calls (currently indirect via match dicts, so survivable); `RRQueryEngine` needs the filter vocabulary that `search_memory` currently implements inline (event-type filter, session-id filter, time window). Two-layer call chain under the surface — marginally harder to debug than Option B.

**Migration.** ~8–12 j across 4–5 PRs. Not a weekend refactor.

**Risque 3e chemin.** Very low. If a new feature wants a read, the only import that makes sense is from `dsm.rr` or from `dsm.recall`/`dsm.context`/`dsm.provenance`; any import of `dsm.core.storage` outside `src/dsm/rr/` or `src/dsm/core/` can be rejected by a lint rule (`scripts/forbid_storage_access.py` — new). `SessionIndex` becomes the obvious 4th-path tail to clean up as a follow-up.

**Lisibilité produit.** Best. README claim stays, RR is reframed as "the I/O gate the CL reads through", and the two doc sets stop competing for top billing.

**Compat PDSM.** Best. PDSM ships `kernel + rr + CL + facade` as a single vertical stack. One dependency chain, one upgrade vector.

**Compat MCP.** Three tools migrate (`dsm_recall`, `dsm_search`, optionally `dsm_recent` if we want semantic consistency — likely kept on RR for raw access). Additive schema preserved.

**Fichiers examinés :** `src/dsm/recall/search.py`, `src/dsm/context/builder.py`, `src/dsm/provenance/builder.py`, `src/dsm/rr/query/rr_query_engine.py`, `src/dsm/rr/relay.py`, `src/dsm/rr/context/rr_context_builder.py`, `src/dsm/integrations/goose/server.py`, `src/dsm/agent.py`, `src/dsm/session/session_index.py`.

---

## Scoring matrix

Scores are 1 (bad) to 5 (good). Raw totals; no weighting. Every cell below was argued in the option blocks above.

**Scope of this matrix.** Recalculated on **"3 read paths → 1 canonical backend"** after `SessionIndex` was formally classified `duplicative` on 2026-04-19 (see `docs/architecture/ADR_0001_SESSIONINDEX_CLASSIFICATION.md`). The v1 matrix implicitly scored "2 read paths (CL, RR) → 1 backend" and carried `SessionIndex` as an out-of-scope follow-up. That deferral has been retired — `SessionIndex` is now in scope — so every option now pays the cost of migrating SessionIndex consumers, and every option is graded on how well it absorbs the third path rather than leaves it dangling.

The **`v1 → v2`** column records the delta vs the original matrix and the attribution for each changed cell. Cells unchanged carry `unchanged`. A cell changed without an attribution would be rejected under the classification-phase rule; none of the cells below fall in that bucket.

| #  | Driver                  | Option A | Option B | Option C | v1 → v2 (attribution)                                                                                                                                |
|----|-------------------------|:--------:|:--------:|:--------:|:----------------------------------------------------------------------------------------------------------------------------------------------------|
| 1  | Anti-redondance         |    1     |    2     |  **5**   | A: 2 → 1 (SessionIndex classification — A leaves 3 read paths coexisting with no structural barrier); B, C: unchanged                                |
| 2  | Cohérence produit       |    2     |    1     |  **5**   | unchanged (scope change does not alter the product-message gap)                                                                                     |
| 3  | Compat MCP (low churn)  |    3     |    4     |    3     | B: 5 → 4 (combination: SessionIndex classification + revised migration cost — `dsm_search` must now migrate off SessionIndex in the same wave, not just switch backends); A, C: unchanged                                                   |
| 4  | PDSM readiness          |    2     |    3     |  **5**   | A: 3 → 2 (SessionIndex classification — PDSM now inherits three optional read packages under A); B, C: unchanged                                     |
| 5  | Stabilité du kernel     |    5     |    5     |    5     | unchanged (kernel untouched under all three options)                                                                                                |
| 6  | Coût de migration       |    3     |    3     |    1     | A: 4 → 3 (revised migration cost — SessionIndex consumer rewiring adds a phase); B: 5 → 3 (revised migration cost — SessionIndex migration adds a phase, no longer "mostly deletion"); C: 2 → 1 (revised migration cost — SessionIndex migration is a 7th phase on top of the six already in plan)          |
| 7  | Testability             |    3     |    4     |    1     | A: unchanged; B: 5 → 4 (revised testability — `tests/test_session_index.py` 242 L needs retirement + goose MCP rewiring tests); C: 2 → 1 (revised testability — SI deprecation tests + RR action-name filter tests added on top)                      |
| 8  | Operational cost        |    1     |    4     |  **5**   | A: 2 → 1 (revised operational cost — three indexes to operate: CL cache, RR index, SessionIndex JSONL); B: unchanged; C: 4 → 5 (revised operational cost — SessionIndex removal collapses to exactly one index, `RRIndexBuilder`)  |
| 9  | Debuggability           |    1     |    4     |    3     | A: 2 → 1 (revised debuggability — three parallel stacks to trace when an agent receives unexpected context); B, C: unchanged                        |
| 10 | Réversibilité           |  **5**   |    2     |    3     | unchanged (rollback model is not affected by SessionIndex scope)                                                                                    |
|    | **Total**               |  **26**  |  **32**  |  **36**  | v1 → v2: A 31 → 26 (−5); B 36 → 32 (−4); C 37 → 36 (−1)                                                                                             |

**Initial intuition before re-scoring:** Option C (unchanged from v1).
**Result of the re-scoring:** Option C wins by **4 points over B**, by **10 over A**. The margin over B widened from 1 (v1) to 4 (v2) because the SessionIndex classification amortises badly under A and B but cleanly under C.
**Published result:** ordering unchanged, margin *widened*. C retained. We leave the v1 matrix's caveat about B's wins on migration cost, testability, and MCP churn — B no longer wins on any of those three drivers in v2, so that caveat is retired.

---

## Scoring deltas (1-sentence reading of the biggest gaps)

Recomputed on the v2 matrix. One delta stayed top-3; two are new because SessionIndex shifted where the pain lives.

- **Driver 8 — Operational cost**, C=5 vs A=1 (Δ=4) — **new top delta (was #8 with Δ=2)**: under v1 both RR and SessionIndex were conceded as operational realities and A's score was pulled down only by the CL cache; in v2 A must keep *three* indexes warm (CL, RR, SessionIndex/JSONL — `src/dsm/rr/index/rr_index_builder.py:119`, `src/dsm/session/session_index.py:44`), while C converges on exactly one (`RRIndexBuilder.build`), making the gap a three-to-one index count, not a style preference.
- **Driver 1 — Anti-redondance**, C=5 vs A=1 (Δ=4) — **moved** (was Δ=3 vs A=2 in v1): A's score fell further because SessionIndex is now a proven-duplicative third path under A's model, and "please use the canonical API" as a cultural rule has been falsified once already by `src/dsm/session/session_index.py` itself — the lint in C (`scripts/forbid_storage_access.py`) is the only mechanical backstop on the table.
- **Driver 2 — Cohérence produit**, C=5 vs B=1 (Δ=4) — **unchanged** (was Δ=4 in v1): B still requires retracting the flagship feature in `README.md:194` and `docs/CONSUMPTION_LAYER.md:5`; SessionIndex's classification does not alter that calculus, which is why this delta survives the scope change intact.

---

## Decision

**Option retenue : C — RR canonical en lecture, Consumption Layer réorientée au-dessus de RR.** Decision unchanged from v1. Margin over Option B widened from 1 to 4 points after the v2 re-scoring that included SessionIndex (classified `duplicative` — see `docs/architecture/ADR_0001_SESSIONINDEX_CLASSIFICATION.md`). The ordering is reported as a matter of record, not reinforced — the matrix above drives the call.

- **Anti-redondance (1):** this is the only option that makes the single-path rule mechanically enforceable via a lint that forbids `Storage` imports outside `src/dsm/{core,rr}/`. SessionIndex having just been demonstrated as a duplicative third path — unblocked by a cultural norm — is the empirical datum that hardens this driver.
- **Cohérence produit (2):** it preserves the public feature set Daryl v1.1.0 shipped while ending the "two stacks" ambiguity in `ARCHITECTURE.md` and `docs/architecture/RR_*`.
- **PDSM readiness (4):** PDSM inherits a single vertical stack (`kernel → RR → CL → facade`) with no optional side-paths to decide about, and crucially no second index format to port.
- **Operational cost (8):** the v2 matrix shifts this driver into the top-3 deltas. Under C the operational target is exactly one index — `RRIndexBuilder.build` (`src/dsm/rr/index/rr_index_builder.py:119`) — replacing two JSONL files at `src/dsm/session/session_index.py:102,107` and eliminating the CL-side implicit cache.
- **Structural reality:** `src/dsm/recall/search.py:264` already reads via `DSMReadRelay`; Option C formalizes a move that is already half-done in the code, which is cheaper than either A (undo the entanglement) or B (delete the layer we entangled with).

**Disposition des options non retenues.**

- **Option A — rejected and removed.** Will not be pursued. `_iter_entries` will *not* be decoupled from RR; the opposite move is the decision.
- **Option B — rejected and removed.** `src/dsm/recall/`, `src/dsm/context/`, `src/dsm/provenance/` are **not** marked deprecated. `docs/CONSUMPTION_LAYER.md` is **not** archived. Any PR that re-proposes deprecating these modules must first file a superseding ADR.

---

## Consequences

**Positives.**
- Exactly one module tree (`src/dsm/rr/`) owns `Storage` access.
- Exactly one index surface (`RRIndexBuilder` at `src/dsm/rr/index/rr_index_builder.py:119`) to operate, after SessionIndex retires in Phase 7. The parallel JSONL index at `src/dsm/session/session_index.py:102,107` is removed.
- CI-enforceable invariant: `scripts/forbid_storage_access.py` fails the build if any file outside `src/dsm/rr/` or `src/dsm/core/` imports `dsm.core.storage.Storage` directly.
- `README.md` §"Consumption Layer" stops being aspirational — the facade methods it promises actually exist on `DarylAgent`.
- PDSM gets a single, clear dependency closure — and a single index format to package, not two.
- I4 (`RRContextBuilder.build_context(resolve=False)` default) is addressed in-scope because CL becomes the canonical caller of `RRContextBuilder` and gets to pick the default that the product wants.

**Négatives.** (we do not explain these away)
- Highest migration cost of the three options. Updated estimate with SessionIndex in scope: **~12–16 engineer-days** across 7 PRs (was ~8–12 / 6 PRs in v1).
- Debuggability regresses slightly vs Option B: two serial layers instead of one when tracing an unexpected context pack.
- `RRQueryEngine` must grow a filter vocabulary (event-type, session-id range, time window, **and now action-name**) it does not ship today. This adds RR surface, not removes it. The action-name filter specifically requires extending `_entry_to_index_record` at `src/dsm/rr/index/rr_index_builder.py:34` to promote `metadata["action_name"]` into a first-class index key — a ~30-line extension plus its tests.
- The SessionIndex deprecation has real blast radius: 8 live consumers across 3 surfaces (3× `DarylAgent` methods, 4× CLI subcommands, 1× MCP tool). The Phase 7 migration must preserve CLI command names (`dsm session-index`, `dsm session-find`, `dsm session-query`, `dsm session-list`) even as their backend changes, to avoid breaking operator muscle memory.

**Dette technique réduite.**
- No more "two parallel stacks" ambiguity between `docs/architecture/RR_*` and `docs/CONSUMPTION_LAYER.md`.
- No more third index (SessionIndex's JSONL at `src/dsm/session/session_index.py:102,107`) hiding behind `DarylAgent.query_actions`.
- Test-count doc drift resolved (README `1230` vs ARCHITECTURE `769` vs CONSUMPTION `1153` vs measured `1138`).
- `_iter_entries`'s direct `DSMReadRelay` usage stops being an accidental cross-cut and becomes the formal read contract.

**Dette technique introduite.**
- `RRQueryEngine` filter vocabulary expansion — must be kept minimal. Specifically: one new filter (`action_name`) and one new iterator (`iter_entries`).
- One new lint (`scripts/forbid_storage_access.py`) to keep green forever.
- A 6-month deprecation window for SessionIndex during which the module still lives under `src/dsm/session/session_index.py` with deprecation warnings — the transient cost of a non-big-bang removal.

**Réversibilité.** If in six months the two-layer chain proves to be a real debuggability tax, rollback is possible in two to three PRs: (a) restore the pre-refactor `_iter_entries` that reads `Storage` via `DSMReadRelay.read_recent` (already the shape today — revert one commit), (b) drop `scripts/forbid_storage_access.py`, (c) if SessionIndex has already been deleted by then, resurrect it from its last git SHA — the module is pure code over a never-rewritten shard, so a revert compiles and runs with no data migration. The facade methods on `DarylAgent` stay; they remain additive. No data migration involved — RR indexes, SessionIndex files, and CL outputs are all derived products of shards that are never rewritten.

---

## Canonical layering model

```
┌────────────────────────────────────────────────────────────────┐
│ MCP / external callers (src/dsm/integrations/**)               │
│ dsm_recall · dsm_search · dsm_recent · dsm_summary · ...       │
│ Calls only: DarylAgent facade.                                 │
└───────────────────────────┬────────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────────┐
│ DarylAgent facade  (src/dsm/agent.py)                          │
│ recall_memory() · build_context() · build_provenance()         │
│ (existing) read_with_digests() · query_actions() [deprecated]  │
│ Calls only: Consumption Layer, Digester, or RR directly for    │
│ raw reads (dsm_recent / dsm_summary primitives).               │
└───────────────────────────┬────────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────────┐
│ Consumption Layer                                              │
│   src/dsm/recall/    — search_memory (scoring + status enums)  │
│   src/dsm/context/   — build_context, build_prompt_context     │
│   src/dsm/provenance/— build_provenance (verify)               │
│ Calls only: RR (no direct Storage access).                     │
└───────────────────────────┬────────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────────┐
│ RR — Read Relay  (src/dsm/rr/)                                 │
│   relay · index · navigator · query engine · context builder   │
│ *** SOLE GATE over Storage reads. Enforced by lint. ***        │
└───────────────────────────┬────────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────────┐
│ DSM kernel  (src/dsm/core/) — FROZEN since 2026-03-14          │
│ Storage · Entry · ShardMeta · hash chain · segments            │
└────────────────────────────────────────────────────────────────┘
```

**Authority rules.**
- MCP may call DarylAgent facade methods only.
- DarylAgent facade may call Consumption Layer, Digester (`src/dsm/collective.py`), or RR primitives (`read_recent`, `summary`) for raw-read MCP tools.
- Consumption Layer may call RR only. No `from dsm.core.storage import Storage` is allowed in `src/dsm/{recall,context,provenance}/`.
- RR is the only module outside `src/dsm/core/` allowed to construct or import `Storage`.
- `SessionIndex` (`src/dsm/session/session_index.py`) is classified `duplicative` as of 2026-04-19 (see `docs/architecture/ADR_0001_SESSIONINDEX_CLASSIFICATION.md`). It is **not** an authorised specialised index in this model — it is a scheduled deprecation. It is therefore absent from the diagram above by design. Its live consumers (`DarylAgent.index_sessions` / `find_session` / `query_actions` at `src/dsm/agent.py:620,625,630`; CLI `dsm session-*` at `src/dsm/cli.py:570–633`; MCP `dsm_search` at `src/dsm/integrations/goose/server.py:378`) rebranch onto RR during Phase 7 of the migration plan below.

---

## Required code changes (file-by-file)

> **File:** `src/dsm/integrations/goose/server.py`
> **Change type:** modify
> **Diff conceptuel:**
> - `dsm_recall` (lines 208–311): replace `agent.read_with_digests(...)` + `DSMReadRelay` fallback with `agent.recall_memory(max_tokens=max_tokens, hours_back=hours_back)` returning a `RecallResult` dataclass. Keep JSON output keys `recent_entries`, `hourly_digests`, `daily_digests`, `weekly_digests`, `total_tokens`, `coverage` unchanged (additive `provenance_block` key may be introduced).
> - `dsm_search` (lines 378–402): replace `agent.query_actions(...)` with `agent.search_memory(query=action_name or "", hours_back=hours_back, limit=limit)`. Document output-shape shift in release notes (action-name filter remains available via an `action_name` kwarg).
> - `dsm_recent` (lines 314–340), `dsm_summary` (lines 343–352): unchanged — these are intentionally raw reads and stay on `DSMReadRelay`.
> **Breaking ?** `dsm_search` returns match dicts instead of action dicts — schema change, breaking. `dsm_recall` additive.
> **Tests impactés:** `tests/integrations/test_goose_canonical.py` (new), `tests/integrations/test_goose.py` if present.

> **File:** `src/dsm/agent.py`
> **Change type:** modify (add 3 methods)
> **Diff conceptuel:** Add three thin facade methods around line 845 (next to `read_with_digests`):
> - `def recall_memory(self, query: str = "", *, max_tokens: int = 8000, hours_back: float = 24.0, verify: bool = True) -> dict`: wraps `dsm.context.build_context` and returns a dict with keys matching the current `dsm_recall` JSON.
> - `def build_context(self, query: str, **kwargs) -> dict`: passes `storage=self.storage` and delegates to `dsm.context.build_context`.
> - `def build_provenance(self, items: list, *, verify: bool = True) -> dict`: delegates to `dsm.provenance.build_provenance(items=items, storage=self.storage, verify=verify)`.
> - Mark `query_actions` (line 630) with a deprecation `warnings.warn(...)` pointing at `recall_memory`. Do not remove — out of scope (see Non-goals, `SessionIndex`).
> **Breaking ?** no (additive).
> **Tests impactés:** `tests/agent/test_recall_facade.py` (new).

> **File:** `src/dsm/recall/search.py`
> **Change type:** modify
> **Diff conceptuel:**
> - `_iter_entries` (lines 259–271): stop constructing `DSMReadRelay` inline; accept an `RRQueryEngine` instance (or its interface) as a parameter. The query engine must expose at minimum `iter(shard_ids, since_ts, until_ts, limit_per_shard)`; if it does not, extend it (see next file).
> - `search_memory` (line 343) signature unchanged; internally constructs an `RRQueryEngine` wrapping `self.storage` when none passed.
> - Remove direct `Storage` instantiation at line 205 and 232 — always build through RR.
> **Breaking ?** no (internal refactor, public signature preserved).
> **Tests impactés:** `tests/recall/test_search.py` (adapt fixture to inject RR query engine), `tests/recall/test_search_rr_integration.py` (new).

> **File:** `src/dsm/context/builder.py`
> **Change type:** modify (minor)
> **Diff conceptuel:** No signature change. `build_context` (line 206) delegates to `search_memory` (line 228) which is now RR-backed; verify that no place in this module re-opens `Storage` outside of the `storage` parameter pass-through.
> **Breaking ?** no.
> **Tests impactés:** `tests/context/test_builder.py` (may need RR fixture update).

> **File:** `src/dsm/provenance/builder.py`
> **Change type:** modify (audit-only)
> **Diff conceptuel:** `build_provenance` (line 173) operates on match dicts passed in. Audit that no helper below it reads `Storage` directly — if it does, route through RR. No signature change.
> **Breaking ?** no.
> **Tests impactés:** `tests/provenance/test_builder.py` (fixture check).

> **File:** `src/dsm/rr/query/rr_query_engine.py`
> **Change type:** modify (add filter vocabulary)
> **Diff conceptuel:** Extend `RRQueryEngine.query` (current 138-line module) with parameters needed by `search_memory`: `shard_ids: list[str] | None`, `since: datetime | None`, `until: datetime | None`, `limit_per_shard: int`. Provide a generator variant `iter_entries(...)` that yields `Entry` objects in streaming fashion for use by `_iter_entries`.
> **Breaking ?** no (additive kwargs, existing positional callers untouched).
> **Tests impactés:** `tests/rr/query/test_rr_query_engine.py` (if present) + new test cases for the iterator.

> **File:** `src/dsm/rr/context/rr_context_builder.py`
> **Change type:** modify (fix I4)
> **Diff conceptuel:** Change default `resolve: bool = False` (line 56) to `resolve: bool = True` **for internal CL callers** — or, safer: add an explicit `resolve: bool | None = None` which delegates to `RRQueryEngine.default_resolve` configured by the CL. Document in the module docstring that `RRContextBuilder` is internal to the CL. Raw callers that want the cheap path pass `resolve=False` explicitly.
> **Breaking ?** behavior change; any caller that relied on the empty `content_preview` to save I/O must now opt in.
> **Tests impactés:** `tests/rr/context/test_rr_context_builder.py` — update `resolve` defaults; `tests/rr/context/test_resolve_default_true.py` (new).

> **File:** `src/dsm/rr/relay.py`
> **Change type:** keep (unchanged)
> **Diff conceptuel:** Reaffirm that `DSMReadRelay.read_recent` / `summary` are intentionally raw primitives. Module docstring updated to cite ADR 0001 and explicitly list the CL as its primary consumer.
> **Breaking ?** no.
> **Tests impactés:** none.

> **File:** `src/dsm/summarizer.py`
> **Change type:** keep (unchanged)
> **Diff conceptuel:** None — `summarizer.py` (259 L) is deterministic post-processing over match dicts, not a read path. Stays as CL utility.
> **Breaking ?** no.
> **Tests impactés:** none.

> **File:** `scripts/forbid_storage_access.py`
> **Change type:** new
> **Diff conceptuel:** Lint script, ~40 lines. Walks `src/dsm/`, rejects any import matching `from dsm.core.storage import` or `from ..core.storage import` outside `src/dsm/core/` and `src/dsm/rr/`. Wired into CI as a separate job.
> **Breaking ?** will fail the build if a dev regresses — intended.
> **Tests impactés:** `tests/scripts/test_forbid_storage_access.py` (new, small).

> **File:** `pyproject.toml`
> **Change type:** modify (minor)
> **Diff conceptuel:** Consider exposing a console entry-point `daryl-dsm-lint = scripts.forbid_storage_access:main` so CI can invoke it without a shell path. Optional.
> **Breaking ?** no.
> **Tests impactés:** none.

**Tests to add (paths):**
- `tests/agent/test_recall_facade.py`
- `tests/integrations/test_goose_canonical.py`
- `tests/recall/test_search_rr_integration.py`
- `tests/rr/query/test_iter_entries.py`
- `tests/rr/context/test_resolve_default_true.py`
- `tests/scripts/test_forbid_storage_access.py`

---

## Required documentation changes

- **`ARCHITECTURE.md`** — add a `Consumption Layer` subsection between current §"Query layers" (line 189) and §"Repository layout" (line 197). Update §"Repository layout" (lines 199–228) to list `recall/`, `context/`, `provenance/`. Harmonize test count to the measured value on `main` at time of merge.
- **`README.md`** — harmonize `tests-XXXX-passing` badge (line 25) to measured count. §"Consumption Layer" (line 194) stays; add one paragraph clarifying "reads via RR under the hood". Fix line 350 and line 373 test-count mentions.
- **`docs/CONSUMPTION_LAYER.md`** — update line 5 to reflect current test totals (no more "77 tests, 0 regressions against the existing 1153"). Add a "Read path" subsection citing this ADR.
- **`docs/architecture/RR_ARCHITECTURE.md`** — add a banner under the title: "As of ADR 0001, RR is the sole read gate over Storage. Agent-facing consumers should not import RR directly; use the Consumption Layer or `DarylAgent` facade."
- **`docs/architecture/DSM_STABILIZATION_ROADMAP.md`** — mark I4 (lines 37, 98, 119) as "resolved by ADR 0001 wave". Mark the read-path question superseded by this ADR. The other stabilization items are untouched.
- **`docs/DSM_FULL_SYSTEM_AUDIT.md`** — dated `2025-03-13`, references `memory/dsm/*` paths that no longer exist. **Archive** under `docs/archive/2025-03-13_DSM_FULL_SYSTEM_AUDIT.md` with a README note pointing at this ADR for the read-path narrative.
- **Test-count harmonization sweep** — one PR that reconciles every doc to the value measured on the merge commit: `README.md:25,350,373`, `ARCHITECTURE.md:3,226`, `docs/CONSUMPTION_LAYER.md:5`. No more drift.

---

## Impact on PDSM

`docs/roadmap/PDSM_PORTABLE_DSM.md` (status: "Low priority", 0 lines of code) describes a portable DSM instance packaged for cross-device use. As of ADR 0001, PDSM MUST consume the canonical stack: `kernel → RR → CL → facade`. PDSM MUST NOT:
- Introduce a new read path over `Storage`.
- Ship a subset of RR that skips indexing (the lint forbids it).
- Bypass the Consumption Layer to build prompt packs "for speed".

**Implementation location (prescriptive).** When PDSM moves from concept to code, it lives at `src/dsm/portable/`. Its dependencies are strictly: `dsm.core` (types only), `dsm.rr`, `dsm.recall`, `dsm.context`, `dsm.provenance`, `dsm.agent`. A packaged PDSM bundle is a tarball of `data/` (shards + manifest as described in `docs/roadmap/PDSM_PORTABLE_DSM.md:24–43`) plus a version pin on the canonical stack. No custom reader.

**Fichiers examinés :** `docs/roadmap/PDSM_PORTABLE_DSM.md`, `src/dsm/` (no existing `portable/` directory — confirmed by `ls src/dsm/`), `src/dsm/rr/`, `src/dsm/agent.py`.

---

## Required MCP changes

**Nouveaux tools.**
- `dsm_context` *(optional, nice-to-have, additive)* — returns the output of `build_context(query, max_tokens, verify=True)` as a structured JSON blob. Signature: `dsm_context(query: str, max_tokens: int = 8000, hours_back: float = 24.0) -> str`.
- `dsm_provenance` *(optional, nice-to-have, additive)* — returns the output of `build_provenance(items)` for a given list of entry hashes.

**Tools à modifier.**
- `dsm_recall(max_tokens: int, hours_back: float) -> str` — implementation migrated from `agent.read_with_digests` + `DSMReadRelay` fallback to `agent.recall_memory(...)`. JSON output keys preserved: `recent_entries`, `hourly_digests`, `daily_digests`, `weekly_digests`, `total_tokens`, `coverage`. Additive key `provenance_block` may be introduced.
- `dsm_search(action_name: str, hours_back: float, limit: int) -> str` — implementation migrated from `agent.query_actions` (via `SessionIndex`) to `agent.search_memory`. **Breaking** output schema: returns match dicts (with `entry_hash`, `score`, `status`, `type`) instead of action dicts. `action_name` kwarg retained as a pre-filter. Document as a breaking change in release notes, bump `integrations/goose` tool version.

**Tools à déprécier avec backward-compat.** None strictly required. Consider alias `dsm_query_actions` pointing at the old `agent.query_actions` behavior for a two-release horizon, to ease downstream migration.

**Tools inchangés.** `dsm_status`, `dsm_start_session`, `dsm_end_session`, `dsm_log_action`, `dsm_confirm_action`, `dsm_snapshot`, `dsm_recent`, `dsm_summary`, `dsm_verify` — 9 tools, unchanged. (`dsm_recent` and `dsm_summary` stay on `DSMReadRelay` by design: they are raw-access primitives.)

---

## Migration plan

Phased. No big bang. Each phase has a falsifiable exit criterion.

- **Phase 1 (PR1, ~2 j)** — Add `recall_memory`, `build_context`, `build_provenance` methods on `DarylAgent` (`src/dsm/agent.py`). Keep CL internals unchanged; keep MCP unchanged. **Exit criterion:** `pytest tests/agent/test_recall_facade.py` green; new methods exercised in at least three test cases each.
- **Phase 2 (PR2, ~3 j)** — Extend `RRQueryEngine` with iterator + filters (`iter_entries(shard_ids, since, until, limit_per_shard)`). Refactor `src/dsm/recall/search.py:_iter_entries` to use it. **Exit criterion:** `pytest tests/recall/ tests/rr/query/` green; `grep -n 'Storage(' src/dsm/recall/` returns 0.
- **Phase 3 (PR3, ~2 j)** — Migrate MCP tool `dsm_recall` in `src/dsm/integrations/goose/server.py` to the new facade. `dsm_search` migration is deferred to Phase 7 (the SessionIndex phase) because its backend — `agent.query_actions` → `SessionIndex.get_actions` — is the SessionIndex rebranching. **Exit criterion:** `pytest tests/integrations/` green; `tests/integrations/test_goose_canonical.py` passes for `dsm_recall`.
- **Phase 4 (PR4, ~1 j)** — Fix I4 in `src/dsm/rr/context/rr_context_builder.py` (default `resolve=True` for CL, explicit opt-out for raw callers). **Exit criterion:** `pytest tests/rr/context/` green; `tests/rr/context/test_resolve_default_true.py` passes.
- **Phase 5 (PR5, ~1 j)** — Introduce `scripts/forbid_storage_access.py` + CI job. **Exit criterion:** CI green on a PR that intentionally violates the rule (the violation PR is rejected by CI; the lint PR itself passes).
- **Phase 6 (PR6, ~1 j)** — Doc sweep: `ARCHITECTURE.md`, `README.md`, `docs/CONSUMPTION_LAYER.md`, `docs/architecture/RR_ARCHITECTURE.md`, `docs/architecture/DSM_STABILIZATION_ROADMAP.md`, archive `docs/DSM_FULL_SYSTEM_AUDIT.md`. Test-count harmonization. **Exit criterion:** `grep -rn '769 passing\|1230 passing\|1153\|77 tests' README.md ARCHITECTURE.md docs/CONSUMPTION_LAYER.md` → one consistent number.
- **Phase 7 (PR7, ~3–4 j) — SessionIndex deprecation.** Added in v2 after `SessionIndex` was classified `duplicative` (see `docs/architecture/ADR_0001_SESSIONINDEX_CLASSIFICATION.md`). Runs in two sub-steps:
  - **7a.** Extend `RRIndexBuilder` with an `action_index: Dict[str, List[record]]` populated by `_entry_to_index_record` at `src/dsm/rr/index/rr_index_builder.py:34` (promote `metadata["action_name"]` to a first-class index key). Add a corresponding `RRNavigator.navigate_action(action_name)` method and an `action_name` filter on `RRQueryEngine.query` at `src/dsm/rr/query/rr_query_engine.py:47`. **Exit criterion:** `pytest tests/rr/` green; `RRQueryEngine.query(action_name="X")` returns results matching the reference output of `SessionIndex.get_actions(action_name="X")` on a frozen fixture.
  - **7b.** Rebranch live SessionIndex consumers onto RR. Rewire `DarylAgent.index_sessions` / `find_session` / `query_actions` (`src/dsm/agent.py:620,625,630`) to call `RRIndexBuilder` / `RRNavigator` / `RRQueryEngine` respectively; preserve the public signatures. Rewire CLI `dsm session-index` / `session-find` / `session-query` / `session-list` (`src/dsm/cli.py:570–633`) — **CLI command names stay identical**, only the backend module changes. Rewire MCP `dsm_search` (`src/dsm/integrations/goose/server.py:378–402`) to call `agent.search_memory(action_name=...)` via the CL → RR path. Add `warnings.warn(DeprecationWarning)` in `SessionIndex.__init__` at `src/dsm/session/session_index.py:34`. Do NOT delete the module yet — that is scheduled for ADR 0001 + 6 months. Retire `tests/test_session_index.py` (242 L) once no production consumer remains. **Exit criterion:** `grep -rn "from .session.session_index import SessionIndex\|from dsm.session.session_index" src/dsm/ | grep -v 'session_index.py'` returns 0; `pytest` full suite green; CLI commands yield identical output on a fixture before and after the backend swap; all eight live consumers listed in the classification report are rebranched.

**Total: 7 PRs, ~12–16 engineer-days** (was 6 PRs / ~10 j in v1; Phase 7 added as a consequence of the SessionIndex classification).

---

## Success criteria

Concrete, falsifiable gates. All must be met before this ADR can be promoted from `Proposed` to `Accepted`.

1. After migration, `dsm_recall` returns the same top-level JSON keys (`recent_entries`, `hourly_digests`, `daily_digests`, `weekly_digests`, `total_tokens`, `coverage`) for a frozen fixture as the pre-migration baseline. Additive keys are documented in `docs/CONSUMPTION_LAYER.md`.
2. `grep -rn "search_memory\|build_context\|build_provenance" src/dsm/agent.py src/dsm/integrations/` returns **≥ 4 occurrences** (currently: 0).
3. `grep -rn "DSMReadRelay" src/dsm/integrations/` returns **≤ 2** occurrences (currently: 3 — `dsm_recall` fallback goes away, `dsm_recent` and `dsm_summary` stay).
4. `grep -rn "Storage(\|from ..core.storage import Storage\|from dsm.core.storage import Storage" src/dsm/recall/ src/dsm/context/ src/dsm/provenance/` returns **0 occurrences** (currently: non-zero).
5. `scripts/forbid_storage_access.py` runs in CI and is green on `main`.
6. The full test suite reports the same passing count in `README.md`, `ARCHITECTURE.md`, and `docs/CONSUMPTION_LAYER.md` — and that count matches local `pytest` output.
7. `RRContextBuilder.build_context` returns non-empty `content_preview` by default for any fixture with resolved entries (I4 closed).

---

## Rollback plan

If operational experience shows the two-layer CL → RR chain is prohibitively hard to debug or tune:

1. Revert PR3 first (MCP back to direct `agent.read_with_digests` + `DSMReadRelay`). User-visible effect reverts to today's behavior — this is the operational rollback.
2. Revert PR2 (restore direct `Storage` iteration inside `_iter_entries`). CL stops depending on `RRQueryEngine` filter vocabulary.
3. Drop `scripts/forbid_storage_access.py` (PR5 revert). Removes the lint constraint.
4. **Keep** PR1 (facade methods on `DarylAgent`) — they are purely additive and harmless even if unused.
5. **Keep** PR4 (I4 fix) — unrelated to the read-path question; should not be rolled back.
6. **Keep** doc harmonization (PR6) — unrelated.

No data migration is involved. Shards are append-only and never rewritten; the RR index and CL outputs are derived products. Rollback is bounded to ~2 reverts touching ~6 files.

---

## Non-goals

- Modifying `src/dsm/core/` (frozen since 2026-03-14 per `src/dsm/core/KERNEL_VERSION`).
- Refactoring `agent-mesh/` (separate scope).
- Changing the schema of `Entry` or `ShardMeta` (`src/dsm/core/models.py`).
- Introducing embeddings or vector search in any module.
- Deprecating or rewriting `RollingDigester` (`src/dsm/collective.py:521`) — the digester is a Tier-D primitive, not a read path, and `dsm_recall`'s happy-path use of it is preserved.
- Introducing a public Python package for PDSM. PDSM remains "concept" until a separate ADR authorizes its first code.
- Changing MCP transport, schema negotiation, or tool discovery. Only tool implementations change.

> Note: the v1 Non-goals listed "Consolidating `SessionIndex` into RR" as out of scope, deferred to a future `ADR_0002_SESSION_INDEX_CONSOLIDATION`. That deferral was retired on 2026-04-19 when SessionIndex was classified `duplicative` (see `docs/architecture/ADR_0001_SESSIONINDEX_CLASSIFICATION.md`) and absorbed into Phase 7 of the migration plan above.

---

## Open questions before Accepted

Open questions must be resolved (or explicitly left open with a stated reason) before this ADR can be promoted from `Proposed` to `Accepted`. Resolved questions keep their original text here so that the decision trail is legible.

### Q1 — `SessionIndex` classification

*Rule.* `SessionIndex` (`src/dsm/session/session_index.py`) is `canonical-supporting` if (a) it demonstrates an access pattern materially orthogonal to RR, **or** (b) it demonstrates an operational model materially distinct from RR. Otherwise it is `duplicative`. Dormant API or hypothetical future use does not count.

*Criteria used.*
- **(a)** Access pattern orthogonality vs RR. Measured by enumerating `SessionIndex` public methods, finding their RR equivalents, and comparing algorithmic cost and semantic coverage.
- **(b)** Invalidation / freshness model. Measured by comparing SessionIndex's build / load / staleness-detection semantics to `RRIndexBuilder`'s.
- **(c)** Consumer count. Informational only — confirms blast radius; does not argue for `canonical-supporting` by itself.

**Resolved 2026-04-19 → see `docs/architecture/ADR_0001_SESSIONINDEX_CLASSIFICATION.md`.** Result: **`duplicative`**. Neither (a) nor (b) met at the "materially distinct" threshold. Consequence: SessionIndex migration folded into the ADR 0001 migration plan as Phase 7; scoring matrix and Consequences section recalculated on the "3 read paths → 1 canonical backend" scope.

---

## Closing statement

> From this point forward, any new context, recall, handoff, onboarding, or portable-packaging feature in Daryl **MUST** build on the canonical path defined by this ADR: `MCP → DarylAgent facade → Consumption Layer → RR → Storage`. **No third read path over `Storage` will be accepted without a superseding ADR.** The lint in `scripts/forbid_storage_access.py` makes this rule mechanical; the mechanical rule is a feature, not a ceremony.
