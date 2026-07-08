#!/usr/bin/env python3
"""Relation Graph 1 — Inventaire formel de toutes les arêtes implicites.

Méthode: scan statique exhaustif de tous les champs/attributs qui référencent
un autre objet DSM (entry_hash, prev_hash, dispatch_hash, entry_id, agent_id,
public_key, shard_id, shard_tip_hash, etc.).

Chaque arête = (source_type, field, target_type, location).
Classification automatique de chaque arête selon 4 axes.
"""
from __future__ import annotations
import re, sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

REPO = Path(__file__).resolve().parent.parent


@dataclass
class Edge:
    source_type: str      # Entry, Receipt, Dispatch, Identity, Attestation, Session
    field: str            # prev_hash, dispatch_hash, entry_id, ...
    target_type: str      # Entry, Agent, Receipt, Dispatch, ...
    location: str         # file:line
    storage: str = ""     # "in_hash" | "separate" | "metadata" | "payload"
    notes: str = ""


# Patterns that indicate a cross-object reference (an edge in the relation graph)
EDGE_PATTERNS = [
    # (regex, source_type_hint, field_name, target_type, storage_classification)
    (r'\bprev_hash\b',                "Entry",        "prev_hash",            "Entry",        "in_hash"),
    (r'\bentry_hash\b',               "any",          "entry_hash",           "Entry",        "separate"),
    (r'\bentry_id\b',                 "any",          "entry_id",             "Entry",        "separate"),
    (r'\bdispatch_hash\b',            "any",          "dispatch_hash",        "Dispatch",     "separate"),
    (r'\brouting_hash\b',             "any",          "routing_hash",         "Router",       "separate"),
    (r'\bdispatcher_entry_hash\b',    "DispatchRecord","dispatcher_entry_hash","Entry",        "separate"),
    (r'\bdispatcher_agent_id\b',      "DispatchRecord","dispatcher_agent_id",  "Agent",        "separate"),
    (r'\btarget_agent_id\b',          "DispatchRecord","target_agent_id",      "Agent",        "separate"),
    (r'\bissuer_agent_id\b',          "Receipt",      "issuer_agent_id",      "Agent",        "in_receipt_hash"),
    (r'\bagent_id\b',                 "any",          "agent_id",             "Agent",        "metadata"),
    (r'\bpublic_key\b',               "any",          "public_key",           "Agent",        "separate"),
    (r'\bowner_id\b',                 "any",          "owner_id",             "Owner",        "separate"),
    (r'\bshard_id\b',                 "any",          "shard_id",             "Shard",        "separate"),
    (r'\bshard_tip_hash\b',           "Receipt",      "shard_tip_hash",       "Shard-tip",    "in_receipt_hash"),
    (r'\bshard_entry_count\b',        "Receipt",      "shard_entry_count",    "Shard",        "in_receipt_hash"),
    (r'\bsession_id\b',               "any",          "session_id",           "Session",      "in_hash"),
    (r'\bcited_entry_hash\b',         "Entry",        "cited_entry_hash",     "Entry",        "metadata"),
    (r'\bcited_entry_id\b',           "Entry",        "cited_entry_id",       "Entry",        "metadata"),
    (r'\battestation_hash\b',         "Attestation",  "attestation_hash",     "Attestation",  "self"),
    (r'\binput_hash\b',               "Attestation",  "input_hash",           "Input",        "in_attest_hash"),
    (r'\boutput_hash\b',              "Attestation",  "output_hash",          "Output",       "in_attest_hash"),
    (r'\bmodel_id\b',                 "Attestation",  "model_id",             "Model",        "in_attest_hash"),
]

# Scan these files only — the trust-layer objects
SCAN_FILES = [
    ("src/dsm/core/models.py",          "Entry",        "Entry model"),
    ("src/dsm/core/storage.py",         "Entry",        "Entry write/read"),
    ("src/dsm/core/signing.py",         "Entry",        "hash chain"),
    ("src/dsm/causal.py",               "DispatchRecord","causal P10"),
    ("src/dsm/exchange.py",             "TaskReceipt",  "receipts P-exchange"),
    ("src/dsm/attestation.py",          "ComputeAttestation","attestation P11"),
    ("src/dsm/identity/identity_registry.py","RegisterEvent","identity registry"),
    ("src/dsm/identity/identity_manager.py","IdentityEvent","identity manager"),
    ("src/dsm/verify.py",               "Verifier",     "verification"),
    ("src/dsm/audit.py",                "Audit",        "audit"),
]


def scan_file(path, default_source):
    edges = []
    p = REPO / path
    if not p.exists():
        return edges
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        for pat, src_hint, fld, tgt, storage in EDGE_PATTERNS:
            if re.search(pat, line) and not line.strip().startswith("#"):
                src = src_hint if src_hint != "any" else default_source
                edges.append(Edge(src, fld, tgt, f"{path}:{i}", storage))
    return edges


all_edges = []
for path, default_src, _ in SCAN_FILES:
    all_edges.extend(scan_file(path, default_src))

# Dedupe by (source, field, target, storage)
seen = set()
unique_edges = []
for e in all_edges:
    key = (e.source_type, e.field, e.target_type, e.storage)
    if key not in seen:
        seen.add(key)
        unique_edges.append(e)

# Group by storage classification (the core finding)
by_storage = {}
for e in unique_edges:
    by_storage.setdefault(e.storage, []).append(e)

print("=" * 100)
print("RELATION GRAPH — INVENTAIRE DES ARÊTES IMPLICITES")
print("=" * 100)
print()
print(f"Total arêtes uniques identifiées: {len(unique_edges)}")
print()

print("=== ARÊTES PAR MODE DE STOCKAGE (classification d'intégrité) ===")
print()
order = ["in_hash", "in_receipt_hash", "in_attest_hash", "metadata", "separate", "self"]
labels = {
    "in_hash":        "DANS LE HASH CANONIQUE (protégé)",
    "in_receipt_hash":"DANS LE HASH DU RECEIPT (protégé)",
    "in_attest_hash": "DANS LE HASH D'ATTESTATION (protégé)",
    "metadata":       "DANS METADATA (protégé car metadata est hashé)",
    "separate":       "CHAMP SÉPARÉ (non protégé par défaut)",
    "self":           "SELF-REFERENCE (hash de l'objet lui-même)",
}
for storage in order:
    if storage not in by_storage:
        continue
    edges = by_storage[storage]
    print(f"--- {labels.get(storage, storage)} : {len(edges)} arêtes ---")
    for e in edges:
        print(f"  {e.source_type:22} ──{e.field:28}──▶ {e.target_type}")
    print()

print("=" * 100)
print("SYNTHÈSE: distribution des arêtes par niveau de protection")
print("=" * 100)
protected = sum(len(v) for k, v in by_storage.items() if k.startswith("in_") or k == "metadata")
unprotected = by_storage.get("separate", [])
print(f"  Arêtes PROTÉGÉES (dans un hash):     {protected}")
print(f"  Arêtes NON PROTÉGÉES (champ séparé): {len(unprotected)}")
print(f"  Ratio protégé/total:                 {protected}/{protected+len(unprotected)} = {protected*100//(protected+len(unprotected))}%")
print()
print("=== ARÊTES NON PROTÉGÉES (les relations fragiles) ===")
for e in unprotected:
    print(f"  {e.source_type:22} ──{e.field:28}──▶ {e.target_type}   [{e.location}]")
