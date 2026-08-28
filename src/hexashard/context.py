"""Active state, budget enforcement, and context epochs.

The active state is the whole point of HexaShard: a small, serialisable,
explicitly bounded working set that sits in front of a much larger project
store.  Everything in this module is deterministic bookkeeping -- no model
call is needed to enforce a budget or rotate an epoch.

Budget policy (priority order, from spec section 15):

    never dropped   mission, current objective, critical pins,
                    unresolved open questions (compacted at worst)
    dropped first   retrieval hints, then hex refs, then decisions,
                    then the running summary, then resolved questions,
                    then non-critical pins

Anything removed leaves its address behind in ``dropped_refs``, so nothing
becomes unreachable -- only unloaded.
"""

from __future__ import annotations

import copy

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Pin
from .store import PinStore, atomic_write_json, read_json
from .tokens import TokenCounter, estimate_tokens, json_tokens

#: Fractions of the budget at which the runtime warns / rotates.
DEFAULT_WARNING_THRESHOLD = 0.75
DEFAULT_ROTATION_THRESHOLD = 0.90

#: Caps applied while compacting.  Configurable, not claimed to be optimal.
SUMMARY_HEAD_CHARS = 600
QUESTION_HEAD_CHARS = 80
MAX_HANDOFF_HEX_REFS = 24


def pin_view(pin: Pin) -> dict[str, Any]:
    """What a pin looks like inside the active state: value *and* pointer."""
    return {
        "pin_id": pin.pin_id,
        "key": pin.key,
        "value": pin.value,
        "source_ref": pin.source_ref,
        "critical": pin.critical,
        "status": pin.status.value,
    }


@dataclass
class ActiveState:
    """The bounded conversational working set.  Serialises to one JSON file."""

    epoch: int = 1
    turn: int = 0
    mission: str = ""
    current_objective: str = ""
    current_summary: str = ""
    active_pins: list[dict] = field(default_factory=list)
    open_questions: list[dict] = field(default_factory=list)
    active_hex_refs: list[str] = field(default_factory=list)
    recent_decisions: list[dict] = field(default_factory=list)
    retrieval_hints: list[str] = field(default_factory=list)
    #: Addresses of everything compaction removed, grouped by kind, so that
    #: nothing becomes unreachable -- only unloaded.
    dropped_refs: dict[str, list[str]] = field(default_factory=dict)
    #: Set when the ledger itself was spilled to a file to fit the budget.
    unloaded_ledger: str | None = None
    #: Address of the hex holding this epoch's full running summary, so the
    #: summary can be truncated or unloaded without becoming unreachable.
    summary_hex: str | None = None
    over_budget: bool = False

    # -- serialisation ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "turn": self.turn,
            "mission": self.mission,
            "current_objective": self.current_objective,
            "current_summary": self.current_summary,
            "active_pins": self.active_pins,
            "open_questions": self.open_questions,
            "active_hex_refs": self.active_hex_refs,
            "recent_decisions": self.recent_decisions,
            "retrieval_hints": self.retrieval_hints,
            "dropped_refs": self.dropped_refs,
            "unloaded_ledger": self.unloaded_ledger,
            "summary_hex": self.summary_hex,
            "over_budget": self.over_budget,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ActiveState":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def save(self, path: Path) -> None:
        atomic_write_json(Path(path), self.to_dict())

    @classmethod
    def load(cls, path: Path) -> "ActiveState | None":
        d = read_json(Path(path))
        return cls.from_dict(d) if d else None

    def tokens(self, counter: TokenCounter = estimate_tokens) -> int:
        return json_tokens(self.to_dict(), counter)

    # -- mutation helpers -------------------------------------------------
    def sync_pins(self, pins: PinStore) -> None:
        """Refresh embedded pin views from the pin store, criticals first."""
        live = pins.live()
        self.active_pins = [pin_view(p) for p in live if p.critical] + \
                           [pin_view(p) for p in live if not p.critical]

    def add_open_question(self, qid: str, text: str) -> dict:
        q = {"id": qid, "text": text, "resolved": False}
        self.open_questions.append(q)
        return q

    def resolve_question(self, qid: str) -> None:
        for q in self.open_questions:
            if q.get("id") == qid:
                q["resolved"] = True

    def unresolved_questions(self) -> list[dict]:
        return [q for q in self.open_questions if not q.get("resolved")]

    def note_decision(self, hex_id: str, title: str, source_ref: str | None = None) -> None:
        self.recent_decisions.append({"hex_id": hex_id, "title": title, "source_ref": source_ref})

    def touch_hex(self, hex_id: str) -> None:
        if hex_id in self.active_hex_refs:
            self.active_hex_refs.remove(hex_id)
        self.active_hex_refs.append(hex_id)

    def add_hint(self, hint: str) -> None:
        if hint in self.retrieval_hints:
            self.retrieval_hints.remove(hint)
        self.retrieval_hints.append(hint)

    def _drop(self, kind: str, ref: Any) -> None:
        if ref is None:
            return
        bucket = self.dropped_refs.setdefault(kind, [])
        if ref not in bucket:
            bucket.append(ref)

    def unloaded(self, kind: str) -> list[str]:
        return list(self.dropped_refs.get(kind, ()))


