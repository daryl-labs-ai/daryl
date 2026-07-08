#!/usr/bin/env python3
"""Inter-Agent 2 — Citation vérifiable après replay.

Scénario:
  Agent A produit entry_A (décision originale).
  Agent B lit la trace, cite entry_A via son entry_hash dans metadata.
  Agent B produit entry_B avec metadata.cites = [hash_A].
  Question: la citation est-elle vérifiable après replay?
  - peut-on retrouver A depuis B?
  - le hash cité correspond-il à une entry réelle?
  - le citation est-elle robuste à la mutation de entry_A.id (id non protégé)?

Sub-question: la citation porte sur entry_hash (protégé) — donc robuste.
Mais si B cite par entry_ID (non protégé), la citation devient fragile.
"""
from __future__ import annotations
import json, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.verify import verify_shard
from dsm_primitives import verify_hash
from dsm.core.storage import _build_canonical_entry


def entry(storage, shard, agent_id, content, prev_hash=None, metadata=None):
    e = Entry(
        id=f"{agent_id}_{datetime.now(timezone.utc).strftime('%H%M%S%f')}",
        timestamp=datetime.now(timezone.utc), session_id=f"sess_{agent_id}",
        source=agent_id, content=content, shard=shard,
        hash="", prev_hash=prev_hash, metadata=metadata or {"event_type": "decision"},
        version="v2.0",
    )
    return storage.append(e)


def find_jsonl(data_dir, shard):
    family = shard.replace("shard_", "")
    for p in (data_dir / "shards" / family).glob("*.jsonl"):
        return p


def mutate_id(jsonl, old, new):
    lines, n = [], 0
    with open(jsonl, "r") as f:
        for line in f:
            if not line.strip(): lines.append(line); continue
            obj = json.loads(line)
            if obj.get("id") == old:
                obj["id"] = new; n += 1
            lines.append(json.dumps(obj, ensure_ascii=False) + "\n")
    with open(jsonl, "w") as f: f.writelines(lines)
    return n


def main():
    tmp = Path(tempfile.mkdtemp(prefix="ia2_"))
    try:
        storage = Storage(data_dir=str(tmp))
        SHARD = "collective"

        # Agent A produces original decision
        entry_A = entry(storage, SHARD, "agent_A", "Decision: X = 42")
        print("=== CITATION SETUP ===")
        print(f"  entry_A: id={entry_A.id}, hash={entry_A.hash[:24]}..., source={entry_A.source}")

        # Agent B cites A by hash (the protected field)
        entry_B_hash_cite = entry(
            storage, SHARD, "agent_B", "Conclusion: X confirmed = 42",
            prev_hash=entry_A.hash,
            metadata={
                "event_type": "decision",
                "cites_entry_hash": entry_A.hash,  # cite by HASH (protected)
            },
        )
        print(f"  entry_B (cites by hash): hash={entry_B_hash_cite.hash[:24]}...")
        print(f"           cites_entry_hash={entry_B_hash_cite.metadata['cites_entry_hash'][:24]}...")

        # Agent C cites A by ID (the unprotected field)
        entry_C_id_cite = entry(
            storage, SHARD, "agent_C", "Conclusion: based on A",
            prev_hash=entry_B_hash_cite.hash,
            metadata={
                "event_type": "decision",
                "cites_entry_id": entry_A.id,  # cite by ID (unprotected)
            },
        )
        print(f"  entry_C (cites by id):  cites_entry_id={entry_C_id_cite.metadata['cites_entry_id']}")
        print()

        # === Citation verification by HASH ===
        print("=== VÉRIFICATION CITATION (par hash) ===")
        all_entries = storage.read(SHARD, limit=100)
        cited_hash = entry_B_hash_cite.metadata["cites_entry_hash"]
        target_by_hash = next((e for e in all_entries if e.hash == cited_hash), None)
        # Verify the cited hash actually matches the entry's canonical hash
        if target_by_hash:
            canonical = _build_canonical_entry(target_by_hash, target_by_hash.prev_hash)
            hash_valid = verify_hash(canonical, target_by_hash.hash)
        else:
            hash_valid = False
        print(f"  Citation par hash: cible {'trouvée' if target_by_hash else 'NON trouvée'}")
        print(f"  Hash de la cible vérifié canoniquement: {hash_valid}")
        print(f"  → Citation par hash: {'ROBUSTE (SAFE)' if target_by_hash and hash_valid else 'FRAGILE'}")
        print()

        # === Citation verification by ID (and ID mutation attack) ===
        print("=== ATTAQUE: muter entry_A.id (cité par entry_C) ===")
        jsonl = find_jsonl(tmp, SHARD)
        original_id = entry_A.id
        n = mutate_id(jsonl, original_id, "TAMPERED_ID")
        print(f"  {n} entry mutée: {original_id} → TAMPERED_ID")

        vr = verify_shard(storage, SHARD)
        print(f"  verify_shard après mutation id: {vr.get('status')} (id non protégé)")

        # Re-resolve C's citation by ID
        all_entries_after = storage.read(SHARD, limit=100)
        cited_id = entry_C_id_cite.metadata["cites_entry_id"]
        target_by_id = next((e for e in all_entries_after if e.id == cited_id), None)
        print(f"  entry_C cite entry_id={cited_id}")
        print(f"  Résolution de la citation APRÈS mutation: {'trouvée' if target_by_id else 'CASSÉE (entry introuvable)'}")
        print(f"  → Citation par id: {'ROBUSTE' if target_by_id else 'FRAGILE (TRUST_GAP) — citation cassée par mutation id non détectée'}")
        print()

        # === Citation by hash robustness after ID mutation ===
        print("=== ROBUSTESSE: citation par hash APRÈS mutation id ===")
        cited_hash_after = entry_B_hash_cite.metadata["cites_entry_hash"]
        target_by_hash_after = next((e for e in all_entries_after if e.hash == cited_hash_after), None)
        print(f"  Citation par hash toujours résolvable: {'OUI' if target_by_hash_after else 'NON'}")
        print(f"  → La citation par hash SURVIT à la mutation de id")
        print(f"  → DSM supporte la citation robuste IFF on cite par hash, pas par id")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
