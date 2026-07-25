"""compare_ab.py — the double replay comparison, run only after B was sealed.

Compares implementation A's frozen results with implementation B's results on the SEVEN AXES
SEPARATELY, and separately compares each of A and B against the frozen oracles in
resolution-vectors.v0.1.json.

    python3 compare_ab.py sealed    B exactly as sealed, before it had seen anything of A
    python3 compare_ab.py r2        B after its one genuine defect (D1) was corrected

`sealed` is the independence result and is the run that produced `divergences-raw.json`.
`r2` produced `divergences-r2.json`. Both variants are verified by sha256 before anything is read.

This script never edits either result file, never regenerates an oracle, and never touches the ADRs,
the schemas or the vectors.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROOF = os.path.dirname(HERE)
PACKS = os.path.dirname(PROOF)

A_FILE = os.path.join(PROOF, "results-a.json")
VEC_FILE = os.path.join(PACKS, "resolution-vectors.v0.1.json")
B_ROOT = os.path.join(PROOF, "implementation-b")
B_INPUTS = os.path.join(B_ROOT, "inputs", "resolution-vectors.INPUTS-ONLY.json")

# Sealed at 2026-07-25T20:46:52Z, before B's author had any contact with A or with an oracle.
# The `sealed` sources were recovered byte-exactly from the session edit record and re-verified:
# running them reproduces results-b.json under `sealed/` bit for bit.
SEALED_SHA256 = {
    "sealed": {
        "resolver_b.py": "d86d7ea931e1e91d488bcfc41208c6781d20ec558b25f60558750c447dbe3299",
        "replay_b.py": "8d029c8bedc6e1facd70e456eb58f8966385e0818b272657dc3a6742978eef70",
        "results-b.json": "5588919f360e0fb06b2010faa6a568c71d477aeeaa6b347305a7f870e58aaeaa",
    },
    "r2": {
        "resolver_b.py": "835b58352d7673d2cb312770344de600b94aa893c4b885b0d9760d7b6fd3f491",
        "replay_b.py": "8d029c8bedc6e1facd70e456eb58f8966385e0818b272657dc3a6742978eef70",
        "results-b.json": "eff8a7bb22f66691ea4c5366d29c87dd560180986ea3ae2860e9814885de3794",
    },
}

OUT_FILE = {"sealed": "divergences-raw.json", "r2": "divergences-r2.json"}


def cform(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def hv1(value):
    return "v1:" + hashlib.sha256(cform(value).encode("utf-8")).hexdigest()


def sha_file(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


AXES = [
    ("1_status", lambda e: e["outcome"]),
    ("2_effective_manifest", lambda e: e.get("effective_manifest")),
    ("3_resolution_trace", lambda e: e.get("resolution_trace")),
    ("4_refusals_and_order", lambda e: [e.get("phase"), e.get("refusals")]),
    ("5_manifest_hash", lambda e: e.get("effective_manifest_hash")),
    ("6_refusal_hash", lambda e: e.get("refusal_hash")),
    ("7_artifacts", lambda e: e.get("artifacts")),
]

# oracle keys that live directly in the replay envelope, per outcome
ORACLE_DIRECT = {
    "resolved": [
        "outcome",
        "effective_manifest",
        "effective_manifest_hash",
        "resolution_trace",
        "trace_hash",
        "contested_paths",
    ],
    "refused": ["outcome", "phase", "refusal_codes", "refusal_hash"],
}


def envelope_of(results, vector_id):
    for vector in results["vectors"]:
        if vector["vector_id"] == vector_id:
            if len(vector["outputs"]) != 1:
                raise SystemExit(
                    "fan-out in {} for {}".format(results["implementation"], vector_id)
                )
            return next(iter(vector["outputs"].values())), vector
    raise SystemExit("vector {} absent from {}".format(vector_id, results["implementation"]))


def b_full_documents(variant):
    """Re-derive B's full resolution documents (the objects the hashes are taken over).

    The replay envelope carries `refusals` but not the whole `resolution_refusal` document, and the
    oracle states the whole document. This calls B's own resolve() on the source verified by sha256
    above — so nothing new is computed, only re-projected.
    """
    sys.path.insert(0, os.path.join(B_ROOT, variant))
    from resolver_b import resolve  # noqa: E402  (import after the seal check)

    spec = json.load(open(B_INPUTS))
    registry = spec["packs"]
    out = {}
    for vector in spec["vectors"]:
        documents = [registry[k]["document"] for k in sorted(vector["packs"])]
        result = resolve(
            documents,
            evaluated_at=vector["evaluated_at"],
            resolver_version=spec["resolver_version"],
        )
        if result["outcome"] == "resolved":
            out[vector["id"]] = {
                "effective_manifest": result["effective_manifest"],
                "resolution_trace": result["resolution_trace"],
            }
        else:
            out[vector["id"]] = {"resolution_refusal": result["refusal"]}
    return out


def compare_to_oracle(label, envelope, expected, extra):
    """Return the list of oracle keys on which `envelope` (+ extra documents) differs."""
    notes = []
    outcome = envelope["outcome"]
    for key in ORACLE_DIRECT.get(outcome, []):
        if key in expected and cform(expected[key]) != cform(envelope.get(key)):
            notes.append(key)
    for key in ("resolution_refusal", "effective_manifest", "resolution_trace"):
        if key in expected and key in (extra or {}):
            if cform(expected[key]) != cform(extra[key]):
                notes.append(key)
    # outcome mismatch makes the whole comparison meaningless — flag it loudly
    if expected.get("outcome") != outcome:
        notes.insert(0, "OUTCOME")
    return notes


def main():
    variant = sys.argv[1] if len(sys.argv) > 1 else "sealed"
    if variant not in SEALED_SHA256:
        raise SystemExit("usage: compare_ab.py [sealed|r2]")
    b_dir = os.path.join(B_ROOT, variant)
    b_file = os.path.join(b_dir, "results-b.json")

    print("=" * 100)
    print("SEAL VERIFICATION — variant {!r}".format(variant))
    print("=" * 100)
    seal_ok = True
    for name, expected_sha in sorted(SEALED_SHA256[variant].items()):
        actual = sha_file(os.path.join(b_dir, name))
        ok = actual == expected_sha
        seal_ok = seal_ok and ok
        print("  {:32s} {}".format(name, "OK" if ok else "ALTERED " + actual))
    if not seal_ok:
        raise SystemExit("sealed artefact altered — comparison aborted")
    if variant == "sealed":
        print("  B as sealed at 2026-07-25T20:46:52Z — no contact with A or with any oracle")
    else:
        print("  B after the D1 correction; the sealed result stands unaltered under sealed/")
    print()

    a = json.load(open(A_FILE))
    b = json.load(open(b_file))
    vectors = json.load(open(VEC_FILE))["vectors"]
    extra_b = b_full_documents(variant)

    ids_a = [v["vector_id"] for v in a["vectors"]]
    ids_b = [v["vector_id"] for v in b["vectors"]]
    print("A: {} vectors, {} permutations, implementation={!r}".format(
        len(ids_a), sum(v["permutation_count"] for v in a["vectors"]), a["implementation"]))
    print("B: {} vectors, {} permutations, implementation={!r}".format(
        len(ids_b), sum(v["permutation_count"] for v in b["vectors"]), b["implementation"]))
    print("vector sets identical:", ids_a == ids_b)
    print("A distinct_outputs all 1:", all(v["distinct_outputs"] == 1 for v in a["vectors"]))
    print("B distinct_outputs all 1:", all(v["distinct_outputs"] == 1 for v in b["vectors"]))
    print()

    divergences = []
    axis_totals = {name: [0, 0] for name, _ in AXES}

    print("=" * 100)
    print("AXIS-BY-AXIS COMPARISON — A versus B")
    print("=" * 100)
    print("{:34s} {:>5s}  {}".format("vector", "perm", "axes that DIFFER"))
    print("-" * 100)
    for vector_id in ids_a:
        env_a, blk_a = envelope_of(a, vector_id)
        env_b, blk_b = envelope_of(b, vector_id)

        differing = []
        for name, project in AXES:
            va, vb = project(env_a), project(env_b)
            if cform(va) == cform(vb):
                axis_totals[name][0] += 1
            else:
                axis_totals[name][1] += 1
                differing.append(name)
                divergences.append({"vector": vector_id, "axis": name, "a": va, "b": vb})

        assert blk_a["permutation_count"] == blk_b["permutation_count"], vector_id
        print("{:34s} {:>5d}  {}".format(
            vector_id, blk_a["permutation_count"],
            "— none —" if not differing else ", ".join(differing)))

    print()
    print("Per-axis totals over {} vectors (agree / differ):".format(len(ids_a)))
    for name, _ in AXES:
        agree, differ = axis_totals[name]
        print("  {:24s} {:2d} / {:2d}".format(name, agree, differ))

    print()
    print("=" * 100)
    print("EACH IMPLEMENTATION AGAINST THE FROZEN ORACLES in resolution-vectors.v0.1.json")
    print("=" * 100)
    print("{:34s} {:24s} {:24s}".format("vector", "A vs oracle", "B vs oracle"))
    print("-" * 100)
    oracle_diffs = {"A": [], "B": []}
    for vector in vectors:
        vid = vector["id"]
        expected = vector.get("expected")
        env_a, _ = envelope_of(a, vid)
        env_b, _ = envelope_of(b, vid)
        if expected is None:
            print("{:34s} (no expected block)".format(vid))
            continue
        notes_a = compare_to_oracle("A", env_a, expected, None)
        notes_b = compare_to_oracle("B", env_b, expected, extra_b.get(vid))
        if notes_a:
            oracle_diffs["A"].append((vid, notes_a))
        if notes_b:
            oracle_diffs["B"].append((vid, notes_b))
        print("{:34s} {:24s} {:24s}".format(
            vid,
            "MATCH" if not notes_a else "DIFFER: " + ",".join(notes_a),
            "MATCH" if not notes_b else "DIFFER: " + ",".join(notes_b)))

    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print("A/B axis divergences        :", len(divergences))
    print("A/oracle vector divergences :", len(oracle_diffs["A"]))
    print("B/oracle vector divergences :", len(oracle_diffs["B"]))

    payload = {
        "generated_before_any_correction": variant == "sealed",
        "b_file": "results-b.json",
        "sealed_b_hash": "v1:" + SEALED_SHA256["sealed"]["results-b.json"],
        "ab_axis_divergences": divergences,
        "oracle_divergences": {
            "A": [{"vector": v, "keys": k} for v, k in oracle_diffs["A"]],
            "B": [{"vector": v, "keys": k} for v, k in oracle_diffs["B"]],
        },
    }

    # The committed divergence files are the RECORD — taken at the moment the two result files were
    # first placed side by side, and cited by name in DIVERGENCE-JOURNAL.md. A re-run verifies that
    # record; it never overwrites it.
    record_path = os.path.join(HERE, OUT_FILE[variant])
    print()
    if os.path.exists(record_path):
        record = json.load(open(record_path))
        same = all(
            cform(record.get(key)) == cform(payload[key])
            for key in ("ab_axis_divergences", "oracle_divergences")
        )
        print("record {}: {}".format(
            OUT_FILE[variant],
            "REPRODUCED — divergence content identical" if same else "DIFFERS from this run"))
        if not same:
            rerun = os.path.join(tempfile.gettempdir(), OUT_FILE[variant] + ".rerun")
            with open(rerun, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=1, sort_keys=True)
            print("  this run written to {} for inspection — the record is unchanged".format(rerun))
            return 1
    else:
        with open(record_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1, sort_keys=True)
        print("record {} did not exist; written".format(OUT_FILE[variant]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
