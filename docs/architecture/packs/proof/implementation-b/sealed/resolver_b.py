"""resolver_b.py — implementation B of ADR-PACK-0001 (pack composition and precedence).

Built only from the ADRs, the two schemas, the example packs and the oracle-free vectors.
No Daryl module is imported; canonicalisation and hashing are implemented from the ADR-0002 formula.

Shape (see ARCHITECTURE.md): the pack set is normalised ONCE into two flat relations,

    DECL    (path, rank, pack_ref, merge?, override?)
    CONTRIB (leaf_path, rank, pack_ref, value)

after which every phase is a pure query over those relations returning a frozen set of refusals, and
composition is a memoised recursive value function over the fixed four-rank lattice whose downstream facts
are queried from the resulting value vector rather than accumulated during a traversal.

Nothing in this module performs I/O, reads a clock, consults the environment, or depends on the order the
caller supplied the packs in (R7, R8, R10).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------------------------------
# constants fixed by the law
# --------------------------------------------------------------------------------------------------

LAYERS: Tuple[str, ...] = ("core", "domain", "jurisdiction", "organization")
LAYER_RANK: Dict[str, int] = {name: i for i, name in enumerate(LAYERS)}

OVERRIDE_RANK: Dict[str, int] = {"open": 0, "requires_derogation": 1, "forbidden": 2}
OVERRIDE_BY_RANK: Tuple[str, ...] = ("open", "requires_derogation", "forbidden")

MERGE_DEFAULT = "replace"
OVERRIDE_DEFAULT = "forbidden"

PROOF_SCOPE: Tuple[str, ...] = ("required_checks", "vocabulary")

RULE_STRENGTH: Dict[str, int] = {
    "introduction": 0,
    "commutative_fold": 1,
    "layer_override": 2,
    "derogated_override": 3,
}
RULE_BY_STRENGTH: Tuple[str, ...] = (
    "introduction",
    "commutative_fold",
    "layer_override",
    "derogated_override",
)

SCHEMA_MANIFEST = "pack-resolution.v0.1"
KIND_MANIFEST = "effective_manifest"
KIND_TRACE = "resolution_trace"
KIND_REFUSAL = "resolution_refusal"

PHASES: Tuple[str, ...] = (
    "P1_identity",
    "P2_compatibility",
    "P3_control",
    "P4_derogation_form",
    "P5_composition",
)


# --------------------------------------------------------------------------------------------------
# ADR-0002 canonicalisation — implemented from the formula, not imported
# --------------------------------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def cform(value: Any) -> str:
    """The canonical string. This is B's single test of value identity everywhere the law says
    'identical value' (R4 peers, R12bis selected_from, union element dedup)."""
    return canonical_bytes(value).decode("ascii")


def hash_v1(value: Any) -> str:
    return "v1:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


# --------------------------------------------------------------------------------------------------
# refusal construction
# --------------------------------------------------------------------------------------------------


def refusal(code: str, path: str, pack_refs: Sequence[str], detail: Optional[dict] = None) -> dict:
    r: Dict[str, Any] = {"code": code, "path": path, "pack_refs": sorted(pack_refs)}
    if detail is not None:
        r["detail"] = detail
    return r


def _refusal_sort_key(r: dict) -> Tuple[str, str, Tuple[str, ...], str]:
    # R9 total key: (code, path, pack_refs) then the canonical form of the whole object as tie-break.
    return (r["code"], r["path"], tuple(r["pack_refs"]), cform(r))


def order_refusals(refusals) -> List[dict]:
    """Deduplicate by canonical form, then apply R9's total order."""
    seen: Dict[str, dict] = {}
    for r in refusals:
        seen.setdefault(cform(r), r)
    return sorted(seen.values(), key=_refusal_sort_key)


# --------------------------------------------------------------------------------------------------
# semver helpers
# --------------------------------------------------------------------------------------------------


def semver_tuple(text: str) -> Tuple[int, int, int]:
    a, b, c = text.split(".")
    return (int(a), int(b), int(c))


def range_bounds(version_range: str) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """'>=A.B.C <D.E.F' — the only grammar v0.1 admits (pack schema pins it)."""
    lo_text, hi_text = version_range.split(" ")
    return semver_tuple(lo_text[2:]), semver_tuple(hi_text[1:])


def version_in_range(version: str, version_range: str) -> bool:
    lo, hi = range_bounds(version_range)
    v = semver_tuple(version)
    return lo <= v < hi


