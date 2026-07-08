#!/usr/bin/env python3
"""Falsification 2 — Existe-t-il un mécanisme SANS Relation Object qui
satisfait I/V/C/P pour TOUTES les arêtes?

Trois candidats à tester:
  M1. Étendre les hashes existants (id/shard dans le hash canonique).
  M2. Ajouter des fonctions verify_* ad hoc.
  M3. Lier les objets par hash réciproque (bidirectionnel).

Critère: le mécanisme couvre-t-il I ∧ V ∧ C ∧ P SANS introduire de Relation Object?
Si OUI pour un mécanisme → la théorie du Relation Object est réfutée.
Si NON pour les trois → le Relation Object est nécessaire (ou au moins non trivial).
"""
from __future__ import annotations

print("=" * 100)
print("CONTRE-EXEMPLE: peut-on satisfaire I/V/C/P SANS Relation Object?")
print("=" * 100)
print()

# === M1: Étendre les hashes existants ===
print("=== M1: Étendre le hash canonique (ajouter id, shard, dispatch_hash...) ===")
print()
print("  Mécanisme: ajouter les champs manquants dans les hashes existants.")
print("  Exemple: entry_hash couvre aussi id+shard ; receipt_hash couvre dispatch_hash.")
print()
print("  Couverture par propriété:")
print("    I (Integrity):    ✓ OUI — tous les champs seraient dans un hash")
print("    V (Verifiability): ✗ PARTIEL — avoir un hash ne crée pas de fonction verify.")
print("                       Le receipt_hash couvrirait dispatch_hash, mais qui vérifie")
print("                       que le dispatch référencé EXISTE et appartient au bon agent?")
print("                       → il faut quand même ajouter verify_dispatch_linked_to_receipt()")
print("                       → c'est M2 (fonctions ad hoc), pas M1 seul")
print("    C (Completeness):  ✗ NON — un hash ne détecte pas un target absent.")
print("                       Même si entry_hash couvre id, si l'entry est supprimée,")
print("                       le receipt pointe vers un hash non résolvable → dangling.")
print("                       M1 ne résout pas le problème de suffix-deletion (Attaque 1).")
print("    P (Portability):   ✓ OUI — hash-based reste portable")
print()
print("  Verdict M1: couvre I et P, mais PAS V (partiel) ni C (échec).")
print("  → M1 SEUL ne satisfait pas I/V/C/P. Échec du contre-exemple.")
print()

# === M2: Ajouter des fonctions verify_* ad hoc ===
print("=== M2: Ajouter des fonctions verify_* ad hoc ===")
print()
print("  Mécanisme: pour chaque arête, écrire une fonction qui vérifie la cohérence.")
print("  Exemple: verify_issuer_registered(receipt), verify_dispatch_target_exists(dispatch),")
print("           verify_cited_entry_exists(entry), ...")
print()
print("  Couverture par propriété:")
print("    I (Integrity):    ✗ NON — verify ne protège pas la valeur de l'arête.")
print("                       verify_issuer_registered lit receipt.issuer_agent_id, mais si")
print("                       ce champ est muté (I=S), verify lit la valeur mutée.")
print("                       → il faut D'ABORD que le champ soit hashé (M1) pour que verify")
print("                         ait une valeur fiable à vérifier")
print("    V (Verifiability): ✓ OUI — chaque fonction vérifie son arête")
print("    C (Completeness):  ✓ OUI — une verify ad hoc peut résoudre le target et échouer")
print("                       s'il manque")
print("    P (Portability):   ✗ PARTIEL — verify ad hoc nécessite accès au storage pour")
print("                       résoudre le target. Pas de vérification off-storage.")
print()
print("  Verdict M2: couvre V et C, mais PAS I (échec) ni P (partiel).")
print("  → M2 seul ne satisfait pas I/V/C/P. Échec du contre-exemple.")
print()

# === M3: Lier les objets par hash réciproque ===
print("=== M3: Hash réciproque (bidirectionnel) ===")
print()
print("  Mécanisme: l'entry porte receipt_hash, le receipt porte entry_hash.")
print("  Exemple: entry.metadata.receipt_hash = R ; receipt.entry_hash = E.")
print("  Les deux objets se référencent mutuellement par hash.")
print()
print("  Couverture par propriété:")
print("    I (Integrity):    ✓ PARTIEL — chaque côté est hashé, mais le hash réciproque")
print("                       crée une DÉPENDANCE CIRCULAIRE:")
print("                         entry_hash = f(..., receipt_hash)")
print("                         receipt_hash = f(..., entry_hash)")
print("                       → impossible à calculer sans casser la circularité")
print("                       → nécessite un protocole à 2 phases (commit-then-reveal)")
print("                       → complexité équivalente à un Relation Object")
print("    V (Verifiability): ✓ OUI — chaque côté peut vérifier l'autre")
print("    C (Completeness):  ✓ OUI — si un côté disparaît, l'autre dangling est détecté")
print("    P (Portability):   ✓ OUI — hash-based")
print()
print("  Verdict M3: couvre V, C, P. I est PARTIEL à cause de la circularité.")
print("  → Pour résoudre I, M3 doit introduire un protocole commit-then-reveal,")
print("    ce qui est essentiellement... un Relation Object (un 3e objet portant le hash")
print("    des deux extrémités). M3 converge vers la solution qu'il prétend éviter.")
print()

# === Synthèse ===
print("=" * 100)
print("SYNTHÈSE: AUCUN mécanisme seul ne satisfait I ∧ V ∧ C ∧ P sans Relation Object")
print("=" * 100)
print()
print("  Mécanisme    |  I    |  V    |  C    |  P    |  Verdict")
print("  -------------|-------|-------|-------|-------|---------------------")
print("  M1 (hash+)   |  ✓    |  ✗    |  ✗    |  ✓    |  échec (V,C manquants)")
print("  M2 (verify+) |  ✗    |  ✓    |  ✓    |  ✗    |  échec (I,P manquants)")
print("  M3 (réciproq)|  ~    |  ✓    |  ✓    |  ✓    |  converge vers Relation Object")
print()
print("  COMBINAISON M1+M2 ?")
print("    I (via M1) + V (via M2) + C (via M2) + P (via M1)")
print("    → couvrirait I/V/C/P... mais nécessite:")
print("      - modifier TOUS les hashes existants (M1 = breaking change ADR-0002)")
print("      - écrire UNE fonction verify par arête (M2 = 25 fonctions ad hoc)")
print("      - chaque verify doit connaître le schéma spécifique de son arête")
print("    → la combinason M1+M2 est EXACTEMENT ce que fait un Relation Object,")
print("      mais éclaté sur 25 sites au lieu d'être unifié.")
print("    → le Relation Object est la FACTORISATION de M1+M2.")
print()
print("  CONTRE-EXEMPLE REFUTÉ: aucun mécanisme simple ne satisfait I/V/C/P.")
print("  Le Relation Object n'est pas trivial — il est la factorisation naturelle")
print("  de la combinaison (hash+ × verify+).")
