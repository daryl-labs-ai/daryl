"""Knowledge Object — a **projection**, not an entity (first product surface).

The model already knows what an object is; this makes it **visible to a user**. A Knowledge Object
is a **`KnowledgeObjectProjection`** — a *stable derived view* of an object, recomputed from its acts,
**never stored** and with **no `object_id`** (keyed by the `subject_id` referent, #4a). It is the next
projection after `standing` / `governed_standing` / `object_standing` / `governance` — same discipline:
derived, droppable, never a second source of truth.

It **composes only** the proven second-epoch derivations — it invents no rule and computes nothing anew:
- **object standing** (`object_standing`, ADR-0012) + **coherence** (#4b) + per-claim **governed**
  (`governed_standing`, ADR-0011) / **conflict** (#2) — via `SubjectStandingsQuery`;
- **governance posture** (`clear`/`contested`/`divergent`) — via `GovernanceQuery`;
- **the chain / why** (proposal + resolutions, each receipt-backed) — via `ExplainQuery`.

v1 = **Discovery** (`discover_objects`: "what objects do I own?") + **Object View** (`project`: one page).
Deferred: **actions** (they open permissions/workflows) and **#4b-C** (content/lineage compilation — the
Object View is built first, to *observe* whether compiled content is actually needed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from ..types import ConsultationNode, from_entry
from .consultation_read import ConsultationQuery
from .explain_read import ExplainQuery
from .governance_read import GovernanceQuery
from .standing_read import RegistryProjection, derive_governed_standing
from .subject_read import SubjectStandingsQuery


@dataclass(frozen=True)
class KnowledgeObjectSummary:
    """One row in Discovery — an object's headline governed state (derived)."""

    subject_id: str
    object_standing: str   # ADR-0012 — the subject's authoritative reading
    coherence: str         # #4b — aligned / divergent / unsettled
    governance: str        # step (c) — clear / contested / divergent
    n_claims: int
    has_conflict: bool
    org_id: str = ""
    last_ord: int = -1     # record-order recency (max act index seen) — v1 proxy for "recent"


@dataclass(frozen=True)
class ClaimLine:
    """One claim on the Object View — its raw + governed standing and its **raw content** (the
    proposal's `answer`). Composed, not recomputed; the raw content is shown so the object is read
    from its claims' actual text — the cheaper alternative to a compiled content (#4b-C)."""

    claim_id: str
    mode: str
    raw_standing: str
    governed_standing: str
    conflict: bool
    answer: str = ""     # the claim's RAW content (the proposal's answer) — not compiled
    agent_id: str = ""
    carrier: str = ""


@dataclass(frozen=True)
class TimelineItem:
    """One certified act on the Object View — proposal or resolution, receipt-backed."""

    claim_id: str
    kind: str      # "proposal" | "resolution"
    label: str     # the mode or the decision
    agent_id: str
    carrier: str
    receipt: str


@dataclass(frozen=True)
class KnowledgeObjectProjection:
    """The consolidated Object View — a **derived projection** keyed by `subject_id`, never stored,
    no `object_id`. Composes object standing + coherence + governance + per-claim governed state +
    the certified timeline. It **invents nothing** — every field comes from a proven query."""

    subject_id: str
    object_standing: str
    coherence: str
    governance: str
    claims: tuple[ClaimLine, ...]
    timeline: tuple[TimelineItem, ...]


def render_objects(summaries: list[KnowledgeObjectSummary]) -> str:
    """Pure display — the Discovery listing (recency-first)."""
    if not summaries:
        return "no knowledge objects"
    lines = [f"{len(summaries)} knowledge object(s):"]
    for s in summaries:
        flag = "  ⚠ conflict" if s.has_conflict else ""
        org = f"  org={s.org_id}" if s.org_id else ""
        lines.append(f"  {s.subject_id}   object={s.object_standing.upper()}   "
                     f"coherence={s.coherence}   gov={s.governance.upper()}   "
                     f"claims={s.n_claims}{org}{flag}")
    return "\n".join(lines)


def object_reason(object_standing: str, coherence: str, has_conflict: bool) -> str:
    """A one-line **human reason** for the object's status — a *narrative* over the proven signals,
    not a new derivation. It turns the two vocabularies (`object_standing` vs `coherence`/governance)
    into a single story: the model keeps two concepts, the user reads one."""
    if object_standing == "contested":
        if coherence == "divergent":
            return "claims diverge"
        if has_conflict:
            return "a constituent claim is contested"
        return "contested"
    if object_standing in ("accepted", "rejected"):
        return "claims agree"
    if object_standing == "proposed":
        return "no governed claim yet"
    return object_standing


def render_knowledge_object(proj: KnowledgeObjectProjection) -> str:
    """Pure display — the one-page Object View (composes proven derivations; recomputes nothing).
    Leads with a **single story** — `status` + a human `reason` — and shows each claim's **raw
    content** (its `answer`), so the object is read from the claims' actual text, not a compiled one."""
    has_conflict = any(c.conflict for c in proj.claims)
    lines = [f"Knowledge Object — {proj.subject_id}",
             f"  status:  {proj.object_standing.upper()}",
             f"  reason:  {object_reason(proj.object_standing, proj.coherence, has_conflict)}",
             f"  signals: coherence={proj.coherence} · governance={proj.governance}",
             "  claims:"]
    if not proj.claims:
        lines.append("    (none)")
    for c in proj.claims:
        cf = "  ⚠ conflict" if c.conflict else ""
        raw = f"  raw={c.raw_standing.upper()}" if c.governed_standing != c.raw_standing else ""
        lines.append(f"    {c.claim_id}  [{c.mode}]  governed={c.governed_standing.upper()}{raw}  "
                     f"agent={c.agent_id or '(unknown)'}{cf}")
        if c.answer:
            lines.append(f"        “{c.answer}”")               # the claim's RAW content (not compiled)
    lines.append("  timeline (certified acts):")
    if not proj.timeline:
        lines.append("    (none)")
    for t in proj.timeline:
        lines.append(f"    {t.kind:<11}{t.label:<11}claim={t.claim_id}  "
                     f"agent={t.agent_id or '(unknown)'}  receipt {t.receipt}")
    return "\n".join(lines)


