#!/usr/bin/env python3
"""Relation Graph 3 — Prototype: une relation peut-elle être un objet vérifiable?

Hypothèse à falsifier: on PEUT définir une Relation(a,b) qui est elle-même
un objet hashé/signé/vérifiable, résistant aux attaques des Boucles 1-4.

Modèle proposé: SignedRelation
  Une relation entre deux objets est elle-même un objet avec:
    - relation_type: "produced_by", "cited_by", "dispatched_to", ...
    - source_hash:   hash canonique de l'objet source
    - target_hash:   hash canonique de l'objet target
    - relation_hash: hash canonique de (relation_type, source_hash, target_hash, metadata)
    - signature:     Ed25519 du relation_hash par l'objet source

Test: construire une relation Agent→Entry (produced_by) et vérifier qu'elle:
  R1. survit à la mutation de entry.id (Loop 3)
  R2. survit à la mutation de entry.shard (Loop 3)
  R3. détecte la mutation de l'agent_id (Loop 4 IA3 forgery)
  R4. détecte la mutation du contenu de l'entry
  R5. reste vérifiable indépendamment de a et b (portabilité)
"""
from __future__ import annotations
import hashlib, json, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage, _build_canonical_entry
from dsm.core.models import Entry
from dsm_primitives import hash_canonical, verify_hash


# === PROTOTYPE: SignedRelation ===

class SignedRelation:
    """Une relation entre deux objets DSM, elle-même vérifiable.

    relation_hash = hash_canonical({
        "relation_type": str,
        "source_hash": str,       # hash canonique de l'objet source
        "target_hash": str,       # hash canonique de l'objet target
        "metadata": dict,
    })

    Le relation_hash couvre les DEUX extrémités de la relation par leur hash
    canonique — pas par leur id ou leur champ mutable.
    """

    def __init__(self, relation_type, source_hash, target_hash, metadata=None):
        self.relation_type = relation_type
        self.source_hash = source_hash
        self.target_hash = target_hash
        self.metadata = metadata or {}
        self.relation_hash = self._compute_hash()

    def _compute_hash(self):
        return hash_canonical({
            "relation_type": self.relation_type,
            "source_hash": self.source_hash,
            "target_hash": self.target_hash,
            "metadata": self.metadata,
        })

    def verify(self, source_obj_hash, target_obj_hash):
        """Vérifie que la relation est intègre ET que ses extrémités
        correspondent aux objets réels."""
        # 1. relation_hash integrity
        expected = self._compute_hash()
        if expected != self.relation_hash:
            return {"valid": False, "reason": "relation_hash mismatch"}
        # 2. source binding
        if self.source_hash != source_obj_hash:
            return {"valid": False, "reason": "source hash does not match actual source"}
        # 3. target binding
        if self.target_hash != target_obj_hash:
            return {"valid": False, "reason": "target hash does not match actual target"}
        return {"valid": True, "reason": "relation fully verified"}


def make_entry(storage, shard, agent_id, content, metadata=None):
    e = Entry(
        id=f"{agent_id}_{datetime.now(timezone.utc).strftime('%H%M%S%f')}",
        timestamp=datetime.now(timezone.utc), session_id=f"sess_{agent_id}",
        source=agent_id, content=content, shard=shard,
        hash="", prev_hash=None, metadata=metadata or {"event_type": "decision"},
        version="v2.0",
    )
    return storage.append(e)


def find_jsonl(data_dir, shard):
    family = shard.replace("shard_", "")
    for p in (data_dir / "shards" / family).glob("*.jsonl"):
        return p


def mutate_field(jsonl, field, old, new):
    lines, n = [], 0
    with open(jsonl, "r") as f:
        for line in f:
            if not line.strip(): lines.append(line); continue
            obj = json.loads(line)
            if obj.get(field) == old:
                obj[field] = new; n += 1
            lines.append(json.dumps(obj, ensure_ascii=False) + "\n")
    with open(jsonl, "w") as f: f.writelines(lines)
    return n


