# État après alias dsm_v2 – Problèmes restants et patches minimaux

## Alias en place

- **`dsm_v2`** : symlink à la racine du repo vers `memory/dsm` (`/opt/daryl/dsm_v2 -> memory/dsm`).
- Avec **`PYTHONPATH=/opt/daryl`** (racine du repo), les imports `from dsm_v2.core.*`, `from dsm_v2.session.*`, `from dsm_v2.skills.*` fonctionnent.

## Problèmes restants (vérifiés)

| # | Problème | Cause |
|---|----------|--------|
| 1 | **`SkillRouter`** non exporté par `dsm_v2.skills` | `skills/__init__.py` n’exporte que `Skill` et `SkillRegistry`. |
| 2 | **`dsm_v2.modules.dsm_rm`** échoue au chargement | `from shard_segments import ShardSegmentManager` : le module est dans `core.shard_segments`, pas en top-level. |
| 3 | **`dsm_v2.moltbook`** échoue au chargement | `moltbook/__init__.py` fait `.moltbook_home_client` alors que les fichiers sont à la racine de `dsm` (`moltbook_home_client.py`), pas dans `moltbook/`. |
| 4 | **`recycling_test.py`** | `from dsm_recycling_memory import DSMRecyclingMemory` : module inexistant ; la classe est dans `dsm_v2.modules.dsm_rm`. |
| 5 | **Tests « session »** | Ils ajoutent `memory/dsm` au path puis `from session_graph import` / `from session_limits_manager import` ; ces modules sont dans `session/`, pas à la racine de dsm. |
| 6 | **Scripts « from skills »** avec path = `memory/dsm` | Ils font `from skills import ...` ; `skills/__init__.py` fait ensuite `from dsm_v2.skills...`, mais `dsm_v2` n’est pas sur le path (seul `memory/dsm` l’est). |
| 7 | **full_chain_validation.py** | `base_dir = dirname(dirname(__file__))` → `memory` ; il ajoute donc `memory/` au path, pas `memory/dsm`, donc `from skills` ne résout pas. |

## Patches minimaux proposés

- **Pas de refactor d’architecture** : uniquement corrections d’imports et de path pour que les usages existants passent.

---

### Patch 1 – `memory/dsm/skills/__init__.py`

- **Objectif** : exporter `SkillRouter` et faire que `from dsm_v2.skills...` fonctionne quand seul `memory/dsm` est sur le path (en ajoutant la racine du repo au path).
- **Modifications** :
  - Ajouter la racine du repo à `sys.path` (ex. 4× `dirname` à partir de `__file__` résolu, pour remonter de `.../memory/dsm/skills` à la racine).
  - Importer et réexporter `SkillRouter` depuis `dsm_v2.skills.router` (ou `.router` en relatif) et l’ajouter à `__all__`.

---

### Patch 2 – `memory/dsm/modules/dsm_rm.py`

- **Objectif** : faire résoudre l’import de `ShardSegmentManager`.
- **Modification** : remplacer  
  `from shard_segments import ShardSegmentManager`  
  par  
  `from dsm_v2.core.shard_segments import ShardSegmentManager`  
  ou, si le module est toujours chargé comme sous-package de `dsm_v2`, par  
  `from ..core.shard_segments import ShardSegmentManager`.  
  Supprimer ou garder le `sys.path.insert` selon besoin (si tout est lancé via `dsm_v2`, le relatif suffit).

---

### Patch 3 – `memory/dsm/moltbook/__init__.py`

- **Objectif** : importer les implémentations qui sont à la racine de `dsm`.
- **Modification** : remplacer  
  `from .moltbook_home_client import ...` et `from .moltbook_home_normalizer import ...`  
  par  
  `from ..moltbook_home_client import MoltbookHomeClient` et  
  `from ..moltbook_home_normalizer import MoltbookHomeNormalizer`.

---

### Patch 4 – `memory/dsm/recycling_test.py`

- **Objectif** : importer la classe depuis le bon module.
- **Modifications** :
  - Ajouter la racine du repo à `sys.path` (ex. `Path(__file__).resolve().parent.parent.parent`).
  - Remplacer  
    `from dsm_recycling_memory import DSMRecyclingMemory`  
    par  
    `from dsm_v2.modules.dsm_rm import DSMRecyclingMemory`.

---

### Patch 5 – Tests session (imports plats → dsm_v2.session + repo root)

- **Fichiers** :  
  `session_test_runner.py`, `session_test_home_real.py`, `session_stress_test.py`,  
  `session_dedup_test.py`, `session_dedup_validation_test.py`, `session_cooldown_test.py`,  
  `real_moltbook_observation_test.py`, `moltbook_observation_runner.py`.
- **Modification** :  
  - Ajouter la racine du repo à `sys.path` (ex. `Path(__file__).resolve().parent.parent.parent`) pour que `dsm_v2` soit importable.  
  - Remplacer `from session_graph import SessionGraph` par `from dsm_v2.session.session_graph import SessionGraph`.  
  - Remplacer `from session_limits_manager import SessionLimitsManager` par `from dsm_v2.session.session_limits_manager import SessionLimitsManager`.  
  (On utilise `dsm_v2.session` et non `session` seul car avec path = `memory/dsm`, le sous-package `session` n’a pas de parent package reconnu et les imports relatifs `..core` dans `session_graph.py` échouent.)

---

### Patch 6 – `memory/dsm/skills/__init__.py` (path pour `dsm_v2`)

- **Objectif** : que les scripts qui n’ajoutent que `memory/dsm` au path puissent faire `from skills import ...` et que le `from dsm_v2.skills...` interne réussisse.
- **Modification** : au début du fichier (avant tout import depuis `dsm_v2`), ajouter la racine du repo à `sys.path` :  
  `_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__))))))`  
  puis `sys.path.insert(0, _repo_root)` (une seule fois, en tête si besoin).  
  Ainsi, quand le répertoire courant ou le path ne contient que `memory/dsm`, `import dsm_v2` pourra quand même résoudre via le symlink à la racine.

---

### Patch 7 – `memory/dsm/full_chain_validation.py`

- **Objectif** : que `from skills import ...` résolve bien `memory/dsm/skills`.
- **Modification** : remplacer  
  `base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`  
  par  
  `base_dir = os.path.dirname(os.path.abspath(__file__))`  
  pour que `base_dir` soit `memory/dsm` et que l’insertion dans `sys.path` permette de trouver le package `skills`.

---

## Résumé

- **Résolus par l’alias** : tous les usages qui lancent avec `PYTHONPATH=/opt/daryl` et `from dsm_v2....` (trace_replay, tests_v2, cli, etc.) fonctionnent.
- **Corrigés par les patches ci-dessus** : export de `SkillRouter`, import dans `dsm_rm`, imports dans `moltbook`, recycling_test, tests session (repo root + `dsm_v2.session.*`), path dans `skills/__init__.py` pour le cas « path = memory/dsm », et `base_dir` dans full_chain_validation.
- **Problème préexistant (hors périmètre)** : `test_imports.py` attend `SkillIngestionReport` depuis `skills.ingestor`, mais ce nom n’existe pas dans `ingestor.py` ; à corriger soit dans le test soit en exposant le bon type depuis le module.
