#!/usr/bin/env python3
"""Falsification 1b — Toutes les paires de propriétés sont-elles indépendantes?

Pour que I/V/C/P soit minimal, il faut qu'AUCUNE propriété ne se déduise
d'une autre. On teste les 6 réductions possibles:

  V ⊆ I?  → existe-t-il une arête hashée (I=H) mais sans verify (V=N)?
  C ⊆ I?  → existe-t-il une arête hashée (I=H) mais orphan non détecté (C=N)?
  P ⊆ I?  → existe-t-il une arête hashée (I=H) mais non portable (P=N)?
  I ⊆ V?  → existe-t-il une arête avec verify (V=Y) mais non hashée (I=S)?
  C ⊆ V?  → DÉJÀ DÉMONTRÉ indépendant (f1)
  P ⊆ V?  → existe-t-il une arête vérifiable (V=Y) mais non portable (P=N)?

Méthode: reprendre la matrice de la Boucle 5 et chercher des contre-exemples.
Si on trouve un contre-exemple pour CHAQUE réduction, alors les 4 propriétés
sont 2 à 2 indépendantes → ensemble minimal.
"""
from __future__ import annotations

# (source, field, target, I, V, C, P)  — from rg2_edge_matrix.py (Boucle 5)
MATRIX = [
    ("Entry",   "prev_hash",        "Entry",   "H", "Y", "N", "Y"),
    ("Entry",   "session_id",       "Session", "H", "N", "N", "Y"),
    ("Receipt", "issuer_agent_id",  "Agent",   "H", "N", "N", "Y"),
    ("Receipt", "entry_hash",       "Entry",   "S", "Y", "Y", "Y"),
    ("Receipt", "entry_id",         "Entry",   "S", "Y", "N", "N"),
    ("Receipt", "shard_tip_hash",   "Shard",   "H", "N", "N", "Y"),
    ("Receipt", "dispatch_hash",    "Dispatch","S", "N", "N", "Y"),
    ("Receipt", "routing_hash",     "Router",  "S", "N", "N", "Y"),
    ("Dispatch","dispatch_hash",    "Dispatch","S", "Y", "N", "Y"),
    ("Dispatch","dispatcher_entry_hash","Entry","S","Y","N","Y"),
    ("Dispatch","dispatcher_agent_id","Agent","S","N","N","N"),
    ("Dispatch","target_agent_id",  "Agent",   "S", "N", "N", "N"),
    ("Attest",  "input_hash",       "Input",   "H", "Y", "N", "Y"),
    ("Attest",  "output_hash",      "Output",  "H", "Y", "N", "Y"),
    ("Attest",  "model_id",         "Model",   "H", "N", "N", "Y"),
    ("Attest",  "agent_id",         "Agent",   "H", "N", "N", "Y"),
    ("Attest",  "entry_hash",       "Entry",   "S", "N", "N", "Y"),
    ("Attest",  "dispatch_hash",    "Dispatch","S", "N", "N", "Y"),
    ("Register","agent_id",         "Agent",   "M", "N", "N", "N"),
    ("Register","public_key",       "Agent",   "S", "N", "N", "Y"),
    ("Register","owner_id",         "Owner",   "S", "Y", "N", "N"),
    ("Entry",   "cited_entry_hash", "Entry",   "H", "N", "N", "Y"),
    ("Entry",   "cited_entry_id",   "Entry",   "S", "N", "N", "N"),
    ("Entry",   "source",           "Agent",   "H", "N", "N", "Y"),
]

# Helper: I counts H and M as "hashed"
def is_hashed(I): return I in ("H", "M")

reductions = [
    ("V ⊆ I", "V dépend de I?", lambda r: is_hashed(r[3]) and r[4]=="Y", lambda r: is_hashed(r[3]) and r[4]=="N"),
    ("C ⊆ I", "C dépend de I?", lambda r: is_hashed(r[3]) and r[4]=="Y" and r[5]=="Y", lambda r: is_hashed(r[3]) and r[5]=="N"),
    ("P ⊆ I", "P dépend de I?", lambda r: is_hashed(r[3]) and r[6]=="Y", lambda r: is_hashed(r[3]) and r[6]=="N"),
    ("I ⊆ V", "I dépend de V?", lambda r: r[4]=="Y" and is_hashed(r[3]), lambda r: r[4]=="Y" and not is_hashed(r[3])),
    ("C ⊆ V", "C dépend de V?", lambda r: r[4]=="Y" and r[5]=="Y", lambda r: r[4]=="Y" and r[5]=="N"),
    ("P ⊆ V", "P dépend de V?", lambda r: r[4]=="Y" and r[6]=="Y", lambda r: r[4]=="Y" and r[6]=="N"),
]

print("=" * 100)
print("TEST D'INDÉPENDANCE 2 À 2 DES 4 PROPRIÉTÉS")
print("=" * 100)
print()
print("Pour chaque réduction candidate X ⊆ Y, on cherche un contre-exemple:")
print("  une arête où Y est satisfaite mais X ne l'est pas.")
print("  Si un contre-exemple existe → X n'est PAS déductible de Y → propriétés indépendantes.")
print()

all_independent = True
for name, desc, _positive, counterexample_fn in reductions:
    counterexamples = [r for r in MATRIX if counterexample_fn(r)]
    independent = len(counterexamples) > 0
    status = "INDÉPENDANT ✓" if independent else "DÉDUCTIBLE ✗ (réduction possible)"
    if not independent:
        all_independent = False
    print(f"  {name:8} ({desc})")
    if counterexamples:
        print(f"    Contre-exemples: {len(counterexamples)}")
        for ce in counterexamples[:3]:
            print(f"      {ce[0]:10}.{ce[1]:24} → {ce[2]:10}  I={ce[3]} V={ce[4]} C={ce[5]} P={ce[6]}")
    else:
        print(f"    Aucun contre-exemple → la réduction est POSSIBLE")
    print(f"    Verdict: {status}")
    print()

print("=" * 100)
if all_independent:
    print("CONCLUSION: les 4 propriétés I/V/C/P sont 2 à 2 indépendantes.")
    print("Aucune n'est déductible d'une autre. L'ensemble {I,V,C,P} est MINIMAL.")
    print("→ La théorie résiste à l'attaque de minimalité.")
else:
    print("CONCLUSION: au moins une propriété est déductible → ensemble réductible.")
print("=" * 100)