def restore(state: "ActiveState", snapshot: dict) -> None:
    """Put a state back to a previously captured ``to_dict`` snapshot."""
    for key, value in snapshot.items():
        if key in ActiveState.__dataclass_fields__:
            setattr(state, key, copy.deepcopy(value))


def spill_ledger(state: "ActiveState", path: Path) -> str:
    """Move the in-state address ledger to a file, merging with any prior one."""
    prior = read_json(path, default={}) or {}
    merged: dict[str, list[str]] = {k: list(v) for k, v in prior.items()}
    for kind, refs in state.dropped_refs.items():
        bucket = merged.setdefault(kind, [])
        for r in refs:
            if r not in bucket:
                bucket.append(r)
    atomic_write_json(path, merged)
    state.dropped_refs = {}
    return path.name


@dataclass
class BudgetReport:
    budget: int
    tokens_before: int
    tokens_after: int
    steps: list[str] = field(default_factory=list)
    over_budget: bool = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def enforce_budget(
    state: ActiveState,
    budget: int,
    counter: TokenCounter = estimate_tokens,
    *,
    summary_pointer: str | None = None,
    spill_path: Path | str | None = None,
) -> BudgetReport:
    """Compact ``state`` in place until it fits, or report that it cannot.

    Critical pins, the mission, the current objective and the *existence* of
    unresolved questions are never removed.  If the irreducible core alone
    exceeds the budget the state is marked ``over_budget`` rather than having
    required material silently deleted.

    The address ledger is treated as material too: rather than discard
    addresses to make room, it is spilled to ``spill_path`` and replaced by a
    pointer, so unloaded material stays reachable.
    """
    before = state.tokens(counter)
    report = BudgetReport(budget=budget, tokens_before=before, tokens_after=before)
    if before <= budget:
        state.over_budget = False
        return report

    def fits() -> bool:
        return state.tokens(counter) <= budget

    #: Full snapshot, so a ladder that somehow made the state *larger* can be
    #: undone rather than shipped.  Compaction must never cost tokens.
    #: Deep-copied: ``to_dict`` hands back the live lists, not copies of them.
    snapshot = copy.deepcopy(state.to_dict())

    # 1. retrieval hints -- cheapest to lose, trivially regenerated
    if state.retrieval_hints and not fits():
        while state.retrieval_hints and not fits():
            state.retrieval_hints.pop(0)
        report.steps.append("trimmed retrieval_hints")

    # 2. hex refs -- the map row stays reachable by address.  Stop as soon as
    #    unloading stops helping: moving an address into the ledger is close to
    #    token-neutral, and the ladder must never make the state larger.
    if state.active_hex_refs and not fits():
        while state.active_hex_refs and not fits():
            state._drop("hex", state.active_hex_refs.pop(0))
        report.steps.append(f"unloaded {len(state.dropped_refs.get('hex', ()))} hex refs")

    # 3. decisions -> addresses, then unloaded oldest-first
    if not fits() and any("title" in d for d in state.recent_decisions):
        for d in state.recent_decisions:
            d.pop("title", None)
        report.steps.append("compacted recent_decisions to addresses")
    while state.recent_decisions and not fits():
        d = state.recent_decisions.pop(0)
        state._drop("decision", d.get("hex_id") or d.get("source_ref"))
        report.steps.append("unloaded a decision")

    # 4. running summary -> head slice, then a pointer only.  The summary is
    #    only compacted when its full text is addressable elsewhere; without a
    #    pointer the tail would be destroyed, so the ladder skips this rung and
    #    says so rather than losing it silently.
    if not fits() and len(state.current_summary) > SUMMARY_HEAD_CHARS:
        if summary_pointer:
            state.current_summary = state.current_summary[:SUMMARY_HEAD_CHARS].rstrip() + " [...]"
            state._drop("summary", summary_pointer)
            report.steps.append(f"truncated current_summary (full text at {summary_pointer})")
        else:
            report.steps.append(
                "skipped summary truncation: no addressable copy was supplied"
            )
    if not fits() and state.current_summary and summary_pointer:
        state.current_summary = ""
        state._drop("summary", summary_pointer)
        report.steps.append(f"unloaded current_summary (full text at {summary_pointer})")

    # 5. resolved questions
    if not fits() and any(q.get("resolved") for q in state.open_questions):
        keep = []
        for q in state.open_questions:
            if q.get("resolved"):
                state._drop("question", q.get("id"))
                report.steps.append(f"unloaded resolved question {q.get('id')}")
            else:
                keep.append(q)
        state.open_questions = keep

    # 6. non-critical pins -> address-only (criticals are untouchable)
    if not fits() and any(not p.get("critical") for p in state.active_pins):
        keep = []
        for p in state.active_pins:
            if p.get("critical"):
                keep.append(p)
            else:
                state._drop("pin", p["pin_id"])
                report.steps.append(f"unloaded non-critical pin {p['pin_id']}")
        state.active_pins = keep

    # 7. compact the text of unresolved questions, keeping their ids.  This
    #    rung is lossy: the discarded tail is not addressable anywhere.  It is
    #    reported in `steps` for exactly that reason.
    if not fits() and any(len(q.get("text", "")) > QUESTION_HEAD_CHARS
                          for q in state.open_questions):
        for q in state.open_questions:
            if len(q.get("text", "")) > QUESTION_HEAD_CHARS:
                q["text"] = q["text"][:QUESTION_HEAD_CHARS].rstrip() + " [...]"
        report.steps.append("compacted unresolved question text (lossy)")

    # 8. the address ledger is itself material: spill it to a file and keep a
    #    pointer, rather than dropping addresses to make room.
    if not fits() and state.dropped_refs and spill_path is not None:
        state.unloaded_ledger = spill_ledger(state, Path(spill_path))
        report.steps.append(f"spilled address ledger to {state.unloaded_ledger}")

    report.tokens_after = state.tokens(counter)
    if report.tokens_after > before:
        restore(state, snapshot)
        report.tokens_after = state.tokens(counter)
        report.steps.append("reverted: compaction would have increased the state")
    report.over_budget = report.tokens_after > budget
    state.over_budget = report.over_budget
    return report


