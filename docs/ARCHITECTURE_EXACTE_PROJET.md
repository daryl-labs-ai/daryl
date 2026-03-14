# Architecture exacte du projet Daryl

Référence unique pour la structure réelle du dépôt et des couches. Le **noyau DSM** (`memory/dsm/core/`) est **gelé** (mars 2026) et ne doit pas être modifié.

---

## 1. Arborescence du dépôt

```
/opt/daryl/
├── AGENTS.md                 # Guide pour agents AI (DSM, sessions, skills)
├── ARCHITECTURE.md           # Vue d’ensemble Daryl (concepts, runtime)
├── HEARTBEAT.md
├── pyproject.toml            # Package dsm-v2, entry point: dsm = dsm_v2.cli:main_dsm
├── .gitignore
│
├── agents/                   # Runtimes agents (ex. Clawdbot)
│   └── clawdbot/             # Lien ou répertoire vers runtime de prod
│
├── data/                     # Données DSM (générées à l’exécution)
│   ├── integrity/            # Dernier hash par shard (default_last_hash.json)
│   ├── security/             # Baseline, audit, policy (integrity.json, audit.jsonl)
│   └── shards/               # Shards segmentés (ex. default/default_0001.jsonl)
│
├── docs/
│   ├── ARCHITECTURE_ANALYSIS.md
│   ├── ARCHITECTURE_EXACTE_PROJET.md   # Ce document
│   ├── DSM_FULL_SYSTEM_AUDIT.md
│   ├── DSM_FUTURE_ARCHITECTURE.md
│   ├── DSM_MEMORY_LEDGER.md
│   ├── LAB_TO_DARYL_MIGRATION_PLAN.md
│   ├── RR_INTEGRATION_SPEC.md
│   ├── architecture/         # Spécifications DSM, RR, VM, audits
│   │   ├── DSM_ARCHITECTURE_MAP.md     # Carte d’architecture de référence
│   │   ├── DSM_KERNEL_FREEZE_2026_03.md
│   │   ├── DSM_STABILIZATION_ROADMAP.md
│   │   ├── RR_ARCHITECTURE.md
│   │   ├── RR_* (index, navigator, query, context)
│   │   └── ...
│   ├── modules/              # Modules cognitifs futurs (documentation)
│   │   ├── DARYL_COGNITIVE_ARCHITECTURE.md
│   │   ├── DSM_RR_READ_RELAY.md
│   │   ├── PERSONALITY_ENGINE.md
│   │   ├── WORLD_MODEL_ENGINE.md
│   │   ├── SKILL_DISCOVERY_ENGINE.md
│   │   ├── SKILL_LIBRARY.md
│   │   └── TIME_TRAVEL_MEMORY.md
│   └── roadmap/
│       ├── README.md
│       ├── DSM_STABILIZATION_ROADMAP.md
│       └── PDSM_PORTABLE_DSM.md
│
├── memory/
│   └── dsm/                  # Package principal (installé comme dsm_v2)
│       ├── __init__.py       # Exporte Storage, Entry, ShardMeta
│       ├── cli.py            # Point d’entrée CLI (dsm)
│       ├── security.py       # Raccourci / façade sécurité (hors core)
│       │
│       ├── core/             # ★ NOYAU GELÉ — Ne pas modifier
│       │   ├── KERNEL_VERSION
│       │   ├── models.py     # Entry, ShardMeta
│       │   ├── storage.py    # Storage: append, read, list_shards, segments
│       │   ├── shard_segments.py  # ShardSegmentManager, rotation
│       │   ├── signing.py    # Chaîne de hash (Signing)
│       │   ├── replay.py     # Replay de traces (verify_record, replay_session)
│       │   ├── security.py   # SecurityLayer, baseline, audit, protected files
│       │   └── session.py   # (si présent: suivi heartbeat / kernel)
│       │
│       ├── session/          # Couche session (au-dessus du noyau)
│       │   ├── session_graph.py      # SessionGraph: start_session, snapshot, execute_action, end_session
│       │   └── session_limits_manager.py
│       │
│       ├── rr/               # Read Relay — navigation mémoire (lecture seule)
│       │   ├── relay.py              # DSMReadRelay
│       │   ├── index/                # RRIndexBuilder
│       │   ├── navigator/            # RRNavigator
│       │   ├── query/                # RRQueryEngine
│       │   └── context/              # RRContextBuilder
│       │
│       ├── block_layer/      # Optionnel — batching en blocs (expérimental)
│       │   ├── manager.py    # BlockManager, BlockConfig
│       │   └── benchmark.py
│       │
│       ├── skills/           # Registry, router, ingestor, télémetrie
│       │   ├── registry.py   # SkillRegistry
│       │   ├── router.py    # SkillRouter
│       │   ├── ingestor.py  # Chargement depuis bibliothèques
│       │   ├── skill_usage_logger.py / skill_success_logger.py
│       │   ├── success_analyzer.py
│       │   ├── skill_graph.py
│       │   ├── anthropic_parser.py
│       │   ├── cli.py
│       │   └── libraries/
│       │       ├── anthropic/   # skills/*.json, manifest.json
│       │       ├── community/
│       │       └── custom/
│       │
│       ├── ans/              # Audience Neural System — analyse de performance
│       │   ├── ans_models.py
│       │   ├── ans_analyzer.py
│       │   ├── ans_scorer.py
│       │   ├── ans_engine.py
│       │   └── cli.py
│       │
│       ├── moltbook/         # Client / normaliseur Moltbook (observations)
│       │   └── (MoltbookHomeClient, MoltbookHomeNormalizer)
│       │
│       ├── modules/         # Modules utilitaires (ex. dsm_rm)
│       │   └── dsm_rm.py
│       │
│       ├── storage/         # Réexport / usage ShardSegmentManager (compat)
│       │   └── __init__.py
│       │
│       ├── tests_v2/        # Tests unitaires DSM (core, security, replay)
│       └── *.py             # Scripts de test, runners (session_*, moltbook_*, etc.)
│
├── modules/                 # Composants réutilisables (hors DSM)
├── skills/                  # Skills agents (futur)
├── examples/                # Exemples d’agents
│
└── tests/                   # Tests d’intégration
    ├── clawdbot_dsm_session_test.py
    ├── dsm_rr_test.py
    └── rr/                  # Tests RR (index, navigator, query, resolve)
```

