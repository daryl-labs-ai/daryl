# ADR — Contrat PRL ↔ Read Relay (DSM-RR)

**Statut** : Accepté · **Date** : 2026-06-25 · **Portée** : verrouille l'interface structurelle de PRL **avant** `feat/prl-foundation`.

**Source de vérité** : lecture du code réel sur `github.com/daryl-labs-ai/daryl` (`src/dsm/rr/`, `src/dsm/core/`), pas des suppositions de `ROADMAP_PRL.md`.

---

## 1. Contexte

`ROADMAP_PRL.md` supposait que PRL définirait un graphe (`FileNode`, `CommitNode`,
`SessionNode`, `Edge`) puis l'interrogerait « via `rr/` ». Avant de coder P0 (les types),
on a lu le vrai Read Relay pour vérifier que cette forme se branche proprement. **Elle ne
se branche pas telle quelle.** Cet ADR fixe le contrat réel.

---

## 2. Ce que Read Relay EST réellement (faits, pas intentions)

Stack en couches, toutes **read-only** vers DSM (`src/dsm/rr/`) :

| Couche | Classe | Surface publique réelle |
|---|---|---|
| Relay | `DSMReadRelay` (`relay.py`) | `read_recent(shard_id, limit)`, `summary(shard_id, limit)` |
| Index | `RRIndexBuilder` (`index/rr_index_builder.py`) | `build() -> dict`, `ensure_index()`, `load()` |
| Navigation | `RRNavigator` (`navigator/rr_navigator.py`) | `navigate_session`, `navigate_agent`, `timeline(start,end)`, `navigate_shard`, `navigate_action(name, limit)`, `resolve_entries(records, limit)` |
| Requête | `RRQueryEngine` (`query/rr_query_engine.py`) | `query(session_id, agent, shard_id, start_time, end_time, resolve, limit, sort)`, `query_actions(action_name, session_id, start, end, limit)` |
| Contexte | `RRContextBuilder` (`context/rr_context_builder.py`) | `build_context(...)` |
| Helpers | `helpers.py` | `get_populated_rr_builder(storage, index_dir)`, `build_session_summary(records, session_id)` |

**Faits déterminants :**

1. **RR n'a aucune notion de nœud/arête/graphe.** Le seul modèle de donnée est
   `Entry` (`core/models.py`) : `id, timestamp, session_id, source, content, shard,
   hash, prev_hash, metadata, version`. DSM est un **log append-only plat** d'`Entry` ;
   RR en construit des **index dérivés**.

2. **Les axes d'index sont fixes**, dérivés des champs d'`Entry` :
   `session_index` (par `session_id`), `agent_index` (par `source`), `timeline_index`
   (par `timestamp`), `shard_index` (par `shard`), `action_index` (par
   `metadata["action_name"]`). Un *index record* est un dict à clés fixes :
   `{session_id, timestamp, agent, event_type, shard_id, entry_id, offset, action_name,
   success}`.

3. **RR ne fait ni recherche de contenu, ni jointure.** `query()` sans filtre retourne
   `[]` (pas de full scan). Il n'existe **aucun axe** `content_hash`, `project_id`, ni
   relation `file↔commit` / `session↔file`. Ces axes sont précisément ceux dont PRL a
   besoin — et RR ne les fournit pas.

4. **RR est strictement read-only.** L'écriture passe par `Storage.append(entry)` /
   `SessionGraph`. RR lit via `Storage.read()` et `list_shards()` uniquement.

5. **ADR-0001 (kernel) : RR est le seul chemin de lecture autorisé.** Les consommateurs
   (DarylAgent, CLI, MCP) ne lisent pas `Storage` directement ; ils passent par
   `RRQueryEngine`/`RRNavigator` + `resolve_entries()`. PRL doit respecter cette règle.

---

## 3. Décision

PRL **ne définit pas un graphe que RR interrogerait**. PRL :

### D-1 — Encode chaque nœud/arête PRL dans une `Entry`

Une donnée PRL (FileNode, CommitNode, SessionNode, Edge) devient une `Entry` où :