def resolver_triple(resolver_version: str) -> Tuple[int, int, int]:
    return semver_tuple(resolver_version.split("@", 1)[1])


# --------------------------------------------------------------------------------------------------
# ingestion — the one and only place the caller's list is touched
# --------------------------------------------------------------------------------------------------


def content_hash(document: dict) -> str:
    """R12: hash of the pack document with provenance.source_ref removed.

    The parent object is kept (emptied if that was its only key) — the rule removes a field, not a parent.
    """
    stripped = json.loads(json.dumps(document))  # structural deep copy, no aliasing of the caller's data
    prov = stripped.get("provenance")
    if isinstance(prov, dict):
        prov.pop("source_ref", None)
    return hash_v1(stripped)


def pack_ref_of(document: dict) -> str:
    identity = document.get("identity", {})
    return "{}@{}".format(identity.get("pack_id"), identity.get("pack_version"))


class PackSet:
    """The normalised, order-free view of the input.

    Built by a set-union over content hashes; after construction nothing here remembers, or can remember,
    the sequence the caller supplied.
    """

    __slots__ = ("by_hash", "refs", "docs")

    def __init__(self, documents: Sequence[dict]) -> None:
        by_hash: Dict[str, dict] = {}
        for document in documents:
            by_hash.setdefault(content_hash(document), document)
        self.by_hash: Dict[str, dict] = by_hash
        # ref -> document, and ref -> content hash; a ref is pack_id@pack_version
        self.docs: Dict[str, dict] = {}
        self.refs: Dict[str, str] = {}
        for chash, document in by_hash.items():
            ref = pack_ref_of(document)
            # two DISTINCT contents under one ref is duplicate_pack_identity, detected in P1; keep the
            # canonically-first content so that the structure itself stays order-free.
            existing = self.docs.get(ref)
            if existing is None or cform(document) < cform(existing):
                self.docs[ref] = document
                self.refs[ref] = chash

    # -- derived, order-free views ------------------------------------------------------------------

    def hash_of(self, ref: str) -> str:
        return self.refs[ref]

    def rank_of(self, ref: str) -> int:
        layer = self.docs[ref].get("identity", {}).get("layer")
        return LAYER_RANK.get(layer, -1)

    def all_refs(self) -> List[str]:
        return sorted(self.docs)

    def canonical_refs(self) -> List[str]:
        """R7's derived order (layer_rank, pack_id, pack_version) — reporting and commutative folding only."""

        def key(ref: str):
            identity = self.docs[ref]["identity"]
            return (
                self.rank_of(ref),
                identity["pack_id"],
                semver_tuple(identity["pack_version"]),
                ref,
            )

        return sorted(self.docs, key=key)

    def refs_by_pack_id(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for ref in self.docs:
            out.setdefault(self.docs[ref]["identity"]["pack_id"], []).append(ref)
        return {k: sorted(v) for k, v in out.items()}


# --------------------------------------------------------------------------------------------------
# the two relations
# --------------------------------------------------------------------------------------------------


def build_decl(packs: PackSet) -> List[dict]:
    """DECL(path, rank, pack_ref, merge?, override?) — one row per control declaration.

    An axis key that is absent from the control object is absent from the row: B does not read a
    JSON-Schema `default` as an act of declaration (design journal E05).
    """
    rows: List[dict] = []
    for ref in packs.all_refs():
        rank = packs.rank_of(ref)
        for control in packs.docs[ref].get("composition", {}).get("controls", []) or []:
            row = {"path": control["path"], "rank": rank, "pack_ref": ref}
            if "merge" in control:
                row["merge"] = control["merge"]
            if "override" in control:
                row["override"] = control["override"]
            rows.append(row)
    return sorted(rows, key=lambda r: (r["path"], r["rank"], r["pack_ref"]))


def _flatten(node: Any, prefix: str, out: List[Tuple[str, Any]]) -> None:
    if isinstance(node, dict):
        for key in sorted(node):
            _flatten(node[key], prefix + "." + key if prefix else key, out)
    else:
        out.append((prefix, node))


def build_contrib(packs: PackSet) -> List[dict]:
    """CONTRIB(leaf_path, rank, pack_ref, value) — one row per governed leaf a pack actually carries.

    Only the two in-scope sections are flattened (R15 proof scope); reserved sections are ignored.
    """
    rows: List[dict] = []
    for ref in packs.all_refs():
        rank = packs.rank_of(ref)
        document = packs.docs[ref]
        for section in PROOF_SCOPE:
            if section not in document:
                continue
            leaves: List[Tuple[str, Any]] = []
            _flatten(document[section], section, leaves)
            for leaf_path, value in leaves:
                rows.append(
                    {"leaf_path": leaf_path, "rank": rank, "pack_ref": ref, "value": value}
                )
    return sorted(rows, key=lambda r: (r["leaf_path"], r["rank"], r["pack_ref"]))


def build_derogations(packs: PackSet) -> List[dict]:
    rows: List[dict] = []
    for ref in packs.all_refs():
        rank = packs.rank_of(ref)
        for derogation in packs.docs[ref].get("composition", {}).get("derogations", []) or []:
            rows.append({"rank": rank, "pack_ref": ref, "derogation": derogation})
    return sorted(rows, key=lambda r: (r["pack_ref"], cform(r["derogation"])))


# --------------------------------------------------------------------------------------------------
# control lookup — per axis, longest match, fail-closed default (R3bis)
# --------------------------------------------------------------------------------------------------


def _covers(declared_path: str, leaf_path: str) -> bool:
    return leaf_path == declared_path or leaf_path.startswith(declared_path + ".")


def merge_for(decl: Sequence[dict], leaf_path: str) -> Tuple[str, Optional[str]]:
    """(merge semantics, declared path or None if defaulted)."""
    candidates = [d for d in decl if "merge" in d and _covers(d["path"], leaf_path)]
    if not candidates:
        return MERGE_DEFAULT, None
    longest = max(len(d["path"]) for d in candidates)
    winners = [d for d in candidates if len(d["path"]) == longest]
    return winners[0]["merge"], winners[0]["path"]


def override_floor_upto(decl: Sequence[dict], leaf_path: str, max_rank: int) -> str:
    """R3 monotone tightening: the floor at rank r is max() over every declaration covering the leaf at
    ranks <= r. Longest match selects, within a rank, which declarations speak for the leaf."""
    floor = OVERRIDE_RANK[OVERRIDE_DEFAULT]
    seen_any = False
    for rank in range(0, max_rank + 1):
        candidates = [
            d
            for d in decl
            if "override" in d and d["rank"] == rank and _covers(d["path"], leaf_path)
        ]
        if not candidates:
            continue
        longest = max(len(d["path"]) for d in candidates)
        values = [
            OVERRIDE_RANK[d["override"]] for d in candidates if len(d["path"]) == longest
        ]
        rank_value = max(values)
        floor = rank_value if not seen_any else max(floor, rank_value)
        seen_any = True
    return OVERRIDE_BY_RANK[floor]


# --------------------------------------------------------------------------------------------------
# P1 — identity
# --------------------------------------------------------------------------------------------------


def phase_p1(packs: PackSet) -> FrozenSet[str]:
    out: List[dict] = []
    for ref in packs.all_refs():
        layer = packs.docs[ref].get("identity", {}).get("layer")
        if layer not in LAYER_RANK:
            out.append(refusal("unknown_referent", "", [ref]))
    for pack_id, refs in packs.refs_by_pack_id().items():
        if len(refs) > 1:
            out.append(refusal("duplicate_pack_identity", "", refs))
    return frozenset(cform(r) for r in out), out


# --------------------------------------------------------------------------------------------------
# P2 — compatibility
# --------------------------------------------------------------------------------------------------


def phase_p2(packs: PackSet, resolver_version: str) -> List[dict]:
    out: List[dict] = []
    running = resolver_triple(resolver_version)
    present: Dict[str, List[str]] = {}
    for ref in packs.all_refs():
        identity = packs.docs[ref]["identity"]
        present.setdefault(identity["pack_id"], []).append(identity["pack_version"])

    for ref in packs.all_refs():
        compat = packs.docs[ref].get("compatibility", {}) or {}
        for requirement in compat.get("requires_packs", []) or []:
            versions = present.get(requirement["pack_id"], [])
            if not any(version_in_range(v, requirement["version_range"]) for v in versions):
                out.append(
                    refusal(
                        "compatibility_violation",
                        "",
                        [ref],
                        {
                            "pack_id": requirement["pack_id"],
                            "version_range": requirement["version_range"],
                        },
                    )
                )
        requires_resolver = compat.get("requires_resolver")
        if requires_resolver:
            needed = resolver_triple(requires_resolver["min_version"])
            if running < needed:
                out.append(
                    refusal(
                        "compatibility_violation",
                        "",
                        [ref],
                        {"requires_resolver": requires_resolver["min_version"]},
                    )
                )
    return out


# --------------------------------------------------------------------------------------------------
# P3 — control
# --------------------------------------------------------------------------------------------------


def phase_p3(decl: Sequence[dict]) -> List[dict]:
    out: List[dict] = []
    paths = sorted({d["path"] for d in decl})

    for path in paths:
        rows = [d for d in decl if d["path"] == path]

        # merge is fixed at introduction and never overridable: two distinct declared values at one path
        # is a conflict regardless of which ranks declared them (R3, R3bis).
        merge_rows = [d for d in rows if "merge" in d]
        merge_values = sorted({d["merge"] for d in merge_rows})
        if len(merge_values) > 1:
            out.append(
                refusal(
                    "merge_semantics_conflict", path, [d["pack_ref"] for d in merge_rows]
                )
            )

        # override may only be tightened: a declaration strictly looser than the floor established at
        # strictly lower ranks is a refused relaxation (R3).
        override_rows = sorted(
            [d for d in rows if "override" in d], key=lambda d: (d["rank"], d["pack_ref"])
        )
        for row in override_rows:
            lower = [
                OVERRIDE_RANK[d["override"]] for d in override_rows if d["rank"] < row["rank"]
            ]
            if lower and OVERRIDE_RANK[row["override"]] < max(lower):
                out.append(
                    refusal("strategy_relaxation_refused", path, [row["pack_ref"]])
                )
    return out


# --------------------------------------------------------------------------------------------------
# P4 — derogation form
# --------------------------------------------------------------------------------------------------

_TS_LEN = len("0000-00-00T00:00:00Z")


def _is_rfc3339_utc(text: Any) -> bool:
    if not isinstance(text, str) or len(text) != _TS_LEN:
        return False
    shape = "dddd-dd-ddTdd:dd:ddZ"
    for ch, kind in zip(text, shape):
        if kind == "d":
            if not ch.isdigit():
                return False
        elif ch != kind:
            return False
    return True


def phase_p4(derogations: Sequence[dict]) -> List[dict]:
    out: List[dict] = []
    for row in derogations:
        d = row["derogation"]
        ok = True
        granted_by = d.get("granted_by")
        if not isinstance(granted_by, dict) or not granted_by.get("authority_id") or not granted_by.get("key_id"):
            ok = False
        scope = d.get("scope")
        if not isinstance(scope, list) or not scope or not all(
            isinstance(s, str) and s and "*" not in s for s in scope
        ):
            ok = False
        if not _is_rfc3339_utc(d.get("not_before")) or not _is_rfc3339_utc(d.get("expires_at")):
            ok = False
        elif not d["not_before"] < d["expires_at"]:
            ok = False
        if not isinstance(d.get("justification"), str) or not d.get("justification"):
            ok = False
        if not isinstance(d.get("signature"), str) or not d.get("signature"):
            ok = False
        if not d.get("derogation_id"):
            ok = False
        if not ok:
            out.append(
                refusal(
                    "derogation_invalid",
                    "",
                    [row["pack_ref"]],
                    {"derogation_id": d.get("derogation_id", "")},
                )
            )
    return out


# --------------------------------------------------------------------------------------------------
# P5 — composition, as a memoised value function over the rank lattice
# --------------------------------------------------------------------------------------------------


def _fold_union(previous: Any, current: Any) -> Any:
    base = list(previous) if isinstance(previous, list) else []
    add = list(current) if isinstance(current, list) else []
    seen: Dict[str, Any] = {}
    for element in base + add:
        seen.setdefault(cform(element), element)
    return [seen[k] for k in sorted(seen)]


def _fold_intersect(previous: Any, current: Any) -> Any:
    base = list(previous) if isinstance(previous, list) else []
    keep = {cform(e) for e in (current if isinstance(current, list) else [])}
    seen: Dict[str, Any] = {}
    for element in base:
        key = cform(element)
        if key in keep:
            seen.setdefault(key, element)
    return [seen[k] for k in sorted(seen)]


def _fold_append(previous: Any, current: Any) -> Any:
    base = list(previous) if isinstance(previous, list) else []
    add = list(current) if isinstance(current, list) else []
    return base + add


class LeafEvaluation:
    """Everything decided about one leaf, computed by querying a value vector rather than by walking."""

    __slots__ = (
        "leaf_path",
        "merge",
        "contributions",
        "peer_value",
        "refusals",
        "value_upto",
        "changed_ranks",
        "first_rank",
        "effective_value",
        "rule",
        "derogation_applied",
        "selected_from",
        "overridden_sources",
        "override",
    )

    def __init__(self) -> None:
        self.refusals: List[dict] = []
        self.derogation_applied: Optional[dict] = None


def evaluate_leaf(
    leaf_path: str,
    contrib: Sequence[dict],
    decl: Sequence[dict],
    derogations: Sequence[dict],
    evaluated_at: str,
) -> LeafEvaluation:
    ev = LeafEvaluation()
    ev.leaf_path = leaf_path
    merge, _ = merge_for(decl, leaf_path)
    ev.merge = merge

    rows = [c for c in contrib if c["leaf_path"] == leaf_path]
    by_rank: Dict[int, List[dict]] = {}
    for row in rows:
        by_rank.setdefault(row["rank"], []).append(row)

    # --- step 1: reduce peers within each rank (R4) -------------------------------------------------
    peer_value: Dict[int, Any] = {}
    for rank in sorted(by_rank):
        peers = by_rank[rank]
        distinct = {}
        for p in peers:
            distinct.setdefault(cform(p["value"]), p)
        if len(distinct) == 1:
            peer_value[rank] = peers[0]["value"]
            continue
        if merge in ("union", "intersect"):
            values = [distinct[k]["value"] for k in sorted(distinct)]
            folded = values[0]
            for nxt in values[1:]:
                folded = _fold_union(folded, nxt) if merge == "union" else _fold_intersect(folded, nxt)
            peer_value[rank] = folded
        else:
            ev.refusals.append(
                refusal(
                    "peer_conflict",
                    leaf_path,
                    sorted({distinct[k]["pack_ref"] for k in distinct}),
                )
            )
            peer_value[rank] = peers[0]["value"]
    ev.peer_value = peer_value
    ev.contributions = by_rank

    if not peer_value:
        ev.effective_value = None
        ev.value_upto = {}
        ev.changed_ranks = []
        ev.first_rank = None
        ev.rule = "introduction"
        ev.selected_from = []
        ev.overridden_sources = []
        ev.override = override_floor_upto(decl, leaf_path, len(LAYERS) - 1)
        return ev

    contributing = sorted(peer_value)
    ev.first_rank = contributing[0]

    # --- step 2: the value function over the rank lattice, memoised ---------------------------------
    memo: Dict[int, Any] = {}

    def val_upto(rank: int) -> Any:
        if rank in memo:
            return memo[rank]
        below = [r for r in contributing if r < rank]
        if rank not in peer_value:
            result = val_upto(max(below)) if below else None
        elif not below:
            result = peer_value[rank]
        else:
            previous = val_upto(max(below))
            current = peer_value[rank]
            if merge == "replace":
                result = current
            elif merge == "append":
                result = _fold_append(previous, current)
            elif merge == "union":
                result = _fold_union(previous, current)
            else:
                result = _fold_intersect(previous, current)
        memo[rank] = result
        return result

    value_upto = {rank: val_upto(rank) for rank in contributing}
    ev.value_upto = value_upto
    ev.effective_value = value_upto[contributing[-1]]

    # --- step 3: which ranks CHANGED the value (queried, not accumulated) ----------------------------
    changed: List[int] = []
    for index, rank in enumerate(contributing):
        if index == 0:
            continue
        if cform(value_upto[rank]) != cform(value_upto[contributing[index - 1]]):
            changed.append(rank)
    ev.changed_ranks = changed

    # --- step 4: permission check at every changing rank (R5, R6) ------------------------------------
    strength = RULE_STRENGTH["introduction"]
    if merge in ("union", "intersect", "append") and len(contributing) > 1:
        strength = max(strength, RULE_STRENGTH["commutative_fold"])

    for rank in changed:
        floor = override_floor_upto(decl, leaf_path, rank)
        actors = sorted({c["pack_ref"] for c in by_rank[rank]})
        if floor == "forbidden":
            ev.refusals.append(refusal("forbidden_override", leaf_path, actors))
            continue
        if floor == "open":
            strength = max(strength, RULE_STRENGTH["layer_override"])
            continue
        # requires_derogation — a derogation carried at this rank must literally name the leaf (R6)
        naming = [
            row
            for row in derogations
            if row["rank"] == rank and leaf_path in (row["derogation"].get("scope") or [])
        ]
        if not naming:
            ev.refusals.append(refusal("derogation_required", leaf_path, actors))
            continue
        live = [
            row
            for row in naming
            if row["derogation"]["not_before"] <= evaluated_at < row["derogation"]["expires_at"]
        ]
        if not live:
            chosen = sorted(naming, key=lambda row: cform(row["derogation"]))[0]["derogation"]
            ev.refusals.append(
                refusal(
                    "derogation_expired",
                    leaf_path,
                    actors,
                    {"derogation_id": chosen["derogation_id"]},
                )
            )
            continue
        chosen = sorted(live, key=lambda row: cform(row["derogation"]))[0]["derogation"]
        ev.derogation_applied = {
            "derogation_id": chosen["derogation_id"],
            "authority_id": chosen["granted_by"]["authority_id"],
            "key_id": chosen["granted_by"]["key_id"],
            "expires_at": chosen["expires_at"],
        }
        strength = max(strength, RULE_STRENGTH["derogated_override"])

    ev.rule = RULE_BY_STRENGTH[strength]
    ev.override = override_floor_upto(decl, leaf_path, len(LAYERS) - 1)

    # --- step 5: R12bis — trace facts derived from the RESOLVED VALUE, not from the fold --------------
    effective = cform(ev.effective_value)
    if merge in ("append", "union", "intersect"):
        # every contribution survives into the result, so nothing was overridden
        ev.selected_from = sorted({c["pack_ref"] for r in by_rank for c in by_rank[r]})
        ev.overridden_sources = []
    else:
        selected, overridden = [], []
        for rank in by_rank:
            for c in by_rank[rank]:
                (selected if cform(c["value"]) == effective else overridden).append(c["pack_ref"])
        ev.selected_from = sorted(set(selected))
        ev.overridden_sources = sorted(set(overridden))
    return ev


# --------------------------------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------------------------------


def _nest(entries: Sequence[dict]) -> dict:
    sections: Dict[str, Any] = {}
    for entry in entries:
        parts = entry["path"].split(".")
        node = sections
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = entry["effective_value"]
    return sections


def _context(packs: PackSet) -> dict:
    domains, jurisdictions, orgs = set(), set(), set()
    for ref in packs.all_refs():
        identity = packs.docs[ref].get("identity", {})
        if identity.get("domain"):
            domains.add(identity["domain"])
        if identity.get("jurisdiction"):
            jurisdictions.add(identity["jurisdiction"])
        if identity.get("org_id"):
            orgs.add(identity["org_id"])
    return {
        "domain": sorted(domains),
        "jurisdiction": sorted(jurisdictions),
        "org_id": sorted(orgs),
    }


def _pack_stamps(packs: PackSet) -> List[dict]:
    stamps = []
    for ref in packs.canonical_refs():
        identity = packs.docs[ref]["identity"]
        stamps.append(
            {
                "pack_id": identity["pack_id"],
                "pack_version": identity["pack_version"],
                "layer": identity["layer"],
                "content_hash": packs.hash_of(ref),
            }
        )
    return stamps


def _refused(phase: str, refusals: Sequence[dict], resolver_version: str, evaluated_at: str) -> dict:
    return {
        "schema_version": SCHEMA_MANIFEST,
        "kind": KIND_REFUSAL,
        "resolver_version": resolver_version,
        "evaluated_at": evaluated_at,
        "phase": phase,
        "refusals": list(refusals),
    }


def resolve(
    documents: Sequence[dict],
    evaluated_at: str,
    resolver_version: str = "pack-resolver@0.1.0",
) -> dict:
    """Pure function (R10). Returns {'outcome': 'resolved'|'refused', ...}."""
    packs = PackSet(documents)
    decl = build_decl(packs)
    contrib = build_contrib(packs)
    derogations = build_derogations(packs)

    # R9: the first phase producing any refusal terminates and reports EVERY refusal of that phase.
    _, p1 = phase_p1(packs)
    staged = [
        ("P1_identity", p1),
        ("P2_compatibility", phase_p2(packs, resolver_version) if not p1 else []),
    ]
    if p1:
        return {
            "outcome": "refused",
            "packs": packs,
            "refusal": _refused("P1_identity", order_refusals(p1), resolver_version, evaluated_at),
        }
    p2 = staged[1][1]
    if p2:
        return {
            "outcome": "refused",
            "packs": packs,
            "refusal": _refused("P2_compatibility", order_refusals(p2), resolver_version, evaluated_at),
        }
    p3 = phase_p3(decl)
    if p3:
        return {
            "outcome": "refused",
            "packs": packs,
            "refusal": _refused("P3_control", order_refusals(p3), resolver_version, evaluated_at),
        }
    p4 = phase_p4(derogations)
    if p4:
        return {
            "outcome": "refused",
            "packs": packs,
            "refusal": _refused(
                "P4_derogation_form", order_refusals(p4), resolver_version, evaluated_at
            ),
        }

    leaves = sorted({c["leaf_path"] for c in contrib})
    evaluations = [evaluate_leaf(leaf, contrib, decl, derogations, evaluated_at) for leaf in leaves]

    p5 = [r for ev in evaluations for r in ev.refusals]
    if p5:
        return {
            "outcome": "refused",
            "packs": packs,
            "refusal": _refused("P5_composition", order_refusals(p5), resolver_version, evaluated_at),
        }

    entries = []
    for ev in evaluations:
        entries.append(
            {
                "path": ev.leaf_path,
                "effective_value": ev.effective_value,
                "selected_from": ev.selected_from,
                "overridden_sources": ev.overridden_sources,
                "resolution_rule": ev.rule,
                "merge": ev.merge,
                "override": ev.override,
                "derogation_applied": ev.derogation_applied,
            }
        )
    entries.sort(key=lambda e: e["path"])

    manifest = {
        "schema_version": SCHEMA_MANIFEST,
        "kind": KIND_MANIFEST,
        "resolver_version": resolver_version,
        "evaluated_at": evaluated_at,
        "proof_scope": list(PROOF_SCOPE),
        "context": _context(packs),
        "packs": _pack_stamps(packs),
        "sections": _nest(entries),
    }
    manifest_hash = hash_v1(manifest)

    trace = {
        "schema_version": SCHEMA_MANIFEST,
        "kind": KIND_TRACE,
        "resolver_version": resolver_version,
        "evaluated_at": evaluated_at,
        "effective_manifest_hash": manifest_hash,
        "entries": entries,
    }

    contested = sorted(
        e["path"]
        for e in entries
        if e["overridden_sources"] or e["derogation_applied"] is not None
    )

    return {
        "outcome": "resolved",
        "packs": packs,
        "effective_manifest": manifest,
        "effective_manifest_hash": manifest_hash,
        "resolution_trace": trace,
        "trace_hash": hash_v1(trace),
        "contested_paths": contested,
    }


# --------------------------------------------------------------------------------------------------
# envelope (REPLAY-ENVELOPE.md — container only)
# --------------------------------------------------------------------------------------------------


def envelope(result: dict) -> dict:
    packs: PackSet = result["packs"]
    artifacts = [
        {"role": "pack_content", "ref": ref, "key": packs.hash_of(ref)}
        for ref in packs.all_refs()
    ]

    if result["outcome"] == "resolved":
        artifacts.append(
            {"role": "effective_manifest", "ref": "", "key": result["effective_manifest_hash"]}
        )
        artifacts.append({"role": "resolution_trace", "ref": "", "key": result["trace_hash"]})
        out = {
            "outcome": "resolved",
            "effective_manifest": result["effective_manifest"],
            "effective_manifest_hash": result["effective_manifest_hash"],
            "resolution_trace": result["resolution_trace"],
            "trace_hash": result["trace_hash"],
            "contested_paths": result["contested_paths"],
        }
    else:
        refusal_object = result["refusal"]
        refusal_hash = hash_v1(refusal_object)
        artifacts.append({"role": "resolution_refusal", "ref": "", "key": refusal_hash})
        out = {
            "outcome": "refused",
            "phase": refusal_object["phase"],
            "refusals": refusal_object["refusals"],
            "refusal_codes": sorted({r["code"] for r in refusal_object["refusals"]}),
            "refusal_hash": refusal_hash,
        }

    out["artifacts"] = sorted(artifacts, key=lambda a: (a["role"], a["ref"], a["key"]))
    return out