# --------------------------------------------------------------------------
# Context epochs
# --------------------------------------------------------------------------


def pressure(state: ActiveState, budget: int, counter: TokenCounter = estimate_tokens) -> float:
    return (state.tokens(counter) / budget) if budget else 0.0


def rotation_signal(
    state: ActiveState,
    budget: int,
    counter: TokenCounter = estimate_tokens,
    *,
    warning_threshold: float = DEFAULT_WARNING_THRESHOLD,
    rotation_threshold: float = DEFAULT_ROTATION_THRESHOLD,
) -> str:
    """``"ok"`` | ``"warning"`` | ``"rotate"`` from one ratio.

    Deliberately not a cognitive saturation score: it is
    ``active_state_tokens / budget`` against two configurable thresholds,
    instrumented so a later experiment can evaluate them.
    """
    p = pressure(state, budget, counter)
    if p >= rotation_threshold:
        return "rotate"
    if p >= warning_threshold:
        return "warning"
    return "ok"


@dataclass
class EpochTransition:
    from_epoch: int
    to_epoch: int
    turns_in_epoch: int
    handoff_tokens: int
    active_state_before: int
    active_state_after: int
    pins_preserved: int
    critical_pins_preserved: int
    open_questions_preserved: int
    checkpoint_path: str
    summary_hex: str | None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def build_handoff(
    state: ActiveState,
    fallback_hex_refs: list[str],
    *,
    summary_hex: str | None,
) -> dict[str, Any]:
    """The bounded packet that crosses an epoch boundary.

    It carries authority and unresolved work forward, plus *addresses* for
    everything else.  It never carries the previous epoch's transcript,
    running summary, or full hex map.

    Hex references come from what this epoch actually had loaded, topped up
    from ``fallback_hex_refs`` only if the state had none; taking them from the
    project's whole HOT/WARM set would let a handoff be *larger* than the state
    it replaces.  Whatever the cap discards is counted in the packet.
    """
    refs = list(state.active_hex_refs) or list(fallback_hex_refs)
    hints = ([f"previous epoch summary: {summary_hex}"] if summary_hex else []) \
        + state.retrieval_hints[-3:]
    return {
        "mission": state.mission,
        "current_objective": state.current_objective,
        "critical_pins": [p for p in state.active_pins if p.get("critical")],
        "pin_refs": [p["pin_id"] for p in state.active_pins if not p.get("critical")],
        "open_questions": state.unresolved_questions(),
        "decisions": [
            {"hex_id": d.get("hex_id"), "source_ref": d.get("source_ref")}
            for d in state.recent_decisions
        ],
        "hexmap_refs": refs[-MAX_HANDOFF_HEX_REFS:],
        "hexmap_refs_omitted": max(0, len(refs) - MAX_HANDOFF_HEX_REFS),
        "retrieval_hints": hints,
        "retrieval_hints_omitted": max(0, len(state.retrieval_hints) - 3),
        "unloaded_ledger": state.unloaded_ledger,
        "summary_hex": summary_hex,
    }


