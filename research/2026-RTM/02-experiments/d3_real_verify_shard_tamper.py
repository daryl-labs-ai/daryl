#!/usr/bin/env python3
"""Découverte 3 — Vérification en conditions réelles: l'altération de id/shard/version
passe-t-elle verify_shard() sans détection sur un shard JSONL réel?

Méthode:
  1. Créer un shard avec 10 entries via Storage.append() (le chemin write normal).
  2. Laisser Storage écrire les entrées normalement — pas de proto.
  3. Intercepter les fichiers JSONL sur disque.
  4. Pour chaque entry, muter id, shard, ou version EN PLACE dans le fichier JSONL.
  5. Relancer verify_shard().
  6. Mesurer: détecte-t-il le tampering?

AUCUNE modification du kernel. On écrit directement dans les fichiers JSONL (append-only
est une propriété logique du kernel, pas un filesystem lock).
"""
from __future__ import annotations
import json, sys, tempfile, shutil
from datetime import datetime, timezone
from pathlib import Path

REPO = __import__("pathlib").Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage   # noqa
from dsm.core.models import Entry      # noqa
from dsm.verify import verify_shard   # noqa


def make_entry(i: int) -> Entry:
    return Entry(
        id=f"entry_{i:04d}",
        timestamp=datetime(2026, 3, 15, 10, 0, i % 60, tzinfo=timezone.utc),
        session_id="session_0001",
        source="agent_x",
        content=f"Entry content number {i}",
        shard="sessions",
        hash="",  # will be computed by Storage
        prev_hash=None,
        metadata={"event_type": "tool_call", "action_name": f"action_{i % 5}"},
        version="v2.0",
    )


def find_jsonl_lines(data_dir: Path, shard_id: str) -> Path:
    """Find the JSONL file for a segmented shard."""
    family_dir = data_dir / "shards" / shard_id.replace("shard_", "")
    if not family_dir.exists():
        return None
    segs = sorted(family_dir.glob("*.jsonl"))
    return segs[0] if segs else None


def mutate_field_in_jsonl(jsonl_path: Path, field: str, new_value) -> bool:
    """Mutate a field in every line of a JSONL file. Returns True if any line mutated."""
    mutated = 0
    lines = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                lines.append(line)
                continue
            obj = json.loads(line)
            old_val = obj.get(field)
            if old_val != new_value:
                obj[field] = new_value
                lines.append(json.dumps(obj, ensure_ascii=False) + "\n")
                mutated += 1
            else:
                lines.append(line)
    if mutated:
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    return mutated


def main():
    tmp = Path(tempfile.mkdtemp(prefix="d3_"))
    try:
        storage = Storage(data_dir=str(tmp))
        SHARD = "sessions"

        # Write 10 entries via the NORMAL write path
        print("=== Écriture de 10 entries via Storage.append() ===")
        for i in range(10):
            e = make_entry(i)
            result = storage.append(e)
            print(f"  entry_{i:04d} -> hash={result.hash[:16]}...")
        print()

        # Verify baseline (should be clean)
        result_clean = verify_shard(storage, SHARD)
        print(f"=== Vérification baseline (aucune altération) ===")
        print(f"  status = {result_clean.get('status')}")
        print(f"  entries_checked = {result_clean.get('entries_checked')}")
        print()

        # Find JSONL file
        jsonl = find_jsonl_lines(tmp, SHARD)
        print(f"  JSONL file: {jsonl}")
        print()

        # Test 1: mutate 'id' on ALL entries
        print("=== Test 1: Altération du champ 'id' (toutes les entries) ===")
        n_mut = mutate_field_in_jsonl(jsonl, "id", "TAMPERED_ID")
        result1 = verify_shard(storage, SHARD)
        print(f"  entries mutées: {n_mut}")
        print(f"  status = {result1.get('status')}")
        print(f"  DÉTECTÉ? {'NON — tampering invisible!' if result1.get('status') != 'TAMPERED' else 'OUI'}")
        print()

        # Restore ids
        lines = []
        with open(jsonl, "r") as f:
            for i, line in enumerate(f):
                if not line.strip(): continue
                obj = json.loads(line)
                obj["id"] = f"entry_{i:04d}"
                lines.append(json.dumps(obj, ensure_ascii=False) + "\n")
        with open(jsonl, "w") as f:
            f.writelines(lines)

        # Test 2: mutate 'shard'
        print("=== Test 2: Altération du champ 'shard' ===")
        mutate_field_in_jsonl(jsonl, "shard", "TAMPERED_SHARD")
        result2 = verify_shard(storage, SHARD)
        print(f"  status = {result2.get('status')}")
        print(f"  DÉTECTÉ? {'NON — tampering invisible!' if result2.get('status') != 'TAMPERED' else 'OUI'}")
        print()

        # Restore shard
        lines = []
        with open(jsonl, "r") as f:
            for line in f:
                if not line.strip(): continue
                obj = json.loads(line)
                obj["shard"] = "sessions"
                lines.append(json.dumps(obj, ensure_ascii=False) + "\n")
        with open(jsonl, "w") as f:
            f.writelines(lines)

        # Test 3: mutate 'version'
        print("=== Test 3: Altération du champ 'version' ===")
        mutate_field_in_jsonl(jsonl, "version", "CORRUPTED_VERSION")
        result3 = verify_shard(storage, SHARD)
        print(f"  status = {result3.get('status')}")
        print(f"  DÉTECTÉ? {'NON — tampering invisible!' if result3.get('status') != 'TAMPERED' else 'OUI'}")
        print()

        # Test 4: mutate 'content' (in-perimeter, should be detected)
        print("=== Test 4: Altération du champ 'content' (DANS le périmètre) ===")
        mutate_field_in_jsonl(jsonl, "content", "MUTATED CONTENT - ATTACK VECTOR")
        result4 = verify_shard(storage, SHARD)
        print(f"  status = {result4.get('status')}")
        print(f"  DÉTECTÉ? {'OUI — hash chain brisé!' if result4.get('status') == 'TAMPERED' else 'NON'}")
        print()

        # Test 5: mutate metadata.action_name (in-perimeter, should be detected)
        print("=== Test 5: Altération de metadata.action_name (DANS le périmètre) ===")
        mutate_field_in_jsonl(jsonl, "metadata", {"event_type": "tool_call", "action_name": "HACKED"})
        result5 = verify_shard(storage, SHARD)
        print(f"  status = {result5.get('status')}")
        print(f"  DÉTECTÉ? {'OUI — hash chain brisé!' if result5.get('status') == 'TAMPERED' else 'NON'}")
        print()

        # Summary
        print("=" * 60)
        print("=== RÉSUMÉ: périmètre d'intégrité de verify_shard() ===")
        detected_count = sum(1 for r in [result1, result2, result3] if r.get('status') == 'TAMPERED')
        protected_count = sum(1 for r in [result4, result5] if r.get('status') == 'TAMPERED')
        print(f"  Champs hors périmètre détectés comme TAMPERED : {detected_count}/3")
        print(f"  Champs dans périmètre détectés comme TAMPERED : {protected_count}/2")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
