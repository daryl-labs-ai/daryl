#!/usr/bin/env python3
"""Falsification 3 — Le Relation Object crée-t-il une RÉGRESSION?

La critique: si on introduit un Relation Object, on crée un nouveau graphe.
Les arêtes DE CE NOUVEAU GRAPHE sont-elles protégées?
Sinon, il faut des 'Relation-Relations' → régression infinie.

Arêtes potentielles du graphe de Relations:
  R1. Relation ──source_hash──▶ Entry      (déjà analysée, I/V/C/P ✓ par construction)
  R2. Relation ──target_hash──▶ Target     (déjà analysée, I/V/C/P ✓ par construction)
  R3. Relation ──relation_hash──▶ self     (hash de l'objet lui-même)
  R4. Relation ──prev_relation──▶ Relation (chaînage, comme prev_hash sur Entry)
  R5. Relation ──signed_by──▶ Agent        (qui a signé cette relation)

Questions de régression:
  Q1. Les arêtes R1,R2 sont-elles auto-couvertes par le modèle?
  Q2. R4 (chaînage) crée-t-il une NOUVELLE classe d'arêtes non protégées?
  Q3. R5 (signature) est-elle un gap nouveau?
  Q4. Y a-t-il une 'meta-régression' (le hash du Relation Object a-t-il
      besoin d'être lui-même référencé de manière vérifiable)?
"""
from __future__ import annotations
import sys, hashlib
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))
from dsm_primitives import hash_canonical, verify_hash

print("=" * 100)
print("RÉGRESSION: le Relation Object crée-t-il un nouveau graphe non protégé?")
print("=" * 100)
print()

# === Q1: R1, R2 (source_hash, target_hash) auto-couvertes? ===
print("=== Q1: source_hash et target_hash sont auto-couverts ===")
print()
print("  SignedRelation.relation_hash = hash(type, source_hash, target_hash, payload)")
print("  → source_hash et target_hash sont DANS relation_hash (I=H)")
print("  → verify() recompose et compare (V=Y)")
print("  → target absent → hash non recomposable → échec (C=Y)")
print("  → hash-based, pas d'id (P=Y)")
print("  → I/V/C/P TOUS satisfaits PAR CONSTRUCTION. Pas de nouvelle arête non protégée.")
print()

# === Q2: R4 (prev_relation chaining) — nouvelle arête? ===
print("=== Q2: chaînage des Relations (R4: prev_relation) ===")
print()
print("  Si on chaîne les Relations (R_n.prev = R_{n-1}.relation_hash),")
print("  on crée une arête Relation→Relation.")
print("  Cette arête a-t-elle besoin d'un META-Relation Object?")
print()
print("  NON, et voici pourquoi:")
print("  - prev_relation_hash est DANS relation_hash (comme prev_hash dans entry_hash)")
print("  - la vérification de la chaîne est IDENTIQUE à verify_shard sur les entries")
print("  - ce n'est pas une NOUVELLE classe de problème, c'est le MÊME mécanisme")
print("    déjà résolu pour les entries (verify_chain).")
print()
print("  → Le chaînage des Relations ne crée pas de méta-régression:")
print("    il réutilise le mécanisme déjà prouvé sur les entries.")
print()

# === DÉMONSTRATION: une chaîne de Relations se vérifie comme une chaîne d'entries ===
print("=== DÉMO: chaîne de Relations vérifiable (pas de méta-regression) ===")
print()

class SignedRelation:
    def __init__(self, rtype, source_hash, target_hash, prev_relation_hash=None, payload=None):
        self.rtype = rtype
        self.source_hash = source_hash
        self.target_hash = target_hash
        self.prev_relation_hash = prev_relation_hash
        self.payload = payload or {}
        self.relation_hash = hash_canonical({
            "type": rtype, "source": source_hash, "target": target_hash,
            "prev": prev_relation_hash, "payload": self.payload,
        })

    def verify_self(self):
        expected = hash_canonical({
            "type": self.rtype, "source": self.source_hash, "target": self.target_hash,
            "prev": self.prev_relation_hash, "payload": self.payload,
        })
        return expected == self.relation_hash

# Build a chain: agent_A produced entry_E1, entry_E1 cited entry_E0
h_A = "v1:" + "a"*10
h_E0 = "v1:" + "0"*10
h_E1 = "v1:" + "1"*10

r0 = SignedRelation("produced_by", h_E0, h_A, prev_relation_hash=None)
r1 = SignedRelation("cited_by", h_E1, h_E0, prev_relation_hash=r0.relation_hash)
r2 = SignedRelation("produced_by", h_E1, h_A, prev_relation_hash=r1.relation_hash)

