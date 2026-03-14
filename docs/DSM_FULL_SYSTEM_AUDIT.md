# DSM — Full System Audit

**Type:** Read-only architecture audit. Aucune modification de code.

**Date:** 2025-03-13

**Objectif:** Comprendre l’architecture complète du dépôt Daryl/DSM (Daryl Sharding Memory) pour les couches futures (RR, Context Packs, ANS).

---

## 1. Global Architecture

### 1.1 Vue d’ensemble

DSM est un **noyau de mémoire déterministe** (append-only) conçu pour les agents IA. Le dépôt contient le noyau « gelé », des couches optionnelles (block layer, RR), le cycle de vie des sessions, la sécurité et le replay, ainsi que des modules expérimentaux ou lab (skills, ANS, Moltbook, tests).

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AGENTS / RUNTIME                                 │
│                    (ex: Clawdbot, intégrations)                         │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  SKILLS / ANS (optionnel, hors kernel)                                  │
│  Registry, Router, Ingestor, Usage/Success loggers, SkillGraph, ANS     │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  CONTEXT PACKS (prévu, non implémenté)                                  │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  RR — Read Relay (Step 1 implémenté)                                     │
│  DSMReadRelay: read_recent(), summary() — Storage.read() uniquement     │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  BLOCK LAYER (expérimental)                                              │
│  BlockManager: buffer → flush par blocs via Storage.append()             │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  SESSION LAYER                                                           │
│  SessionGraph, SessionLimitsManager — shard "sessions"                   │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  SECURITY LAYER (kernel + façade)                                        │
│  Baseline, intégrité fichiers critiques, audit, rate limit, protected   │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  DSM CORE (kernel gelé)                                                 │
│  Storage, Entry/ShardMeta, ShardSegmentManager, Signing, Replay,         │
│  SessionTracker (runtime), SecurityLayer                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  PERSISTANCE                                                             │
│  data/shards/<family>/<family>_NNNN.jsonl, data/integrity/*_last_hash.json│
│  data/security/integrity.json, audit.jsonl, policy.json                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Rôles des couches

| Couche | Rôle |
|--------|------|
| **DSM Core** | Stockage append-only JSONL, modèles Entry/ShardMeta, segmentation des shards, chaîne de hash par shard, calcul et vérification d’intégrité. Aucune requête ni index ; uniquement append et read récents. |
| **Block Layer** | Agrège des entrées en blocs (une entrée = un bloc JSON `{"block": true, "entries": [...]}`) et appelle `Storage.append()` pour chaque bloc. Shards dédiés (suffixe `_block`). Ne modifie pas le core. |
| **Storage (API)** | `Storage.append(entry)`, `Storage.read(shard_id, limit)`, `Storage.list_shards()`, `Storage.get_shard_size()`. Point d’entrée unique pour écriture et lecture des shards. |
| **Session Layer** | SessionGraph : start_session, record_snapshot, execute_action, end_session. Écrit dans le shard `sessions` via Storage. SessionLimitsManager : cooldown home poll, cooldown actions, budget journalier. |
| **Security Layer** | Vérification d’intégrité des fichiers critiques (baseline), garde d’écriture sur fichiers protégés, audit JSONL, rate limiting (API/writes), gate de mise à jour de baseline (git propre, --reason, "I UNDERSTAND"). Les shards ne sont pas dans la baseline (protégés par la chaîne de hash). |
| **Replay Layer** | Deux mécanismes : (1) **core/replay.py** : replay de traces **trace_log.jsonl** (format TraceRecord avec prev_step_hash/step_hash) — audit d’une session de trace ; (2) **trace_replay.py** (script) : lecture des événements du shard `sessions` par session_id, vérification de la hash chain et de la séquence d’événements. |

### 1.3 Emplacement du code

- **Package installé :** `dsm-v2` (nom PyPI), point d’entrée CLI `dsm` → `dsm_v2.cli:main_dsm`.
- **Sources :** Le dépôt contient à la fois `memory/dsm/` et (dans SOURCES.txt) `dsm_v2/` ; les imports utilisent le préfixe `dsm_v2`. La référence architecturale est **memory/dsm/** ; le noyau et les couches stables sont sous `memory/dsm/core/`, `memory/dsm/session/`, `memory/dsm/rr/`, `memory/dsm/block_layer/`, etc.

---

## 2. Storage System

### 2.1 Classes principales

- **`Storage`** (`memory/dsm/core/storage.py`)  
  - `__init__(self, data_dir="data")`  
  - Crée `data_dir`, `data_dir/shards`, `data_dir/integrity` et une instance de `ShardSegmentManager(base_dir=data_dir)`.

- **`Entry`** (`memory/dsm/core/models.py`)  
  - Champs : `id`, `timestamp`, `session_id`, `source`, `content`, `shard`, `hash`, `prev_hash`, `metadata`, `version`.

- **`ShardMeta`** (`memory/dsm/core/models.py`)  
  - Champs : `shard_id`, `created_at`, `last_updated`, `entry_count`, `size_bytes`, `integrity_status`.

- **`ShardSegmentManager`** (`memory/dsm/core/shard_segments.py`)  
  - Gère la segmentation par famille de shards (répertoire par shard, fichiers `*_NNNN.jsonl`).  
  - Utilisé par Storage pour obtenir le segment actif et itérer sur les événements.

### 2.2 Mécanisme d’append (pas de « append_event » explicite)

Il n’existe pas de méthode nommée `append_event`. L’unique point d’écriture public est :

- **`Storage.append(entry: Entry) -> Entry`**
  1. Calcule `entry.hash` (SHA-256 du `content`) si absent.
  2. Détermine le shard : `entry.shard or "default"`.
  3. Obtient le segment actif via `segment_manager.get_active_segment(shard)`.
  4. Charge le dernier hash du shard depuis `data/integrity/{shard_id}_last_hash.json`.
  5. Met à jour `entry.prev_hash`.
  6. Ouvre le fichier segment en mode `'a'`, écrit une ligne JSON (entry sérialisée), ferme.
  7. Met à jour `_set_last_hash(shard, entry.hash)`.
  8. Met à jour les métadonnées du shard (`_update_shard_metadata`).

Donc : **un append = une ligne JSONL ajoutée** dans le segment actif du shard ; la chaîne de hash est maintenue par shard via les fichiers `*_last_hash.json`.

### 2.3 Création de « blocs » (fichiers segments)

Les **segments** (fichiers) sont créés par `ShardSegmentManager` :

- Répertoire par shard : `shards/<family>/` avec `family = shard_id.replace("shard_", "")` (ex. shard `sessions` → `shards/sessions/`).
- Fichiers : `<family>_0001.jsonl`, `<family>_0002.jsonl`, …
- Rotation : quand le segment actif dépasse `MAX_EVENTS_PER_SEGMENT` (10 000) ou `MAX_BYTES_PER_SEGMENT` (10 Mo), le prochain append crée un nouveau fichier.

La **block layer** (BlockManager) ne crée pas de fichiers ; elle crée des **entrées** dont le `content` est un JSON de bloc ; ces entrées sont écrites via `Storage.append()` dans des shards dédiés (ex. `sessions_block`).

### 2.4 Persistance des événements

- Chaque événement est une **Entry** sérialisée en une ligne JSON (id, timestamp, session_id, source, content, shard, hash, prev_hash, metadata, version).
- Fichiers : `data/shards/<family>/<family>_NNNN.jsonl` (mode segmenté) ou, en fallback, `data/shards/<shard_id>.jsonl` (mode monolithique).
- Intégrité : `data/integrity/<shard_id>_last_hash.json` contient le dernier hash et la date de mise à jour.

### 2.5 API Storage exposée aux modules externes

Méthodes **publiques** de `Storage` :

| Méthode | Signature | Description |
|---------|-----------|-------------|
| `append` | `(entry: Entry) -> Entry` | Ajoute une entrée (append-only), calcule hash si besoin, enchaîne prev_hash, écrit dans le segment actif. |
| `read` | `(shard_id: str, limit: int = 100) -> List[Entry]` | Retourne les `limit` entrées les plus récentes du shard (ordre inverse chronologique). Gère shards segmentés et monolithiques. |
| `list_shards` | `() -> List[ShardMeta]` | Liste tous les shards (monolithiques + familles de segments) avec métadonnées. |
| `get_shard_size` | `(shard_id: str) -> int` | Taille en octets du shard (somme des segments ou fichier unique). |

Attributs utilisés en interne mais exposés sur l’instance : `data_dir`, `shards_dir`, `integrity_dir`, `segment_manager` (utilisé par la block layer et RR pour itérer sur les événements).

---

## 3. Block Model

### 3.1 Structure interne des blocs (block layer)

Les « blocs » ne sont pas des fichiers dédiés ; ce sont des **entrées** dont le champ `content` est un JSON :

```json
{
  "block": true,
  "entries": [
    { "id", "timestamp", "session_id", "source", "content", "shard", "hash", "prev_hash", "metadata", "version" },
    ...
  ],
  "count": N
}
```

- **Métadonnées de l’entrée bloc :**  
  - `metadata.block == true`, `metadata.logical_shard`, `metadata.entry_count`.  
  - `id` de la forme `block-<first_entry_id>-<count>`.  
  - `source` = `"block_layer"`.  
  - `shard` = shard logique + suffixe (ex. `sessions_block`).

- **Hash chain :**  
  - Le hash de l’entrée bloc est le SHA-256 du `content` (tout le JSON du bloc).  
  - `prev_hash` de cette entrée pointe vers l’entrée précédente (bloc ou entrée classique) dans le même shard bloc, comme pour toute autre entrée.

- **Référence aux shards :**  
  - Le shard stocké est le shard **bloc** (ex. `sessions_block`).  
  - Le shard **logique** (ex. `sessions`) est dans `metadata["logical_shard"]`.

La block layer utilise uniquement `Storage.append()` et `Storage.read()` (et éventuellement `segment_manager.iter_shard_events` pour un flux complet). Aucune structure de fichier spécifique « bloc » en dehors du format JSON ci-dessus.

---

## 4. Shard System

### 4.1 Logique de segmentation

- **Shard ID** : chaîne (ex. `sessions`, `default`, `sessions_block`).  
- **Famille** : `shard_id` sans préfixe `shard_` (ex. `sessions` reste `sessions`).  
- **Répertoire** : `data/shards/<family>/`.  
- **Fichiers** : `<family>_0001.jsonl`, `<family>_0002.jsonl`, … triés par numéro.

### 4.2 Rotation des segments

- Gérée dans `ShardSegmentManager._get_active_segment_path()` :
  - S’il n’y a aucun segment, le segment actif est `<family>_0001.jsonl`.
  - Sinon, lecture du dernier segment : taille en octets et nombre de lignes (approximatif).
  - Si `last_segment_events >= MAX_EVENTS_PER_SEGMENT` (10 000) ou `last_segment_size >= MAX_BYTES_PER_SEGMENT` (10 Mo), le prochain segment est `<family>_NNNN+1.jsonl`.

### 4.3 Format des fichiers shard

- Une ligne = un enregistrement JSON (UTF-8, `ensure_ascii=False` côté écriture).
- Champs par ligne : id, timestamp (ISO), session_id, source, content, shard, hash, prev_hash, metadata, version.

### 4.4 Emplacement du stockage

- Base : `data_dir` passé à `Storage` (défaut `"data"`).
- Shards : `data_dir/shards/` (fichiers `.jsonl` ou sous-répertoires `<family>/`).
- Intégrité : `data_dir/integrity/` (fichiers `{shard_id}_last_hash.json`).
- Sécurité : `data/security/` (integrity.json, audit.jsonl, policy.json, baseline.lock) — chemins définis dans core/security.py.

---

## 5. Hash Chain / Integrity

### 5.1 Chaînage des entrées

- Par **shard** : chaque entrée a `prev_hash` = hash de l’entrée précédente dans le même shard.
- La première entrée d’un shard a `prev_hash = None`.
- `hash` = SHA-256 du champ `content` (string).
- Le dernier hash connu par shard est stocké dans `data/integrity/<shard_id>_last_hash.json` et mis à jour à chaque append.

### 5.2 Vérification d’intégrité

- **Signing.verify_chain(entries)** (core/signing.py) : pour une liste d’entrées (ordre chronologique), vérifie que `entry.prev_hash == last_valid_hash` et que le hash recalculé du `content` correspond à `entry.hash`. Retourne des métriques (verified, corrupted, tampering_detected, verification_rate).
- **SecurityLayer._verify_chain_integrity()** : lit un fichier **data/integrity/chain.json** (optionnel) et vérifie une chaîne d’entrées stockée là. Ce fichier est distinct des `*_last_hash.json` utilisés par Storage ; il peut être utilisé pour un audit supplémentaire ou rester vide/absent.
- **trace_replay.py** (script) : pour une session donnée, lit les événements du shard `sessions`, vérifie que chaque `prev_hash` correspond au `hash` de l’événement précédent et signale une divergence.

### 5.3 Détection de corruption

- **Modification de contenu** : le recalcul de `hash(content)` ne correspond plus à `entry.hash` → tampering_detected dans Signing.verify_chain.
- **Chaîne brisée** : `prev_hash` ne correspond pas au hash de l’entrée précédente → corrupted dans verify_chain, ou erreur dans _verify_chain_integrity / trace_replay.
- **Fichiers critiques (security)** : tout écart de hash par rapport à la baseline (integrity.json) est signalé comme MODIFIED et enregistré dans l’audit.

---

## 6. Security Layer

### 6.1 Implémentation

- **Référence** : `memory/dsm/core/security.py` (SecurityLayer).
- **Façade** : `memory/dsm/security.py` réexporte le core et ajoute des context vars optionnelles : `allow_writes()`, `deny_writes()`, `writes_allowed()`.

### 6.2 Signing / vérification

- **Fichiers critiques** : liste `CRITICAL_FILES` (fichiers kernel, CLI, data/security/baseline.json, policy.json).  
- **compute_file_hash(filepath)** : SHA-256 du contenu fichier.  
- **verify_integrity()** : pour chaque fichier critique, compare le hash actuel à la baseline ; retourne un dict (fichier → True/False/None) et un indicateur d’anomalies. Les shards ne sont pas dans la baseline.

### 6.3 Protections

- **Baseline gating** : mise à jour de la baseline conditionnée à : arbre git propre, argument `--reason`, acknowledgment manuel "I UNDERSTAND". Mode forcé : `--force` avec double "I UNDERSTAND I UNDERSTAND".
- **Protected files** : `check_protected_write(path)` refuse l’écriture sur certains chemins sauf si policy `allow_rewrite` ou variable d’environnement `DSM_SECURITY_REWRITE_OK=1`.
- **Audit** : chaque événement significatif (file_modified, baseline_update, rate_limit_exceeded, protected_write_blocked, etc.) est appendé dans `data/security/audit.jsonl`.
- **Rate limiting** : compteurs par cycle (api_requests, file_writes, external_connections) et limites (MAX_API_REQUESTS_PER_CYCLE, MAX_FILE_WRITES_PER_CYCLE) ; dépassement loggé et audit.

---

## 7. Replay System

### 7.1 Deux mécanismes de replay

**A) Replay de traces (core/replay.py)**  
- **Entrée** : fichier **trace** (ex. `data/traces/trace_log.jsonl`), format TraceRecord (trace_id, ts, session_id, action_type, intent, ok, error, state_before, state_after, prev_step_hash, step_hash).  
- **API** : `replay_session(trace_file, session_id, strict=False, limit=None)` → ReplayReport (total_records, verified_records, corrupt_records, missing_hash_records, broken_chain_records, status OK/DIVERGENCE/CORRUPT, errors).  
- **Déterminisme** : vérification des step_hash (canonical JSON) et de la chaîne prev_step_hash → step_hash. Pas de reconstruction d’état DSM ; c’est un audit de trace.

**B) Replay d’événements session (trace_replay.py)**  
- **Entrée** : répertoire DSM (ex. `~/clawdbot_dsm_test/memory`), session_id.  
- **Comportement** : lecture directe des fichiers `shards/sessions/*.jsonl`, filtrage par session_id, tri par timestamp, vérification de la hash chain (prev_hash) et des métadonnées.  
- **Sortie** : rapport (replay_status, hash_chain_verification, divergence_detected, etc.). Ce script lit les fichiers shard directement (hors API Storage) pour le diagnostic.

### 7.2 APIs qui déclenchent du replay

- **CLI** : sous-commande replay (ex. `dsm replay --session <id> --trace-file ...`) qui appelle le replay de traces (core/replay).  
- **Script** : `python -m dsm_v2.trace_replay --session <id>` (ou équivalent depuis memory/dsm) pour le replay par session sur les shards.

### 7.3 Replay déterministe

- Pour les **traces** : le même fichier trace + session_id produit le même ReplayReport (vérification des hash et de la chaîne).  
- Pour le **shard sessions** : la séquence d’entrées lue est ordonnée par timestamp ; la chaîne prev_hash/hash est vérifiée pour détecter toute altération ou incohérence.

---

## 8. Session System

### 8.1 Cycle de vie

- **SessionGraph** (session/session_graph.py) :  
  - `start_session(source)` : génère un `session_id`, écrit un événement `session_start` dans le shard `sessions`, garde l’état en mémoire (current_session_id, session_start_time, session_source).  
  - `record_snapshot(snapshot_data)` : écrit un événement `snapshot` si une session est active et si `SessionLimitsManager.can_poll_home()` l’autorise.  
  - `execute_action(action_name, payload)` : écrit un événement `tool_call` si session active et si `can_execute_action()` l’autorise.  
  - `end_session()` : écrit `session_end`, réinitialise l’état en mémoire.

Tous les événements de session sont écrits dans le shard **`sessions`** via `Storage.append(entry)`.

### 8.2 Session graph vs SessionTracker

- **SessionGraph** : couche au-dessus de Storage, produit des événements typés (session_start, snapshot, tool_call, session_end) dans le shard `sessions`.  
- **SessionTracker** (core/session.py) : état runtime dans un fichier JSON (sessions, current_session, heartbeats, entries_count, etc.). Utilisé par le CLI et d’autres scripts pour suivre la session « courante » sans nécessairement passer par SessionGraph. Les deux peuvent coexister : SessionGraph pour l’audit DSM, SessionTracker pour l’état runtime.

### 8.3 Attachement des événements aux sessions

- Chaque `Entry` a un champ `session_id`. SessionGraph remplit ce champ avec `current_session_id` pour tous les événements qu’il écrit.  
- La lecture « par session » n’est pas dans le kernel : il faut lire le shard (ex. `Storage.read("sessions", limit=N)` ou itérer) et filtrer par `entry.session_id` côté client (comme dans trace_replay.py).

---

## 9. Current Query Capabilities

- **Requêtes par type d’événement** : non. Le kernel n’a pas de type d’événement indexé ; le type est dans `metadata.event_type` (rempli par SessionGraph). Pour « requérir par type », il faut lire des entrées et filtrer en mémoire.  
- **Lecture par session** : non dans le kernel. `Storage.read(shard_id, limit)` retourne les N entrées les plus récentes du shard ; le filtrage par `session_id` doit être fait par l’appelant (ex. RR ou scripts).  
- **Lecture par plage de temps** : non. Aucun index temps ; il faut lire des entrées et filtrer sur `timestamp`.  
- **Lecture par thème/topic** : non. Aucun index sémantique ou par tag ; le contenu est opaque (string) et les tags sont dans `metadata` sans index.

En résumé : **aucune requête structurée** ; uniquement `read(shard_id, limit)` (ordre inverse chronologique) et éventuellement itération complète via le segment manager, puis filtrage en mémoire.

---

## 10. Indexing / Search

- **Index** : le projet ne contient pas d’index sur le contenu des shards dans le dépôt Daryl. Les idées d’index (ShardCatalog, query cache) sont décrites dans RR_INTEGRATION_SPEC et DSM_FUTURE_ARCHITECTURE comme **futures** et optionnelles ; le lab (clawd) a un module dsm_rr avec indexer/navigator basé sur des lectures fichier, à ne pas migrer tel quel (utiliser uniquement l’API Storage).  
- **Outils de navigation** : DSM-RR Step 1 (`read_recent`, `summary`) permet de naviguer « récent » et d’obtenir des résumés (entry_count, unique_sessions, errors, top_actions). Pas de recherche full-text ni de requêtes par critères.  
- **Recherche** : aucune recherche intégrée ; tout doit être fait en lisant des entrées et en filtrant en mémoire (ex. dans un futur RR navigator).

---

## 11. Lab / Experimental Code

| Zone | Rôle | Dans le core ? | Recommandation |
|------|------|-----------------|----------------|
| **block_layer** | Agrégation d’entrées en blocs via Storage uniquement. | Non, couche au-dessus. | Conserver comme couche optionnelle ; ne pas intégrer dans le kernel. |
| **rr** | Read relay Step 1 (read_recent, summary). | Non. | Conserver ; étendre éventuellement (index/navigator) en respectant l’API Storage. |
| **skills** | Registry, Router, Ingestor, usage/success loggers, SkillGraph, bibliothèques (anthropic, community, custom). | Non. Télémetrie dans des JSONL séparés (logs/skills_*). | Rester hors kernel ; intégration agents via SessionGraph + skills. |
| **ans** | ANS (Audience Neural System) : analyse de performance des skills, recommandations. Lit les logs skills. | Non. | Rester hors kernel. |
| **moltbook_observation_runner**, **moltbook_home_client**, **moltbook/** | Observation Moltbook, normalisation, tests. | Non. | Code produit/expérimental ; à garder en lab ou dans un module dédié, pas dans core. |
| **trace_replay.py** (racine memory/dsm) | Replay d’une session à partir des shards (lecture fichier directe), vérification hash chain. | Non. | Script de diagnostic ; pourrait à terme utiliser uniquement Storage.read() + filtrage pour rester cohérent avec RR. |
| **full_chain_validation.py** | Validation end-to-end skills (routing, logs, graph, CLI). | Non. | Reste un script de validation, chemins lab en dur à adapter. |
| **session_*_test.py**, **recycling_test.py**, **run_stability_suite.py** | Tests de session, cooldown, dédup, stress, recyclage, stabilité. | Non. | Tests / lab ; à garder hors kernel. |
| **modules/dsm_rm.py** | DSMRecyclingMemory : compaction, résumés de session, archive. Utilise ShardSegmentManager. | Non. | Module optionnel ; ne pas mettre dans core. |
| **CLI (cli.py)** | Point d’entrée `dsm` : status, list-shards, read, append, replay, security, etc. | Non (utilise le core). | Conserver comme unique entrée CLI officielle. |

Résumé : le **kernel** se limite à `memory/dsm/core/` (Storage, models, shard_segments, signing, replay, session tracker, security). Tout le reste (session graph, block layer, rr, skills, ans, moltbook, modules, tests) est **hors kernel** et peut rester externe ou optionnel.

---

## 12. Integration Surfaces

Points d’intégration **sans modifier le kernel** :

1. **Storage**  
   - Créer une instance `Storage(data_dir=...)` et utiliser uniquement `append`, `read`, `list_shards`, `get_shard_size`.  
   - Pour un flux complet sur un shard : utiliser `storage.segment_manager.iter_shard_events(shard_id)` (exposé par l’instance Storage).

2. **SessionGraph**  
   - Construire avec `SessionGraph(storage=..., limits_manager=...)` et appeler start_session, record_snapshot, execute_action, end_session. Toutes les écritures passent par Storage.

3. **BlockManager**  
   - Construire avec `BlockManager(storage=..., block_size=...)` ; utiliser `append(entry)` et `flush()` ; lecture via `read(shard_id, limit)` ou itération. Shards suffixés `_block`.

4. **DSMReadRelay**  
   - `DSMReadRelay(storage=...)` ou `data_dir=...` ; `read_recent(shard_id, limit)` et `summary(shard_id, limit)`. Idéal pour couches « lecture seule » (analytics, context packs, futur index/navigator).

5. **Sécurité**  
   - Utiliser `SecurityLayer(workspace_dir=...)` pour vérification d’intégrité et audit ; ne pas contourner les gardes (protected files, baseline) dans du code qui modifie des fichiers critiques.

6. **Modèles**  
   - Importer `Entry`, `ShardMeta` depuis `dsm_v2.core.models` (ou équivalent) pour construire des entrées compatibles avec Storage et BlockManager.

7. **Replay (traces)**  
   - Utiliser `replay_session()` depuis `dsm_v2.core.replay` pour des traces au format TraceRecord ; pas de modification du stockage.

Aucun de ces points ne nécessite de toucher à `memory/dsm/core/` (storage, models, shard_segments, signing, replay, security, session.py).

---

## 13. Architectural Risks

- **Scalabilité lecture** : `read(shard_id, limit)` pour les shards segmentés charge tous les segments puis tronque et inverse ; pour de très gros shards, le coût mémoire et I/O peut augmenter. L’itération complète (iter_shard_events) est linéaire. Un index ou un curseur par segment pourrait être utile plus tard sans changer le contrat Storage.  
- **Double arbre de sources** : présence de `memory/dsm/` et `dsm_v2/` dans SOURCES.txt ; risque de confusion et de divergence. Clarifier un seul arbre source canonique (ex. memory/dsm) et le mapping du package `dsm_v2`.  
- **Replay trace vs shard** : deux formats (TraceRecord dans trace_log.jsonl vs Entry dans shards) et deux scripts (core/replay vs trace_replay.py). Pour une vision unifiée « replay déterministe », définir si le replay cible les traces, les shards, ou les deux avec des contrats clairs.  
- **SecurityLayer et chemins** : CRITICAL_FILES et _verify_chain_integrity référencent des chemins (dsm_v2/core/..., data/integrity/chain.json). En fonction du répertoire de travail et du layout (memory/dsm vs dsm_v2), les chemins relatifs peuvent ne pas correspondre ; à documenter ou rendre configurables.  
- **SessionLimitsManager** : état dans un fichier JSON (session_limits.json) ; en environnement multi-processus, les limites peuvent être dépassées sans coordination. Acceptable pour un usage single-agent ; à documenter.  
- **BlockManager prev_hash** : les entrées bloc sont ajoutées avec `prev_hash=None` dans le code actuel (block_entry) ; la chaîne est donc maintenue entre les **blocs** par Storage, mais à vérifier que le dernier hash du shard bloc est bien pris en compte à chaque flush (Storage.append gère le prev_hash côté Storage, donc cohérent).

---

## 14. Recommendations

Recommandations pour les **futurs modules** (sans implémentation dans ce document).

### RR (Read Relay)

- Garder **Step 1** (read_recent, summary) comme API stable et unique entrée de lecture pour les couches au-dessus.  
- Toute extension (index, navigator, query cache) doit utiliser **uniquement** Storage.read() et/ou itération publique (iter_shard_events) ; pas de lecture directe des fichiers shard.  
- Documenter et, si implémenté, placer l’index/cache sous `data/index/` (régénérable).  
- Voir RR_INTEGRATION_SPEC et LAB_TO_DARYL_MIGRATION_PLAN pour la migration éventuelle d’idées du lab (indexer/navigator) en s’appuyant sur l’API Storage.

### Context Packs

- Construire les packs à partir de **Storage.read()** ou **DSMReadRelay.read_recent()** (et éventuellement summary), avec filtrage optionnel par session_id ou plage de temps en mémoire.  
- Pas d’écriture dans les shards ; pas d’appel LLM dans la v0 si la spec le prévoit ainsi.  
- Sortie : structure (liste d’entrées ou d’extraits + refs) ; cache optionnel dans `data/index/`.

### ANS (learning layer)

- Conserver l’ANS comme couche **hors kernel** : lecture des logs skills (usage/success), calcul de métriques et recommandations.  
- Ne pas stocker d’état d’apprentissage dans le kernel DSM ; utiliser des fichiers ou bases dédiés (comme aujourd’hui).  
- Interface claire entre DSM (sessions, événements) et ANS (télémetrie skills) pour éviter de mélanger les responsabilités.

### Block Layer

- Conserver la sémantique append-only et le fait qu’un bloc = une Entry ; pas de modification du format dans le core.  
- Si évolution (block hash, Merkle, compression), la faire dans la block layer uniquement, en restant compatible avec Storage (content opaque ou décompressé à la lecture).

### Kernel

- Ne pas ajouter de requêtes, d’index ou de recherche dans le core.  
- Toute nouvelle capacité de « requête » ou « navigation » doit vivre dans RR ou une couche équivalente au-dessus de Storage.

---

*Ce document est un audit en lecture seule. Aucun code n’a été modifié. Références : ARCHITECTURE.md, AGENTS.md, DSM_FUTURE_ARCHITECTURE.md, RR_INTEGRATION_SPEC.md, LAB_TO_DARYL_MIGRATION_PLAN.md, HEARTBEAT.md.*
