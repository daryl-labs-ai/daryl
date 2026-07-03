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

import re
from dataclasses import dataclass
from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from ..types import ConsultationNode, from_entry
from .consultation_read import ConsultationQuery
from .explain_read import ExplainQuery
from .governance_read import GovernanceQuery
from .links import LinkAnnotator
from .standing_read import RegistryProjection, StandingIndex, derive_governed_standing
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
    reason: str = ""       # the v2 one-line human story (object_reason) — context, derived
    last_kind: str = ""    # the object's latest act mode (observation | proposal) — "last activity"
    last_agent: str = ""   # the agent behind that latest act — "last activity"
    match_fields: tuple[str, ...] = ()  # which fields matched --search (provenance); () = no search
    match_snippet: str = ""             # a short snippet of the first match (why it matched)


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
class RelatedDecision:
    """One **derived mention** edge (Decision Lineage v1, Level 1) — **textual evidence, NEVER causality**.
    A mention is deterministic token presence, nothing inferred: `direction` distinguishes *mentions*
    (this object's act names B) from *mentioned by* (B's act names this object); `evidence_class` is
    `subject-token` (B's `subject_id` verbatim or its derived name-form) or `shared-marker` (a rare
    `PR #NNN` shared by both). Every edge carries the matched `token`, a verbatim `snippet`, the act's
    `receipt`, and lands via `[go object B]`. It is not a declared relation (that is Level 2, unbuilt)."""

    subject_id: str        # B — the related decision
    direction: str         # "mentions" (this → B) | "mentioned by" (B → this) | "shares marker"
    evidence_class: str    # "subject-token" | "shared-marker"
    token: str             # the matched token: B's id / name-form, or "PR #NNN"
    snippet: str           # verbatim snippet of the act's answer carrying the mention
    receipt: str           # receipt of the act carrying the mention


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
    org_id: str = ""                     # owning org (first consultation's org) — object→org hop
                                         # (Linked Projections v1); a view field, back-compat default
    related: tuple[RelatedDecision, ...] = ()   # derived MENTION edges (Decision Lineage v1, Level 1) —
                                         # textual evidence, not causality; back-compat default


_VERSION_TOKEN = re.compile(r"^v\d+$")
_PR_MARKER = re.compile(r"PR #\d+")


def _name_form(subject_id: str) -> str:
    """The **derived name-form** of a subject id (documented, deterministic — Decision Lineage v1): strip
    the ``daryl.`` prefix, split on dots/hyphens, drop version tokens (``v1``, ``v2``, …), join with
    spaces, lowercased. Purely from the id itself — no fuzzy matching, no synonyms, no inference.
    e.g. ``daryl.receipt-hop.v1`` → ``"receipt hop"``."""
    body = subject_id[len("daryl."):] if subject_id.startswith("daryl.") else subject_id
    parts = [p for p in re.split(r"[.\-]", body) if p and not _VERSION_TOKEN.match(p)]
    return " ".join(parts).lower()


def _markers(text: str) -> set[str]:
    """The rare shared markers in an act — ``PR #NNN`` only (the S02 shared-marker case). Narrow and
    pattern-bound; anything looser would be inference (forbidden)."""
    return set(_PR_MARKER.findall(text))


def _snippet(value: str, q_lower: str, width: int = 48) -> str:
    """A short context window around the first match of ``q_lower`` in ``value`` (why it matched)."""
    if len(value) <= width:
        return value
    i = value.lower().find(q_lower)
    if i < 0:
        return value[:width] + "…"
    start = max(0, i - 12)
    end = min(len(value), i + len(q_lower) + 24)
    return ("…" if start > 0 else "") + value[start:end] + ("…" if end < len(value) else "")


def _match_search(query: str, doc: dict[str, list[str]]) -> tuple[tuple[str, ...], str]:
    """Match ``query`` (case-insensitive substring) against a per-object search document. Returns the
    **fields that matched** (provenance) and a short **snippet** of the first match. Pure; no ranking."""
    ql = query.lower()
    matched: list[str] = []
    snippet = ""
    for field, values in doc.items():
        for v in values:
            if v and ql in v.lower():
                if field not in matched:
                    matched.append(field)
                if not snippet:
                    snippet = f'{field}: "{_snippet(v, ql)}"'
                break
    return tuple(matched), snippet


