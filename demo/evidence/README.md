# DARYL Evidence Demo

Démonstration de preuve d'intégrité DSM pour un scénario métier générique.

---

## Objectif

Un étranger (éditeur logiciel B2B français, non-cryptographe) peut, en deux minutes, voir que DSM est réel et comprendre ce qu'il peut et ne peut pas prouver.

---

## Scénario

| Objet | Description |
|-------|-------------|
| **Q16** | Questionnaire investisseur, version 16 |
| **Q17** | Questionnaire investisseur, version 17 (ajout question ESG) |
| **R42** | Recommandation déclarant être basée sur Q17 |
| **M61** | Manifeste liant Q16, Q17 et R42 |

La recommandation R42 déclare `"based_on": "Q17"`. Cette relation est **enregistrée comme contenu** dans DSM. L'intégrité de cet enregistrement est garantie — pas la véracité de la déclaration.

---

## Exécution

```bash
# Depuis la racine du dépôt
python demo/evidence/run_demo.py

# Conserver les données pour inspection
python demo/evidence/run_demo.py --keep-data
```

---

## Résultat attendu

### Étape 1 — Enregistrement
Les 4 documents sont enregistrés dans DSM avec leurs hash SHA-256.

### Étape 2 — Vérification initiale
```
[VÉRIFICATION INITIALE]
✓ Status       : OK
  Entrées      : 4
  Vérifiées    : 4
  Altérées     : 0
  Ruptures     : 0
```

### Étape 3 — Altération
Un octet de Q17 est modifié (titre : "Version 17" → "Version 17-bis").
Le hash stocké ne correspond plus au contenu.

### Étape 4 — Vérification après altération
```
[VÉRIFICATION APRÈS ALTÉRATION]
✗ Status       : TAMPERED
  Entrées      : 4
  Vérifiées    : 3
  Altérées     : 1
  Ruptures     : 0
```

Note : 3 entrées restent vérifiées (Q16, R42, M61). Seule Q17 est détectée comme altérée.
`Ruptures` compte les discontinuités de chaîne (`prev_hash`), pas les altérations de contenu.

---

## Ce que DSM prouve

| Garantie | Explication |
|----------|-------------|
| ✓ **Intégrité de l'état enregistré** | Les documents n'ont pas été modifiés depuis leur enregistrement |
| ✓ **Relation déclarée intacte** | Si R42 déclare `based_on: Q17`, cette déclaration est préservée |
| ✓ **Détection d'altération** | Toute modification post-hoc est détectée |

---

## Ce que DSM ne prouve PAS

| Limite | Explication |
|--------|-------------|
| ✗ **Usage effectif** | DSM ne prouve pas que le conseiller a utilisé Q17 pour produire R42 |
| ✗ **Qualité de la recommandation** | DSM ne prouve pas que R42 est une bonne recommandation |
| ✗ **Conformité réglementaire** | DSM ne prouve pas la conformité AI Act, AMF, MIF2, etc. |
| ✗ **Véracité des réponses** | DSM ne prouve pas que les réponses client sont vraies |
| ✗ **Adéquation du conseil** | DSM ne prouve pas que le processus de conseil était adéquat |

---

## Relation `based_on`

DSM n'a pas de notion native de "relation basé-sur" entre documents.

Dans cette démo, la relation est **enregistrée comme contenu** :
- R42 contient `"based_on": "Q17"` dans son JSON
- M61 (manifeste) documente explicitement la liaison

Ce contenu est hashé comme tout autre contenu DSM. Son intégrité est garantie, pas sa véracité.

---

## Architecture

```
demo/evidence/
├── Q16.json      # Questionnaire v16
├── Q17.json      # Questionnaire v17
├── R42.json      # Recommandation (based_on: Q17)
├── M61.json      # Manifeste de liaison
├── run_demo.py   # Script de démonstration
├── test_demo.py  # Tests automatisés
└── README.md     # Ce fichier
```

---

## Intégration

Pour intégrer DSM dans votre application, consultez le [README principal](../../README.md)
et les exemples dans `demo/`. L'API recommandée passe par `SessionGraph` pour
l'enregistrement et `dsm verify` (CLI) ou `verify_shard` pour la vérification.

Vérification en ligne de commande :

```bash
dsm verify --shard my_shard --data-dir my_data
```

---

## En résumé

**DSM garantit l'intégrité de l'état enregistré.**

**DSM ne garantit pas la véracité, la qualité ou la conformité du contenu.**

C'est une couche de preuve cryptographique, pas un certificat de conformité.
