#!/usr/bin/env python3
"""Découverte 2 — Périmètre du hash canonique : quels champs sont protégés?

Hypothèse à falsifier: "tous les champs pertinents d'un entry sont dans le hash."

_canonical_hash ne couvre que 6 champs sur 9+ dans l'Entry model:
  couverts: session_id, source, timestamp, metadata, content, prev_hash
  absents: id, shard, hash, version

Question: si on mute un champ ABSENT du hash, verify_hash ne le détecte pas.
Est-ce intentionnel (design choice) ou un oubli?

Méthode:
  1. Construire un entry canonique et hasher.
  2. Pour chaque champ du JSONL (y compris ceux hors canonique), muter la valeur.
  3. Appeler verify_hash sur la version mutée avec le hash d'origine.
  4. Si verify retourne True => le champ est HORS PÉRIMÈTRE D'INTÉGRITÉ.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone

REPO = __import__("pathlib").Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))
from dsm_primitives import hash_canonical, verify_hash  # noqa

# Build canonical entry (exact replica of _build_canonical_entry)
CANONICAL_ENTRY = {
    "session_id": "session_0001",
    "source": "agent_x",
    "timestamp": "2026-03-15T10:30:00.123456+00:00",
    "metadata": {"event_type": "tool_call", "action_name": "write_file"},
    "content": "Hello world",
    "prev_hash": None,
}
original_hash = hash_canonical(CANONICAL_ENTRY)
print(f"Hash original: {original_hash}")
print()

# Full on-disk JSONL representation (what _entry_from_event_data would see)
FULL_ENTRY = {
    "id": "abc-123-def",
    "timestamp": CANONICAL_ENTRY["timestamp"],
    "session_id": CANONICAL_ENTRY["session_id"],
    "source": CANONICAL_ENTRY["source"],
    "content": CANONICAL_ENTRY["content"],
    "shard": "sessions",
    "hash": original_hash,
    "prev_hash": None,
    "metadata": CANONICAL_ENTRY["metadata"],
    "version": "v2.0",
}

# Now test: for each field in FULL_ENTRY, mutate it, rebuild canonical, verify
mutations = [
    ("id",          "MUTATED-ID-999",          "absent du canonique"),
    ("shard",       "MUTATED_SHARD",           "absent du canonique"),
    ("version",     "MUTATED_VERSION",         "absent du canonique"),
    ("session_id",  "MUTATED_SESSION",          "DANS le canonique"),
    ("source",      "MUTATED_SOURCE",           "DANS le canonique"),
    ("timestamp",   "2099-01-01T00:00:00+00:00","DANS le canonique"),
    ("content",     "MUTATED_CONTENT",          "DANS le canonique"),
    ("prev_hash",   "deadbeef",                 "DANS le canonique"),
    ("metadata",    {"injected": "attack"},     "DANS le canonique"),
]

print(f"{'champ':14} {'dans canonique?':18} {'verify original?':17} {'impact':10}")
print("-" * 65)

detected_by_hash = 0
undetected = []

for field, new_val, note in mutations:
    mutated_full = dict(FULL_ENTRY)
    mutated_full[field] = new_val

    # Rebuild canonical entry from the MUTATED full entry (simulating verify path)
    mutated_canonical = {
        "session_id": mutated_full["session_id"],
        "source": mutated_full["source"],
        "timestamp": mutated_full["timestamp"],
        "metadata": mutated_full.get("metadata") or {},
        "content": mutated_full["content"],
        "prev_hash": mutated_full["prev_hash"],
    }

    still_verifies = verify_hash(mutated_canonical, original_hash)

    if still_verifies:
        impact = "NON DÉTECTÉ"
        undetected.append((field, note))
    else:
        impact = "DÉTECTÉ ✓"
        detected_by_hash += 1

    canon = "OUI" if note.startswith("DANS") else "NON"
    ver = "True (TAMPERED!)" if still_verifies else "False (OK)"
    print(f"{field:14} {canon:18} {ver:17} {impact:10}")

print()
print(f"=== Synthèse ===")
print(f"  Champs protégés par le hash : {detected_by_hash}/{len(mutations)}")
print(f"  Champs MUTABLES sans détection : {len(undetected)}/{len(mutations)}")
if undetected:
    print()
    print(f"  Champs hors périmètre d'intégrité:")
    for field, note in undetected:
        print(f"    • {field:14} — {note}")
    print()
    print(f"  === PROPRIÉTÉ DÉCOUVERTE ===")
    print(f"  Ces champs peuvent être altérés post-écriture sans que verify_shard()")
    print(f"  ne signale TAMPERED. Le hash chain protège 6 champs sur 9+.")
    print(f"  Les champs id, shard, version sont des MÉTADONNÉES NON INTÈGRES.")
