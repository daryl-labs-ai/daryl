"""replay_b.py — replays every vector under EVERY permutation of its pack list and emits results-b.json
exactly as inputs/REPLAY-ENVELOPE.md specifies.

Reads only /tmp/implb/inputs/. No expected output and no expected hash exists in the file it reads.
"""

from __future__ import annotations

import json
import os
import sys
from itertools import permutations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from resolver_b import envelope, hash_v1, resolve  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
VECTOR_FILE = os.path.join(HERE, "inputs", "resolution-vectors.INPUTS-ONLY.json")
OUT_FILE = os.path.join(HERE, "results-b.json")


def main() -> int:
    with open(VECTOR_FILE, "r", encoding="utf-8") as handle:
        spec = json.load(handle)

    registry = spec["packs"]
    resolver_version = spec["resolver_version"]

    vectors_out = []
    total_permutations = 0
    fanned_out = []

    for vector in spec["vectors"]:
        keys = list(vector["packs"])
        evaluated_at = vector["evaluated_at"]

        by_permutation = []
        outputs = {}

        for order in permutations(keys):
            documents = [registry[k]["document"] for k in order]
            result = resolve(documents, evaluated_at, resolver_version)
            env = envelope(result)
            key = hash_v1(env)
            outputs.setdefault(key, env)
            by_permutation.append({"order": list(order), "output_hash": key})

        by_permutation.sort(key=lambda row: row["order"])
        total_permutations += len(by_permutation)
        if len(outputs) != 1:
            fanned_out.append((vector["id"], len(outputs)))

        vectors_out.append(
            {
                "vector_id": vector["id"],
                "permutation_count": len(by_permutation),
                "distinct_outputs": len(outputs),
                "by_permutation": by_permutation,
                "outputs": outputs,
            }
        )

    document = {
        "schema_version": "replay-envelope.v0.1",
        "implementation": "B",
        "resolver_version": resolver_version,
        "vector_file": "resolution-vectors.v0.1.json",
        "vectors": vectors_out,
    }

    with open(OUT_FILE, "w", encoding="utf-8") as handle:
        json.dump(document, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    for vector in vectors_out:
        env = next(iter(vector["outputs"].values()))
        if env["outcome"] == "resolved":
            summary = "resolved  manifest={} contested={}".format(
                env["effective_manifest_hash"][:14], len(env["contested_paths"])
            )
        else:
            summary = "refused   {} {}".format(env["phase"], ",".join(env["refusal_codes"]))
        print(
            "{:34s} perms={:3d} distinct={}  {}".format(
                vector["vector_id"],
                vector["permutation_count"],
                vector["distinct_outputs"],
                summary,
            )
        )

    print("\nvectors={} permutations={}".format(len(vectors_out), total_permutations))

    if fanned_out:
        print("\nPERMUTATION FAN-OUT (defect):")
        for vector_id, count in fanned_out:
            print("  {} -> {} distinct outputs".format(vector_id, count))
        return 1

    print("permutation-invariance: distinct_outputs == 1 for every vector")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
