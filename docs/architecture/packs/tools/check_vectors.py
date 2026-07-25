#!/usr/bin/env python3
"""Conformance harness for ADR-PACK-0001.

Runs ``resolution-vectors.v0.1.json`` against ``pack_resolver_ref.py`` and asserts,
for every vector:

  1. the pack documents are schema-valid (and that the ones flagged
     ``schema_valid: false`` really are invalid — a flag nobody checks is a lie);
  2. every pack that names a ``source_example`` still has that example's exact
     content hash, so the YAML fixtures and the vectors cannot drift apart;
  3. the declared ``content_hash`` of every pack recomputes;
  4. the outcome matches by **value identity**, not merely by hash — a hash-only
     check tells a failing implementation nothing about *what* it got wrong;
  5. the canonical hash matches;
  6. **every permutation** of the input order produces byte-identical canonical
     output. This is the acceptance criterion's first half, tested exhaustively
     rather than sampled;
  7. vectors linked by ``same_result_as`` agree with their reference;
  8. every produced manifest, trace, refusal and receipt validates against
     ``pack-resolution.v0.1.schema.json``;
  9. the resolver is *structurally* pure — no clock, no randomness, no I/O, and no
     import of the frozen kernel. Checked by reading the AST, not by trusting the
     docstring.

**What this harness does NOT prove.** It exercises ONE implementation. The
acceptance criterion asks for two independent ones; the frozen vector file is the
instrument that makes the second one gradeable, and it is not a substitute for it.
Until a second implementation reproduces these hashes, this contract stays below
🟢 on the proof ladder.

Usage:  python3 docs/architecture/packs/tools/check_vectors.py
Exit code 0 = all checks passed.
"""

from __future__ import annotations

import ast
import copy
import itertools
import json
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import pack_resolver_ref as R  # noqa: E402

_PACKS_DIR = _HERE.parent
_VECTORS = _PACKS_DIR / "resolution-vectors.v0.1.json"
_PACK_SCHEMA = _PACKS_DIR / "pack.v0.1.schema.json"
_RESOLUTION_SCHEMA = _PACKS_DIR / "pack-resolution.v0.1.schema.json"

#: Above this, permutations are reported as skipped rather than silently sampled.
#: A harness that quietly stops covering what it claims to cover is worse than one
#: that covers less and says so.
_PERMUTATION_CAP = 6

_FAILURES: list[str] = []
_CHECKS = 0


def check(condition: bool, label: str, detail: str = "") -> bool:
    global _CHECKS
    _CHECKS += 1
    if not condition:
        _FAILURES.append(f"{label}{(': ' + detail) if detail else ''}")
    return condition


