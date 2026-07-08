#!/usr/bin/env python3
"""Relation Graph 2 — Matrice 4-axes de chaque arête.

Pour chaque arête du graphe, classification selon:
  I (Integrity)    : la valeur de l'arête est-elle protégée par un hash?
                     - HASHED: dans un hash canonique/receipt/attestation
                     - SEPARATE: champ libre, mutable sans invalider l'objet porteur
  V (Verifiability): existe-t-il une fonction de vérification qui valide cette arête?
                     - YES: verify_X() ou équivalent contrôle la cohérence
                     - NO : aucune fonction ne valide la relation
  C (Completeness) : la suppression de l'arête (target disparu) est-elle détectée?
                     - YES: orphan/missing détecté à la lecture
                     - NO : dangling silencieux
  P (Portability)  : l'arête survit-elle à un export/import (receipt cross-shard)?
                     - YES: hash-based, reproductible
                     - NO : id/path-based, dépend du contexte local
"""
from __future__ import annotations

# Each entry: (source, field, target, I, V, C, P, evidence)
# I/V/C/P ∈ {H/S}x{Y/N}x{Y/N}x{Y/N}  where H=hashed, S=separate
MATRIX = [
    # === Entry internal edges ===
    ("Entry",   "prev_hash",        "Entry",   "H", "Y", "N", "Y", "in_hash; verify_shard checks chain; but truncation of target = orphan undetected without pin"),
    ("Entry",   "session_id",       "Session", "H", "N", "N", "Y", "in_hash; but no verify_session_link() exists; session may not exist"),

    # === Receipt edges ===
    ("Receipt", "issuer_agent_id",  "Agent",   "H", "N", "N", "Y", "in_receipt_hash; but no verify_issuer_registered()"),
    ("Receipt", "entry_hash",       "Entry",   "S", "Y", "Y", "Y", "separate field; verify_receipt_against_storage checks hash_matches"),
    ("Receipt", "entry_id",         "Entry",   "S", "Y", "N", "N", "separate; resolve by id (unprotected); orphan if id mutated (Loop3)"),
    ("Receipt", "shard_tip_hash",   "Shard",   "H", "N", "N", "Y", "in_receipt_hash; no verify_tip_matches_storage()"),
    ("Receipt", "dispatch_hash",    "Dispatch","S", "N", "N", "Y", "separate; NOT in receipt_hash (Loop4 IA1); no receipt-level verify"),
    ("Receipt", "routing_hash",     "Router",  "S", "N", "N", "Y", "separate; NOT in receipt_hash; no verify"),

    # === DispatchRecord edges ===
    ("Dispatch","dispatch_hash",    "Dispatch","S", "Y", "N", "Y", "self-computed via create_dispatch_hash; verify_dispatch_hash re-computes"),
    ("Dispatch","dispatcher_entry_hash","Entry","S","Y","N","Y","input to dispatch_hash; verify_dispatch_hash covers it"),
    ("Dispatch","dispatcher_agent_id","Agent","S","N","N","N","separate; NOT in dispatch_hash; agent may not exist"),
    ("Dispatch","target_agent_id",  "Agent",   "S", "N", "N", "N", "separate; NOT in dispatch_hash (Loop4); rewirable"),
    ("Dispatch","routing_hash",     "Router",  "S", "N", "N", "Y", "separate; create_routing_hash exists but no verify against registry"),

    # === Attestation edges ===
    ("Attest",  "input_hash",       "Input",   "H", "Y", "N", "Y", "in_attestation_hash; re-computable"),
    ("Attest",  "output_hash",      "Output",  "H", "Y", "N", "Y", "in_attestation_hash; re-computable"),
    ("Attest",  "model_id",         "Model",   "H", "N", "N", "Y", "in_attestation_hash; but no verify_model_registered()"),
    ("Attest",  "agent_id",         "Agent",   "H", "N", "N", "Y", "in_attestation_hash; but no link to identity registry"),
    ("Attest",  "entry_hash",       "Entry",   "S", "N", "N", "Y", "separate pointer; no verify_attest_against_entry()"),
    ("Attest",  "dispatch_hash",    "Dispatch","S", "N", "N", "Y", "separate; no verify"),

    # === Identity edges ===
    ("Register","agent_id",         "Agent",   "M", "N", "N", "N", "metadata field (in entry hash); latest-wins overwrite (Loop4 IA3)"),
    ("Register","public_key",       "Agent",   "S", "N", "N", "Y", "separate; no verify key matches identity claim"),
    ("Register","owner_id",         "Owner",   "S", "Y", "N", "N", "separate; revoke() checks owner_id matches (partial)"),

    # === Cross-object citation (convention, not enforced) ===
    ("Entry",   "cited_entry_hash", "Entry",   "H", "N", "N", "Y", "metadata; protected IF used; but no verify_citation()"),
    ("Entry",   "cited_entry_id",   "Entry",   "S", "N", "N", "N", "metadata convention; unprotected; breaks on id mutation (Loop4 IA2)"),

    # === Entry → Agent (the produced_by relation, implicit) ===
    ("Entry",   "source",           "Agent",   "H", "N", "N", "Y", "in_hash as 'source'; but no verify_producer_registered()"),
]


