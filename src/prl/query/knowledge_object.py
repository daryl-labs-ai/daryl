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
    """One claim on the Object View — its raw + governed standing (composed, not recomputed)."""

    claim_id: str
    mode: str
    raw_standing: str
    governed_standing: str
    conflict: bool
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


def render_knowledge_object(proj: KnowledgeObjectProjection) -> str:
    """Pure display — the one-page Object View (composes proven derivations; recomputes nothing)."""
    lines = [f"Knowledge Object — {proj.subject_id}",
             f"  object standing: {proj.object_standing.upper()}",
             f"  coherence:       {proj.coherence.upper()}",
             f"  governance:      {proj.governance.upper()}",
             "  claims:"]
    if not proj.claims:
        lines.append("    (none)")
    for c in proj.claims:
        cf = "  ⚠ conflict" if c.conflict else ""
        raw = f"  raw={c.raw_standing.upper()}" if c.governed_standing != c.raw_standing else ""
        lines.append(f"    {c.claim_id}  [{c.mode}]  governed={c.governed_standing.upper()}{raw}  "
                     f"agent={c.agent_id or '(unknown)'}{cf}")
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
        `search` (substring on the subject id)."""
        last_ord: dict[str, int] = {}
        org_of: dict[str, str] = {}
        for i, v in enumerate(self._consult.list()):
            last_ord[v.subject_id] = i
            if v.subject_id not in org_of:
                org_of[v.subject_id] = v.org_id
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
            claims.append(ClaimLine(
                claim_id=c.claim_id, mode=c.mode, raw_standing=c.standing,
                governed_standing=derive_governed_standing(c.standing, c.conflict),
                conflict=c.conflict, agent_id=c.agent_id, carrier=c.carrier))
            ex = self._explain.explain(c.claim_id)
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