def trim_handoff(handoff: dict[str, Any], ceiling: int,
                 counter: TokenCounter = estimate_tokens) -> dict[str, Any]:
    """Shed addresses until the handoff is strictly smaller than ``ceiling``.

    Only material that is reachable by other means is shed -- hex references
    first, then decision addresses.  Critical pins, unresolved questions, the
    mission and the objective are never touched, so a handoff can still exceed
    the ceiling; the caller checks for that rather than being lied to.
    """
    while json_tokens(handoff, counter) >= ceiling and handoff["hexmap_refs"]:
        handoff["hexmap_refs"].pop(0)
        handoff["hexmap_refs_omitted"] += 1
    while json_tokens(handoff, counter) >= ceiling and handoff["decisions"]:
        handoff["decisions"].pop(0)
        handoff["decisions_omitted"] = handoff.get("decisions_omitted", 0) + 1
    return handoff


def state_from_handoff(handoff: dict[str, Any], epoch: int) -> ActiveState:
    """Seed the next epoch's active state from the handoff and nothing else."""
    s = ActiveState(
        epoch=epoch,
        turn=0,
        mission=handoff["mission"],
        current_objective=handoff["current_objective"],
        current_summary="",
        active_pins=list(handoff["critical_pins"]),
        open_questions=list(handoff["open_questions"]),
        active_hex_refs=list(handoff["hexmap_refs"]),
        recent_decisions=list(handoff["decisions"]),
        retrieval_hints=list(handoff["retrieval_hints"]),
    )
    # the ledger of unloaded addresses belongs to the project, not the epoch
    s.unloaded_ledger = handoff.get("unloaded_ledger")
    for pid in handoff.get("pin_refs", []):
        s._drop("pin", pid)
    return s
