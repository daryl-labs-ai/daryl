# VM Organization TODO — Actionable Plan

This document turns the VM structure audit (VM_STRUCTURE_AUDIT.md) into a **structured, actionable TODO plan**. It is **planning only**: no files are moved, no code is refactored, and the DSM kernel is not modified.

---

## 1. Current Architecture Summary

| Zone | Path | Role |
|------|------|------|
| **DSM official repository** | `/opt/daryl` | Canonical DSM kernel (memory/dsm: core, session, rr, block_layer, ans), docs, tests. |
| **Daryl laboratory** | `~/clawd` | Experiments, scripts, partial DSM copy (dsm_v2), dsm_modules, Moltbook/Telegram, runtime data. |
| **Runtime memory** | `~/memory` | Logs (e.g. dsm_*.log). |
| **Experimental project** | `~/dsm_staging_repo_2` | Separate repo: slot normalizer + custom dsm_kernel/dsm_modules (not the Daryl DSM layout). |

**Canonical layout check (Step 1):** The directory `/opt/daryl` contains the full canonical DSM layout:

- `memory/dsm/core` — present  
- `memory/dsm/session` — present  
- `memory/dsm/rr` — present  
- `memory/dsm/block_layer` — present  
- `memory/dsm/ans` — present  

**Missing or inconsistent:** None. The official repo has the complete structure. No structural change is required for the kernel layout.

---

## 2. Structural Problems

Problems identified in the audit and confirmed for this plan:

| Problem | Description |
|---------|-------------|
| **Runtime inside repo** | `/opt/daryl` contains `data/` (shards, integrity, security) and, historically, tracked files under `memory/dsm/core/data/`, `memory/dsm/logs/`, `memory/dsm/skills/logs/`. |
| **Tracked files that should be ignored** | Git currently tracks: `memory/dsm/core/data/*`, `memory/dsm/logs/*.jsonl`, `memory/dsm/skills/logs/*.jsonl`, and several `__pycache__/*.pyc`. These match .gitignore intent but were committed before the rules. |
| **Root data/ not ignored** | `.gitignore` does not list root `data/`; only `memory/dsm/core/data/`. So `data/` at repo root can be added accidentally. |
| **Build artifacts** | `dsm_v2.egg-info/` exists at repo root and should be ignored. |
| **Duplicated DSM** | `~/clawd/dsm_v2` is a partial copy (no rr, no block_layer); risk of divergence from `/opt/daryl`. |
| **Multiple DSM names** | dsm_v2, dsm_lite, dsm_modules, dsm_kernel exist in lab or other repo; only `/opt/daryl` is the canonical kernel. |
| **Lab runtime in repo** | `~/clawd` has `data/`, `dsm_v2/data/`, `dsm_v2/core/data/`, `dsm_v2/logs/` inside its Git tree; these should not be committed. |
| **Symlink to lab** | `/opt/daryl/agents/clawdbot/runtime` → `~/clawd`; official repo references lab for that agent. |

---

## 3. Repository Cleanup Tasks (DSM repo: /opt/daryl)

Everything that **must not** be inside the DSM repository:

| Category | Examples | Action |
|----------|----------|--------|
| **Runtime data** | `data/`, `data/shards/`, `data/integrity/`, `data/security/` | Ignore; do not commit. |
| **Logs** | `memory/dsm/logs/`, `memory/dsm/skills/logs/`, any `*.jsonl` under logs | Ignore; remove from tracking if already committed. |
| **Shard / integrity files** | `memory/dsm/core/data/**`, any `*_last_hash.json`, `*_0001.jsonl` | Ignore; remove from tracking if already committed. |
| **Build artifacts** | `dsm_v2.egg-info/`, `__pycache__/`, `*.pyc` | Ignore; remove from tracking if committed. |
| **Temporary files** | `*.tmp`, `*.bak`, `.pytest_cache/` | Add to .gitignore if not already. |
| **Secrets / env** | `.env`, `*.json` with credentials or wallet paths | Already in .gitignore; ensure no such files are tracked. |

**Proposed .gitignore additions (merge with existing):**

- `data/` — root-level DSM data directory.  
- `dsm_v2.egg-info/` — setuptools build info.  
- `.pytest_cache/` — test cache.  
- Optional: `memory/dsm/data/` if it exists as alternate data dir.

No deletion of files from disk; only Git tracking and .gitignore updates.

---

## 4. Laboratory Separation Tasks (~/clawd)

Objectives: keep clawd as the laboratory without interfering with the DSM repo; clarify what is experiment vs runtime vs DSM-dependent.