def render_objects(summaries: list[KnowledgeObjectSummary]) -> str:
    """Pure display — the Discovery listing (recency-first). When a `--search` matched, each row shows
    its **provenance** (which fields matched + a snippet); rows also carry a `reason` + `last activity`."""
    if not summaries:
        return "no knowledge objects"
    ann = LinkAnnotator()   # v1.2 (F1): each row's subject gets its [go object …] jump — the entry edge
    lines = [f"{len(summaries)} knowledge object(s):"]
    for s in summaries:
        flag = "  ⚠ conflict" if s.has_conflict else ""
        org = f"  org={s.org_id}" if s.org_id else ""
        lines.append(f"  {s.subject_id}   object={s.object_standing.upper()}   "
                     f"coherence={s.coherence}   gov={s.governance.upper()}   "
                     f"claims={s.n_claims}{org}{flag}{ann.tag('object', s.subject_id)}")
        ctx = s.reason or ""
        if s.last_kind:
            ctx += f"{' · ' if ctx else ''}last: {s.last_kind} by {s.last_agent or 'unknown'}"
        if ctx:
            lines.append(f"      {ctx}")
        if s.match_fields:
            lines.append(f"      match [{', '.join(s.match_fields)}]  {s.match_snippet}")
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
    ann = LinkAnnotator()   # per-page typed-link annotator (first occurrence of each id, the noise rule)
    lines = [f"Knowledge Object — {proj.subject_id}",
             f"  status:  {proj.object_standing.upper()}",
             f"  reason:  {object_reason(proj.object_standing, proj.coherence, any(c.conflict for c in claims))}",
             f"  signals: coherence={proj.coherence} · governance={proj.governance}"]
    if proj.org_id:   # object → org hop (Linked Projections v1)
        lines.append(f"  org:     {proj.org_id}{ann.tag('org', proj.org_id)}")
    lines += ["", "  current decision:"]
    # --- Current decision (never a fabricated winner) ---
    if proj.object_standing == "contested":
        lines.append("    contested — no single governing decision (see alternatives)")
    elif accepted:
        for c in accepted:
            lines.append(f"    ✓ {c.answer or f'({c.claim_id})'}   ({c.claim_id} · {c.agent_id or 'unknown'})"
                         f"{ann.tag('claim', c.claim_id)}{ann.tag('agent', c.agent_id)}")
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
        lines.append(_claim_line(c) + ann.tag("claim", c.claim_id) + ann.tag("agent", c.agent_id))
    # --- Discussion (observation-mode acts only) ---
    lines += ["", "  discussion:"]
    if not proj.discussion:
        lines.append("    (none)")
    for d in proj.discussion:
        body = d.answer or f"({d.claim_id})"
        lines.append(f"    “{body}”   ({d.agent_id or 'unknown'} · receipt {d.receipt})"
                     f"{ann.tag('agent', d.agent_id)}")
    # --- History (decision-thread record order) ---
    lines += ["", "  history:  (ordered by consultation record; resolutions grouped under their proposal)"]
    if not proj.timeline:
        lines.append("    (none)")
    for t in proj.timeline:
        lines.append(f"    {t.kind:<12}{t.label:<11}claim={t.claim_id}  "
                     f"agent={t.agent_id or 'unknown'}  receipt {t.receipt}"
                     f"{ann.tag('claim', t.claim_id)}{ann.tag('agent', t.agent_id)}")
    # --- Receipts (distinct certified receipts of the object's acts) ---
    seen: set[str] = set()
    receipts = [t.receipt for t in proj.timeline if t.receipt and not (t.receipt in seen or seen.add(t.receipt))]
    lines += ["", "  receipts:"]
    if not receipts:
        lines.append("    (none)")
    for r in receipts:
        lines.append(f"    {r}{ann.tag('receipt', r)}")   # receipt → certified act (Receipt Hop v1)
    # --- Related decisions (Decision Lineage v1, Level 1 — MENTIONS: textual evidence, NOT causality) ---
    lines += ["", "  related decisions:  (mentions — textual evidence, NOT causality)"]
    if not proj.related:
        lines.append("    (none)")
    for rel in proj.related:
        lines.append(f"    {rel.subject_id}   {rel.direction} [{rel.evidence_class} \"{rel.token}\"]: "
                     f"“{rel.snippet}”   receipt {rel.receipt}{ann.tag('object', rel.subject_id)}")
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
        # one-pass grouping of resolutions by claim — gives resolver agents + decisions for --search
        self._standing = StandingIndex(storage, index_dir, _navigator=_navigator)

    def discover_objects(
        self, *, org_id: str | None = None, contested: bool = False,
        conflicts: bool = False, search: str | None = None,
    ) -> list[KnowledgeObjectSummary]:
        """Enumerate the Knowledge Objects (distinct `subject_id`) with their headline state, recency
        first. Derived + droppable: a scan of `prl.consultation` → distinct subjects, each summarized by
        the proven queries. Filters: owning `org`, `contested` object standing, `conflicts` present,
        `search` (substring over the object's certified content + metadata — see below).

        Recency is the **authoritative record order** — from ``navigate_action`` (ascending, stable),
        **never** from ``resolve_entries`` (which does not preserve order; v1.0 read recency from the
        resolved order and mis-sorted). Replay records in order and join record→entry by id — the same
        rule as ``standing_read._resolutions_for``.

        ``search`` (v1, Knowledge Map) matches **any** already-certified field — `subject_id`, raw
        `answer`s, `agent_id` (contributors *and* resolvers), `org_id`, `claim_id`, decision/standing,
        abbreviated receipts — as a case-insensitive substring. It is a **derived in-memory scan** over the
        acts already gathered (no persistent index, no new entity); each match records its **provenance**
        (which fields matched + a snippet)."""
        records = self._nav.navigate_action("prl.consultation")
        entries = self._nav.resolve_entries(records)
        by_id = {getattr(e, "id", None): e for e in entries}
        last_ord: dict[str, int] = {}
        org_of: dict[str, str] = {}
        last_kind: dict[str, str] = {}
        last_agent: dict[str, str] = {}
        answers_of: dict[str, list[str]] = {}
        agents_of: dict[str, set[str]] = {}
        claims_of: dict[str, list[str]] = {}
        receipts_of: dict[str, list[str]] = {}
        for i, rec in enumerate(records):
            eid = rec.get("entry_id") if isinstance(rec, dict) else getattr(rec, "entry_id", None)
            entry = by_id.get(eid)
            if entry is None:
                continue
            node = from_entry(entry)
            if not isinstance(node, ConsultationNode):
                continue
            subj = node.subject_id
            last_ord[subj] = i                     # authoritative record order = recency
            last_kind[subj] = node.mode            # latest act wins (ascending walk) = "last activity"
            last_agent[subj] = node.mef.agent_id or ""
            org_of.setdefault(subj, node.org_id or "")
            answers_of.setdefault(subj, []).append(node.answer or "")
            agents_of.setdefault(subj, set()).add(node.mef.agent_id or "")
            claims_of.setdefault(subj, []).append(node.mef.claim_id)
            receipts_of.setdefault(subj, []).append(str(getattr(entry, "hash", "") or ""))
        out: list[KnowledgeObjectSummary] = []
        for subj, ord_ in last_ord.items():
            sv = self._subject.standings_of_subject(subj)
            mfields: tuple[str, ...] = ()
            msnip = ""
            if search:
                doc = self._search_doc(
                    subj, sv, answers_of.get(subj, []), agents_of.get(subj, set()),
                    claims_of.get(subj, []), receipts_of.get(subj, []), org_of.get(subj, ""))
                mfields, msnip = _match_search(search, doc)
                if not mfields:
                    continue                        # no field matched → not a result
            out.append(KnowledgeObjectSummary(
                subject_id=subj,
                object_standing=sv.object_standing,
                coherence=sv.coherence,
                governance=self._gov.governance_of_subject(subj).governance,
                n_claims=len(sv.claims),
                has_conflict=any(c.conflict for c in sv.claims),
                org_id=org_of.get(subj, ""),
                last_ord=ord_,
                reason=object_reason(sv.object_standing, sv.coherence, any(c.conflict for c in sv.claims)),
                last_kind=last_kind.get(subj, ""),
                last_agent=last_agent.get(subj, ""),
                match_fields=mfields,
                match_snippet=msnip,
            ))
        if org_id is not None:
            out = [s for s in out if s.org_id == org_id]
        if contested:
            out = [s for s in out if s.object_standing == "contested"]
        if conflicts:
            out = [s for s in out if s.has_conflict]
        out.sort(key=lambda s: s.last_ord, reverse=True)   # recency-first
        return out

    def _search_doc(
        self, subj: str, sv: Any, answers: list[str], agents: set[str],
        claims: list[str], receipts: list[str], org: str,
    ) -> dict[str, list[str]]:
        """The per-object **search document** — the already-certified fields a query can match, grouped
        by field for provenance. Composed from acts already gathered (consultations) + the one-pass
        resolution grouping (`StandingIndex`): resolver agents + decisions. No new read of the store."""
        decisions: list[str] = []
        resolver_agents: list[str] = []
        for c in sv.claims:
            decisions.append(c.standing)
            decisions.append(derive_governed_standing(c.standing, c.conflict))
            for rf in self._standing.resolutions_of(c.claim_id):
                decisions.append(rf.decision)
                if rf.agent_id:
                    resolver_agents.append(rf.agent_id)
        return {
            "subject": [subj],
            "answer": [a for a in answers if a],
            "agent": sorted({a for a in agents if a} | set(resolver_agents)),
            "org": [org] if org else [],
            "claim": list(claims),
            "decision": decisions,
            "receipt": [r[:12] for r in receipts if r],
        }

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
        owning_org = ""
        owner_set = False   # owning org = the FIRST consultation's org (same rule as discovery's setdefault)
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
            if not owner_set:
                owning_org = node.org_id or ""
                owner_set = True
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
            timeline=tuple(timeline), org_id=owning_org, related=self._related(subject_id))

    def _related(self, subject_id: str) -> tuple[RelatedDecision, ...]:
        """Decision Lineage v1, **Level 1** — a derived, per-call, in-memory **mention adjacency** over the
        consultation acts already gathered. Subject A *mentions* B when an act on A contains B's
        **subject-token** (B's ``subject_id`` verbatim or its derived name-form) or **shares a rare
        ``PR #NNN`` marker** with an act on B. **Textual evidence, never causality**; nothing stored,
        nothing inferred beyond token presence (no fuzzy match, no synonyms — the level's invariant).
        This is NOT a declared relation (Level 2, unbuilt): a mention is never rendered as an authored edge."""
        records = self._nav.navigate_action("prl.consultation")
        by_id = {getattr(e, "id", None): e for e in self._nav.resolve_entries(records)}
        acts: dict[str, list[tuple[str, str]]] = {}   # subject → [(answer, receipt)]
        for rec in records:
            eid = rec.get("entry_id") if isinstance(rec, dict) else getattr(rec, "entry_id", None)
            entry = by_id.get(eid)
            if entry is None:
                continue
            node = from_entry(entry)
            if not isinstance(node, ConsultationNode):
                continue
            acts.setdefault(node.subject_id, []).append(
                (node.answer or "", str(getattr(entry, "hash", "") or "")))

        subjects = list(acts)
        nf = {s: _name_form(s) for s in subjects}
        mine = acts.get(subject_id, [])
        my_nf = nf.get(subject_id, "")
        seen: set[tuple[str, str, str]] = set()
        out: list[RelatedDecision] = []

        def add(b: str, direction: str, klass: str, token: str, answer: str, receipt: str) -> None:
            key = (b, direction, token)
            if b == subject_id or not token or key in seen:
                return
            seen.add(key)
            out.append(RelatedDecision(subject_id=b, direction=direction, evidence_class=klass,
                                       token=token, snippet=_snippet(answer, token.lower()), receipt=receipt))

        # (a) subject-token — this object's acts NAME B (outgoing: "mentions")
        for answer, receipt in mine:
            low = answer.lower()
            for b in subjects:
                if b == subject_id:
                    continue
                if b in answer:
                    add(b, "mentions", "subject-token", b, answer, receipt)
                elif nf[b] and nf[b] in low:
                    add(b, "mentions", "subject-token", nf[b], answer, receipt)
        # (b) subject-token — B's acts NAME this object (incoming: "mentioned by")
        for b in subjects:
            if b == subject_id:
                continue
            for answer, receipt in acts[b]:
                if subject_id in answer:
                    add(b, "mentioned by", "subject-token", subject_id, answer, receipt)
                elif my_nf and my_nf in answer.lower():
                    add(b, "mentioned by", "subject-token", my_nf, answer, receipt)
        # (c) shared-marker — both carry the same rare `PR #NNN` (symmetric)
        my_markers: set[str] = set()
        for answer, _ in mine:
            my_markers |= _markers(answer)
        if my_markers:
            for b in subjects:
                if b == subject_id:
                    continue
                for answer, receipt in acts[b]:
                    for m in sorted(my_markers & _markers(answer)):
                        add(b, "shares marker", "shared-marker", m, answer, receipt)
        out.sort(key=lambda r: (r.subject_id, r.direction, r.token))
        return tuple(out)
