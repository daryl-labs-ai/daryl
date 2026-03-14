# Analyse de l’architecture Daryl

Document dérivé de `ARCHITECTURE.md` : description détaillée des briques (memory/dsm, agents/clawdbot/runtime, skills, modules), puis inventaire des **imports cassés** et **plan de refactor** proposé.

---

## 1. Vue d’ensemble

Daryl est une architecture d’agent IA expérimentale centrée sur un **noyau de mémoire déterministe** (DSM — Daryl Sharding Memory). Le runtime de production (Clawdbot) vit dans un dépôt externe (`/home/buraluxtr/clawd`), relié par le symlink `agents/clawdbot/runtime`. Le dépôt Daryl contient surtout le **DSM** et les **skills** associés.

---

## 2. Memory / DSM

### 2.1 Rôle

- **Stockage append-only** : entrées en JSONL, shards par segment.
- **Replay déterministe** : rejeu de traces pour vérification.
- **Sécurité** : couche de protection des fichiers critiques, baseline de hachage, audit.

### 2.2 Structure sous `memory/dsm/`

| Chemin | Rôle |
|--------|------|
| **core/** | Cœur du stockage et runtime : `Storage`, `Entry`, `ShardMeta`, `ShardSegmentManager`, `Signing`, `SessionTracker`, `SecurityLayer`, `replay`, `tracing`, `runtime`. |
| **session/** | Graphe de sessions et limites : `SessionGraph`, `SessionLimitsManager`. |
| **skills/** | Système de skills réutilisable : modèles, registry, router, ingestor, usage/success loggers, skill graph, analyse de succès, CLI, libs (anthropic, community, custom), browser. |
| **ans/** | Audience Neural System : analyse de performance des skills, recommandations, `ANSEngine`, modèles ANS, CLI. |
| **storage/** | Ré-export du gestionnaire de segments (`ShardSegmentManager` depuis `shard_segments`). Redondant avec `core/shard_segments.py`. |
| **modules/** | Composants réutilisables (ex. `dsm_rm` : recyclage de mémoire). |
| **moltbook/** | Client et normalizer Moltbook (intégration externe). |

Les points d’entrée sont `cli.py` (CLI principale) et `__main__.py` (exécution en `python -m dsm_v2`).

### 2.3 Dépendances internes

- **core** : `models`, `shard_segments` ; pas de dépendance vers session/skills/ans.
- **session** : dépend de `..core.storage` et `..core.models`.
- **skills** : logique autonome ; certains scripts s’attendent à un package parent `dsm_v2`.
- **ans** : lit les logs produits par skills, utilise `ans_models`, `ans_analyzer`, `ans_engine`.
- **cli** : agrège `core` (Storage, Signing, SessionTracker, SecurityLayer) et délègue à security/trace replay.

---

## 3. Agents / Clawdbot / Runtime

### 3.1 Organisation

- **agents/clawdbot/** : répertoire dans Daryl.
- **agents/clawdbot/runtime** : **symlink** vers `/home/buraluxtr/clawd` (runtime de production).

Aucun code agent n’est dans le dépôt Daryl ; tout l’exécutable (Clawdbot) est dans `clawd`. Daryl fournit le DSM (et éventuellement les skills) que le runtime consomme.

### 3.2 Workflow

- **Cursor** : développement dans Daryl (DSM, skills, modules).
- **Clawdbot** : exécution et tests en conditions réelles.
- **DSM** : journalisation et mémoire persistante pour l’agent.
- **Git** : versionnement du code DSM/skills dans Daryl.

---

## 4. Skills

### 4.1 Rôle

- **Registry** : enregistrement des skills (définition, triggers).
- **Router** : sélection du skill à partir de la description de la tâche.
- **Ingestor** : chargement depuis des répertoires (libraries).
- **Télémétrie** : `SkillUsageLogger`, `SkillSuccessLogger` → JSONL.
- **Analyse** : `SkillSuccessAnalyzer`, `SkillGraph` (transitions, succès).
- **CLI** : `skills/cli.py` pour lister, valider, analyser.
- **Libs** : `libraries/anthropic`, `community`, `custom` ; skill **browser** (Playwright).

### 4.2 Intégration DSM

- Les skills sont **dans** le DSM (`memory/dsm/skills/`) et conçus pour être réutilisables.
- Plusieurs scripts de test ou de validation (à la racine de `memory/dsm/`) font `sys.path.insert(0, memory/dsm)` puis `from skills import ...` ; ils supposent donc que le répertoire de travail ou le path permet d’importer le package `skills` (i.e. `memory/dsm/skills`).

---

## 5. Modules

### 5.1 Emplacement

- **memory/dsm/modules/** : composants réutilisables du DSM.
- **modules/** (racine du repo) : vide ou peu utilisé ; `ARCHITECTURE.md` le décrit comme « reusable components ».

### 5.2 Exemple : `modules/dsm_rm.py`

- **DSMRecyclingMemory** : recyclage / archivage de sessions DSM (shards, summaries, archive, recycled).
- Dépend de `ShardSegmentManager` ; l’import actuel est **cassé** (voir section 6).

---

## 6. Imports cassés et incohérences

### 6.1 Nom de package : `dsm_v2` vs emplacement réel `memory/dsm`

- Beaucoup de fichiers supposent un **package top-level `dsm_v2`** :
  - `from dsm_v2.core.storage import ...`
  - `from dsm_v2.session.session_graph import ...`
  - `from dsm_v2.skills....`
- Dans Daryl, le code est sous **`memory/dsm/`** et il n’y a ni `pyproject.toml` ni `setup.py` pour définir un package `dsm_v2`. Ces imports ne peuvent fonctionner que si :
  - le projet est installé sous le nom `dsm_v2`, ou
  - un répertoire nommé `dsm_v2` (contenant ce code) est sur `PYTHONPATH`.
- **Fichiers concernés** (liste non exhaustive) :  
  `trace_replay.py`, `tests_v2/*`, `skills/__init__.py`, `skills/cli.py`, `security.py`, `core/security.py`, `run_stability_suite.py`, `full_chain_validation.py`, `ans/cli.py`, `ans/ans_test.py`, etc.

### 6.2 Package `skills` : exports et chemins

- **skills/__init__.py** :
  - Ajoute le **parent** du package skills au path et fait `from dsm_v2.skills.models import ...` et `from dsm_v2.skills.registry import ...`. Donc dépend du fait que le répertoire parent s’appelle `dsm_v2` (ce n’est pas le cas : il s’appelle `dsm`).
  - **N’exporte pas `SkillRouter`**, alors que plusieurs tests font `from skills import SkillRegistry, SkillRouter` (ex. `test_usage_logging.py`, `test_routing_multi.py`, `test_ingestion.py`, `test_final_validation.py`, `full_chain_validation.py`, `test_imports.py`).

### 6.3 Tests « session » : imports plats

- Plusieurs tests insèrent `memory/dsm` dans `sys.path` puis importent comme si les modules étaient à la **racine** de `memory/dsm` :
  - `from session_graph import SessionGraph`  
    → `SessionGraph` est dans `session/session_graph.py`, pas à la racine.
  - `from session_limits_manager import SessionLimitsManager`  
    → idem, dans `session/session_limits_manager.py`.
- **Fichiers** : `session_test_runner.py`, `session_stress_test.py`, `session_dedup_test.py`, `session_dedup_validation_test.py`, `session_cooldown_test.py`, `session_test_home_real.py`, `moltbook_observation_runner.py`, `real_moltbook_observation_test.py`.

### 6.4 Moltbook

- **moltbook/__init__.py** fait :
  - `from .moltbook_home_client import MoltbookHomeClient`
  - `from .moltbook_home_normalizer import MoltbookHomeNormalizer`
- Les implémentations sont dans **`memory/dsm/moltbook_home_client.py`** et **`memory/dsm/moltbook_home_normalizer.py`**, pas dans `memory/dsm/moltbook/`. Les imports relatifs `.moltbook_home_*` sont donc **cassés**.

### 6.5 modules/dsm_rm.py

- Fait `sys.path.insert(0, parent.parent)` (répertoire `memory/dsm`) puis :
  - `from shard_segments import ShardSegmentManager`
- `ShardSegmentManager` est défini dans **`core/shard_segments.py`**, pas dans un module top-level `shard_segments`. L’import devrait être par ex. `from core.shard_segments import ShardSegmentManager` (ou équivalent selon la stratégie de package choisie).

### 6.6 recycling_test.py

- `from dsm_recycling_memory import DSMRecyclingMemory`
- La classe est dans **`memory/dsm/modules/dsm_rm.py`**. Il n’existe pas de module `dsm_recycling_memory`. Import **cassé**.

### 6.7 Fichiers « core » et sécurité

- **cli.py** (racine dsm) : `from core.models import ...` etc. Fonctionne **uniquement** si le répertoire courant ou `sys.path` contient `memory/dsm` (alors `core` = `memory/dsm/core`). Cohérent avec un usage type « script lancé depuis memory/dsm ».
- **core/security.py** et **security.py** : listes de fichiers protégés en dur avec le préfixe **`dsm_v2/`** (ex. `dsm_v2/core/storage.py`). En déploiement sous Daryl (`memory/dsm/`), les chemins réels ne matchent pas ; la protection peut ne pas s’appliquer correctement.

### 6.8 ANS

- **ans/cli.py** et **ans/ans_test.py** : `sys.path.insert(0, dsm_v2_dir)` puis `from ans.ans_engine import ...`. Si `dsm_v2_dir = memory/dsm`, le package `ans` est bien trouvé. Les références à des chemins ou messages contenant `dsm_v2` restent des incohérences de nommage/documentation plutôt que des imports cassés.

---

## 7. Plan de refactor proposé

### 7.1 Choisir un nom de package unique

- **Option A — Garder `dsm_v2` comme nom logique**  
  - Ajouter un `pyproject.toml` (ou `setup.py`) à la racine du repo (ou sous `memory/`) qui définit un package installable nommé `dsm_v2`, dont les sources sont par ex. `memory/dsm` (structure de dossiers à ajuster si besoin pour que `import dsm_v2` résolve bien).
  - Ou : à la racine du repo, un symlink ou un répertoire `dsm_v2` qui pointe vers `memory/dsm`, et l’usage systématique de `PYTHONPATH=<repo_root>` pour que `import dsm_v2` fonctionne.
- **Option B — Renommer en `memory.dsm` (ou équivalent)**  
  - Remplacer partout `dsm_v2` par un nom aligné sur la structure (ex. `memory.dsm` si le repo root est sur `PYTHONPATH` et contient `memory/dsm`). Mettre à jour tous les imports, chemins dans la sécurité, et commentaires/CLI.

Recommandation : **Option A** si la compatibilité avec un runtime existant (ex. Clawdbot) qui utilise déjà `dsm_v2` est importante ; sinon **Option B** pour aligner le code sur l’arborescence Daryl.

### 7.2 Corriger les imports sans toucher au nom `dsm_v2`

Si on garde temporairement le nom `dsm_v2` mais qu’on veut que le projet soit exécutable depuis la racine du repo Daryl :

1. **Package installable**  
   - Créer `pyproject.toml` (ou `setup.py`) pour que `dsm_v2` soit le package correspondant à `memory/dsm` (ou à un répertoire `dsm_v2` qui pointe vers lui).  
   - Tous les imports `from dsm_v2....` restent alors valides une fois le package installé ou le path configuré.

2. **skills**  
   - Dans `skills/__init__.py` : utiliser des **imports relatifs** (ex. `from .models import ...`, `from .registry import ...`) et exporter aussi **`SkillRouter`** (ex. `from .router import SkillRouter` ; `__all__` = `["Skill", "SkillRegistry", "SkillRouter"]`).  
   - Supprimer la manipulation `sys.path` et le recours à `dsm_v2_dir` dans ce fichier si le package parent est correctement défini.

3. **Tests session**  
   - Remplacer `from session_graph import ...` par `from session.session_graph import ...` (et idem pour `session_limits_manager`).  
   - Si le répertoire de travail est `memory/dsm`, s’assurer que `memory/dsm` est sur `sys.path` (déjà le cas dans ces tests) pour que `session` soit bien `memory.dsm.session`.

4. **Moltbook**  
   - Soit déplacer `moltbook_home_client.py` et `moltbook_home_normalizer.py` **dans** `memory/dsm/moltbook/` (et garder `from .moltbook_home_client` / `.moltbook_home_normalizer`).  
   - Soit laisser les fichiers à la racine de `memory/dsm` et dans `moltbook/__init__.py` faire par ex. `from ..moltbook_home_client import ...` et `from ..moltbook_home_normalizer import ...`.

5. **modules/dsm_rm.py**  
   - Remplacer `from shard_segments import ShardSegmentManager` par un import depuis le core, ex. `from dsm_v2.core.shard_segments import ShardSegmentManager` (ou `from ..core.shard_segments import ShardSegmentManager` si on utilise des relatifs depuis un package `dsm_v2`).

6. **recycling_test.py**  
   - Remplacer `from dsm_recycling_memory import DSMRecyclingMemory` par ex. `from dsm_v2.modules.dsm_rm import DSMRecyclingMemory` (ou `from memory.dsm.modules.dsm_rm import ...` selon le nom de package retenu).

7. **Sécurité**  
   - Remplacer les chemins en dur `dsm_v2/core/...` par des chemins dérivés du **répertoire du package** (ex. `Path(__file__).resolve().parent`, puis `.../ "core" / "storage.py"`) ou par une constante unique (ex. `DSM_ROOT`) définie au chargement du module, pour que la protection reste valide que le package s’appelle `dsm_v2` ou soit sous `memory/dsm`.

### 7.3 Ordre de travail suggéré

1. Décider du nom de package (7.1) et créer `pyproject.toml` / structure si besoin.  
2. Corriger **moltbook** (déplacement ou imports relatifs) et **modules/dsm_rm** + **recycling_test**.  
3. Corriger **skills/__init__.py** (relatifs + export `SkillRouter`).  
4. Corriger tous les tests **session** (imports `session.session_graph`, `session.session_limits_manager`).  
5. Unifier les chemins dans **core/security** et **security.py** (relatifs ou `DSM_ROOT`).  
6. Lancer la suite de tests (tests_v2, test_imports, session tests, full_chain_validation, etc.) et corriger les derniers imports ou chemins résiduels.

---

## 8. Résumé

| Zone | Problème principal | Action proposée |
|------|--------------------|-----------------|
| **Package** | Nom `dsm_v2` alors que code sous `memory/dsm`, pas de package installable | Définir un package (pyproject/setup ou symlink) et/ou migrer vers un nom aligné (ex. `memory.dsm`) |
| **skills** | __init__ utilise `dsm_v2` et n’exporte pas `SkillRouter` | Imports relatifs + export `SkillRouter` |
| **Session tests** | Imports plats `session_graph`, `session_limits_manager` | Importer depuis `session.session_graph` / `session.session_limits_manager` |
| **moltbook** | Fichiers à la racine dsm, package attend des fichiers dans moltbook/ | Déplacer les modules dans moltbook/ ou importer depuis le parent |
| **modules/dsm_rm** | Import `shard_segments` top-level | Importer depuis `dsm_v2.core.shard_segments` (ou package choisi) |
| **recycling_test** | Module `dsm_recycling_memory` inexistant | Importer depuis `dsm_v2.modules.dsm_rm` (ou équivalent) |
| **Sécurité** | Chemins `dsm_v2/...` en dur | Chemins relatifs au package ou `DSM_ROOT` |

En appliquant ce plan, les imports et la cohérence entre l’arborescence Daryl (memory/dsm, agents/clawdbot/runtime, skills, modules) et le nom de package seront alignés, et les imports cassés listés seront corrigés.
