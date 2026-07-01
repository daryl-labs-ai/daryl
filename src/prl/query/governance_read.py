"""Governance layer — a read-only posture **above** latest-wins (step (c) v0 probe).

Frontier #2 (per-claim conflict) and #4b (inter-claim divergence) are **proven at the
visibility level**: the disagreement is surfaced, never governed. Step (c) is the convergent
governance question — *when must a divergence govern?* — and its grounding verdict was **ABSENT**
(latest-wins is the sole rule; `MEF.contested` is an inert hook; no authority; supersession never
required).

This module is the **first, read-only probe** of frame (iv): keep latest-wins as the *projection*
rule, and add a **governance layer above** it that **derives a governance state** —
`clear | contested | divergent` — **consolidating** the proven #2/#4b signals. It is the *seam* a
future governing rule will plug into.

What it does — and deliberately does NOT do:
- It **derives** a governance posture (rule **G-1**), **read-only**, from the already-derived signals.
- It does **NOT** change the standing (latest-wins is untouched — the state is a **separate**
  descriptor, never an `accepted`/`rejected` value).
- It does **NOT** block, escalate, or validate any write — there is **no write path** here.
- It does **NOT** consume `MEF.contested` (the inert hook stays inert); it derives from #2 `conflict`
  and #4b `coherence` only.
- It is **derived every call, never stored**; drop it and the state recomputes from the acts.

Governing (what `contested`/`divergent` should *do* — contested standing / authority / required
supersession) is the **next** step, and that is where the first governance ADR lands. Not here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from .standing_read import RegistryProjection, StandingQuery
from .subject_read import SubjectStandingsQuery


def derive_governance_state(conflict: bool) -> str:
    """Governance posture of **one claim** (rule G-1): ``contested`` iff the claim is in a #2
    conflict (two live authorities opposed), else ``clear``. A claim is never ``divergent`` —
    divergence is *across* claims. Pure; derived from the #2 signal; never a standing."""
    return "contested" if conflict else "clear"


def derive_subject_governance_state(coherence: str, claim_conflicts: Sequence[bool]) -> str:
    """Governance posture of **one subject** (rule G-1, collapsed precedence
    ``divergent > contested > clear``):
    - ``divergent`` iff #4b ``coherence == "divergent"`` (the subject's governed claims disagree);
    - else ``contested`` iff **any** of its claims is itself #2-contested;
    - else ``clear``.
    Pure; derived from the #4b + #2 signals; never a subject standing."""
    if coherence == "divergent":
        return "divergent"
    if any(claim_conflicts):
        return "contested"
    return "clear"


@dataclass(frozen=True)
class ClaimGovernance:
    """The read-only governance posture of one claim, beside its (unchanged) standing."""

    claim_id: str
    governance: str   # "clear" | "contested" — derived, NOT a standing
    standing: str     # the latest-wins standing, carried for context (unchanged)


@dataclass(frozen=True)
class SubjectGovernance:
    """The read-only governance posture of one subject, beside its #4b coherence."""

    subject_id: str
    governance: str                    # "clear" | "contested" | "divergent" — derived, NOT a standing
    coherence: str                     # the #4b coherence descriptor, carried for context
    contested_claims: tuple[str, ...]  # the subject's claims that are themselves #2-contested


def render_claim_governance(g: ClaimGovernance) -> str:
    """Pure display. Governance posture beside the unchanged latest-wins standing."""
    return (f"claim {g.claim_id}: governance {g.governance.upper()}  "
            f"(standing {g.standing.upper()}, latest-wins — unchanged)")


def render_subject_governance(g: SubjectGovernance) -> str:
    """Pure display. Governance posture beside the #4b coherence; the subject has no standing."""
    extra = f"; contested claims: {', '.join(g.contested_claims)}" if g.contested_claims else ""
    return (f"subject {g.subject_id}: governance {g.governance.upper()}  "
            f"(coherence {g.coherence}{extra})")


class GovernanceQuery:
    """The governance layer (read-only). Composes ``StandingQuery`` (#2 conflict) and
    ``SubjectStandingsQuery`` (#4b coherence) over one shared projection, and **derives** the
    governance state above latest-wins. It holds **no write path**; it changes nothing."""

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RegistryProjection | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()
            _navigator = RRNavigator(builder, storage)
        self._standing = StandingQuery(storage, index_dir, _navigator=_navigator)
        self._subject = SubjectStandingsQuery(storage, index_dir, _navigator=_navigator)

    def governance_of_claim(self, claim_id: str) -> ClaimGovernance:
        """Derive a claim's governance posture from its #2 conflict signal — the standing is
        read for context only and is **not** changed."""
        view = self._standing.standing_of(claim_id)
        return ClaimGovernance(
            claim_id=claim_id,
            governance=derive_governance_state(view.conflict),
            standing=view.standing,
        )

    def governance_of_subject(self, subject_id: str) -> SubjectGovernance:
        """Derive a subject's governance posture from its #4b coherence + its claims' #2
        conflicts (rule G-1). Consolidates the proven signals; governs nothing."""
        sv = self._subject.standings_of_subject(subject_id)
        conflicts = [c.conflict for c in sv.claims]
        return SubjectGovernance(
            subject_id=subject_id,
            governance=derive_subject_governance_state(sv.coherence, conflicts),
            coherence=sv.coherence,
            contested_claims=tuple(c.claim_id for c in sv.claims if c.conflict),
        )