---

## 2. Couches d’architecture (de haut en bas)

| Couche | Répertoire / composant | Rôle |
|--------|------------------------|------|
| **Agents** | `agents/` | Runtimes (ex. Clawdbot) qui utilisent mémoire et skills. |
| **Skills / ANS** | `memory/dsm/skills/`, `memory/dsm/ans/` | Registry de skills, router, télémetrie usage/succès, apprentissage (ANS). |
| **Context Packs** | (prévu) | Transformation de la mémoire DSM en contexte prêt pour LLM. |
| **RR (Read Relay)** | `memory/dsm/rr/` | Navigation lecture seule : read_recent, summary, index, navigator, query, context. |
| **Block Layer** | `memory/dsm/block_layer/` | Batching optionnel en blocs (expérimental). |
| **Session** | `memory/dsm/session/` | SessionGraph : start_session, snapshot, tool_call, end_session. |
| **Security** | `memory/dsm/core/security.py` | Baseline d’intégrité, audit, fichiers protégés, rate limiting (dans le noyau gelé). |
| **DSM Core** | `memory/dsm/core/` | **Noyau gelé** : Storage, models, segments, signing, replay, security. |
| **Stockage** | Fichiers sous `data/` | JSONL append-only par shard/famille, métadonnées d’intégrité. |

Les couches supérieures n’utilisent que l’API publique du noyau (Storage : append, read, list_shards, get_shard_size).

---

## 3. Package Python `dsm_v2`

- **Nom installé :** `dsm-v2` (pyproject.toml).
- **Entry point CLI :** `dsm = dsm_v2.cli:main_dsm`.
- **Racine package :** le code vit sous `memory/dsm/` mais le package importable est `dsm_v2` (mapping via setuptools/pyproject).

**Exports principaux (depuis `memory/dsm/__init__.py`) :**

- `Storage`, `Entry`, `ShardMeta` (depuis `core`).

**Modules clés :**

- `dsm_v2.core` — Storage, Entry, ShardMeta (core n’expose pas signing/replay/security dans __all__ par défaut, mais ils sont dans le même répertoire gelé).
- `dsm_v2.session` — SessionGraph, SessionLimitsManager.
- `dsm_v2.skills` — Skill, SkillRegistry, SkillRouter (et ingestor, loggers).
- `dsm_v2.rr` — DSMReadRelay ; sous-modules index, navigator, query, context.
- `dsm_v2.ans` — ANSEngine, modèles, analyseur, scorer.

---

## 4. Noyau gelé (`memory/dsm/core/`)

Fichiers **non modifiables** sans processus d’évolution du noyau :

| Fichier | Rôle |
|---------|------|
| `storage.py` | Append/read/list, JSONL append-only, coordination segments. |
| `shard_segments.py` | Layout segments, rotation, résolution O(1) du segment actif. |
| `models.py` | Entry, ShardMeta (et types liés intégrité). |
| `signing.py` | Chaîne de hash SHA-256 (Signing). |
| `replay.py` | Vérification et replay de traces (audit). |
| `security.py` | SecurityLayer, baseline, audit, fichiers protégés. |
| `KERNEL_VERSION` | Marqueur version (ex. 1.0, 2026-03-14). |

Référence : `docs/architecture/DSM_KERNEL_FREEZE_2026_03.md`.

---

## 5. Données et stockage

- **Shards :** `data/shards/<shard_id>/<shard_id>_NNNN.jsonl` (segments).
- **Intégrité :** `data/integrity/` (dernier hash par shard, etc.).
- **Sécurité :** `data/security/` (baseline, audit, policy).
- **Traces :** fichiers trace JSONL (replay) et logs skills/ANS en dehors des shards kernel.

Le noyau ne fait qu’append et lecture ; pas de recherche ni d’index dans le kernel.

---

## 6. Flux résumé

```
Utilisateur → Agent (ex. Clawdbot)
    → Planner / Skill Router
    → Skills
    → Session (SessionGraph) / Storage.append
    → DSM Kernel (Storage)
    → data/shards, data/integrity

Lecture / navigation :
    Agent ou outil
    → RR (DSMReadRelay) ou Storage.read
    → DSM Kernel (read, list_shards)
    → data/shards
```

---

## 7. Documents de référence

| Document | Contenu |
|----------|---------|
| `AGENTS.md` | Comment les agents utilisent DSM (sessions, écriture, lecture, skills). |
| `docs/architecture/DSM_ARCHITECTURE_MAP.md` | Carte d’architecture officielle, couches, règles. |
| `docs/architecture/DSM_KERNEL_FREEZE_2026_03.md` | Périmètre du gel, garanties, limitations. |
| `docs/modules/DARYL_COGNITIVE_ARCHITECTURE.md` | Vision future : User → Planner → Skills → DSM → RR → World Model → Skill Discovery. |

---

*Dernière mise à jour : d’après l’état du dépôt et la documentation d’architecture existante.*
