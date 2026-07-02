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
class DiscussionItem:
    """One **observation**-mode act — a non-governing note *around* the subject (Discussion, v2).
    It is a consultation, never a proposal; it carries raw content and a receipt, governs nothing."""

    claim_id: str
    answer: str
    agent_id: str
    carrier: str
    receipt: str


@dataclass(frozen=True)
class TimelineItem:
    """One certified act on the object's History — observation | proposal | resolution, receipt-backed."""

    claim_id: str
    kind: str      # "observation" | "proposal" | "resolution"
    label: str     # the mode or the decision
    agent_id: str
    carrier: str
    receipt: str


@dataclass(frozen=True)
class KnowledgeObjectProjection:
    """The consolidated Object View (v2) — a **derived projection** keyed by `subject_id`, never
    stored, no `object_id`. A **decision space to navigate**, not a compiled document: it partitions
    the object's acts into **proposal claims** (the decision + its alternatives), **observations**
    (the discussion), and a record-ordered **history** — composing only proven queries + the `mode` /
    `governed_standing` fields already on each act. It **invents nothing**."""

    subject_id: str
    object_standing: str
    coherence: str
    governance: str
    claims: tuple[ClaimLine, ...]        # PROPOSAL-mode claims (Current decision + Alternatives)
    discussion: tuple[DiscussionItem, ...]  # OBSERVATION-mode acts (the discussion)
    timeline: tuple[TimelineItem, ...]   # all acts, decision-thread record order (History)


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


_MARK = {"accepted": "✓", "rejected": "✗", "proposed": "·", "contested": "⚠"}


def _claim_line(c: ClaimLine) -> str:
    """One proposal-claim line — raw content first (O-001: read the actual text), governed state + author."""
    mark = _MARK.get(c.governed_standing, "·")
    body = c.answer or f"({c.claim_id})"
    return f"    {mark} {body}   ({c.governed_standing} · {c.claim_id} · {c.agent_id or 'unknown'})"