- `content` = `canonical_bytes(payload)` (JCS via `dcp.canonical`), stocké inline
  (base64/JSON), pattern V1 identique à DCP.
- `metadata["action_name"]` = **le genre d'enregistrement** : `"prl.file"`,
  `"prl.commit"`, `"prl.session"`, `"prl.edge"`. C'est le hook qui rend la donnée
  récupérable via `navigate_action(...)` / `query_actions(action_name=...)`
  (l'`action_index` existe exactement pour ça).
- `metadata` mirroir des champs filtrables nativement si besoin (`event_type`, etc.).
- `shard` = un shard PRL dédié (`"prl"` ou `"prl_<project_id>"`).
- `session_id` = l'**id du run de harvest** (groupe une passe d'indexation).
- `timestamp` = horodatage du fait (mtime fichier, date commit, début session).

> Conséquence : `project_id` et `content_hash` **vivent dans le payload**
> (`content`), pas dans un axe RR. RR les ramène en bloc via `navigate_action("prl.file")`
> + `resolve_entries()`, puis PRL parse le `content`.

### D-2 — PRL possède un index d'adjacence secondaire (le graphe est à PRL, pas à RR)

Comme RR n'indexe ni `content_hash` ni les relations, PRL maintient son **propre index**
construit à partir des Entries résolues :

- `content_hash → [file entry_ids]`
- `file content_hash → [commit shas]` (arêtes `modified`)
- `session_id → [content_hash | commit sha]` (arêtes `produced`/`references`, P7)

Cet index PRL se persiste comme RR le fait (fichiers `.idx` sous
`~/.daryl/prl/index/`), reconstruit depuis les Entries via RR. **Il ne duplique pas le
log** : il indexe des pointeurs (`entry_id`, `content_hash`).

### D-3 — Write via Storage/SessionGraph, Read via RR (jamais `Storage.read()` en direct)

- **Écriture (P3)** : `SessionGraph.execute_action(...)` ou `Storage.append(entry)` pour
  poser les Entries PRL. Conforme : RR est read-only, on n'écrit pas via RR.
- **Lecture (P5, P9)** : exclusivement via `RRQueryEngine`/`RRNavigator` +
  `resolve_entries()`, puis parse du `content`. Conforme à ADR-0001.
- PRL utilise `get_populated_rr_builder(storage, index_dir)` (helper existant) pour
  obtenir un builder peuplé, puis `RRNavigator` → `RRQueryEngine`.

### D-4 — La couche structurelle PRL (P5) s'écrit en composant RR, pas en le remplaçant

`StructuralQuery` (P5) :
1. `query_actions(action_name="prl.file")` → métadonnées → `resolve_entries()` → FileNodes.
2. construit/charge l'index d'adjacence PRL (D-2).
3. répond aux requêtes graphe (`commits_touching(content_hash)`, `project_of_file`, …)
   depuis l'index PRL, **pas** depuis RR (qui ne sait pas faire ces jointures).

---

## 4. Conséquences sur le code et la roadmap

### Impacts (deltas à appliquer à `ROADMAP_PRL.md`)

| Milestone | Avant (supposé) | Après (contrat réel) |
|---|---|---|
| **P0 types** | nœuds/arêtes comme modèles graphe autonomes | + un **mapping explicite nœud → `Entry`** : `to_entry()` / `from_entry()` par type ; `action_name` = genre PRL ; payload canonique dans `content` |
| **P3 store** | « commit chaque nœud/arête » (déjà ~OK) | préciser : `metadata["action_name"]` posé pour l'indexation RR ; shard PRL dédié ; un `session_id` par run |
| **P5 structural** | « requêtes graphe via rr/ » | **reformulé** : RR fournit *récupération par axe + resolve* ; le **graphe/adjacence est un index PRL secondaire** (D-2) construit au-dessus de RR |
| **P7 binder** | arêtes `produced`/`references` | inchangé conceptuellement ; les arêtes sont des Entries `prl.edge` + entrées dans l'index d'adjacence PRL |
| **P9 recall** | sémantique × structurel | inchangé ; le « structurel » lit l'index PRL (D-2), pas RR direct |

