"""Subject standings — read-only gather of a subject's claims and their standings
(#4a Object referent, the *read-gather* experiment).

The frontier #4 asks: many Acts (across producers, claims, subjects) → one coherent
**Knowledge Object**. Before a *compiler* can exist, the **referent** must be settled: can
``subject_id`` gather the governed state of all its claims, read-only, with **no new
identity**? This module answers only the *gather* half.

What it does — and deliberately does NOT do:
- It **GATHERS**: for one ``subject_id``, it lists that subject's consultation acts, takes
  their ``claim_id``s, and reads each claim's derived standing — returning them **side by
  side** (*N claims, N standings*).
- It does **NOT COMPILE**: it never merges those claims into one "object standing"; conflict /
  supersession / provenance *across* claims is the next frontier (#4b), out of scope here.
- It **walks the latent bridge** ``subject_id`` → (consultation) ``claim_id`` →
  ``standing_of(claim_id)``. It adds **no field** to any act (``subject_id`` is *not* put on
  resolutions), mints **no ``object_id``**, and **writes nothing**.
- Read-only and **derived**: composed from acts every call, droppable, the acts stay the source.
  ``#1`` (StandingIndex) / ``#2`` (conflict) derivations are reused unchanged.

Reads go through a shared :class:`RegistryProjection` (RR by default), so the same code runs
on any projection (Identity across projections v1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator

from .consultation_read import ConsultationQuery
from .standing_read import RegistryProjection, StandingQuery


@dataclass(frozen=True)
class ClaimStanding:
    """One claim a subject produced, with its derived standing — a single entry in the
    gather (never a merged object). ``conflict`` is the per-claim #2 signal, carried verbatim."""

    claim_id: str
    mode: str          # the consultation mode that minted the claim: "observation" | "proposal"
    standing: str      # derived (StandingQuery), single source — never recomputed here
    conflict: bool = False  # per-claim conflict signal (#2); never aggregated across claims
    agent_id: str = ""  # the contributor that produced the claim's consultation (ADR-0009)
    carrier: str = ""   # the execution carrier-of-record (ADR-0009)


@dataclass(frozen=True)
class SubjectStandingsView:
    """A subject's claims and their standings, **gathered side by side** (not compiled).
    The unit is a *list*, on purpose: #4a proves the referent reaches the governed layer; it
    does **not** yet produce one coherent Knowledge Object.

    ``coherence`` (#4b v1) is a **derived descriptor of the gathered set** — do the subject's
    live governed claims `agree`, `disagree`, or are they `unsettled`? It describes a *relation
    among* the claims; it does **not** merge, rank, or resolve them.

    ``object_standing`` (ADR-PRL-0012, #4b-S) is the subject's **authoritative reading** derived
    **above** the gather + coherence (precedence: a `contested` claim > `divergent` > the shared
    `aligned` decision > `unsettled`). It is **read-only, derived, never stored**; it creates **no
    `object_id`** and does **not** compile the claims' content (that is #4b-C, deferred). The gather,
    the raw per-claim standings, each claim's `governed_standing`, and `coherence` are all untouched."""

    subject_id: str
    claims: tuple[ClaimStanding, ...]  # one per distinct claim_id under the subject (record order)
    coherence: str = "unsettled"       # "aligned" | "divergent" | "unsettled" — derived, not a standing
    divergent_claims: tuple[str, ...] = ()  # the governed claim_ids in disagreement (empty unless divergent)
    object_standing: str = "proposed"  # AUTHORITATIVE subject reading (ADR-0012): contested/accepted/
                                       # rejected/proposed — derived above the gather, never stored, no object_id


def detect_coherence(claims: Sequence[ClaimStanding]) -> tuple[str, tuple[str, ...]]:
    """Derive the **coherence descriptor** of a subject's gathered claims (#4b v1, reading d).
    Pure; computed from the claims' standings every call, **never stored**. It **surfaces**
    agreement/disagreement — it does **not** merge, rank, resolve, or give the subject a
    standing.

    Rule **C-d** — over the subject's **live governed** claims (standing ∈ {``accepted``,
    ``rejected``}); ``superseded`` / ``withdrawn`` are **closed transitions, excluded** from the
    agreement check; ``proposed`` / observations are not governed:
    - ``divergent`` — at least one ``accepted`` **and** at least one ``rejected`` live governed
      claim → the subject's live claims disagree (**surfaced, never resolved**).
    - ``aligned``   — there is ≥1 live governed claim and **all** share the same decision.
    - ``unsettled`` — **no** live governed claim.

    Returns ``(coherence, divergent_claims)`` — ``divergent_claims`` are the governed claim_ids
    on both sides (empty unless ``divergent``)."""
    governed = [c for c in claims if c.standing in ("accepted", "rejected")]
    if not governed:
        return ("unsettled", ())
    decisions = {c.standing for c in governed}
    if "accepted" in decisions and "rejected" in decisions:
        return ("divergent", tuple(sorted(c.claim_id for c in governed)))
    return ("aligned", ())