def render_knowledge_object(proj: KnowledgeObjectProjection) -> str:
    """Pure display — the Object View **v2**, a *decision space to navigate* (O-001), in five sections:
    **Current decision · Alternatives · Discussion · History · Receipts**. It partitions the object's
    acts (proposal-claims vs observations) and shows raw content; it **compiles nothing** (no #4b-C).
    A contested object shows *"no single governing decision"* — v2 never fabricates a winner."""
    claims = proj.claims
    accepted = [c for c in claims if c.governed_standing == "accepted"]
    lines = [f"Knowledge Object — {proj.subject_id}",
             f"  status:  {proj.object_standing.upper()}",
             f"  reason:  {object_reason(proj.object_standing, proj.coherence, any(c.conflict for c in claims))}",
             f"  signals: coherence={proj.coherence} · governance={proj.governance}",
             "",
             "  current decision:"]
    # --- Current decision (never a fabricated winner) ---
    if proj.object_standing == "contested":
        lines.append("    contested — no single governing decision (see alternatives)")
    elif accepted:
        for c in accepted:
            lines.append(f"    ✓ {c.answer or f'({c.claim_id})'}   ({c.claim_id} · {c.agent_id or 'unknown'})")
    elif proj.object_standing == "rejected":
        for c in (c for c in claims if c.governed_standing == "rejected"):
            lines.append(f"    ✗ rejected — {c.answer or f'({c.claim_id})'}   ({c.claim_id})")
    else:  # proposed / unsettled
        lines.append("    no decision yet")
    # --- Alternatives (the other options) ---
    if proj.object_standing == "contested":
        alternatives = list(claims)                                    # all competing options
    elif accepted:
        alternatives = [c for c in claims if c.governed_standing != "accepted"]
    elif proj.object_standing == "rejected":
        alternatives = [c for c in claims if c.governed_standing != "rejected"]
    else:
        alternatives = list(claims)
    lines += ["", "  alternatives:"]
    if not alternatives:
        lines.append("    (none)")
    for c in alternatives:
        lines.append(_claim_line(c))
    # --- Discussion (observation-mode acts only) ---
    lines += ["", "  discussion:"]
    if not proj.discussion:
        lines.append("    (none)")
    for d in proj.discussion:
        body = d.answer or f"({d.claim_id})"
        lines.append(f"    “{body}”   ({d.agent_id or 'unknown'} · receipt {d.receipt})")
    # --- History (decision-thread record order) ---
    lines += ["", "  history:  (ordered by consultation record; resolutions grouped under their proposal)"]
    if not proj.timeline:
        lines.append("    (none)")
    for t in proj.timeline:
        lines.append(f"    {t.kind:<12}{t.label:<11}claim={t.claim_id}  "
                     f"agent={t.agent_id or 'unknown'}  receipt {t.receipt}")
    # --- Receipts (distinct certified receipts of the object's acts) ---
    seen: set[str] = set()
    receipts = [t.receipt for t in proj.timeline if t.receipt and not (t.receipt in seen or seen.add(t.receipt))]
    lines += ["", "  receipts:"]
    if not receipts:
        lines.append("    (none)")
    for r in receipts:
        lines.append(f"    {r}")
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
        """The Object View v2 — a **decision space to navigate**, composed from proven queries. It
        **partitions** the object's acts by `mode`: proposal-claims (the Current decision + Alternatives)
        vs observations (Discussion), plus a **decision-thread** History. Nothing is recomputed."""
        sv = self._subject.standings_of_subject(subject_id)
        governance = self._gov.governance_of_subject(subject_id).governance
        # answers + receipts per claim (observations AND proposals) from the subject's consultations.
        consults = self._consult.list(subject_id=subject_id)
        answer_of = {v.claim_id: v.answer for v in consults}
        receipt_of = {v.claim_id: v.receipt for v in consults}

        # Partition the gathered claims by mode: proposals → the decision space; observations → discussion.
        claims: list[ClaimLine] = []
        discussion: list[DiscussionItem] = []
        for c in sv.claims:
            if c.mode == "observation":
                discussion.append(DiscussionItem(
                    claim_id=c.claim_id, answer=answer_of.get(c.claim_id, ""),
                    agent_id=c.agent_id, carrier=c.carrier, receipt=receipt_of.get(c.claim_id, "")))
            else:
                claims.append(ClaimLine(
                    claim_id=c.claim_id, mode=c.mode, raw_standing=c.standing,
                    governed_standing=derive_governed_standing(c.standing, c.conflict),
                    conflict=c.conflict, answer=answer_of.get(c.claim_id, ""),
                    agent_id=c.agent_id, carrier=c.carrier))

        # History — decision-thread record order: walk consultation acts in AUTHORITATIVE record order
        # (navigate_action, never resolve_entries); each proposal is followed by its resolutions; each
        # observation appears at its record position. (No global cross-stream ordinal exists to interleave
        # resolutions by absolute time — this is the derived, readable approximation.)
        timeline: list[TimelineItem] = []
        records = self._nav.navigate_action("prl.consultation")
        by_id = {getattr(e, "id", None): e for e in self._nav.resolve_entries(records)}
        for rec in records:
            eid = rec.get("entry_id") if isinstance(rec, dict) else getattr(rec, "entry_id", None)
            entry = by_id.get(eid)
            if entry is None:
                continue
            node = from_entry(entry)
            if not isinstance(node, ConsultationNode) or node.subject_id != subject_id:
                continue
            cid = node.mef.claim_id
            timeline.append(TimelineItem(
                claim_id=cid, kind=node.mode, label=node.mode,
                agent_id=node.mef.agent_id or "",
                carrier=node.mef.carrier.short() if node.mef.carrier is not None else "",
                receipt=str(getattr(entry, "hash", "") or "")))
            if node.mode == "proposal":
                for r in self._explain.explain(cid).resolutions:
                    timeline.append(TimelineItem(
                        claim_id=cid, kind="resolution", label=r.decision,
                        agent_id=r.agent_id, carrier=r.carrier, receipt=r.receipt))
        return KnowledgeObjectProjection(
            subject_id=subject_id, object_standing=sv.object_standing, coherence=sv.coherence,
            governance=governance, claims=tuple(claims), discussion=tuple(discussion),
            timeline=tuple(timeline))