| Task | Description |
|------|-------------|
| **List experiment folders** | Identify top-level folders that are purely experimental: e.g. `daryl-faucet/`, `sharding_project/`, and all `fix_*`, `apply_*`, `add_*` scripts. Document in a short LAB_README or index (plan only; no obligation to create it in this task). |
| **List DSM-dependent code** | Identify what in clawd depends on DSM: `dsm_v2/`, `dsm_modules/`, scripts that import dsm_v2 or use Storage/SessionGraph. Document that these depend on a DSM implementation (clawd’s dsm_v2 or, if symlinked, /opt/daryl). |
| **List runtime folders** | Confirm runtime dirs: `data/`, `dsm_v2/data/`, `dsm_v2/core/data/`, `dsm_v2/logs/`, `dsm_modules/` cache/index if any. Ensure they are in clawd’s .gitignore. |
| **List unrelated-to-DSM** | Identify files/folders unrelated to DSM (e.g. Moltbook-only, Telegram-only, other bots). Optionally group or document so lab stays understandable. |
| **Clawd .gitignore** | Propose or verify .gitignore in ~/clawd so that `data/`, `dsm_v2/data/`, `dsm_v2/core/data/`, `dsm_v2/logs/`, and any `**/logs/*.jsonl` are ignored. No code change in /opt/daryl. |

These are documentation and planning tasks; no file moves or refactors.

---

## 5. Runtime Isolation Tasks

Ensure runtime data is stored **outside** the DSM repository (or clearly ignored inside it).

| Task | Description |
|------|-------------|
| **Confirm runtime locations** | Treat as canonical runtime roots: `~/memory`, `~/clawdbot_dsm_test`, `~/clawd/data`, `~/clawd/dsm_v2/data`, `~/clawd/dsm_v2/core/data`, `~/clawd/dsm_v2/logs`. None of these should be inside `/opt/daryl` as **tracked** content. |
| **DSM repo: no tracked runtime** | Ensure `/opt/daryl` does not track any of: root `data/`, `memory/dsm/core/data/`, `memory/dsm/logs/`, `memory/dsm/skills/logs/`, or any `*.jsonl` under those. Use “Git hygiene” tasks below. |
| **Document runtime layout** | In docs (e.g. VM_STRUCTURE_AUDIT or README), state that runtime data lives in `~/memory` and in lab paths above, and that the DSM repo may contain a local `data/` for development but it must be ignored and never committed. |
| **No runtime in repo** | Add a checklist or CI rule (plan only): “Do not add `data/` or `**/logs/*.jsonl` to Git.” Implement via .gitignore + optional pre-commit or doc. |

---

## 6. DSM Implementation Consolidation Tasks

Classify alternative DSM-related implementations (do not delete or move; classify only).

| Implementation | Location | Classification | Note |
|----------------|----------|----------------|--------|
| **dsm_v2 (package)** | `/opt/daryl` (symlink to memory/dsm) | **Canonical** | This is the official kernel. |
| **dsm_v2 (directory)** | `~/clawd/dsm_v2` | **Experimental / partial copy** | Same name, partial layout (no rr, block_layer). Keep in lab; do not treat as source of truth. |
| **dsm_lite, dsm_lite_fixed** | `~/clawd/*.py` | **Deprecated or experimental** | Old/light clients; stay in lab. |
| **dsm_modules** | `~/clawd/dsm_modules` | **Experimental** | e.g. RR indexer; candidate for porting to /opt/daryl (as RR) per migration plan, but remain in lab until then. |
| **dsm_modules** | `~/dsm_staging_repo_2/src/dsm_modules` | **Other project** | Part of slot-normalizer project; not Daryl DSM. Do not merge into /opt/daryl. |
| **dsm_kernel** | `~/dsm_staging_repo_2/src/dsm_kernel` | **Other project** | Different API (shard_manager, etc.); not the memory/dsm kernel. Keep separate. |
| **memory_sharding_system** | If present in lab | **Experimental** | Per LAB_TO_DARYL_MIGRATION_PLAN, different architecture; do not migrate into DSM kernel. |

**Consolidation rule:** The **only** canonical DSM kernel is `/opt/daryl` (memory/dsm). All other implementations are either experimental (lab) or a different product (dsm_staging_repo_2). No code moves; only clear ownership and documentation.

---

## 7. Git Hygiene Tasks (/opt/daryl)

Tasks to clean the Git repository **without** modifying the DSM kernel or moving files on disk.

| Task | Action |
|------|--------|
| **Update .gitignore** | Add: `data/`, `dsm_v2.egg-info/`, `.pytest_cache/`. Ensure `memory/dsm/core/data/`, `logs/`, `*.jsonl` remain. Optionally add `memory/dsm/data/`, `memory/dsm/logs/`, `memory/dsm/skills/logs/` explicitly. |
| **Stop tracking runtime (git rm --cached)** | Run (when ready): `git rm --cached -r memory/dsm/core/data/` (if tracked), `git rm --cached memory/dsm/logs/*.jsonl`, `git rm --cached memory/dsm/skills/logs/*.jsonl`. Do not use `git rm` without `--cached` so that files remain on disk. |
| **Stop tracking cache (git rm --cached)** | Run: `git rm --cached -r memory/dsm/__pycache__/` and any other `**/__pycache__/` that are tracked. |
| **Verify no data/ at root tracked** | If `data/` at repo root was ever added, run `git rm --cached -r data/`. Then add `data/` to .gitignore. |
| **Commit hygiene changes** | After updating .gitignore and running git rm --cached, commit with a message such as “chore: stop tracking runtime and cache; update .gitignore”. |

