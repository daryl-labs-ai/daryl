#!/usr/bin/env python3
"""NON-NORMATIVE reference resolver for Daryl packs v0.1.

This file is documentation that runs. It is deliberately placed under
``docs/architecture/packs/tools/`` and **not** under ``src/``:

  * it is not part of DSM, not part of PRL, and not shipped;
  * ``src/dsm/core/`` is frozen and is not touched, imported or extended here;
  * where this code and ``ADR-PACK-0001`` disagree, **the ADR governs and this
    code is the defect**.

Its only job is to make the acceptance criterion falsifiable:

    Two independent implementations receiving the same packs, in any input
    order, must either produce the same effective manifest by value identity
    and the same canonical hash, or produce the same typed refusal.

It reuses ``dsm_primitives`` for canonicalization and hashing and introduces
**no new hashing law**. If ``dsm_primitives`` cannot be imported, this module
fails loudly rather than falling back to a local ``json.dumps`` — a second
canonicalizer is exactly the divergence this lot exists to prevent.

Purity: no clock, no I/O, no network, no locale, no randomness, no filesystem
order inside ``resolve()``. ``evaluated_at`` is an input (ADR-PACK-0001 R8).
Instants are compared as strings: the schema admits only ``...Z`` RFC 3339 with
fixed-width fields, for which lexicographic order *is* chronological order, so
no date library and no timezone database enters the trust base.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_PRIMITIVES = _REPO_ROOT / "packages" / "dsm-primitives" / "src"
if str(_PRIMITIVES) not in sys.path:
    sys.path.insert(0, str(_PRIMITIVES))

from dsm_primitives.canonical import canonical_json  # noqa: E402
from dsm_primitives.hashing import hash_canonical  # noqa: E402

RESOLVER_VERSION = "pack-resolver@0.1.0"

LAYER_RANK = {"core": 0, "domain": 1, "jurisdiction": 2, "organization": 3}
OVERRIDE_RANK = {"open": 0, "requires_derogation": 1, "forbidden": 2}
RANK_OVERRIDE = {v: k for k, v in OVERRIDE_RANK.items()}
MERGE_KINDS = ("replace", "append", "union", "intersect")

#: R12bis — ordered weakest to strongest. A path's rule is the strongest fact
#: true of it, so the label does not depend on which rank is visited last.
RULE_LEVELS = ("introduction", "commutative_fold", "layer_override", "derogated_override")

#: ADR-PACK-0001 — the v0.1 proof carries only these two sections. Every other
#: section of the envelope is reserved: declarable, but never composed and never
#: hashed into the effective manifest.
PROOF_SCOPE = ("required_checks", "vocabulary")

#: R3bis — a leaf covered by no control declaration fails closed.
DEFAULT_MERGE = "replace"
DEFAULT_OVERRIDE = "forbidden"

PHASES = {
    "P1": "P1_identity",
    "P2": "P2_compatibility",
    "P3": "P3_control",
    "P4": "P4_derogation_form",
    "P5": "P5_composition",
}


class ResolverContract(Exception):
    """Raised when an input breaks a precondition the schema is meant to enforce.

    Deliberately *not* a refusal: refusals are governed outcomes with a closed
    taxonomy (R11). A malformed input that the schema should have rejected is a
    caller error, and silently coercing it into a refusal code would let schema
    bugs masquerade as governance decisions.
    """


# --------------------------------------------------------------------------
# canonical helpers — one law, borrowed, never re-implemented
# --------------------------------------------------------------------------


def _ckey(value: Any) -> str:
    """Canonical comparison key for any JSON value.

    Wraps the value so the single canonicalizer in ``dsm_primitives`` can be
    reused verbatim for non-dict values too.
    """
    return canonical_json({"v": value}).decode("ascii")


def _sorted_canonical(values: list[Any]) -> list[Any]:
    return [v for _, v in sorted(((_ckey(v), v) for v in values), key=lambda p: p[0])]


def _dedupe_canonical(values: list[Any]) -> list[Any]:
    seen: dict[str, Any] = {}
    for v in values:
        seen.setdefault(_ckey(v), v)
    return _sorted_canonical(list(seen.values()))


def _semver(text: str) -> tuple[int, int, int]:
    parts = text.split(".")
    if len(parts) != 3:
        raise ResolverContract(f"not a semver: {text!r}")
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError as exc:  # pragma: no cover - schema guards this
        raise ResolverContract(f"not a semver: {text!r}") from exc


def pack_ref(pack: dict) -> str:
    ident = pack.get("identity", {})
    return f"{ident.get('pack_id')}@{ident.get('pack_version')}"


def content_hash(pack: dict) -> str:
    """``hash_canonical`` of the pack with ``provenance.source_ref`` removed.

    A ``source_ref`` records *where a copy was found*; a referent is never its
    carrier (ADR-PRL-0014). Two deployments loading the same pack from
    different paths must obtain the same content hash.
    """
    stripped = _deep_copy(pack)
    prov = stripped.get("provenance")
    if isinstance(prov, dict):
        prov.pop("source_ref", None)
    return hash_canonical(stripped)


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy(v) for v in value]
    return value


# --------------------------------------------------------------------------
# flattening — objects are namespaces, leaves are scalars or arrays
# --------------------------------------------------------------------------


def _flatten(section_name: str, node: Any, prefix: str, out: dict[str, Any]) -> None:
    if isinstance(node, dict):
        for key in node:
            if "." in key:
                raise ResolverContract(
                    f"leaf key segment contains '.', which would make the path "
                    f"ambiguous: {prefix}.{key!r}"
                )
            _flatten(section_name, node[key], f"{prefix}.{key}", out)
        return
    out[prefix] = node


def leaves_of(pack: dict) -> dict[str, Any]:
    """In-proof-scope leaves only. Reserved sections are never composed."""
    out: dict[str, Any] = {}
    for section in PROOF_SCOPE:
        if section in pack:
            _flatten(section, pack[section], section, out)
    return out


def _covers(decl_path: str, leaf: str) -> bool:
    return leaf == decl_path or leaf.startswith(decl_path + ".")


def _depth(path: str) -> int:
    return path.count(".") + 1


def _unflatten(leaves: dict[str, Any]) -> dict[str, Any]:
    root: dict[str, Any] = {}
    for path in sorted(leaves):
        parts = path.split(".")
        cursor = root
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = leaves[path]
    return root


# --------------------------------------------------------------------------
# refusals
# --------------------------------------------------------------------------


def _refusal(code: str, path: str, refs: list[str], **detail: Any) -> dict:
    item: dict[str, Any] = {
        "code": code,
        "path": path,
        "pack_refs": sorted(set(refs)),
    }
    if detail:
        item["detail"] = detail
    return item


def _refusal_sort_key(item: dict) -> tuple:
    """ADR-PACK-0001 R9 ordering: ``(code, path, pack_refs)``, then canonical form.

    The trailing ``_ckey(item)`` is a **total** tie-break. Without it, two refusals
    sharing ``(code, path, pack_refs)`` but differing in ``detail`` would be ordered
    by whatever the sort happened to see first — reintroducing the input-order
    dependence R9 exists to eliminate, inside a structure that gets hashed.
    """
    return (item["code"], item["path"], _ckey(item["pack_refs"]), _ckey(item))


def _refused(phase: str, refusals: list[dict], evaluated_at: str, resolver_version: str) -> dict:
    """Complete within its phase, canonically sorted.

    'First error encountered' is order-dependent and therefore forbidden (R9).
    """
    return {
        "schema_version": "pack-resolution.v0.1",
        "kind": "resolution_refusal",
        "resolver_version": resolver_version,
        "evaluated_at": evaluated_at,
        "phase": PHASES[phase],
        "refusals": sorted(refusals, key=_refusal_sort_key),
    }


# --------------------------------------------------------------------------
# resolve
# --------------------------------------------------------------------------


def resolve(
    packs: list[dict],
    evaluated_at: str,
    resolver_version: str = RESOLVER_VERSION,
) -> dict:
    """``resolve(Set, Instant, Str) -> Resolved(manifest, trace) | Refused(refusals)``.

    ``packs`` is semantically a **set**. It arrives as a list only because JSON
    has no set; the list order is transport and is never read (R7).
    """
    # ---------------- P1 — identity & referents ----------------
    refusals: list[dict] = []
    for pack in packs:
        ident = pack.get("identity")
        if not isinstance(ident, dict) or not ident.get("pack_id") or not ident.get("pack_version"):
            raise ResolverContract("pack without identity.pack_id / identity.pack_version")
        if ident.get("layer") not in LAYER_RANK:
            refusals.append(
                _refusal("unknown_referent", "", [pack_ref(pack)], referent="layer",
                         value=str(ident.get("layer")))
            )

    by_id: dict[str, dict[str, set[str]]] = {}
    for pack in packs:
        ident = pack["identity"]
        by_id.setdefault(ident["pack_id"], {}).setdefault(ident["pack_version"], set()).add(
            content_hash(pack)
        )
    for pid, versions in by_id.items():
        if len(versions) > 1:
            refusals.append(
                _refusal("duplicate_pack_identity", "",
                         [f"{pid}@{v}" for v in versions],
                         reason="same pack_id at multiple versions in one resolution")
            )
            continue
        for ver, hashes in versions.items():
            if len(hashes) > 1:
                refusals.append(
                    _refusal("duplicate_pack_identity", "", [f"{pid}@{ver}"],
                             reason="same pack_id@pack_version with differing content",
                             content_hashes=sorted(hashes))
                )
    if refusals:
        return _refused("P1", refusals, evaluated_at, resolver_version)

    # deduplicate byte-identical repeats: the input is a set
    unique: dict[str, dict] = {}
    for pack in packs:
        unique.setdefault(content_hash(pack), pack)
    packset = sorted(
        unique.values(),
        key=lambda p: (LAYER_RANK[p["identity"]["layer"]],
                       p["identity"]["pack_id"],
                       p["identity"]["pack_version"]),
    )

    # ---------------- P2 — compatibility ----------------
    present = {p["identity"]["pack_id"]: _semver(p["identity"]["pack_version"]) for p in packset}
    rv = _semver(resolver_version.split("@", 1)[1])
    for pack in packset:
        compat = pack.get("compatibility") or {}
        req_resolver = (compat.get("requires_resolver") or {}).get("min_version")
        if req_resolver and _semver(req_resolver.split("@", 1)[1]) > rv:
            refusals.append(
                _refusal("compatibility_violation", "", [pack_ref(pack)],
                         requirement="requires_resolver", expected=req_resolver,
                         actual=resolver_version)
            )
        for req in compat.get("requires_packs") or []:
            lo_txt, hi_txt = req["version_range"].split(" ")
            lo, hi = _semver(lo_txt[2:]), _semver(hi_txt[1:])
            actual = present.get(req["pack_id"])
            if actual is None:
                refusals.append(
                    _refusal("compatibility_violation", "", [pack_ref(pack)],
                             requirement="requires_packs", missing=req["pack_id"],
                             expected=req["version_range"])
                )
            elif not (lo <= actual < hi):
                refusals.append(
                    _refusal("compatibility_violation", "", [pack_ref(pack)],
                             requirement="requires_packs", pack_id=req["pack_id"],
                             expected=req["version_range"],
                             actual=".".join(str(n) for n in actual))
                )
    if refusals:
        return _refused("P2", refusals, evaluated_at, resolver_version)

    # ---------------- gather contributions ----------------
    contributions: dict[str, list[tuple[int, str, Any]]] = {}
    for pack in packset:
        rank = LAYER_RANK[pack["identity"]["layer"]]
        ref = pack_ref(pack)
        for path, value in leaves_of(pack).items():
            contributions.setdefault(path, []).append((rank, ref, value))

    declarations = []  # (rank, ref, path, merge|None, override|None)
    for pack in packset:
        rank = LAYER_RANK[pack["identity"]["layer"]]
        ref = pack_ref(pack)
        for decl in (pack.get("composition") or {}).get("controls") or []:
            declarations.append(
                (rank, ref, decl["path"], decl.get("merge"), decl.get("override"))
            )

    # ---------------- P3 — field control ----------------
    controls: dict[str, dict[str, Any]] = {}
    for path in sorted(contributions):
        intro_rank = min(r for r, _, _ in contributions[path])

        # merge: fixed by the introducing layer, immutable, never overridable.
        merge_decls = [d for d in declarations if d[3] is not None and _covers(d[2], path)]
        merge_kind = DEFAULT_MERGE
        if merge_decls:
            base_rank = min(d[0] for d in merge_decls)
            base = [d for d in merge_decls if d[0] == base_rank]
            deepest = max(_depth(d[2]) for d in base)
            winners = {d[3] for d in base if _depth(d[2]) == deepest}
            if len(winners) > 1:
                refusals.append(
                    _refusal("merge_semantics_conflict", path,
                             [d[1] for d in base if _depth(d[2]) == deepest],
                             reason="competing merge semantics at equal specificity",
                             declared=sorted(winners))
                )
                continue
            merge_kind = winners.pop()
            later = {d[3] for d in merge_decls if d[0] > base_rank and d[3] != merge_kind}
            if later:
                refusals.append(
                    _refusal("merge_semantics_conflict", path,
                             [d[1] for d in merge_decls if d[0] > base_rank and d[3] != merge_kind],
                             reason="merge semantics are fixed by the introducing layer",
                             introduced=merge_kind, attempted=sorted(later))
                )
                continue

        if merge_kind in ("append", "union", "intersect"):
            bad = [ref for _, ref, value in contributions[path] if not isinstance(value, list)]
            if bad:
                refusals.append(
                    _refusal("merge_semantics_conflict", path, bad,
                             reason="declared merge requires an array value", merge=merge_kind)
                )
                continue

        # override: max() over covering declarations, per rank; relaxation refused.
        ov_decls = [d for d in declarations if d[4] is not None and _covers(d[2], path)]
        for rank in sorted({d[0] for d in ov_decls}):
            below = [OVERRIDE_RANK[d[4]] for d in ov_decls if d[0] < rank]
            if below:
                floor = max(below)
                offenders = [d[1] for d in ov_decls
                             if d[0] == rank and OVERRIDE_RANK[d[4]] < floor]
                if offenders:
                    refusals.append(
                        _refusal("strategy_relaxation_refused", path, offenders,
                                 floor=RANK_OVERRIDE[floor],
                                 attempted=sorted({d[4] for d in ov_decls
                                                   if d[0] == rank
                                                   and OVERRIDE_RANK[d[4]] < floor}))
                    )

        controls[path] = {
            "merge": merge_kind,
            "intro_rank": intro_rank,
            "ov_decls": ov_decls,
        }
    if refusals:
        return _refused("P3", refusals, evaluated_at, resolver_version)

    # ---------------- P4 — derogation well-formedness ----------------
    derogations: list[tuple[str, dict]] = []
    for pack in packset:
        for der in (pack.get("composition") or {}).get("derogations") or []:
            derogations.append((pack_ref(pack), der))

    for ref, der in derogations:
        did = der.get("derogation_id") or "<unnamed>"
        granted = der.get("granted_by") or {}
        reasons = []
        if not granted.get("authority_id") or not granted.get("key_id"):
            reasons.append("missing_authority")
        if not der.get("not_before") or not der.get("expires_at"):
            reasons.append("missing_expiry")
        elif der["not_before"] >= der["expires_at"]:
            reasons.append("non_positive_window")
        if not der.get("scope"):
            reasons.append("empty_scope")
        elif any("." not in s for s in der["scope"]):
            reasons.append("scope_not_a_leaf_path")
        if not der.get("justification"):
            reasons.append("missing_justification")
        if not der.get("signature"):
            reasons.append("missing_signature")
        if reasons:
            # Fail closed and unconditional: a malformed derogation refuses the whole
            # resolution even if the path it names is never contested.
            refusals.append(
                _refusal("derogation_invalid", "", [ref],
                         derogation_id=did, reasons=sorted(reasons))
            )
    if refusals:
        return _refused("P4", refusals, evaluated_at, resolver_version)

    # ---------------- P5 — composition ----------------
    effective: dict[str, Any] = {}
    trace: list[dict] = []

    for path in sorted(contributions):
        ctl = controls[path]
        merge_kind = ctl["merge"]
        intro_rank = ctl["intro_rank"]
        ov_decls = ctl["ov_decls"]

        acc: Any = None
        applied_der: dict | None = None
        # R12bis: strongest fact wins, and rank order is total, so this is
        # independent of the order the packs arrived in.
        rule_level = 0  # 0 introduction · 1 commutative_fold · 2 layer_override · 3 derogated_override
        failed = False

        ranks = sorted({r for r, _, _ in contributions[path]})
        for rank in ranks:
            peers = [(ref, val) for r, ref, val in contributions[path] if r == rank]
            peer_refs = sorted(ref for ref, _ in peers)

            if merge_kind in ("replace", "append"):
                distinct = {_ckey(v) for _, v in peers}
                if len(peers) > 1 and len(distinct) > 1:
                    # Nothing distinguishes peers, so nothing may order them.
                    refusals.append(
                        _refusal("peer_conflict", path, peer_refs, merge=merge_kind,
                                 layer_rank=rank, distinct_values=len(distinct))
                    )
                    failed = True
                    break
                value = peers[0][1]
                candidate = (acc + value) if (merge_kind == "append" and acc is not None) else value
            else:
                folded: Any = None
                for _, value in peers:
                    if folded is None:
                        folded = list(value)
                    elif merge_kind == "union":
                        folded = folded + list(value)
                    else:
                        keys = {_ckey(v) for v in value}
                        folded = [v for v in folded if _ckey(v) in keys]
                folded = _dedupe_canonical(folded or [])
                if acc is None:
                    candidate = folded
                elif merge_kind == "union":
                    candidate = _dedupe_canonical(list(acc) + folded)
                else:
                    keys = {_ckey(v) for v in folded}
                    candidate = _sorted_canonical([v for v in acc if _ckey(v) in keys])

            changed = rank > intro_rank and _ckey(candidate) != _ckey(acc)
            if changed:
                floor = max(
                    [OVERRIDE_RANK[d[4]] for d in ov_decls if d[0] < rank]
                    or [OVERRIDE_RANK[DEFAULT_OVERRIDE]]
                )
                permission = RANK_OVERRIDE[floor]
                if permission == "forbidden":
                    # Absolute. No derogation is consulted, because none can reach here.
                    refusals.append(
                        _refusal("forbidden_override", path, peer_refs, layer_rank=rank)
                    )
                    failed = True
                    break
                if permission == "requires_derogation":
                    covering = [(r, d) for r, d in derogations if path in (d.get("scope") or [])]
                    if not covering:
                        refusals.append(
                            _refusal("derogation_required", path, peer_refs, layer_rank=rank)
                        )
                        failed = True
                        break
                    in_force = [
                        (r, d) for r, d in covering
                        if d["not_before"] <= evaluated_at < d["expires_at"]
                    ]
                    if not in_force:
                        refusals.append(
                            _refusal("derogation_expired", path, peer_refs,
                                     evaluated_at=evaluated_at,
                                     derogation_ids=sorted(d["derogation_id"] for _, d in covering))
                        )
                        failed = True
                        break
                    chosen = min(in_force, key=lambda pair: pair[1]["derogation_id"])[1]
                    applied_der = {
                        "derogation_id": chosen["derogation_id"],
                        "authority_id": chosen["granted_by"]["authority_id"],
                        "key_id": chosen["granted_by"]["key_id"],
                        "expires_at": chosen["expires_at"],
                    }
                    rule_level = max(rule_level, 3)
                else:
                    rule_level = max(
                        rule_level, 1 if merge_kind in ("union", "intersect") else 2
                    )
            acc = candidate

        if failed:
            continue

        # R12bis — derived from the finished value, never from the fold order.
        if merge_kind == "replace":
            selected = sorted({ref for _, ref, v in contributions[path]
                               if _ckey(v) == _ckey(acc)})
            overridden = sorted({ref for _, ref, v in contributions[path]
                                 if _ckey(v) != _ckey(acc)})
        else:
            selected = sorted({ref for _, ref, _ in contributions[path]})
            overridden = []

        effective[path] = acc
        trace.append({
            "path": path,
            "effective_value": acc,
            "selected_from": selected,
            "overridden_sources": overridden,
            "resolution_rule": RULE_LEVELS[rule_level],
            "merge": merge_kind,
            "override": RANK_OVERRIDE[
                max([OVERRIDE_RANK[d[4]] for d in ov_decls] or [OVERRIDE_RANK[DEFAULT_OVERRIDE]])
            ],
            "derogation_applied": applied_der,
        })

    if refusals:
        return _refused("P5", refusals, evaluated_at, resolver_version)

    # ---------------- effective manifest + trace ----------------
    sections = _unflatten(effective)
    manifest = {
        "schema_version": "pack-resolution.v0.1",
        "kind": "effective_manifest",
        "resolver_version": resolver_version,
        "evaluated_at": evaluated_at,
        "proof_scope": sorted(PROOF_SCOPE),
        "context": {
            "domain": sorted({p["identity"]["domain"] for p in packset
                              if p["identity"].get("domain")}),
            "jurisdiction": sorted({p["identity"]["jurisdiction"] for p in packset
                                    if p["identity"].get("jurisdiction")}),
            "org_id": sorted({p["identity"]["org_id"] for p in packset
                              if p["identity"].get("org_id")}),
        },
        "packs": [
            {
                "pack_id": p["identity"]["pack_id"],
                "pack_version": p["identity"]["pack_version"],
                "layer": p["identity"]["layer"],
                "content_hash": content_hash(p),
            }
            for p in packset
        ],
        "sections": sections,
    }
    manifest_hash = hash_canonical(manifest)

    trace_doc = {
        "schema_version": "pack-resolution.v0.1",
        "kind": "resolution_trace",
        "resolver_version": resolver_version,
        "evaluated_at": evaluated_at,
        "effective_manifest_hash": manifest_hash,
        "entries": sorted(trace, key=lambda e: e["path"]),
    }

    contested = sorted(
        e["path"] for e in trace if e["overridden_sources"] or e["derogation_applied"]
    )

    return {
        "outcome": "resolved",
        "effective_manifest": manifest,
        "effective_manifest_hash": manifest_hash,
        "resolution_trace": trace_doc,
        "trace_hash": hash_canonical(trace_doc),
        "contested_paths": contested,
    }


def resolution_receipt(result: dict, packset_stamps: list[dict]) -> dict:
    """The PackResolutionReceipt: hashes, versions, outcome, contested fields.

    No effective values, no trace entries, no pack bodies. A receipt is a
    citation, not a copy (R13). In a real system this is issued only after
    ``DSMWriter.write()`` returns non-``None`` (Rule A) — this function builds
    the payload and writes nothing.
    """
    if result.get("outcome") == "resolved":
        manifest = result["effective_manifest"]
        return {
            "schema_version": "pack-resolution.v0.1",
            "kind": "PackResolutionReceipt",
            "resolver_version": manifest["resolver_version"],
            "evaluated_at": manifest["evaluated_at"],
            "packs": packset_stamps,
            "outcome": "resolved",
            "effective_manifest_hash": result["effective_manifest_hash"],
            "trace_hash": result["trace_hash"],
            "contested_paths": result["contested_paths"],
        }
    return {
        "schema_version": "pack-resolution.v0.1",
        "kind": "PackResolutionReceipt",
        "resolver_version": result["resolver_version"],
        "evaluated_at": result["evaluated_at"],
        "packs": packset_stamps,
        "outcome": "refused",
        "refusal_hash": hash_canonical(result),
        "refusal_codes": sorted({r["code"] for r in result["refusals"]}),
    }


def outcome_of(result: dict) -> str:
    return result.get("outcome") or ("refused" if result.get("kind") == "resolution_refusal" else "?")