### Ce qui ne change pas
- La clé de jointure reste **`content_hash = sha256_uri(bytes)`** (`dcp.canonical`).
- PRL reste additif, ne touche jamais le kernel frozen.
- Phase 1 reste livrable sans dépendance externe.

### Positif
- On réutilise toute la machinerie RR éprouvée (index persistant, navigation, resolve,
  helpers) au lieu de réécrire un store.
- Respect natif d'ADR-0001 (RR = seul chemin de lecture).
- Le « genre » via `action_name` est exactement l'usage prévu de l'`action_index`.

### Négatif / coûts acceptés
- PRL doit **maintenir son propre index d'adjacence** (D-2) : RR ne fait pas les
  jointures `content_hash`/relations. C'est du code en plus (≈ celui d'un mini
  index builder), mais calqué sur le pattern RR existant.
- Les requêtes graphe ne sont pas « gratuites via RR » : elles passent par l'index PRL.

---

## 5. Points encore à confirmer (au moment de coder P3/P5)

1. **`SessionGraph.execute_action` vs `Storage.append`** pour poser les Entries PRL :
   vérifier laquelle respecte le mieux la chaîne de hash WAL pour un *batch* d'Entries
   (P3 écrit beaucoup de nœuds d'un coup).
2. **Granularité shard** : un shard `prl` global vs un shard par projet
   (`prl_<project_id>`) — impacte `navigate_shard` et la taille d'index.
3. **`metadata["success"]`** et `event_type` : champs mirroir éventuels si on veut
   filtrer des sous-types PRL nativement via RR avant resolve.
4. **Format de persistance de l'index d'adjacence PRL** : réutiliser le format `.idx`
   de `RRIndexBuilder._write_index_files()` pour cohérence.

---

## 6. Décision nette

**Contrat verrouillé.** RR = *moteur de récupération par axe (session/agent/timeline/shard/
action) + resolve vers `Entry`*, read-only. PRL = *écrit ses nœuds/arêtes comme `Entry`
typées par `action_name`, et possède son propre index d'adjacence pour le graphe*.
On peut maintenant lancer `feat/prl-foundation` (P0) en intégrant `to_entry()/from_entry()`
et en sachant que P5 compose RR sans en dépendre pour les jointures.

---

## 7. Résolu pendant l'intégration P0 dans le repo réel (2026-06-25)

P0 a été codé+validé en staging (Cowork) puis intégré dans `daryl` par Code
(branche `feat/prl-foundation`, empilée sur `architecture/p1-transparency-log-mmr-sth`).
Faits confirmés contre le vrai repo, qui amendent les hypothèses staging :

- **Couche canonique réelle = `dsm_primitives.canonical_json`** (pas `dcp.canonical`,
  pas `rfc8785` — aucun des deux n'existe dans `daryl`). PRL expose la surface étroite
  dont il a besoin (`canonical_bytes` / `sha256_uri` / `utc_now_ms`) via un shim
  `src/prl/_canonical.py` qui **compose `dsm_primitives.canonical_json`**. Conséquence :
  la forme canonique de PRL n'est **pas** RFC-8785/JCS, mais le sérialiseur canonique du
  repo. C'est **voulu et préférable** — PRL partage la primitive du kernel au lieu d'ajouter
  une dépendance. La propriété requise (déterminisme byte-stable pour le round-trip
  `to_entry`/`from_entry`) est préservée. Les hashes PRL sont internes V1 (aucun
  vérificateur JCS externe), donc la non-conformité JCS est sans impact.
- **Clé de jointure PRL = schéma `sha256:<hex>`**, délibérément distinct du `v1:<hex>`
  produit par `dsm_primitives.hash_canonical` côté kernel — concerns séparés, conforme D-1.
- **`EntryDraft.timestamp` est une string ISO-8601** alors que le kernel `Entry`
  (`src/dsm/core/models.py`) utilise `timestamp: datetime`. Les autres champs
  (`session_id`/`source`/`content`/`shard`/`metadata`/`version`) s'alignent ; `id`/`hash`/
  `prev_hash` sont assignés par le kernel. **→ Point P3** : `to_entry` devra bridger
  str→datetime au moment d'écrire via `SessionGraph`/`Storage`. Rien à changer en P0
  (P0 n'écrit jamais).
- **Lint architectural** `scripts/forbid_storage_access.py` ne scanne que `src/dsm/core`
  et `src/dsm/rr` → PRL non concerné. CI scope la couverture via `--cov=src/dsm`.

Résultat : 34 tests PRL verts, suite complète 1338 passed / 52 skipped, `src/dsm/**`
intact. Changements staged, pas encore commit/merge au moment de cette note.

---

## 8. Chemin d'écriture P3 — décidé après lecture du kernel (2026-06-26)

Avant de coder P3 (`feat/prl-dsm-store`, premier milestone qui écrit dans DSM),
lecture de `src/dsm/session/session_graph.py` + `src/dsm/core/storage.py` +
`src/dsm/core/models.py` sur `main` (`976a56d`). Faits :

- **`SessionGraph.execute_action(action_name, payload)`** : shard **codé en dur à
  `"sessions"`**, enveloppe `content` dans `{action_name, payload}` avec
  `metadata.event_type="action_intent"`, **rate-limité** (`can_execute_action()`
  → peut renvoyer `None` en cooldown), exige une session active. → inadapté pour
  committer une carte entière, pour un shard PRL dédié, et pour stocker le payload
  canonique brut.
- **`Storage.append(entry) -> Entry`** : le caller construit l'`Entry` complète
  (shard, `content`, `metadata`) ; `append` calcule la **chaîne de hash par shard**
  (`prev_hash` = dernier hash du shard, `hash` recalculé et jamais fait confiance au
  hash fourni — H5), `fsync`, **pas de rate-limit, pas de session requise**. Un
  nouveau shard est créé à la première écriture.

**Décision (révise D-3)** : PRL écrit via **`Storage.append`**, pas
`execute_action`. **Aucune session `SessionGraph`** (évite le shard `"sessions"` et
le limiteur). Conséquences verrouillées :

1. **Shard par projet** : `shard = "prl_" + <short_project_id>` où
   `short_project_id` = segment stable de `project_id` slugifié pour la sûreté
   fichier (le `project_id` brut est `"sha256:<hex>"`, le `:` n'est pas sûr en nom
   de fichier). Isole la chaîne de hash par projet, accélère `navigate_shard` (P5),
   facilite export/delete/rebuild par projet, évite un méga-shard global.
2. **Pont timestamp** : `EntryDraft.timestamp` (str ISO-8601 `"…Z"`) →
   `Entry.timestamp` (datetime) via
   `datetime.fromisoformat(ts.replace("Z", "+00:00"))` (compatible 3.10 ; le kernel
   sérialise ensuite via `.isoformat()`).
3. **`run_id`** de harvest = `EntryDraft.session_id`, généré par PRL (pas de
   `SessionGraph`).
4. **`Entry.version = "prl.v1"`** (distinct du `"v2.0"` kernel ; aucun validateur
   kernel sur `version`).
5. **Lecture interdite en P3** : `commit_map` n'écrit que. Toute requête (ex.
   `latest_map_hash`) relève du chemin de lecture RR (ADR-0001) → P5, pas
   d'appel `Storage.read` direct depuis PRL.

`commit_map(pmap)` itère `project + files + commits + edges`, `to_entry(node,
shard=prl_shard, session_id=run_id)` → conversion `EntryDraft → Entry` (pont
timestamp) → `Storage.append`. Retourne le `run_id`, le shard, le nombre d'entries
et le hash de tête (dernier `entry.hash` de la chaîne du shard).

**Découvert à l'intégration P3 (lint ADR-0001 `forbid_storage_access.py`)** : le
repo applique un lint CI (`lint-forbid-storage.yml`) qui scanne **tout** le repo et
échoue tout module important `dsm.core.storage.Storage` s'il n'est pas un *writer*
explicitement déclaré dans `LEGITIMATE_WRITERS`. Comme `PRLStore` importe `Storage`
pour écrire, il **doit** y être enregistré (`src/prl/store/dsm_commit.py`), au même
titre que `session_graph.py` (« a pure Storage WRITER »). Décision actée : on
**enregistre** plutôt que d'esquiver via `TYPE_CHECKING` — `PRLStore` *est*
honnêtement un writer ; le masquer tromperait le registre architectural. C'est le
seul fichier hors `src/prl/` modifié par P3 (un allowlist de lint, pas le kernel).
**Règle pour la suite** : tout futur module PRL qui importe `Storage` pour écrire
devra être enregistré ; en revanche la couche lecture (P5) passe par RR (jamais
`Storage` direct) et ne déclenche donc pas ce lint.

---

## 9. Chemin de lecture P5 — décidé après lecture de RR + du lint (2026-06-26)

Lecture de `src/dsm/rr/*` et de `scripts/forbid_storage_access.py` sur `main`
(`3ea8bbb`) avant de coder P5 (`feat/prl-rr-bind`, première vraie lecture).

- **Surface RR** : `RRNavigator.navigate_action(name)` → records métadonnées du
  bucket `action_index` (tous shards), puis `resolve_entries(records)` →
  `list[Entry]` (c'est RR qui appelle `Storage.read`, pas PRL). Index construit via
  `RRIndexBuilder(storage, index_dir).build()` (`enable_action_index=True` par
  défaut).
- **Le lint ne flag que l'IMPORT de `Storage`** (« Receiving a Storage instance via
  function parameter is NOT flagged »), et `tests/` est whitelisté. Donc la couche
  lecture PRL **n'importe que `dsm.rr.*`** et **reçoit** `storage` en paramètre →
  **aucune inscription `LEGITIMATE_WRITERS`** (vérifié : lint vert sur main+P5).

**Décision** : `StructuralQuery(storage, index_dir)` construit un index RR **frais**
(`build()`), puis un **index d'adjacence PRL en mémoire** (PAS de `.idx` persistant
en V1) via `navigate_action("prl.{project,file,commit,edge}")` → `resolve_entries`
→ `from_entry`. Sémantique **latest-run** : `index` ajoute un snapshot complet par
run (sans delete) ; l'adjacence ne garde que le dernier run par shard (identifié par
l'entrée `prl.project` au timestamp max — un seul par run, horodaté au wall-clock du
commit), ce qui supprime les snapshots périmés. Méthodes : `files_of_project`,
`commits_touching`, `project_of_file`, `neighbors`. Persistance `.idx` = optimisation
post-P5 seulement si le coût de rebuild devient gênant.