print(f"  Chaîne: r0 → r1 → r2 (3 Relations)")
print(f"    r0: {r0.rtype}, hash={r0.relation_hash[:16]}... prev=None")
print(f"    r1: {r1.rtype}, hash={r1.relation_hash[:16]}... prev={r1.prev_relation_hash[:16]}...")
print(f"    r2: {r2.rtype}, hash={r2.relation_hash[:16]}... prev={r2.prev_relation_hash[:16]}...")
print()

# Verify chain integrity (same logic as verify_chain on entries)
def verify_relation_chain(relations):
    prev = None
    for r in relations:
        if not r.verify_self():
            return False, "relation_hash mismatch"
        if r.prev_relation_hash != prev:
            return False, f"chain broken at {r.rtype}: prev mismatch"
        prev = r.relation_hash
    return True, "chain valid"

ok, msg = verify_relation_chain([r0, r1, r2])
print(f"  verify_relation_chain([r0,r1,r2]): {ok} — {msg}")

# Now tamper: mutate r1's target
r1_tampered = SignedRelation("cited_by", h_E1, "v1:TAMPERED", prev_relation_hash=r0.relation_hash)
ok2, msg2 = verify_relation_chain([r0, r1_tampered, r2])
print(f"  verify_relation_chain avec r1.target muté: {ok2} — {msg2}")
# Note: r2.prev still points to ORIGINAL r1.hash, so chain breaks at r2
print(f"  → r2.prev_relation_hash pointe vers r1 ORIGINAL, pas r1_tampered")
print(f"  → La chaîne se brise elle-même (mécanisme identique à verify_shard)")
print()

# === Q3: signature (R5) — nouveau gap? ===
print("=== Q3: signature de Relation (R5: signed_by) ===")
print()
print("  Une Relation peut être signée: relation.signature = Ed25519(relation_hash).")
print("  L'arête signed_by pointe vers un Agent (via public_key).")
print("  Cette arête a-t-elle un gap?")
print()
print("  - Le signature couvre relation_hash (I=H sur la signature elle-même)")
print("  - verify_signature(relation_hash, sig, pubkey) existe déjà (dsm_primitives)")
print("  - MAIS: qui vérifie que pubkey appartient bien à l'agent claimé?")
print("  → C'est le MÊME gap que entry.source → agent (P4 Boucle 4)")
print("  → le Relation Object n'a PAS résolu ce gap; il l'a REPORTÉ.")
print("  → C'est une limite HONNÊTE du modèle.")
print()

# === Q4: meta-régression? ===
print("=== Q4: méta-régression (Relation sur Relation)? ===")
print()
print("  Le relation_hash couvre (type, source_hash, target_hash, prev, payload).")
print("  Toutes les arêtes de CE graphe (R1-R5) sont:")
print("    - soit dans relation_hash (R1,R2,R3,R4) → auto-couvertes")
print("    - soit réutilisent un mécanisme existant (R5 = signature, comme P9)")
print("  → AUCUNE ne nécessite un méta-Relation Object.")
print("  → La régression S'ARRÊTE au niveau 1.")
print()
print("  Pourquoi? Parce que le relation_hash est AUTO-RÉFÉRENTIEL:")
print("  il couvre ses propres arêtes sortantes. Le hash d'une entry ne le fait pas")
print("  (entry.hash ne couvre pas entry.id), c'est pourquoi les entries avaient")
print("  besoin de Relations. Mais une Relation n'a pas de champs")
print("  'relationnels non couverts' → pas de méta-régression.")
print()

print("=" * 100)
print("VERDICT RÉGRESSION")
print("=" * 100)
print()
print("  Q1 (source/target):  AUTO-COUVERT — I/V/C/P par construction")
print("  Q2 (chaînage):       PAS DE MÉTA-RÉGRESSION — mécanisme identique à verify_chain")
print("  Q3 (signature):      GAP REPORTÉ — relation.signature ne prouve pas que")
print("                        la clé appartient à l'agent claimé (même gap que P4)")
print("  Q4 (meta-regression): AUCUNE — relation_hash est auto-référentiel")
print()
print("  → Le Relation Object NE CRÉE PAS de régression infinie.")
print("  → IL REPORTe un gap existant (signature → identity binding).")
print("  → Honnêtement: le modèle résout I/V/C/P mais ne résout pas")
print("    le problème 'qui possède cette clé' (authenticité).")
print("  → Une 5e propriété (Authenticity) serait nécessaire pour le couvrir.")
print("    C'est la seule faiblesse trouvée.")