**Current tracked files that should be untracked (from scan):**

- `memory/dsm/core/data/integrity/sessions_last_hash.json`  
- `memory/dsm/core/data/shards/security_baseline.jsonl`  
- `memory/dsm/core/data/shards/sessions/sessions_0001.jsonl`  
- `memory/dsm/logs/skills_success.jsonl`  
- `memory/dsm/logs/skills_usage.jsonl`  
- `memory/dsm/skills/logs/skills_success.jsonl`  
- `memory/dsm/skills/logs/skills_usage.jsonl`  
- All `memory/dsm/**/__pycache__/*.pyc`  

---

## 8. Final Target Architecture

Target view of the VM after the organization plan is applied (conceptual; no file moves).

```
VM Structure

DSM Repository (canonical)
    /opt/daryl
    — memory/dsm: core, session, rr, block_layer, ans, skills, modules, storage, moltbook
    — docs/, docs/architecture/, tests/, agents/, pyproject.toml
    — data/ and runtime dirs present on disk but IGNORED; never committed
    — Single source of truth for DSM kernel

Daryl Laboratory
    ~/clawd
    — Experiments, one-off scripts, dsm_v2 (partial copy), dsm_modules
    — Moltbook, Telegram, bots, data/, logs/
    — May reference /opt/daryl or use its own dsm_v2 for testing
    — agents/clawdbot/runtime in /opt/daryl points here

Runtime Memory
    ~/memory
    — Logs only (e.g. dsm_*.log)
    — Never committed to any repo

Experimental Projects
    ~/dsm_staging_repo_2
    — Slot normalizer + custom dsm_kernel / dsm_modules
    — Separate from Daryl DSM; do not merge into /opt/daryl
```

---

## 9. Ordered Execution Plan

Execute in this order to avoid re-tracking or inconsistent state.

**Execution status:** Phase 1–2 (repository hygiene and documentation) have been executed: .gitignore updated, runtime/cache removed from tracking, commit created, REPO_HYGIENE_REPORT.md and VM_ARCHITECTURE_FINAL.md added. Phases 4–5 (validation, optional clawd .gitignore) can be run as needed.

| Phase | Step | Task |
|-------|------|------|
| **1** | 1.1 | **Document** current state: ensure VM_STRUCTURE_AUDIT.md and this VM_ORGANIZATION_TODO.md are committed in /opt/daryl so the plan is versioned. |
| **1** | 1.2 | **Update .gitignore** in /opt/daryl: add `data/`, `dsm_v2.egg-info/`, `.pytest_cache/`; optionally add explicit `memory/dsm/logs/`, `memory/dsm/skills/logs/`, `memory/dsm/data/`. |
| **2** | 2.1 | **Stop tracking runtime:** `git rm --cached -r memory/dsm/core/data/` (if tracked). |
| **2** | 2.2 | **Stop tracking logs:** `git rm --cached memory/dsm/logs/skills_success.jsonl memory/dsm/logs/skills_usage.jsonl` and `memory/dsm/skills/logs/skills_success.jsonl memory/dsm/skills/logs/skills_usage.jsonl` (if tracked). |
| **2** | 2.3 | **Stop tracking root data:** If `data/` is tracked, `git rm --cached -r data/`. |
| **3** | 3.1 | **Stop tracking __pycache__:** `git rm --cached -r memory/dsm/**/__pycache__/` (or per-directory as needed). |
| **3** | 3.2 | **Commit** all above changes with a single “chore: repository hygiene” commit. |
| **4** | 4.1 | **Document lab/repo split** in /opt/daryl (e.g. README or docs): official repo = /opt/daryl; lab = ~/clawd; runtime = ~/memory; symlink agents/clawdbot/runtime → ~/clawd. |
| **4** | 4.2 | **(Optional) Clawd .gitignore:** In ~/clawd, add or update .gitignore for data/, dsm_v2/data/, dsm_v2/core/data/, dsm_v2/logs/, **/logs/*.jsonl. No change in /opt/daryl. |
| **5** | 5.1 | **Validate:** Run `git status` and `git ls-files` in /opt/daryl; confirm no data/, no logs/*.jsonl, no __pycache__ in tracked list. |
| **5** | 5.2 | **Validate:** Ensure kernel layout (memory/dsm/core, session, rr, block_layer, ans) is unchanged and that no kernel files were modified by this plan. |

**Constraints:** Do not move or delete any file from disk. Do not modify DSM kernel code. Only Git tracking and .gitignore content are changed; all other tasks are documentation and validation.

---

**Summary:** This plan cleans the DSM repo (Git tracking and .gitignore), documents lab vs repo vs runtime, classifies alternative DSM implementations, and leaves the VM architecture aligned with “DSM repo = /opt/daryl, lab = ~/clawd, runtime = ~/memory.” Execution is limited to repository hygiene and documentation.