class KnowledgeObjectQuery:
    """Assembles a Knowledge Object as a derived projection (read-only). Builds **one** shared
    registry projection and passes it to the composed queries — `SubjectStandingsQuery`,
    `GovernanceQuery`, `ExplainQuery`, `ConsultationQuery` — so the whole object is read over a single
    index. Holds **no write path**; keyed by `subject_id`; mints no `object_id`; stores nothing."""

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RegistryProjection | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()
            _navigator = RRNavigator(builder, storage)
        self._nav: RegistryProjection = _navigator
        self._consult = ConsultationQuery(storage, index_dir, _navigator=_navigator)
        self._subject = SubjectStandingsQuery(storage, index_dir, _navigator=_navigator)
        self._gov = GovernanceQuery(storage, index_dir, _navigator=_navigator)
        self._explain = ExplainQuery(storage, index_dir, _navigator=_navigator)

    def discover_objects(
        self, *, org_id: str | None = None, contested: bool = False,
        conflicts: bool = False, search: str | None = None,
    ) -> list[KnowledgeObjectSummary]:
        """Enumerate the Knowledge Objects (distinct `subject_id`) with their headline state, recency
        first. Derived + droppable: a scan of `prl.consultation` → distinct subjects, each summarized by
        the proven queries. Filters: owning `org`, `contested` object standing, `conflicts` present,
        `search` (substring on the subject id).

        Recency is the **authoritative record order** — from ``navigate_action`` (ascending, stable),
        **never** from ``resolve_entries`` (which does not preserve order; v1.0 read recency from the
        resolved order and mis-sorted). Replay records in order and join record→entry by id — the same
        rule as ``standing_read._resolutions_for``."""
        records = self._nav.navigate_action("prl.consultation")
        entries = self._nav.resolve_entries(records)
        by_id = {getattr(e, "id", None): e for e in entries}
        last_ord: dict[str, int] = {}
        org_of: dict[str, str] = {}
        for i, rec in enumerate(records):
            eid = rec.get("entry_id") if isinstance(rec, dict) else getattr(rec, "entry_id", None)
            entry = by_id.get(eid)
            if entry is None:
                continue
            node = from_entry(entry)
            if not isinstance(node, ConsultationNode):
                continue
            last_ord[node.subject_id] = i          # authoritative record order = recency
            if node.subject_id not in org_of:
                org_of[node.subject_id] = node.org_id or ""
        out: list[KnowledgeObjectSummary] = []
        for subj, ord_ in last_ord.items():
            sv = self._subject.standings_of_subject(subj)
            out.append(KnowledgeObjectSummary(
                subject_id=subj,
                object_standing=sv.object_standing,
                coherence=sv.coherence,
                governance=self._gov.governance_of_subject(subj).governance,
                n_claims=len(sv.claims),
                has_conflict=any(c.conflict for c in sv.claims),
                org_id=org_of.get(subj, ""),
                last_ord=ord_,
            ))
        if org_id is not None:
            out = [s for s in out if s.org_id == org_id]
        if contested:
            out = [s for s in out if s.object_standing == "contested"]
        if conflicts:
            out = [s for s in out if s.has_conflict]
        if search:
            out = [s for s in out if search.lower() in s.subject_id.lower()]
        out.sort(key=lambda s: s.last_ord, reverse=True)   # recency-first
        return out

    def project(self, subject_id: str) -> KnowledgeObjectProjection:
        """The one-page Object View. Composes object standing + coherence (SubjectStandingsQuery),
        governance posture (GovernanceQuery), and the per-claim chain (ExplainQuery). Per-claim
        `governed_standing` is the pure ADR-0011 derivation; **nothing is recomputed differently**."""
        sv = self._subject.standings_of_subject(subject_id)
        governance = self._gov.governance_of_subject(subject_id).governance
        claims: list[ClaimLine] = []
        timeline: list[TimelineItem] = []
        for c in sv.claims:
            ex = self._explain.explain(c.claim_id)
            answer = ex.proposal.answer if ex.proposal is not None else ""
            claims.append(ClaimLine(
                claim_id=c.claim_id, mode=c.mode, raw_standing=c.standing,
                governed_standing=derive_governed_standing(c.standing, c.conflict),
                conflict=c.conflict, answer=answer, agent_id=c.agent_id, carrier=c.carrier))
            if ex.proposal is not None:
                p = ex.proposal
                timeline.append(TimelineItem(
                    claim_id=c.claim_id, kind="proposal", label="proposal",
                    agent_id=p.agent_id, carrier=p.carrier, receipt=p.receipt))
            for r in ex.resolutions:
                timeline.append(TimelineItem(
                    claim_id=c.claim_id, kind="resolution", label=r.decision,
                    agent_id=r.agent_id, carrier=r.carrier, receipt=r.receipt))
        return KnowledgeObjectProjection(
            subject_id=subject_id, object_standing=sv.object_standing, coherence=sv.coherence,
            governance=governance, claims=tuple(claims), timeline=tuple(timeline))
