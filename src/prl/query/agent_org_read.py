"""Agent / Org navigation views (v1) — read-only derived projections (O-003 → navigation, no entity).

O-003 made objects findable *by* agent / org; the next view starts *from* an agent / org. This module
exposes the already-composable traversals — ``agent → objects`` (contributed + resolved) and
``org → objects`` (owned + touched) — as **navigable, role-distinguished views**, WITHOUT minting an
``Agent`` / ``Org`` entity, a new field, a stored graph, or a persistent index.

It is the **decision-side sibling** of ``PRLAdjacencyIndex`` (code-graph) and ``StandingIndex``
(resolutions by claim): a derived, droppable, **in-memory reverse adjacency** over the two decision-act
streams (``prl.consultation`` + ``prl.resolution``), built per call and never stored. ``agent_id`` /
``org_id`` stay **opaque strings that live on the acts** — no node, no id minting, no registry (the
fence). Object headlines reuse the proven ``standings_of_subject`` exactly as discovery does; nothing is
recomputed differently, and ``types.py`` is untouched (no ``subject_id`` on a resolution — the 2-hop
join *is* the derivation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from ..types import ConsultationNode, ResolutionNode, from_entry
from .knowledge_object import object_reason
from .standing_read import RegistryProjection, ResolutionFact, detect_conflict
from .subject_read import SubjectStandingsQuery

# Reserved label reaching pre-0009 acts (``agent_id`` None → ""). Never merged with a real agent_id;
# if a real agent were literally named "unknown", the view says so (v1 accepts that residual ambiguity).
UNKNOWN_AGENT = "unknown"

# Certified resolution decisions, in presentation order (contested is NOT a decision — it is a derived
# governed state of the claim, surfaced as a per-row flag).
_DECISION_ORDER = ("accepted", "rejected", "superseded", "withdrawn")


@dataclass(frozen=True)
class ActRef:
    """One act's certified reference on a row — the claim it acts on + its receipt. No invented data.
    ``ord`` is the **per-stream** authoritative record order (consultation ord for contributed rows,
    resolution ord for resolved rows) — never a cross-stream global timeline (grounding F3.4)."""

    claim_id: str
    receipt: str
    ord: int


@dataclass(frozen=True)
class ObjectRow:
    """One object under a role sub-bucket — its **proven** headline (``standings_of_subject`` →
    ``object_standing`` + ``object_reason``) + the agent's/org's acts on it, folded per object."""

    subject_id: str
    object_standing: str
    reason: str
    owning_org: str
    acts: tuple[ActRef, ...]
    contested: bool = False   # (resolved rows) the target claim's governed standing is #2-contested


@dataclass(frozen=True)
class AgentView:
    """``prl agent <id>`` — an agent's objects, split by ROLE then decision; recency per stream.
    ``Contributed`` (proposed / observed) and ``Resolved`` (by the agent's own certified decision) are
    never merged; an empty section renders empty (the absence is itself information)."""

    agent_id: str
    is_unknown: bool
    proposed: tuple[ObjectRow, ...]
    observed: tuple[ObjectRow, ...]
    resolved: tuple[tuple[str, tuple[ObjectRow, ...]], ...]   # (decision, rows), decisions present only


@dataclass(frozen=True)
class OrgView:
    """``prl org <id>`` — objects **owned** by the org (owning org = first consultation's org) vs merely
    **touched** by one of its acts (consultation *or* resolution). Disjoint by construction."""

    org_id: str
    owned: tuple[ObjectRow, ...]
    touched: tuple[ObjectRow, ...]


class AgentOrgQuery:
    """Builds Agent / Org navigation views as derived projections (read-only). One reverse adjacency
    over the two act streams, transposed per instance, **never stored**; object headlines reuse the
    proven ``standings_of_subject``. Holds no write path; mints no entity; keyed by opaque strings."""

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RegistryProjection | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()
            _navigator = RRNavigator(builder, storage)
        self._nav: RegistryProjection = _navigator
        self._subject = SubjectStandingsQuery(storage, index_dir, _navigator=_navigator)

        # --- reverse adjacency (two walks, transposed; nothing persisted) ---
        self._subjects: set[str] = set()
        self._claim_subject: dict[str, str] = {}                 # claim → subject (the 2-hop bridge)
        self._owning_org: dict[str, str] = {}                    # subject → owning org (first consult)
        self._touch_orgs: dict[str, set[str]] = {}               # subject → orgs touching it (any act)
        self._subject_ord: dict[str, int] = {}                   # subject → latest consultation ord
        self._org_touch_ord: dict[tuple[str, str], int] = {}     # (org, subject) → latest touch ord
        # contributed: agent → mode → subject → [ActRef];  resolved: agent → decision → subject → [ActRef]
        self._contrib: dict[str, dict[str, dict[str, list[ActRef]]]] = {}
        self._resolved: dict[str, dict[str, dict[str, list[ActRef]]]] = {}
        self._res_facts: dict[str, list[ResolutionFact]] = {}    # claim → facts (for contested detection)

        self._walk_consultations()
        self._walk_resolutions()

    # ── the two act-stream walks ──────────────────────────────────────────────────────────────────
    def _walk_consultations(self) -> None:
        """Consultation stream → agent→contributed acts, claim→subject, owning + touching org."""
        records = self._nav.navigate_action("prl.consultation")
        by_id = {getattr(e, "id", None): e for e in self._nav.resolve_entries(records)}
        for i, rec in enumerate(records):
            eid = rec.get("entry_id") if isinstance(rec, dict) else getattr(rec, "entry_id", None)
            entry = by_id.get(eid)
            if entry is None:
                continue
            node = from_entry(entry)
            if not isinstance(node, ConsultationNode):
                continue
            subj, cid = node.subject_id, node.mef.claim_id
            agent = node.mef.agent_id or ""
            org = node.org_id or ""
            receipt = str(getattr(entry, "hash", "") or "")
            self._subjects.add(subj)
            self._claim_subject[cid] = subj
            self._owning_org.setdefault(subj, org)               # first consultation's org = owning org
            self._subject_ord[subj] = i                          # ascending → latest wins
            if org:
                self._touch_orgs.setdefault(subj, set()).add(org)
                self._org_touch_ord[(org, subj)] = i
            (self._contrib.setdefault(agent, {}).setdefault(node.mode, {})
                 .setdefault(subj, []).append(ActRef(cid, receipt, i)))

    def _walk_resolutions(self) -> None:
        """Resolution stream → agent→resolved claims → objects via claim→subject (the 2-hop join);
        resolution-side touching org. No ``subject_id`` is read off a resolution — the join is it."""
        records = self._nav.navigate_action("prl.resolution")
        by_id = {getattr(e, "id", None): e for e in self._nav.resolve_entries(records)}
        for i, rec in enumerate(records):
            eid = rec.get("entry_id") if isinstance(rec, dict) else getattr(rec, "entry_id", None)
            entry = by_id.get(eid)
            if entry is None:
                continue
            node = from_entry(entry)
            if not isinstance(node, ResolutionNode):
                continue
            cid = node.target_claim_id
            agent = node.mef.agent_id or ""
            org = node.org_id or ""
            receipt = str(getattr(entry, "hash", "") or "")
            self._res_facts.setdefault(cid, []).append(ResolutionFact(
                decision=node.decision, resolver=node.mef.producer, receipt=receipt,
                agent_id=agent, org_id=org))
            subj = self._claim_subject.get(cid, "")              # 2-hop join
            if not subj:
                continue                                          # a resolution to an unknown claim
            if org:
                self._touch_orgs.setdefault(subj, set()).add(org)
                self._org_touch_ord[(org, subj)] = max(self._org_touch_ord.get((org, subj), -1), i)
            (self._resolved.setdefault(agent, {}).setdefault(node.decision, {})
                 .setdefault(subj, []).append(ActRef(cid, receipt, i)))

    # ── row assembly (headline reused, never recomputed differently) ──────────────────────────────
    def _rows(self, by_subject: dict[str, list[ActRef]], *, resolved: bool) -> tuple[ObjectRow, ...]:
        rows: list[ObjectRow] = []
        for subj, acts in by_subject.items():
            sv = self._subject.standings_of_subject(subj)
            contested = resolved and any(
                detect_conflict(self._res_facts.get(a.claim_id, []))[0] for a in acts)
            rows.append(ObjectRow(
                subject_id=subj, object_standing=sv.object_standing,
                reason=object_reason(sv.object_standing, sv.coherence, any(c.conflict for c in sv.claims)),
                owning_org=self._owning_org.get(subj, ""),
                acts=tuple(sorted(acts, key=lambda a: a.ord)), contested=contested))
        rows.sort(key=lambda r: max((a.ord for a in r.acts), default=-1), reverse=True)  # recency/stream
        return tuple(rows)

    def _org_rows(self, subjects: list[str], ord_of: dict[str, int]) -> tuple[ObjectRow, ...]:
        rows: list[ObjectRow] = []
        for subj in subjects:
            sv = self._subject.standings_of_subject(subj)
            rows.append(ObjectRow(
                subject_id=subj, object_standing=sv.object_standing,
                reason=object_reason(sv.object_standing, sv.coherence, any(c.conflict for c in sv.claims)),
                owning_org=self._owning_org.get(subj, ""), acts=()))
        rows.sort(key=lambda r: ord_of.get(r.subject_id, -1), reverse=True)
        return tuple(rows)

    @staticmethod
    def _merge(store: dict[str, dict[str, dict[str, list[ActRef]]]], keys: set[str],
               bucket: str) -> dict[str, list[ActRef]]:
        out: dict[str, list[ActRef]] = {}
        for k in keys:
            for subj, acts in store.get(k, {}).get(bucket, {}).items():
                out.setdefault(subj, []).extend(acts)
        return out

    # ── the two views ─────────────────────────────────────────────────────────────────────────────
    def agent(self, agent_id: str) -> AgentView:
        """One agent's objects. ``prl agent unknown`` reaches the legacy (``agent_id`` None → "") acts;
        a real agent id reaches only its own acts (never merged with the unknown bucket)."""
        is_unknown = agent_id == UNKNOWN_AGENT
        keys = {"", UNKNOWN_AGENT} if is_unknown else {agent_id}
        proposed = self._rows(self._merge(self._contrib, keys, "proposal"), resolved=False)
        observed = self._rows(self._merge(self._contrib, keys, "observation"), resolved=False)
        present: set[str] = set()
        for k in keys:
            present |= set(self._resolved.get(k, {}).keys())
        order = [d for d in _DECISION_ORDER if d in present] + sorted(present - set(_DECISION_ORDER))
        resolved = tuple((d, self._rows(self._merge(self._resolved, keys, d), resolved=True))
                         for d in order)
        return AgentView(agent_id=agent_id, is_unknown=is_unknown,
                         proposed=proposed, observed=observed, resolved=resolved)

    def org(self, org_id: str) -> OrgView:
        """One org's objects. **Owned** = owning org is this org; **Touched** = some act carries this
        org but it is not the owner. Disjoint: an owned object never re-appears under Touched."""
        owned_subs = [s for s in self._subjects if self._owning_org.get(s, "") == org_id]
        touched_subs = [s for s in self._subjects
                        if org_id in self._touch_orgs.get(s, set()) and self._owning_org.get(s, "") != org_id]
        owned = self._org_rows(owned_subs, self._subject_ord)
        touched = self._org_rows(touched_subs, {s: self._org_touch_ord.get((org_id, s), -1) for s in touched_subs})
        return OrgView(org_id=org_id, owned=owned, touched=touched)


# ── pure renderers ───────────────────────────────────────────────────────────────────────────────
def _agent_bucket(label: str, rows: tuple[ObjectRow, ...], *, resolved: bool = False) -> list[str]:
    out = [f"    {label}"]
    if not rows:
        out.append("      (none)")
        return out
    for r in rows:
        flag = "   ⚠ contested" if (resolved and r.contested) else ""
        out.append(f"      {r.subject_id}   object={r.object_standing.upper()}   {r.reason}{flag}")
        for a in r.acts:
            out.append(f"        claim={a.claim_id}  receipt {a.receipt}")
    return out


def render_agent_view(view: AgentView) -> str:
    """Pure display — ``Agent`` page: ``Contributed`` (Proposed / Observed) then ``Resolved`` (by the
    agent's own certified decision, ``⚠ contested`` where the target claim is #2-contested)."""
    title = "unknown / legacy agent" if view.is_unknown else view.agent_id
    lines = [f"Agent — {title}", "  Contributed"]
    lines += _agent_bucket("Proposed", view.proposed)
    lines += _agent_bucket("Observed", view.observed)
    lines.append("  Resolved")
    if not view.resolved:
        lines.append("    (none)")
    for decision, rows in view.resolved:
        lines += _agent_bucket(decision.capitalize(), rows, resolved=True)
    return "\n".join(lines)


def _org_bucket(rows: tuple[ObjectRow, ...], *, touched: bool = False) -> list[str]:
    if not rows:
        return ["    (none)"]
    out: list[str] = []
    for r in rows:
        owner = f"   owner={r.owning_org}" if (touched and r.owning_org) else ""
        out.append(f"    {r.subject_id}   object={r.object_standing.upper()}   {r.reason}{owner}")
    return out


def render_org_view(view: OrgView) -> str:
    """Pure display — ``Org`` page: ``Owned objects`` (owning org = this org) then ``Touched objects``
    (an act carries this org but it is not the owner). The two lists are disjoint by construction."""
    lines = [f"Org — {view.org_id}", "  Owned objects"]
    lines += _org_bucket(view.owned)
    lines.append("  Touched objects")
    lines += _org_bucket(view.touched, touched=True)
    return "\n".join(lines)