def main():
    print("=" * 110)
    print("MATRICE DES RELATIONS — Intégrité(I) Vérifiabilité(V) Complétude(C) Portabilité(P)")
    print("=" * 110)
    print()
    print("I: H=hashé(protégé)  M=métadata(hashé)  S=séparé(non protégé)")
    print("V: Y=verify existe   N=aucune vérification")
    print("C: Y=orphan détecté  N=dangling silencieux")
    print("P: Y=portable(hash)  N=contextuel(id/path)")
    print()
    header = f"{'Source':10} {'Field':24} {'Target':10} {'I':2} {'V':2} {'C':2} {'P':2}  Evidence"
    print(header)
    print("-" * 110)

    counts = {"H_protected": 0, "S_unprotected": 0, "V_yes": 0, "V_no": 0, "C_yes": 0, "C_no": 0, "P_yes": 0, "P_no": 0}
    for src, fld, tgt, I, V, C, P, ev in MATRIX:
        print(f"{src:10} {fld:24} {tgt:10} {I:2} {V:2} {C:2} {P:2}  {ev[:60]}")
        if I in ("H", "M"): counts["H_protected"] += 1
        else: counts["S_unprotected"] += 1
        if V == "Y": counts["V_yes"] += 1
        else: counts["V_no"] += 1
        if C == "Y": counts["C_yes"] += 1
        else: counts["C_no"] += 1
        if P == "Y": counts["P_yes"] += 1
        else: counts["P_no"] += 1

    n = len(MATRIX)
    print()
    print("=" * 110)
    print("SYNTHÈSE — LA THÈSE RELATIONNELLE EN CHIFFRES")
    print("=" * 110)
    print(f"  Arêtes totales:                     {n}")
    print(f"  Intégrité (I) protégées par hash:   {counts['H_protected']}/{n}  = {counts['H_protected']*100//n}%")
    print(f"  Intégrité (I) non protégées:        {counts['S_unprotected']}/{n}  = {counts['S_unprotected']*100//n}%")
    print(f"  Vérifiabilité (V) — verify existe:  {counts['V_yes']}/{n}  = {counts['V_yes']*100//n}%")
    print(f"  Vérifiabilité (V) — AUCUNE verify:  {counts['V_no']}/{n}  = {counts['V_no']*100//n}%")
    print(f"  Complétude (C) — orphan détecté:    {counts['C_yes']}/{n}  = {counts['C_yes']*100//n}%")
    print(f"  Complétude (C) — dangling silencieux:{counts['C_no']}/{n} = {counts['C_no']*100//n}%")
    print(f"  Portabilité (P) — hash-based:       {counts['P_yes']}/{n}  = {counts['P_yes']*100//n}%")
    print(f"  Portabilité (P) — contextuelle:     {counts['P_no']}/{n}  = {counts['P_no']*100//n}%")
    print()

    # The core thesis metric: edges that are FULLY verified objects
    fully_verified = sum(1 for _,_,_,I,V,C,P,_ in MATRIX if I in ("H","M") and V=="Y" and C=="Y" and P=="Y")
    partial = sum(1 for _,_,_,I,V,C,P,_ in MATRIX if (I in ("H","M")) and (V=="Y" or C=="Y"))
    print("=== MÉTRIQUE CENTRALE: les relations comme objets de première classe ===")
    print(f"  Arêtes 'relation-objet' complètes (I=H, V=Y, C=Y, P=Y): {fully_verified}/{n}")
    print(f"  Arêtes partiellement vérifiées:                        {partial}/{n}")
    print(f"  → DSM traite {fully_verified}/{n} relations comme objets vérifiables de bout en bout")
    pct = fully_verified*100//n if n else 0
    print(f"  → Couverture relationnelle: {pct}%")
    if pct < 30:
        print(f"  → CONCLUSION: DSM protège les OBJETS, pas les RELATIONS. La thèse est confirmée.")


if __name__ == "__main__":
    main()
