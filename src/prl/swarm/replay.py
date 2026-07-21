"""DSM Swarm — replay & derivation (v0.1), read-only and kernel-free.

Reconstructs one run from already-decoded Swarm records and **derives** — never
stores — every stateful reading: task standing, decision standing, applied
supersession, review polarity, derived conflicts, check coverage. This mirrors
the ``prl.query.standing_read`` discipline: *standing is computed by replaying
acts in authoritative order; conflict is a distinct derived signal that never
changes standing and is never auto-resolved.*

Input contract
--------------
``records`` is a sequence of :data:`~prl.swarm.types.SwarmRecord` objects in
**authoritative order** — the order RR's ``navigate_action`` returns them; the
caller joins record→entry by ``entry_id`` and decodes with
``from_swarm_entry`` before calling here (never trust ``resolve_entries`` or
``Storage.read`` raw order). The projection is **deterministic**: same input
sequence, same output.

The replay observes; it never writes. Derived conflicts and diagnostics are
surfaced in the projection — they are NOT appended back to DSM. No stored field
named ``verified`` / ``accepted`` / ``conflicted`` / ``superseded`` / ``latest``
exists on any record for a reader to trust: those readings only exist here, as
derived overlays. Nothing in this module turns a claim into truth: a
``WorkReceipt`` stays a claim, a ``ReviewReceipt`` stays a declared opinion,
and check coverage measures declarative completeness only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .types import (
    ConflictRecord,
    DecisionReceipt,
    ReviewReceipt,
    SwarmRecord,
    SwarmRun,
    TaskNode,
    WorkReceipt,
)

# Closed supersession compatibility matrix (v0.1): which record kind may
# supersede which. Only decisions carry a ``supersedes`` field today; the
# matrix is enforced (not assumed) so a decision naming a work/review/task id
# as its target is a diagnostic, never a silent latest-wins.
SUPERSESSION_MATRIX: dict[str, frozenset[str]] = {
    "decision": frozenset({"decision"}),
}

# Diagnostic kinds (closed, documented set).
DIAGNOSTIC_KINDS: frozenset[str] = frozenset(
    {
        "cross_run_record",         # record belongs to another run — excluded
        "task_unknown",             # receipt references a task id with no TaskNode
        "review_of_unknown_ref",    # review's reviewed_ref matches nothing known
        "missing_reference",        # supersession target does not exist
        "self_supersession",        # a record declares it supersedes itself
        "supersession_type_mismatch",  # target exists but kind not allowed by matrix
        "supersession_cycle",       # supersession chain loops
        "concurrent_supersession",  # >1 distinct records supersede the same target
        "reviews_divergent",        # approve AND reject on the same reviewed_ref
        "decision_on_superseded",   # decision's bases reference a superseded line
        "required_checks_uncovered",  # required checks not covered by claimed ones
        "conflict_unresolved",      # explicit conflict left open/acknowledged
    }
)

# The subset of diagnostics that the projection also surfaces as DERIVED
# conflicts (observed incompatibilities, distinct from explicit ConflictRecord).
DERIVED_CONFLICT_KINDS: frozenset[str] = frozenset(
    {
        "reviews_divergent",
        "concurrent_supersession",
        "supersession_cycle",
        "decision_on_superseded",
        "required_checks_uncovered",
    }
)


@dataclass(frozen=True)
class Diagnostic:
    """One derived observation (incoherence, gap, or conflict signal).

    ``kind`` is from :data:`DIAGNOSTIC_KINDS`; ``refs`` names the involved
    record ids in deterministic order; ``detail`` is a human-readable note.
    Diagnostics are observations of the log — they never mutate it.
    """

    kind: str
    refs: tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class CheckCoverage:
    """Declarative check coverage for one WorkReceipt, computed by projection.

    Three distinct axes, never merged: ``required`` (what was demanded),
    ``claimed`` (what the author says they ran), and this computed comparison.
    ``ratio`` = |required ∩ claimed| / |required|, ``None`` when nothing was
    required (undefined, NOT 1.0). This measures **declarative completeness
    only** — it is never proof the checks ran, nor that the work happened.
    """

    work_id: str
    required: tuple[str, ...]
    claimed: tuple[str, ...]
    missing: tuple[str, ...]       # required but not claimed
    unrequested: tuple[str, ...]   # claimed but not required
    ratio: float | None


@dataclass(frozen=True)
class DecisionStanding:
    """Derived standing of one decision line (keyed by ``decision_id``).

    ``status`` is the latest-wins **stored** status of the line's own history
    (a re-emitted id extends the line); ``history`` keeps every stored status
    in authoritative order — older versions are never dropped.
    ``superseded_by`` is applied ONLY when the declared supersession chain is
    valid and unambiguous (same run, matrix-compatible, no self/cycle/branch);
    otherwise ``supersession_ambiguous`` is set and the reading is withheld —
    ambiguity is surfaced, never silently resolved.
    """

    decision_id: str
    subject_id: str
    status: str
    history: tuple[str, ...]
    superseded_by: str | None = None
    supersession_ambiguous: bool = False


@dataclass(frozen=True)
class TaskView:
    """Derived view of one task. All facets computed, none stored.

    ``work_state`` ∈ ``no_work_claimed`` | ``work_claimed`` | ``work_reviewed``
    (a claim stays a claim even when reviewed). ``review_signal`` ∈ ``none`` |
    ``positive`` | ``negative`` | ``divergent`` | ``unpolarized`` (reviews
    exist but none carries a polarized verdict). These facets are deliberately
    NOT reduced to a single boolean or verdict.
    """

    task_node_id: str
    status: str
    status_history: tuple[str, ...]
    parent_task_node_id: str | None
    work_ids: tuple[str, ...]
    review_ids: tuple[str, ...]
    decision_ids: tuple[str, ...]
    work_state: str
    review_signal: str
    limitations: tuple[str, ...]


@dataclass
class RunProjection:
    """The full derived view of one swarm run — recomputed, droppable, never a
    second source of truth."""

    swarm_run_id: str
    run: SwarmRun | None = None
    run_status: str | None = None
    tasks: dict[str, TaskView] = field(default_factory=dict)
    works: dict[str, WorkReceipt] = field(default_factory=dict)      # latest by work_id
    reviews: dict[str, ReviewReceipt] = field(default_factory=dict)  # latest by review_id
    decisions: dict[str, DecisionStanding] = field(default_factory=dict)
    explicit_conflicts: dict[str, ConflictRecord] = field(default_factory=dict)
    check_coverage: dict[str, CheckCoverage] = field(default_factory=dict)
    limitations: tuple[tuple[str, str], ...] = ()   # (record_id, limitation), aggregated
    orphan_record_ids: tuple[str, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    derived_conflicts: tuple[Diagnostic, ...] = ()  # subset of diagnostics


def _review_signal(verdicts: Sequence[str | None]) -> str:
    """Fold review verdicts into one derived polarity facet."""
    if not verdicts:
        return "none"
    has_approve = any(v == "approve" for v in verdicts)
    has_reject = any(v == "reject" for v in verdicts)
    if has_approve and has_reject:
        return "divergent"
    if has_approve:
        return "positive"
    if has_reject:
        return "negative"
    return "unpolarized"


def _coverage(work: WorkReceipt) -> CheckCoverage:
    required = list(dict.fromkeys(work.required_checks))   # dedupe, keep order
    claimed = list(dict.fromkeys(work.claimed_checks))
    required_set, claimed_set = set(required), set(claimed)
    missing = tuple(c for c in required if c not in claimed_set)
    unrequested = tuple(c for c in claimed if c not in required_set)
    ratio = (
        (len(required) - len(missing)) / len(required) if required else None
    )
    return CheckCoverage(
        work_id=work.work_id,
        required=tuple(required),
        claimed=tuple(claimed),
        missing=missing,
        unrequested=unrequested,
        ratio=ratio,
    )


def _record_id(record: SwarmRecord) -> str:
    for attr in ("task_node_id", "work_id", "review_id", "decision_id", "conflict_id"):
        value = getattr(record, attr, None)
        if value:
            return value
    return getattr(record, "swarm_run_id", "")


def _derive_decision_standings(
    decisions: Sequence[DecisionReceipt],
    known_kind_by_id: dict[str, str],
    diags: list[Diagnostic],
) -> dict[str, DecisionStanding]:
    """Fold decision lines latest-wins and apply DECLARED supersession only
    where the chain is valid and unambiguous (see :class:`DecisionStanding`)."""
    line_status: dict[str, str] = {}
    line_subject: dict[str, str] = {}
    line_history: dict[str, list[str]] = {}
    # target -> list of superseder decision_ids (declared edges, pre-validation)
    declared_edges: dict[str, list[str]] = {}

    for d in decisions:
        line_status[d.decision_id] = d.status
        line_subject[d.decision_id] = d.subject_id
        line_history.setdefault(d.decision_id, []).append(d.status)
        if d.supersedes is not None:
            if d.supersedes == d.decision_id:
                diags.append(
                    Diagnostic(
                        kind="self_supersession",
                        refs=(d.decision_id,),
                        detail="decision declares it supersedes itself; edge ignored",
                    )
                )
                continue
            target_kind = known_kind_by_id.get(d.supersedes)
            if target_kind is None:
                diags.append(
                    Diagnostic(
                        kind="missing_reference",
                        refs=(d.decision_id, d.supersedes),
                        detail="supersession target not found in this run; edge ignored",
                    )
                )
                continue
            if target_kind not in SUPERSESSION_MATRIX.get(d.kind, frozenset()):
                diags.append(
                    Diagnostic(
                        kind="supersession_type_mismatch",
                        refs=(d.decision_id, d.supersedes),
                        detail=(
                            f"a {d.kind} may not supersede a {target_kind} "
                            f"(closed matrix); edge ignored"
                        ),
                    )
                )
                continue
            if d.supersedes not in declared_edges:
                declared_edges[d.supersedes] = []
            if d.decision_id not in declared_edges[d.supersedes]:
                declared_edges[d.supersedes].append(d.decision_id)

    # Cycle detection over the declared superseder->target graph.
    supersedes_of: dict[str, str] = {}
    for target, supersessors in declared_edges.items():
        for s in supersessors:
            supersedes_of[s] = target
    in_cycle: set[str] = set()
    for start in supersedes_of:
        seen: list[str] = []
        node: str | None = start
        while node is not None and node not in seen:
            seen.append(node)
            node = supersedes_of.get(node)
        if node is not None:  # revisited => cycle from `node`
            cycle = seen[seen.index(node):] + [node]
            members = tuple(sorted(set(cycle)))
            if not set(members) <= in_cycle:
                diags.append(
                    Diagnostic(
                        kind="supersession_cycle",
                        refs=members,
                        detail="supersession chain loops; latest-wins withheld for members",
                    )
                )
            in_cycle.update(members)

    out: dict[str, DecisionStanding] = {}
    for decision_id in line_status:
        supersessors = declared_edges.get(decision_id, [])
        ambiguous = False
        superseded_by: str | None = None
        if len(supersessors) > 1:
            ambiguous = True
            diags.append(
                Diagnostic(
                    kind="concurrent_supersession",
                    refs=(decision_id, *sorted(supersessors)),
                    detail=(
                        "multiple records supersede the same target; "
                        "latest-wins withheld (surfaced, not resolved)"
                    ),
                )
            )
        elif len(supersessors) == 1:
            candidate = supersessors[0]
            if candidate in in_cycle or decision_id in in_cycle:
                ambiguous = True
            else:
                superseded_by = candidate
        out[decision_id] = DecisionStanding(
            decision_id=decision_id,
            subject_id=line_subject[decision_id],
            status=line_status[decision_id],
            history=tuple(line_history[decision_id]),
            superseded_by=superseded_by,
            supersession_ambiguous=ambiguous,
        )
    return out


def project_run(
    records: Sequence[SwarmRecord], *, swarm_run_id: str | None = None
) -> RunProjection:
    """Deterministic latest-wins projection of ONE run from its records.

    ``records`` must already be in authoritative order (see module docstring).
    ``swarm_run_id`` pins the run; when omitted it is inferred from the latest
    ``SwarmRun`` record (or the first record carrying a run id). Records from
    any other run are excluded and surfaced as ``cross_run_record`` diagnostics.
    """
    diags: list[Diagnostic] = []

    run_records = [r for r in records if isinstance(r, SwarmRun)]
    inferred = (
        run_records[-1].swarm_run_id
        if run_records
        else next(
            (getattr(r, "swarm_run_id", "") for r in records if getattr(r, "swarm_run_id", "")),
            "",
        )
    )
    run_id = swarm_run_id or inferred

    in_run: list[SwarmRecord] = []
    for r in records:
        rid = getattr(r, "swarm_run_id", None)
        if rid != run_id:
            diags.append(
                Diagnostic(
                    kind="cross_run_record",
                    refs=(_record_id(r), str(rid)),
                    detail=f"record belongs to run {rid!r}, not {run_id!r}; excluded",
                )
            )
            continue
        in_run.append(r)

    proj = RunProjection(swarm_run_id=run_id)
    run_in = [r for r in in_run if isinstance(r, SwarmRun)]
    proj.run = run_in[-1] if run_in else None
    proj.run_status = proj.run.status if proj.run else None

    # -- latest-wins folds (histories preserved) ------------------------------
    task_status: dict[str, list[str]] = {}
    task_nodes: dict[str, TaskNode] = {}
    for r in in_run:
        if isinstance(r, TaskNode):
            task_status.setdefault(r.task_node_id, []).append(r.status)
            task_nodes[r.task_node_id] = r
    for r in in_run:
        if isinstance(r, WorkReceipt):
            proj.works[r.work_id] = r
        elif isinstance(r, ReviewReceipt):
            proj.reviews[r.review_id] = r
        elif isinstance(r, ConflictRecord):
            proj.explicit_conflicts[r.conflict_id] = r

    # Global id->kind map for reference validation (matrix, review targets).
    known_kind_by_id: dict[str, str] = {run_id: "run"}
    for tid in task_nodes:
        known_kind_by_id[tid] = "task"
    for wid in proj.works:
        known_kind_by_id[wid] = "work"
    for rid_ in proj.reviews:
        known_kind_by_id[rid_] = "review"
    for r in in_run:
        if isinstance(r, DecisionReceipt):
            known_kind_by_id[r.decision_id] = "decision"
    for cid in proj.explicit_conflicts:
        known_kind_by_id[cid] = "conflict"

    # -- decisions + supersession ---------------------------------------------
    decision_records = [r for r in in_run if isinstance(r, DecisionReceipt)]
    proj.decisions = _derive_decision_standings(decision_records, known_kind_by_id, diags)

    # -- reviews: attachment + divergence -------------------------------------
    reviews_by_ref: dict[str, list[ReviewReceipt]] = {}
    for review in proj.reviews.values():
        if review.reviewed_ref not in known_kind_by_id:
            diags.append(
                Diagnostic(
                    kind="review_of_unknown_ref",
                    refs=(review.review_id, review.reviewed_ref),
                    detail="reviewed_ref matches no known record in this run",
                )
            )
        reviews_by_ref.setdefault(review.reviewed_ref, []).append(review)
    for ref in sorted(reviews_by_ref):
        sig = _review_signal([rv.verdict for rv in reviews_by_ref[ref]])
        if sig == "divergent":
            diags.append(
                Diagnostic(
                    kind="reviews_divergent",
                    refs=(ref, *sorted(rv.review_id for rv in reviews_by_ref[ref])),
                    detail="approve and reject coexist on the same reviewed_ref",
                )
            )

    # -- check coverage (computed, never author-supplied) ----------------------
    for wid in proj.works:
        cov = _coverage(proj.works[wid])
        proj.check_coverage[wid] = cov
        if cov.missing:
            diags.append(
                Diagnostic(
                    kind="required_checks_uncovered",
                    refs=(wid, *cov.missing),
                    detail=(
                        "work claims completion while required checks are not "
                        "covered by claimed checks"
                    ),
                )
            )

    # -- decisions based on superseded lines ----------------------------------
    superseded_ids = {
        d.decision_id for d in proj.decisions.values() if d.superseded_by is not None
    }
    for d in decision_records:
        bases = [b for b in (d.parent_decision_id, *d.evidence_refs) if b]
        stale = sorted(b for b in bases if b in superseded_ids and b != d.supersedes)
        if stale:
            diags.append(
                Diagnostic(
                    kind="decision_on_superseded",
                    refs=(d.decision_id, *stale),
                    detail="decision's declared bases reference a superseded line",
                )
            )

    # -- explicit conflicts left open ------------------------------------------
    for cid in sorted(proj.explicit_conflicts):
        conflict = proj.explicit_conflicts[cid]
        if conflict.state != "resolved":
            diags.append(
                Diagnostic(
                    kind="conflict_unresolved",
                    refs=(cid, *conflict.competing_refs),
                    detail=f"explicit conflict is {conflict.state!r} (observation only)",
                )
            )

    # -- orphan receipts (unknown task) + task views ---------------------------
    orphans: list[str] = []

    def _task_of(ref_task: str | None, record_id: str) -> str | None:
        if ref_task is None:
            return None
        if ref_task not in task_nodes:
            diags.append(
                Diagnostic(
                    kind="task_unknown",
                    refs=(record_id, ref_task),
                    detail="record references a task with no TaskNode in this run",
                )
            )
            orphans.append(record_id)
            return None
        return ref_task

    works_by_task: dict[str, list[str]] = {}
    for wid in proj.works:
        t = _task_of(proj.works[wid].task_node_id, wid)
        if t is not None:
            works_by_task.setdefault(t, []).append(wid)
    decisions_by_task: dict[str, list[str]] = {}
    for d in decision_records:
        t = _task_of(d.task_node_id, d.decision_id)
        if t is not None and d.decision_id not in decisions_by_task.setdefault(t, []):
            decisions_by_task[t].append(d.decision_id)

    reviews_by_task: dict[str, list[str]] = {}
    for review in proj.reviews.values():
        ref_kind = known_kind_by_id.get(review.reviewed_ref)
        target_task: str | None = None
        if ref_kind == "task":
            target_task = review.reviewed_ref
        elif ref_kind == "work":
            target_task = proj.works[review.reviewed_ref].task_node_id
            if target_task is not None and target_task not in task_nodes:
                target_task = None
        if target_task is not None:
            reviews_by_task.setdefault(target_task, []).append(review.review_id)

    limitations: list[tuple[str, str]] = []
    for tid in task_status:
        node = task_nodes[tid]
        wids = tuple(works_by_task.get(tid, []))
        rids = tuple(reviews_by_task.get(tid, []))
        task_limits: list[str] = []
        verdicts: list[str | None] = []
        for wid in wids:
            task_limits.extend(proj.works[wid].limitations)
        for rid_ in rids:
            task_limits.extend(proj.reviews[rid_].limitations)
            verdicts.append(proj.reviews[rid_].verdict)
        if not wids:
            work_state = "no_work_claimed"
        elif rids:
            work_state = "work_reviewed"
        else:
            work_state = "work_claimed"
        proj.tasks[tid] = TaskView(
            task_node_id=tid,
            status=task_status[tid][-1],
            status_history=tuple(task_status[tid]),
            parent_task_node_id=node.parent_task_node_id,
            work_ids=wids,
            review_ids=rids,
            decision_ids=tuple(decisions_by_task.get(tid, [])),
            work_state=work_state,
            review_signal=_review_signal(verdicts),
            limitations=tuple(task_limits),
        )

    # -- run-level aggregated limitations (kept, never dropped) ----------------
    for wid in proj.works:
        for text in proj.works[wid].limitations:
            limitations.append((wid, text))
    for rid_ in proj.reviews:
        for text in proj.reviews[rid_].limitations:
            limitations.append((rid_, text))
    proj.limitations = tuple(limitations)
    proj.orphan_record_ids = tuple(dict.fromkeys(orphans))
    proj.diagnostics = tuple(diags)
    proj.derived_conflicts = tuple(
        d for d in diags if d.kind in DERIVED_CONFLICT_KINDS
    )
    return proj