def main():
    tmp = Path(tempfile.mkdtemp(prefix="rg3_"))
    try:
        storage = Storage(data_dir=str(tmp))
        SHARD = "collective"

        # Setup: Agent A produces an entry
        entry_A = make_entry(storage, SHARD, "agent_A", "Decision: X=42")
        print("=== PROTOTYPE: SignedRelation(Agent→Entry) ===")
        print(f"  entry_A: id={entry_A.id}, hash={entry_A.hash[:24]}...")

        # Build a SignedRelation: agent_A produced_by entry_A
        # source = agent_A (identity hash = hash of agent_id claim)
        agent_hash = hash_canonical({"agent_id": "agent_A", "claim": "produced entry_A"})
        rel = SignedRelation(
            relation_type="produced_by",
            source_hash=entry_A.hash,   # the entry
            target_hash=agent_hash,     # the agent identity
            metadata={"role": "producer", "ts": datetime.now(timezone.utc).isoformat()},
        )
        print(f"  SignedRelation: type={rel.relation_type}")
        print(f"    source_hash(entry)={rel.source_hash[:24]}...")
        print(f"    target_hash(agent)={rel.target_hash[:24]}...")
        print(f"    relation_hash={rel.relation_hash[:24]}...")
        print()

        # === R1: mutate entry.id (Loop 3 attack) ===
        print("=== R1: Mutation entry.id (Loop 3) ===")
        jsonl = find_jsonl(tmp, SHARD)
        mutate_field(jsonl, "id", entry_A.id, "TAMPERED_ID")
        entries_after = storage.read(SHARD, limit=100)
        entry_after = entries_after[0]
        vr1 = rel.verify(entry_after.hash, agent_hash)
        print(f"  verify relation après mutation id: {vr1}")
        print(f"  → La relation SURVIT car elle se base sur hash, pas id: {'OUI (SAFE)' if vr1['valid'] else 'NON'}")
        print()

        # === R2: mutate entry.shard (Loop 3 attack) ===
        print("=== R2: Mutation entry.shard (Loop 3) ===")
        mutate_field(jsonl, "shard", SHARD, "TAMPERED_SHARD")
        entries_after2 = storage.read(SHARD, limit=100)
        entry_after2 = entries_after2[0]
        vr2 = rel.verify(entry_after2.hash, agent_hash)
        print(f"  verify relation après mutation shard: {vr2}")
        print(f"  → La relation SURVIT car shard n'affecte pas le hash: {'OUI (SAFE)' if vr2['valid'] else 'NON'}")
        print()

        # === R3: agent forgery (Loop 4 IA3) — attacker claims different agent ===
        print("=== R3: Forgery agent_id (Loop 4 IA3) ===")
        attacker_agent_hash = hash_canonical({"agent_id": "attacker_Eve", "claim": "produced entry_A"})
        vr3 = rel.verify(entry_after2.hash, attacker_agent_hash)
        print(f"  verify relation avec faux agent_hash: {vr3}")
        print(f"  → Forgery DÉTECTÉ: {'OUI (SAFE)' if not vr3['valid'] else 'NON (BROKEN)'}")
        print()

        # === R4: content mutation (should break relation via hash change) ===
        print("=== R4: Mutation content (modifie le hash de l'entry) ===")
        mutate_field(jsonl, "content", entry_A.content, "TAMPERED CONTENT")
        entries_after3 = storage.read(SHARD, limit=100)
        entry_after3 = entries_after3[0]
        vr4 = rel.verify(entry_after3.hash, agent_hash)
        print(f"  verify relation après mutation content: {vr4}")
        print(f"  → Mutation de contenu DÉTECTÉE: {'OUI (SAFE)' if not vr4['valid'] else 'NON'}")
        print()

        # === R5: portability — verify without storage access ===
        print("=== R5: Portabilité (vérifiable sans accès au storage) ===")
        # Rebuild a fresh relation with original hashes
        rel_portable = SignedRelation("produced_by", entry_A.hash, agent_hash,
                                       {"role": "producer"})
        # Verify using ONLY the hashes, no storage read needed
        vr5 = rel_portable.verify(entry_A.hash, agent_hash)
        print(f"  verify relation avec hashes seuls (no storage): {vr5}")
        print(f"  → Portabilité: {'OUI — la relation est auto-contenue' if vr5['valid'] else 'NON'}")
        print()

        print("=" * 80)
        print("SYNTHÈSE: SignedRelation comme objet de confiance de première classe")
        print("=" * 80)
        results = [("R1 mutation id", vr1), ("R2 mutation shard", vr2),
                   ("R3 forgery agent", vr3), ("R4 mutation content", vr4),
                   ("R5 portabilité", vr5)]
        for name, r in results:
            status = "✓ SAFE" if r["valid"] == (name != "R3 forgery agent" and name != "R4 mutation content") else "?"
            # R3 and R4 should be detected (invalid), others should pass (valid)
            if name.startswith("R3") or name.startswith("R4"):
                ok = not r["valid"]
            else:
                ok = r["valid"]
            print(f"  {name:25} → {'✓' if ok else '✗'} {r['reason']}")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
