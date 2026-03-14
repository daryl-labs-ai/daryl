# Audit du dépôt Daryl

Rapport d’audit : incohérences d’architecture, logique dupliquée, imports cassés, tests manquants et améliorations structurelles proposées. **Aucune modification du noyau DSM (memory/dsm/core) n’est recommandée sans justification explicite.**

---

## 1. Incohérences d’architecture

### 1.1 Package `storage/` vs `core/shard_segments`

- **ARCHITECTURE.md** et **docs/ARCHITECTURE_ANALYSIS.md** décrivent un package **storage/** qui « contient le gestionnaire de segments ».
- **Fait** : `memory/dsm/storage/__init__.py` fait `from .shard_segments import ShardSegmentManager`, mais il n’existe **pas** de fichier `memory/dsm/storage/shard_segments.py`. Le seul fichier est **core/shard_segments.py**.
- **Conséquence** : `import dsm_v2.storage` lève `ModuleNotFoundError: No module named 'dsm_v2.storage.shard_segments'`.
- **Cohérence** : Le noyau utilise uniquement `core/shard_segments` (ex. `core/storage.py`). Le package `storage/` est donc redondant et cassé.

**Recommandation** : Supprimer le package `storage/` ou le faire réexporter depuis le core, sans dupliquer de code dans core. Exemple (hors core) : dans `storage/__init__.py`, remplacer par `from dsm_v2.core.shard_segments import ShardSegmentManager` (ou équivalent selon résolution du nom de package). Ne pas ajouter de fichier dans **core** pour ça.

---

### 1.2 Deux notions de « session »

- **core/session.py** : `SessionTracker` + dataclass `Session` (sessions avec heartbeats, state file, stabilité).
- **session/session_graph.py** : `SessionGraph` (cycle session_start / snapshot / tool_call / session_end, écriture dans le shard `sessions`).

Les deux coexistent ; la CLI (dsm_v2) utilise **SessionTracker** (core), tandis que les scripts de test et le trace_replay utilisent **SessionGraph** (session/). Même vocabulaire (« session ») pour deux mécanismes différents.

**Recommandation** : Documenter clairement la différence (SessionTracker = état runtime / heartbeats ; SessionGraph = log d’événements par session) dans ARCHITECTURE.md ou AGENTS.md, et à terme envisager un renommage ou un regroupement conceptuel pour éviter la confusion. Pas de changement dans le kernel core sans décision d’architecture.

---

### 1.3 Deux implémentations SecurityLayer

- **memory/dsm/security.py** (racine dsm) : `SecurityLayer` avec `allow_writes` / `deny_writes` (contextvar), `CRITICAL_FILES`, etc.
- **memory/dsm/core/security.py** : autre `SecurityLayer` avec `PROTECTED_WRITE_FILES`, API légèrement différente.

La CLI (`cli.py`) importe `from core.security import SecurityLayer` (donc **core**). Plusieurs tests et références parlent de « dsm_v2/core/security.py ». La présence de **deux** fichiers security (racine + core) crée un risque de divergence et de mauvaise utilisation.

**Recommandation** : Choisir une seule source de vérité (idéalement **core/security.py** pour le kernel) et soit déprécier soit faire déléguer `memory/dsm/security.py` vers core, sans dupliquer la logique de protection dans core. Les changements restent en dehors du « kernel » au sens strict (core/storage, core/models, core/signing).

---

### 1.4 Dossiers racine vides ou sous-utilisés

- **modules/** (racine) : vide (aucun composant réutilisable).
- **skills/** (racine) : vide. ARCHITECTURE indique « future agent skills » alors que les skills vivent sous **memory/dsm/skills/**.
- **examples/** : vide.

**Recommandation** : Soit alimenter ces dossiers (ex. un exemple minimal, un module réutilisable), soit mettre à jour ARCHITECTURE.md pour indiquer qu’ils sont réservés / à venir, pour éviter l’impression d’incohérence.

---

## 2. Logique dupliquée

### 2.1 Manipulation de `sys.path`

De nombreux fichiers font `sys.path.insert(0, ...)` pour rendre importables `dsm_v2`, `skills`, `core`, etc. :

- **skills/** : `__init__.py`, `router.py`, `registry.py`, `ingestor.py`, `skill_usage_logger.py`, `skill_success_logger.py`, `success_analyzer.py`, `skill_graph.py`, `cli.py` ; sous-dossier **browser**.
- **Tests / scripts** : `session_*_test.py`, `moltbook_observation_runner.py`, `full_chain_validation.py`, `recycling_test.py`, `modules/dsm_rm.py`, `ans/cli.py`, `ans/ans_test.py`, etc.

**Recommandation** : À long terme, s’appuyer sur un seul schéma d’installation (package `dsm_v2` installable, `pip install -e .`) et des imports absolus `dsm_v2.*`, en réduisant les `sys.path.insert` au strict minimum (ex. scripts de test legacy). Cela réduit la duplication et les chemins magiques.

---

### 2.2 Imports relatifs vs absolus (skills)

- Certains fichiers sous **skills/** utilisent des imports « plats » après `sys.path.insert(0, skills_dir)` : `from models import Skill`, `from registry import ...`, `from skill_usage_logger import ...`.
- D’autres utilisent `dsm_v2.skills.*` (ex. `skills/cli.py`, `skills/__init__.py`).

Mélange de styles selon le contexte d’exécution (path = répertoire skills vs path = racine avec dsm_v2).

**Recommandation** : Unifier en `from dsm_v2.skills.*` (ou relatifs `from .models import ...`) une fois le package correctement installable, et faire évoluer les tests pour lancer avec le package installé.

---

## 3. Imports cassés ou fragiles

### 3.1 `dsm_v2.storage`

- **Problème** : `storage/__init__.py` fait `from .shard_segments import ShardSegmentManager` alors qu’il n’y a pas de `storage/shard_segments.py`.
- **Impact** : Tout code qui fait `from dsm_v2.storage import ...` ou `import dsm_v2.storage` échoue.

**Correctif proposé (hors core)** : Dans `memory/dsm/storage/__init__.py`, remplacer par un réexport depuis le core, par ex. `from dsm_v2.core.shard_segments import ShardSegmentManager`. Aucun nouveau fichier dans **core**.

---

### 3.2 `Skill` vs ingestor (skills)

- **skills/models.py** : `Skill` a les champs `skill_id`, `domain`, `description`, `trigger_conditions`, etc. (pas de `name` ni `category`).
- **skills/ingestor.py** : Construit des instances avec `Skill(skill_id=..., name=..., description=..., trigger_conditions=..., category=...)`. Les champs `name` et `category` n’existent pas sur le dataclass actuel.

**Conséquence** : `ingest_from_file` / `ingest_from_directory` qui construisent un `Skill` avec `name` et `category` lèveront une erreur au moment de l’instanciation si on utilise le modèle actuel.

**Recommandation** : Aligner l’ingestor sur le modèle : utiliser `domain` (et éventuellement un alias `name` → `description` ou `domain`) et supprimer ou mapper `category` vers `domain` ou `tags`. Changement uniquement dans **skills/** (ingestor / modèles), pas dans core.

---

### 3.3 `test_imports.py` et `SkillIngestionReport`

- Le test attend `from skills.ingestor import SkillIngestor, SkillIngestionReport`.
- **SkillIngestionReport** n’existe pas dans `skills/ingestor.py`.

**Recommandation** : Soit ajouter un type/rapport `SkillIngestionReport` (ou équivalent) dans ingestor et l’exporter, soit adapter le test pour ne pas importer ce nom. Pas de changement dans core.

---

### 3.4 Dépendance au répertoire courant pour `core` et `session`

- **cli.py** (racine dsm) : `from core.models import ...`, `from core.storage import ...`, `from core.session import SessionTracker`, `from core.security import SecurityLayer`. Ces imports supposent que le répertoire contenant `core/` est sur `sys.path` (souvent en lançant depuis `memory/dsm` ou après un `sys.path.insert(0, ...)`).
- Cohérent avec l’usage actuel (CLI lancée comme `python -m dsm_v2` avec symlink dsm_v2 → memory/dsm), mais fragile si on change le répertoire de travail ou le path.

**Recommandation** : À terme, passer à des imports `from dsm_v2.core import ...` partout une fois le package installé, pour ne plus dépendre du répertoire courant.

---

## 4. Tests manquants ou fragiles

### 4.1 Couverture

- **core** : Des tests existent dans **tests_v2/** (append_only, replay, security). Pas de suite unifiée (pytest non utilisé par défaut dans l’audit).
- **session** : Plusieurs scripts manuels (session_test_runner, session_stress_test, session_dedup_test, etc.) ; pas de découverte automatique type pytest par répertoire.
- **skills** : test_imports, test_ingestion, skills_test, skills_success_test, skills_graph_test, etc., dispersés à la racine de **memory/dsm/** ; **test_imports** échoue à cause de `SkillIngestionReport`.
- **ans** : ans_test.py présent ; pas de lien évident avec une suite globale.
- **CLI `dsm`** : Pas de tests automatisés pour les commandes (status, read, append, replay, inspect, tail).

**Recommandation** :  
- Unifier la découverte des tests (par ex. `tests/` à la racine + `memory/dsm/tests_v2/` et éventuellement `memory/dsm/test_*.py` en pytest).  
- Corriger ou adapter **test_imports** (SkillIngestionReport).  
- Ajouter des tests minimaux pour la CLI (ex. `dsm status`, `dsm read`, `dsm append` + `dsm read`).

---

### 4.2 Emplacement des tests

- **ARCHITECTURE** : « tests/ validation and stress tests ».
- **Réalité** : Un seul script dans **tests/** (`clawdbot_dsm_session_test.py`) ; la majorité des tests sont dans **memory/dsm/** (test_*.py, *_test.py, tests_v2/).

**Recommandation** : Documenter dans ARCHITECTURE.md que les tests DSM sont principalement sous **memory/dsm/** (et éventuellement sous **tests/** pour les tests d’intégration cross-repo), ou déplacer progressivement les tests vers **tests/** avec une structure claire (sans modifier le kernel, seulement l’organisation des fichiers de test).

---

## 5. Améliorations structurelles suggérées

### 5.1 Noyau DSM (memory/dsm/core)

- **Ne pas modifier** le kernel (storage, models, signing, shard_segments, replay) sans justification (ex. correctif de bug, sécurité). Les changements proposés ci-dessus (storage/, security, session) restent en dehors du « cœur » ou en réexport / délégation.

### 5.2 Package `storage/`

- **Option A** : Supprimer le package **memory/dsm/storage/** et ne garder que **core/shard_segments** (et les imports existants dans core). Mettre à jour la doc.
- **Option B** : Garder **storage/** comme façade : dans `storage/__init__.py` faire `from dsm_v2.core.shard_segments import ShardSegmentManager` (et éventuellement `__all__ = ["ShardSegmentManager"]`). Aucun nouveau fichier dans core.

### 5.3 Sécurité

- Unifier sur **core/security.py** comme référence et faire en sorte que **memory/dsm/security.py** (s’il est conservé) délègue ou réexporte depuis core, sans dupliquer la logique de protection. Documenter quel fichier est la référence.

### 5.4 Skills : modèle et ingestor

- Aligner **skills/ingestor.py** sur **skills/models.Skill** (plus de `name`/`category` non définis).
- Exposer ou adapter **SkillIngestionReport** (ou équivalent) pour que **test_imports** et les usages existants restent valides.

### 5.5 Documentation

- **ARCHITECTURE.md** : Préciser la différence SessionTracker (core) vs SessionGraph (session/) ; indiquer l’état des dossiers **modules/**, **skills/**, **examples/** (vides ou à venir).
- **AGENTS.md** : Déjà utile ; y ajouter une phrase sur le shard dédié Clawdbot (`clawdbot_sessions`) si ce n’est pas déjà fait.
- **docs/** : Conserver et mettre à jour **REMAINING_ISSUES_AND_PATCHES.md** et **CLAWDBOT_DSM_INTEGRATION.md** en fonction des correctifs appliqués.

### 5.6 Tests

- Corriger **test_imports** (SkillIngestionReport ou assertion).
- Ajouter une suite minimale pour la CLI (dsm status, read, append).
- Documenter comment lancer tous les tests (unittest vs pytest, PYTHONPATH, répertoire courant).

---

## 6. Synthèse

| Catégorie              | Problème principal                                      | Action proposée (hors kernel core)                    |
|------------------------|---------------------------------------------------------|------------------------------------------------------|
| Architecture           | Package **storage/** cassé (fichier manquant)          | Réexporter depuis core ou supprimer storage/        |
| Architecture           | Deux « session » (SessionTracker vs SessionGraph)      | Documenter ; pas de changement core                 |
| Architecture           | Deux SecurityLayer (racine + core)                     | Unifier / déléguer ; doc                             |
| Architecture           | Dossiers racine vides (modules, skills, examples)      | Alimenter ou documenter                              |
| Duplication            | Beaucoup de `sys.path.insert`                           | Réduire via package installable et imports absolus  |
| Duplication            | Mélange imports plats vs dsm_v2 dans skills             | Unifier (dsm_v2.skills ou relatifs)                 |
| Imports cassés         | `dsm_v2.storage`                                        | Corriger storage/__init__.py (réexport core)         |
| Imports cassés         | Skill (name, category) dans ingestor vs models          | Aligner ingestor sur Skill (domain, etc.)            |
| Imports cassés         | test_imports + SkillIngestionReport                     | Ajouter type ou adapter le test                      |
| Tests manquants        | Pas de tests CLI dsm                                    | Ajouter tests minimaux (status, read, append)        |
| Tests manquants        | test_imports en échec                                   | Corriger import ou type                              |
| Structure              | Tests dispersés (memory/dsm vs tests/)                  | Documenter ou regrouper progressivement              |

Aucune modification du **noyau DSM** (memory/dsm/core) n’est recommandée sans raison explicite (correctif de bug ou sécurité). Les changements proposés concernent **storage/** (réexport ou suppression), **security** (délégation), **skills** (ingestor + modèle + test_imports), **documentation** et **tests**.
