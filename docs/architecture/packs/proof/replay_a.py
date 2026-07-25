#!/usr/bin/env python3
"""Emit implementation **A**'s complete result in the neutral replay envelope.

This is an *adapter*, not a resolver. It contains no composition rule, no
precedence, no merge semantics and no refusal ordering: it calls
``pack_resolver_ref.resolve`` and serialises what comes back, exactly as
``proof/REPLAY-ENVELOPE.md`` specifies.

It is run **before implementation B exists**, and its output is frozen. That
ordering matters: A cannot have been tuned to agree with B if A's result was
written down first.

    python3 docs/architecture/packs/proof/replay_a.py

Writes ``proof/results-a.json``. Exit code 1 if any vector produced more than
one distinct output across its permutations (a permutation dependence inside A,
which would end the exercise before any comparison).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
_PACKS = _HERE.parent
sys.path.insert(0, str(_PACKS / "tools"))

import pack_resolver_ref as A  # noqa: E402


def canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def h(value) -> str:
    return "v1:" + hashlib.sha256(canonical(value)).hexdigest()


def envelope(result: dict, packs: list[dict]) -> dict:
    """The neutral output envelope for one resolve() call."""
    artifacts = [
        {"role": "pack_content", "ref": A.pack_ref(p), "key": A.content_hash(p)} for p in packs
    ]

    if result.get("outcome") == "resolved":
        artifacts += [
            {"role": "effective_manifest", "ref": "", "key": result["effective_manifest_hash"]},
            {"role": "resolution_trace", "ref": "", "key": result["trace_hash"]},
        ]
        out = {
            "outcome": "resolved",
            "effective_manifest": result["effective_manifest"],
            "effective_manifest_hash": result["effective_manifest_hash"],
            "resolution_trace": result["resolution_trace"],
            "trace_hash": result["trace_hash"],
            "contested_paths": result["contested_paths"],
        }
    else:
        refusal_hash = h(result)
        artifacts += [{"role": "resolution_refusal", "ref": "", "key": refusal_hash}]
        out = {
            "outcome": "refused",
            "phase": result["phase"],
            # Array order is significant: it IS the R9 ordering under test.
            "refusals": result["refusals"],
            "refusal_codes": sorted({r["code"] for r in result["refusals"]}),
            "refusal_hash": refusal_hash,
        }

    out["artifacts"] = sorted(artifacts, key=lambda a: (a["role"], a["ref"], a["key"]))
    return out


def main() -> int:
    vecfile = _PACKS / "resolution-vectors.v0.1.json"
    data = json.loads(vecfile.read_text(encoding="utf-8"))
    registry = data["packs"]
    resolver_version = data["resolver_version"]

    out_vectors = []
    permutation_total = 0
    fanned = []

    for vec in data["vectors"]:
        keys = vec["packs"]
        docs = {k: registry[k]["document"] for k in keys}

        by_perm = []
        outputs: dict[str, dict] = {}
        for order in itertools.permutations(keys):
            packs = [docs[k] for k in order]
            env = envelope(A.resolve(packs, vec["evaluated_at"], resolver_version), packs)
            key = h(env)
            outputs.setdefault(key, env)
            by_perm.append({"order": list(order), "output_hash": key})
            permutation_total += 1

        by_perm.sort(key=lambda e: e["order"])
        if len(outputs) != 1:
            fanned.append((vec["id"], len(outputs)))

        out_vectors.append(
            {
                "vector_id": vec["id"],
                "permutation_count": len(by_perm),
                "distinct_outputs": len(outputs),
                "by_permutation": by_perm,
                "outputs": outputs,
            }
        )

    doc = {
        "schema_version": "replay-envelope.v0.1",
        "implementation": "A",
        "resolver_version": resolver_version,
        "vector_file": vecfile.name,
        "vectors": out_vectors,
    }
    dest = _HERE / "results-a.json"
    dest.write_text(json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                    encoding="utf-8")

    print(f"A: {len(out_vectors)} vectors, {permutation_total} permutations replayed")
    print(f"A: wrote {dest.name} ({dest.stat().st_size} bytes)")
    if fanned:
        for vid, n in fanned:
            print(f"  FAIL  {vid}: {n} distinct outputs across permutations")
        return 1
    print("A: distinct_outputs == 1 for every vector (permutation-invariant within A)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