---

## 10. Binder P7 — décidé avec l'utilisateur (2026-06-26)

P7 (`feat/prl-binder`) relie `SessionNode` (collectors P6) ↔ `FileNode`/`CommitNode`
(P1/P2). **Gap constaté** : `SessionNode` (mergé en P6) ne porte qu'un `text_preview`
≤200 + `title` + timestamps — **pas le texte intégral**. Or `content_hash` (jointure
forte de l'ADR) exige le full-text ; et pour la seule source V1 (**ChatGPT**), un
fichier entier est rarement collé verbatim → ce signal serait haute-précision /
très faible recall (il vaudra surtout pour les sources IDE différées).

**Décision (V1, signaux métadonnées uniquement)** : `bind_sessions(sessions, pmap,
*, min_confidence=0.40) -> list[Edge]`, **fonction pure** (pas de DSM/RR/Storage).
Signaux, chaque arête `references` (session→file/commit) avec `confidence` +
`evidence={"method": …}`, jamais de lien silencieux :

- **path** : chemin relatif (contenant `/`) cité dans `title`+`preview` → 0.75.
- **filename** : basename (longueur ≥ 4) cité → 0.60.
- **commit_window** : `commit.ts_ms` dans la fenêtre de session (± 15 min) → 0.80
  (arête session→commit).
- **mtime_window** : `file.mtime_ms` dans la fenêtre → 0.40 (fallback faible).

Dédup par `(session_id, dst_id)` en gardant le signal le plus fort ; filtrage final
`confidence >= min_confidence`. **`content_hash` matching DIFFÉRÉ** (hors scope V1) :
nécessitera la capture du transcript complet / blocs de code côté collector (champ
optionnel `full_text_ref` ou artefact), activable seulement pour les collectors qui
fournissent le texte complet. `SessionNode` **n'est pas modifié** en P7.

---

## 11. Index sémantique P8 — décidé avec l'utilisateur (2026-06-26)

**Risque** : à ce stade ce n'est plus DSM/RR, c'est la **dépendance ML**
(`sentence-transformers`/torch, lourdes). Env du repo : `numpy` présent mais non
déclaré comme dep dure ; `sentence-transformers` absent.

**Décisions (local-first, dépendance ML isolée)** dans `src/prl/query/semantic.py` :

- **Cosinus en pur Python** sur vecteurs normalisés — **pas de numpy**, pas de torch
  dans le cœur. Le module `semantic` s'importe proprement **sans** la stack ML
  (vérifié).
- `Embedder` (Protocol) ; `LocalEmbedder(model_name="all-MiniLM-L6-v2")` importe
  `sentence-transformers` **paresseusement** (à la construction) et lève
  `SemanticError` actionnable si l'extra manque. → extra optionnel **`[semantic]`**
  dans `pyproject` (jamais dep dure ; la CI/`dev` ne l'installe pas).
- `SemanticIndex(embedder)` : `build(items)` / `add` / `search(query,k)->[(id,score)]`
  + **persistance JSON** `save`/`load` (les embeddings coûtent cher à recalculer,
  contrairement à l'adjacence P5 ; P9 charge sans recompute). Un index chargé ne peut
  `search` que si on lui fournit un embedder (pour vectoriser la requête).
- **Tests via `FakeEmbedder` déterministe** (bag-of-words md5, stable inter-runs) —
  aucun téléchargement de modèle ; + test que `LocalEmbedder` lève bien `SemanticError`
  quand l'extra est absent. Aucune dep ML dans la suite de tests.

---

## 12. Recall NL P9 — décidé avec l'utilisateur (2026-06-26) — FERME LE MVP

P9 (`feat/prl-recall`) ferme la boucle : `collector → binder → semantic → structural
→ answer`. **Strict** : pas de LLM génératif, pas de multi-tour, pas de nouvel état
persisté, pas de dep ML obligatoire.

- **`RecallEngine` orchestrateur pur** (`src/prl/query/recall.py`), injection :
  `SemanticIndex` (sur sessions) + `sessions` (id→SessionNode) + `edges` (binder
  references) + lookups `files` (content_hash→FileNode) / `commits` (sha→CommitNode).
  `ask(question, k=5) -> list[RecallHit]` : recherche sémantique P8 → pour chaque
  session candidate, enrichissement via les arêtes binder (fichiers/commits liés) →
  score combiné `sem_score + 0.20 * max(edge.confidence)` (la sémantique domine, les
  liens boostent) → tri décroissant. `RecallHit{session, score, semantic_score,
  linked_files, linked_commits, why}` ; **`why` = score sémantique + evidence des
  arêtes binder** (sortie explicable, jamais opaque).
- **CLI `python -m prl ask "..." --project <dir> --export <chatgpt.json>`** : wiring
  **complet en mémoire** (collect ChatGPT → `build_map` → `bind_sessions` →
  `SemanticIndex(LocalEmbedder)` → `RecallEngine.ask` → affichage). L'embedder vient
  d'une factory `_make_embedder` (overridable en test). Sans l'extra `[semantic]`,
  `ask` renvoie 2 avec un message clair (pas de crash).
- **Tests** : `RecallEngine` testé à fond avec `FakeEmbedder` + données synthétiques ;
  CLI `ask` testé **end-to-end** en monkeypatchant `_make_embedder` (vrai export
  fixture + vrai repo git tmp, zéro modèle). Le **gate d'acceptation ≥7/10** sur de
  vraies questions exige le vrai modèle + le vrai export → **validation manuelle hors
  CI**.

**État : MVP PRL fermé** — Phase 1 (P0–P4) + Phase 2 (P5–P7) + Phase 3 (P8–P9).