def derive_object_standing(claims: Sequence[ClaimStanding], coherence: str) -> str:
    """The subject's **object standing** (ADR-PRL-0012, #4b-S) — a read-only authoritative reading
    **above** the gather + coherence. Pure; derived every call, **never stored**; creates **no
    ``object_id``** and does **not** compile content.

    Precedence — **`claim contested` > `subject divergent` > `aligned` decision > `unsettled`**:
    1. **any** constituent claim is itself `contested` (its #2 conflict — ADR-0011
       `governed_standing = contested`, i.e. ``ClaimStanding.conflict``) → ``contested``;
    2. else ``coherence == "divergent"`` → ``contested``;
    3. else ``coherence == "aligned"`` → the **shared decision** (all live-governed claims agree —
       ``accepted`` or ``rejected``);
    4. else (``coherence == "unsettled"``) → ``proposed``.

    The precedence is load-bearing: an object is **never** ``accepted``/``rejected`` while a
    constituent claim is ``contested`` — contestation propagates to the object."""
    if any(c.conflict for c in claims):
        return "contested"
    if coherence == "divergent":
        return "contested"
    if coherence == "aligned":
        governed = {c.standing for c in claims if c.standing in ("accepted", "rejected")}
        return next(iter(governed), "proposed")  # aligned ⇒ a single shared decision
    return "proposed"  # unsettled


def render_subject_standings(view: SubjectStandingsView) -> str:
    """Pure display. The subject, its coherence descriptor (relation among claims, never a
    standing), then one line per claim — standings shown side by side, never merged."""
    if not view.claims:
        return f"subject {view.subject_id}: no claims"
    head = f"subject {view.subject_id}: {len(view.claims)} claim(s)  (standings, not compiled)"
    note = {"divergent": "  (claims disagree — surfaced, not resolved)",
            "aligned": "  (live governed claims agree)", "unsettled": ""}.get(view.coherence, "")
    lines = [head,
             f"  object standing: {view.object_standing.upper()}  (derived, ADR-0012 — not compiled content)",
             f"  coherence: {view.coherence.upper()}{note}"]
    for c in view.claims:
        flag = "  ⚠ CONFLICT" if c.conflict else ""
        lines.append(f"  claim {c.claim_id}  [{c.mode}]  agent={c.agent_id or '(unknown)'}  "
                     f"carrier={c.carrier or '(unknown)'}  : {c.standing.upper()}{flag}")
    return "\n".join(lines)


class SubjectStandingsQuery:
    """Gathers a subject's claims and their standings over a shared registry projection
    (read-only). Composes ``ConsultationQuery`` (subject → claims) and ``StandingQuery``
    (claim → standing); the standing is ``StandingQuery``'s single-source derivation, never
    recomputed here. Runs unchanged on RR or any other :class:`RegistryProjection`."""

    def __init__(self, storage: Any, index_dir: Any, *, _navigator: RegistryProjection | None = None,
                 _standing: Any | None = None):
        if _navigator is None:
            builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
            builder.build()
            _navigator = RRNavigator(builder, storage)
        self._consult = ConsultationQuery(storage, index_dir, _navigator=_navigator)
        # v1.3 (perf): accept a shared one-pass ``StandingIndex`` (built once by the discovery path) to
        # avoid ``StandingQuery``'s O(N)-per-claim re-walk of ``prl.resolution``. Both feed the SAME
        # ``derive_standing`` — standings are byte-identical; only the walk is amortized. Default keeps
        # ``StandingQuery`` so every standalone caller's path is unchanged.
        self._standing = _standing if _standing is not None else StandingQuery(
            storage, index_dir, _navigator=_navigator)

    def standings_of_subject(self, subject_id: str, *, _consults: Any | None = None) -> SubjectStandingsView:
        """Gather every claim under ``subject_id`` and read each claim's standing — side by
        side, **no cross-claim logic**. The bridge is ``subject → consultation.claim_id →
        standing_of(claim)``; nothing here merges, ranks, or reconciles the claims.

        ``_consults`` (v1.3, perf) — the subject's consultation views, pre-gathered by the caller from a
        single shared pass (the discovery path already resolves them once). When given, it replaces the
        per-subject ``ConsultationQuery.list(subject_id)`` re-walk. It **must** be exactly what ``list``
        would return (``view_from_entry`` over ``resolve_entries``, subject-filtered) — same views, same
        order — so the claim de-dup and derived standings are **byte-identical**."""
        # subject → its consultation acts → their claim_ids (de-duplicated, record order).
        seen: set[str] = set()
        claims: list[ClaimStanding] = []
        consults = _consults if _consults is not None else self._consult.list(subject_id=subject_id)
        for v in consults:
            if not v.claim_id or v.claim_id in seen:
                continue
            seen.add(v.claim_id)
            # each claim → its derived standing (single source; #1/#2 intact). No merge.
            sv = self._standing.standing_of(v.claim_id)
            claims.append(ClaimStanding(
                claim_id=v.claim_id,
                mode=v.mode,
                standing=sv.standing,
                conflict=sv.conflict,
                agent_id=v.agent_id,
                carrier=v.carrier,
            ))
        # Coherence (#4b) is read ALONGSIDE the gather; object_standing (ADR-0012) is derived
        # ABOVE it. Both are read-only descriptors — the gather is unchanged.
        coherence, divergent = detect_coherence(claims)
        return SubjectStandingsView(
            subject_id=subject_id, claims=tuple(claims),
            coherence=coherence, divergent_claims=divergent,
            object_standing=derive_object_standing(claims, coherence))