def _load_json(path: pathlib.Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _same(a, b) -> bool:
    return R.canonical_json(a) == R.canonical_json(b)


def _first_difference(expected, actual, prefix: str = "") -> str:
    """Locate the first differing path, so a failure names a field, not a hash."""
    if type(expected) is not type(actual):
        return f"{prefix or '<root>'}: type {type(expected).__name__} != {type(actual).__name__}"
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            if key not in expected:
                return f"{prefix}.{key}: unexpected key (actual={actual[key]!r})"
            if key not in actual:
                return f"{prefix}.{key}: missing key (expected={expected[key]!r})"
            if not _same(expected[key], actual[key]):
                return _first_difference(expected[key], actual[key], f"{prefix}.{key}")
        return f"{prefix}: dicts differ but no differing key found"
    if isinstance(expected, list):
        for i, (e, a) in enumerate(zip(expected, actual)):
            if not _same(e, a):
                return _first_difference(e, a, f"{prefix}[{i}]")
        if len(expected) != len(actual):
            return f"{prefix}: length {len(expected)} != {len(actual)}"
        return f"{prefix}: lists differ but no differing item found"
    return f"{prefix or '<root>'}: {expected!r} != {actual!r}"


# ---------------------------------------------------------------------------
# 9 — structural purity of the resolver (read the AST, do not trust the prose)
# ---------------------------------------------------------------------------

_BANNED_MODULES = {"time", "datetime", "random", "os", "socket", "subprocess",
                   "locale", "uuid", "secrets", "requests", "urllib"}
_BANNED_CALLS = {"now", "utcnow", "today", "time", "monotonic", "random", "shuffle",
                 "choice", "open", "input", "getenv"}
#: `pathlib`/`sys` are used once at import time to locate dsm-primitives on sys.path.
#: That is module setup, not resolution: resolve() itself must contain no I/O at all.
_IMPURE_ALLOWED_AT_MODULE_LEVEL = {"pathlib", "sys"}


def check_resolver_purity() -> None:
    source = (_HERE / "pack_resolver_ref.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    banned = sorted((imported & _BANNED_MODULES) - _IMPURE_ALLOWED_AT_MODULE_LEVEL)
    check(not banned, "resolver purity — banned import", ", ".join(banned))

    kernel = sorted(m for m in imported if m in {"dsm", "src"})
    check(not kernel, "resolver does not import the frozen kernel", ", ".join(kernel))

    resolve_fn = next((n for n in tree.body
                       if isinstance(n, ast.FunctionDef) and n.name == "resolve"), None)
    if not check(resolve_fn is not None, "resolve() is defined"):
        return
    impure: list[str] = []
    for node in ast.walk(resolve_fn):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in _BANNED_CALLS:
                impure.append(f"line {node.lineno}: {name}()")
    check(not impure, "resolve() contains no clock/random/IO call", "; ".join(impure))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print("FATAL: jsonschema is required (pip install jsonschema)", file=sys.stderr)
        return 2

    doc = _load_json(_VECTORS)
    pack_validator = Draft202012Validator(_load_json(_PACK_SCHEMA))
    res_validator = Draft202012Validator(_load_json(_RESOLUTION_SCHEMA))

    check(doc["schema_version"] == "resolution-vectors.v0.1", "vectors schema_version")
    check(doc["resolver_version"] == R.RESOLVER_VERSION,
          "vectors target this resolver version", doc["resolver_version"])

    library = doc["packs"]

    # -- 1/2/3: the pack library ------------------------------------------
    print("== pack library ==")
    for key, entry in sorted(library.items()):
        pack = entry["document"]
        errors = sorted(pack_validator.iter_errors(pack), key=lambda e: list(e.path))
        if entry["schema_valid"]:
            check(not errors, f"[{key}] schema-valid",
                  "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:3]))
        else:
            check(bool(errors), f"[{key}] flagged schema_valid=false and really is invalid",
                  "the schema accepted a document the vectors call invalid")

        check(entry["content_hash"] == R.content_hash(pack),
              f"[{key}] declared content_hash recomputes")

        src = entry.get("source_example")
        if src:
            import yaml
            with open(_PACKS_DIR / src, encoding="utf-8") as fh:
                on_disk = yaml.safe_load(fh)
            ok = check(R.content_hash(on_disk) == entry["content_hash"],
                       f"[{key}] matches {src} — examples and vectors have not drifted")
            if not ok:
                _FAILURES[-1] += f" | {_first_difference(on_disk, pack)}"
    print(f"   {len(library)} pack documents checked")

    # -- 4..8: the vectors -------------------------------------------------
    print("\n== vectors ==")
    by_id: dict[str, dict] = {}
    total_permutations = 0

    for vec in doc["vectors"]:
        vid = vec["id"]
        check(vid not in by_id, f"[{vid}] vector id is unique")
        by_id[vid] = vec

        packs = [copy.deepcopy(library[k]["document"]) for k in vec["packs"]]
        result = R.resolve(packs, vec["evaluated_at"])
        expected = vec["expected"]
        outcome = R.outcome_of(result)

        if not check(outcome == expected["outcome"], f"[{vid}] outcome",
                     f"expected {expected['outcome']}, got {outcome}"):
            continue

        if outcome == "resolved":
            ok = check(_same(expected["effective_manifest"], result["effective_manifest"]),
                       f"[{vid}] effective manifest by value identity")
            if not ok:
                _FAILURES[-1] += " | " + _first_difference(
                    expected["effective_manifest"], result["effective_manifest"])
            check(expected["effective_manifest_hash"] == result["effective_manifest_hash"],
                  f"[{vid}] manifest hash", result["effective_manifest_hash"])
            check(_same(expected["resolution_trace"], result["resolution_trace"]),
                  f"[{vid}] resolution trace by value identity")
            check(expected["trace_hash"] == result["trace_hash"], f"[{vid}] trace hash")
            check(expected["contested_paths"] == result["contested_paths"],
                  f"[{vid}] contested paths", str(result["contested_paths"]))
            # the manifest hash must be the hash OF the manifest, not a recorded string
            check(R.hash_canonical(result["effective_manifest"]) == result["effective_manifest_hash"],
                  f"[{vid}] manifest hash is self-consistent")
            check(result["resolution_trace"]["effective_manifest_hash"]
                  == result["effective_manifest_hash"],
                  f"[{vid}] trace cites its own manifest")
            artifacts = [result["effective_manifest"], result["resolution_trace"]]
        else:
            check(expected["phase"] == result["phase"], f"[{vid}] refusal phase", result["phase"])
            check(_same(expected["resolution_refusal"], result),
                  f"[{vid}] complete refusal set by value identity",
                  _first_difference(expected["resolution_refusal"], result))
            check(expected["refusal_codes"] == sorted({r["code"] for r in result["refusals"]}),
                  f"[{vid}] refusal codes")
            check(expected["refusal_hash"] == R.hash_canonical(result), f"[{vid}] refusal hash")
            artifacts = [result]

        stamps = [
            {"pack_id": p["identity"]["pack_id"], "pack_version": p["identity"]["pack_version"],
             "layer": p["identity"]["layer"], "content_hash": R.content_hash(p)}
            for p in packs if p["identity"].get("layer") in R.LAYER_RANK
        ]
        artifacts.append(R.resolution_receipt(result, stamps))

        for artifact in artifacts:
            errors = sorted(res_validator.iter_errors(artifact), key=lambda e: list(e.path))
            check(not errors, f"[{vid}] {artifact.get('kind')} validates against the resolution schema",
                  "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:3]))

        # -- 6: exhaustive permutation invariance --------------------------
        n = len(packs)
        if n > _PERMUTATION_CAP:
            print(f"   ! {vid}: {n} packs — permutations NOT exhausted (cap {_PERMUTATION_CAP})")
        else:
            reference = R.canonical_json(result)
            bad = 0
            count = 0
            for order in itertools.permutations(range(n)):
                count += 1
                shuffled = [copy.deepcopy(library[vec["packs"][i]]["document"]) for i in order]
                if R.canonical_json(R.resolve(shuffled, vec["evaluated_at"])) != reference:
                    bad += 1
            total_permutations += count
            check(bad == 0, f"[{vid}] permutation-invariant over {count} orders",
                  f"{bad} orders produced different canonical output")

        label = (expected["outcome"] if outcome == "resolved"
                 else f"{expected['outcome']} {expected['phase']}")
        print(f"   ok  {vid:34s} {label}")

    # -- 7: declared equivalences -----------------------------------------
    print("\n== declared equivalences ==")
    for vec in doc["vectors"]:
        ref_id = vec.get("same_result_as")
        if not ref_id:
            continue
        ref = by_id.get(ref_id)
        if not check(ref is not None, f"[{vec['id']}] same_result_as target exists", str(ref_id)):
            continue
        check(vec["expected"]["outcome"] == ref["expected"]["outcome"],
              f"[{vec['id']}] same outcome as {ref_id}")
        if vec["expected"]["outcome"] == "resolved":
            check(vec["expected"]["effective_manifest_hash"]
                  == ref["expected"]["effective_manifest_hash"],
                  f"[{vec['id']}] same manifest hash as {ref_id}")
            print(f"   ok  {vec['id']:34s} == {ref_id}")

    # -- 9: purity ---------------------------------------------------------
    print("\n== resolver purity ==")
    check_resolver_purity()
    print("   ok  no clock, no randomness, no I/O in resolve(); frozen kernel not imported")

    # -- report ------------------------------------------------------------
    print(f"\n{_CHECKS} checks, {total_permutations} input orders replayed, "
          f"{len(_FAILURES)} failures")
    if _FAILURES:
        print("\nFAILURES")
        for failure in _FAILURES:
            print(f"  - {failure}")
        return 1
    print("\nPASS — every vector reproduces by value identity and by canonical hash,")
    print("under every permutation of its input order.")
    print("\nNOTE: this exercises ONE implementation. The acceptance criterion asks for two.")
    print("The vector file is the instrument that makes a second one gradeable, not a")
    print("substitute for it. This contract stays below the runtime-proven rung until a")
    print("second, independent implementation reproduces these hashes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
