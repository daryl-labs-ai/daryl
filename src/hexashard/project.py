"""Project: the single facade a caller talks to.

    project = Project.open(path)
    turn = project.handle_turn("what is the capex ceiling?")
    # caller sends turn.response_context to whatever model it likes

HexaShard core owns the context lifecycle, pins, source authority, retrieval,
the hex map, epochs and the bounded active state.  It does not own the chat,
the model account, the final response, or tool execution.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from . import pins as pinlib
from .context import (
    ActiveState,
    BudgetReport,
    DEFAULT_ROTATION_THRESHOLD,
    DEFAULT_WARNING_THRESHOLD,
    EpochTransition,
    build_handoff,
    enforce_budget,
    trim_handoff,
    pressure,
    rotation_signal,
    state_from_handoff,
)
from .ids import validate_project_prefix
from .metrics import Metrics
from .models import Hex, HexType, Pin, PinStatus, Source, SourceStatus
from .providers import ModelProvider, ModelResult
from .retrieval import RetrievalFilters, RetrievalResult, Retriever
from .store import (
    HexMap,
    PinStore,
    RelationStore,
    SourceStore,
    atomic_write_json,
    read_json,
)
from .tokens import TokenCounter, estimate_tokens, json_tokens
from .trust import NullTrustBackend, TrustBackend


@dataclass
class ProjectConfig:
    name: str = "untitled"
    prefix: str = "P1"
    mission: str = ""
    epoch: int = 1
    active_context_budget_tokens: int = 6000
    retrieval_budget_tokens: int = 1500
    warning_threshold: float = DEFAULT_WARNING_THRESHOLD
    rotation_threshold: float = DEFAULT_ROTATION_THRESHOLD
    max_fragments_per_query: int = 8
    max_hex_refs_per_turn: int = 5
    chunk_chars: int = 1200

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class TurnResult:
    """What ``handle_turn`` hands back.  The caller does the model call."""

    response_context: dict[str, Any]
    retrieved_sources: list[dict[str, Any]]
    state_update: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "response_context": self.response_context,
            "retrieved_sources": self.retrieved_sources,
            "state_update": self.state_update,
        }

    def context_tokens(self, counter: TokenCounter = estimate_tokens) -> int:
        return json_tokens(self.response_context, counter)


class Project:
    """A HexaShard project rooted at a directory."""

    # -- lifecycle -------------------------------------------------------
    def __init__(
        self,
        root: Path,
        config: ProjectConfig,
        *,
        trust: TrustBackend | None = None,
        provider: ModelProvider | None = None,
        counter: TokenCounter = estimate_tokens,
    ) -> None:
        self.root = Path(root)
        self.config = config
        self.counter = counter
        self.trust: TrustBackend = trust or NullTrustBackend()
        self.provider = provider
        self.metrics = Metrics()

        self.sources = SourceStore(self.root / "sources", config.prefix)
        self.hexmap = HexMap(self.root / "hexmap.jsonl", config.prefix)
        self.pins = PinStore(self.root / "pins.jsonl", config.prefix)
        self.relations = RelationStore(self.root / "relations.jsonl")
        self.retriever = Retriever(
            self.sources, self.hexmap, self.pins, self.relations,
            counter=counter, chunk_chars=config.chunk_chars,
        )
        self._deferred = False
        loaded = ActiveState.load(self.root / "active_state.json")
        self.state = loaded or ActiveState(epoch=config.epoch, mission=config.mission)
        (self.root / "epochs").mkdir(parents=True, exist_ok=True)
        (self.root / "artifacts").mkdir(parents=True, exist_ok=True)

    @classmethod
    def create(cls, root: str | Path, *, name: str, mission: str = "",
               prefix: str = "P1", trust: TrustBackend | None = None,
               provider: ModelProvider | None = None,
               counter: TokenCounter = estimate_tokens,
               **config_kwargs: Any) -> "Project":
        root = Path(root)
        if (root / "project.json").exists():
            raise FileExistsError(f"a project already exists at {root}")
        validate_project_prefix(prefix)
        cfg = ProjectConfig(name=name, prefix=prefix, mission=mission, **config_kwargs)
        root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(root / "project.json", cfg.to_dict())
        p = cls(root, cfg, trust=trust, provider=provider, counter=counter)
        p.state.mission = mission
        p.save()
        return p

    @classmethod
    def open(cls, root: str | Path, **kwargs: Any) -> "Project":
        root = Path(root)
        d = read_json(root / "project.json")
        if d is None:
            raise FileNotFoundError(f"no project.json at {root}")
        return cls(root, ProjectConfig.from_dict(d), **kwargs)

    @contextmanager
    def bulk(self):
        """Defer persistence and reindexing while authoring many records.

        Every mutating call persists immediately by default, so a crash cannot
        leave a project whose sources exist but whose map and pins do not.
        Bulk authoring of a large corpus is the one case where that is wasteful,
        so it is opted into explicitly and still persists on exit.
        """
        self._deferred = True
        try:
            yield self
        finally:
            self._deferred = False
            self.retriever.reindex()
            self.save()

    def _persist(self) -> None:
        if not self._deferred:
            self.save()

    def _reindex(self) -> None:
        if not self._deferred:
            self.retriever.reindex()

    def save(self) -> None:
        """Persist everything.  All writes are atomic replaces."""
        self.config.epoch = self.state.epoch
        atomic_write_json(self.root / "project.json", self.config.to_dict())
        self.hexmap.save()
        self.pins.save()
        self.relations.save()
        self.state.save(self.root / "active_state.json")

    def close(self) -> None:
        self.save()

    def __enter__(self) -> "Project":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- authoring -------------------------------------------------------
    def add_source(
        self,
        source_type: str,
        title: str,
        content: str,
        *,
        hex_id: str | None = None,
        status: SourceStatus = SourceStatus.CURRENT,
        tags: Iterable[str] | None = None,
        claim_key: str | None = None,
        claim_value: str | None = None,
        created_at: str | None = None,
        metadata: dict | None = None,
    ) -> Source:
        src = self.sources.add(
            source_type, title, content, status=status, tags=list(tags or []),
            claim_key=claim_key, claim_value=claim_value, created_at=created_at,
            metadata=metadata,
        )
        if hex_id is not None:
            self.assign_source(src.source_id, hex_id)
        self._reindex()
        self._persist()
        self.trust.record("source_added", {"source_id": src.source_id, "status": src.status.value})
        return src

    def add_hex(self, title: str, type: HexType, *, summary: str = "",
                source_refs: Iterable[str] | None = None, tags: Iterable[str] | None = None,
                parent_hex: str | None = None, metadata: dict | None = None) -> Hex:
        h = self.hexmap.add(
            title, type, self.state.epoch, summary=summary,
            source_refs=list(source_refs or []), tags=list(tags or []),
            parent_hex=parent_hex,
            depth=(self.hexmap.get(parent_hex).depth + 1) if parent_hex else 0,
            metadata=metadata,
        )
        self._persist()
        return h

    def assign_source(self, source_id: str, hex_id: str) -> Hex:
        h = self.hexmap.get(hex_id)
        if source_id not in h.source_refs:
            h.source_refs.append(source_id)
            self._persist()
        return h

    def relate(self, src: str, type: str, dst: str):
        r = self.relations.add(src, type, dst)
        self._persist()
        return r

    def pin(self, key: str, value: str, source_ref: str | None, *, critical: bool = False,
            hex_id: str | None = None, updated_at: str | None = None,
            note: str | None = None) -> Pin:
        """Create or replace the live pin for ``key``."""
        p = self.pins.add(key, value, source_ref, critical=critical, hex_id=hex_id,
                          updated_at=updated_at, note=note)
        self.state.sync_pins(self.pins)
        self._persist()
        self.trust.record("pin_set", {"pin_id": p.pin_id, "key": key})
        return p

    def supersede(self, old_source_id: str, new_source_id: str, *,
                  reconcile_pins: bool = True) -> dict[str, Any]:
        """Make ``new`` authoritative and ``old`` history, then fix pins."""
        old, new = self.sources.supersede(old_source_id, new_source_id)
        self.relations.add(new.source_id, "SUPERSEDES", old.source_id)
        self._reindex()
        reconciliations = pinlib.reconcile(self.pins, self.sources) if reconcile_pins else []
        self.state.sync_pins(self.pins)
        self._persist()
        self.trust.record("supersession", {"old": old.source_id, "new": new.source_id})
        return {
            "old": old.source_id,
            "new": new.source_id,
            "pin_reconciliations": [r.to_dict() for r in reconciliations],
        }

    # -- reads -----------------------------------------------------------
    def retrieve(self, query: str, filters: RetrievalFilters | None = None,
                 budget: int | None = None) -> RetrievalResult:
        budget = self.config.retrieval_budget_tokens if budget is None else budget
        res = self.retriever.retrieve(
            query, filters, budget, max_fragments=self.config.max_fragments_per_query
        )
        self.metrics.observe_retrieval(res.tokens)
        return res

    def resolve_pin(self, key: str) -> pinlib.PinResolution | None:
        """Follow a pin to its primary source.  Never fabricates grounding."""
        p = self.pins.by_key(key)
        return pinlib.resolve(p, self.sources) if p else None

    def check_pins(self) -> list[pinlib.PinResolution]:
        return pinlib.check_all(self.pins, self.sources)

    def reconcile_pins(self) -> list[pinlib.PinReconciliation]:
        out = pinlib.reconcile(self.pins, self.sources)
        self.state.sync_pins(self.pins)
        self._persist()
        return out

    def by_address(self, address: str):
        return self.retriever.by_address(address)

    # -- context lifecycle ------------------------------------------------
    def retemper(self, extra_warm: Iterable[str] = ()) -> dict[str, int]:
        """Recompute hex temperatures from the active state.  No model call."""
        counts = self.hexmap.retemper(hot=self.state.active_hex_refs, warm=extra_warm)
        self.metrics.hot_hex_count = counts["HOT"]
        self.metrics.warm_hex_count = counts["WARM"]
        self.metrics.cold_hex_count = counts["COLD"]
        return counts

    def summary_pointer(self) -> str | None:
        """Keep this epoch's full running summary in an addressable hex.

        Compaction may truncate or unload the summary from the working set; it
        may not destroy it.  This upserts one SUMMARY hex per epoch and returns
        its address, so the ladder always has somewhere to point.
        """
        if not self.state.current_summary.strip():
            return self.state.summary_hex
        if self.state.summary_hex and self.state.summary_hex in self.hexmap:
            self.hexmap.get(self.state.summary_hex).summary = self.state.current_summary
        else:
            h = self.hexmap.add(
                f"Epoch E{self.state.epoch} running summary", HexType.SUMMARY,
                self.state.epoch, summary=self.state.current_summary,
                tags=["epoch-summary", f"e{self.state.epoch}"],
            )
            self.state.summary_hex = h.hex_id
        return self.state.summary_hex

    def enforce_budget(self, summary_pointer: str | None = None) -> BudgetReport:
        return enforce_budget(
            self.state, self.config.active_context_budget_tokens, self.counter,
            summary_pointer=summary_pointer or self.summary_pointer(),
            spill_path=self.root / "unloaded_refs.json",
        )

    def _proposed_handoff(self) -> dict[str, Any]:
        """The handoff this state would produce, trimmed to be strictly smaller."""
        handoff = build_handoff(
            self.state, list(self.state.active_hex_refs),
            summary_hex=self.summary_pointer(),
        )
        return trim_handoff(handoff, self.state.tokens(self.counter), self.counter)

    def rotation_would_help(self) -> bool:
        """Whether rotating would actually relieve pressure.

        When the irreducible core -- mission, objective, critical pins,
        unresolved questions -- already exceeds the rotation threshold, a new
        epoch inherits the same problem.  Rotating anyway would spend a
        checkpoint, a handoff and a summary hex per turn, forever.
        """
        ceiling = self.config.rotation_threshold * self.config.active_context_budget_tokens
        return json_tokens(self._proposed_handoff(), self.counter) < ceiling

    def rotate_epoch(self) -> EpochTransition:
        """Checkpoint the epoch, build a bounded handoff, start the next one."""
        old = self.state
        before_tokens = old.tokens(self.counter)
        from_epoch, to_epoch = old.epoch, old.epoch + 1

        summary_hex = self.summary_pointer()
        if summary_hex:
            self.hexmap.get(summary_hex).title = f"Epoch E{from_epoch} summary"

        checkpoint = self.root / "epochs" / f"E{from_epoch}.checkpoint.json"
        atomic_write_json(checkpoint, old.to_dict())

        handoff = self._proposed_handoff()
        handoff_tokens = json_tokens(handoff, self.counter)
        atomic_write_json(
            self.root / "epochs" / f"E{from_epoch}.handoff.json", handoff
        )

        self.state = state_from_handoff(handoff, to_epoch)
        self.config.epoch = to_epoch

        transition = EpochTransition(
            from_epoch=from_epoch,
            to_epoch=to_epoch,
            turns_in_epoch=old.turn,
            handoff_tokens=handoff_tokens,
            active_state_before=before_tokens,
            active_state_after=self.state.tokens(self.counter),
            pins_preserved=len(handoff["critical_pins"]) + len(handoff["pin_refs"]),
            critical_pins_preserved=len(handoff["critical_pins"]),
            open_questions_preserved=len(handoff["open_questions"]),
            checkpoint_path=str(checkpoint.relative_to(self.root)),
            summary_hex=summary_hex,
        )
        atomic_write_json(
            self.root / "epochs" / f"E{from_epoch}-to-E{to_epoch}.transition.json",
            transition.to_dict(),
        )
        self.metrics.epoch_rotations += 1
        self.metrics.handoff_tokens.append(handoff_tokens)
        self.save()          # the new epoch is durable before the turn returns
        self.trust.record("epoch_rotation", transition.to_dict())
        return transition

    def epoch_transitions(self) -> list[dict]:
        out = []
        for p in sorted((self.root / "epochs").glob("*.transition.json")):
            out.append(json.loads(p.read_text(encoding="utf-8")))
        return out

    # -- the turn ---------------------------------------------------------
    def handle_turn(
        self,
        user_message: str,
        *,
        filters: RetrievalFilters | None = None,
        objective: str | None = None,
        summary_append: str | None = None,
    ) -> TurnResult:
        """Assemble bounded context for one conversational turn.

        Deliberately does *not* call a model: the caller owns that.  The only
        things that happen here are retrieval, state update, budget
        enforcement and -- if the state is saturated -- an epoch rotation.
        """
        self.state.turn += 1
        if objective is not None:
            self.state.current_objective = objective
        if summary_append:
            self.state.current_summary = (
                f"{self.state.current_summary}\n{summary_append}".strip()
            )

        result = self.retrieve(user_message, filters)
        for hex_id in result.hex_refs[: self.config.max_hex_refs_per_turn]:
            self.state.touch_hex(hex_id)
        self.state.add_hint(user_message[:120])
        self.state.sync_pins(self.pins)

        pin_warnings = [
            r.to_dict() for r in self.check_pins() if r.status is not PinStatus.ACTIVE
        ]

        signal = rotation_signal(
            self.state, self.config.active_context_budget_tokens, self.counter,
            warning_threshold=self.config.warning_threshold,
            rotation_threshold=self.config.rotation_threshold,
        )
        transition = None
        if signal == "rotate":
            if self.rotation_would_help():
                transition = self.rotate_epoch()
            else:
                # rotating would carry the same oversized core into a new
                # epoch every turn; say so instead of churning epochs
                signal = "saturated"

        budget_report = self.enforce_budget()
        counts = self.retemper(extra_warm=result.hex_refs)

        self.metrics.observe_active_state(self.state.tokens(self.counter))
        self.metrics.pin_count = len(self.pins.live())
        self.metrics.source_store_tokens = self.sources.total_tokens(self.counter)
        self.save()

        response_context = {
            "epoch": self.state.epoch,
            "turn": self.state.turn,
            "mission": self.state.mission,
            "current_objective": self.state.current_objective,
            "current_summary": self.state.current_summary,
            "active_pins": self.state.active_pins,
            "open_questions": self.state.unresolved_questions(),
            "active_hex_refs": self.state.active_hex_refs,
            "recent_decisions": self.state.recent_decisions,
            "retrieved": [f.to_dict() for f in result.fragments],
            "ambiguities": [a.to_dict() for a in result.ambiguities],
            "pin_warnings": pin_warnings,
            "unloaded_addresses": self.state.dropped_refs,
            "unloaded_ledger": self.state.unloaded_ledger,
        }
        state_update = {
            "signal": signal,
            "pressure": round(pressure(self.state, self.config.active_context_budget_tokens,
                                       self.counter), 4),
            "budget": budget_report.to_dict(),
            "epoch_transition": transition.to_dict() if transition else None,
            "temperatures": counts,
            "retrieval_tokens": result.tokens,
            "retrieval_truncated": result.truncated,
            "retrieval_over_budget": result.over_budget,
            "active_state_tokens": self.state.tokens(self.counter),
            # what the caller will actually send: active state *plus* grounding.
            # The budget bounds the state; this number bounds nothing and is
            # reported so the caller can see the real size.
            "response_context_tokens": json_tokens(response_context, self.counter),
        }
        return TurnResult(response_context, [f.to_dict() for f in result.fragments], state_update)

    def generate_reply(self, user_message: str, *, system: str = "",
                       **turn_kwargs: Any) -> tuple[TurnResult, ModelResult]:
        """Optional convenience: run a turn *and* call the configured provider.

        Core correctness never depends on this path; it exists so a caller can
        hand HexaShard the model call if it wants to.
        """
        if self.provider is None:
            raise RuntimeError("no ModelProvider configured on this project")
        turn = self.handle_turn(user_message, **turn_kwargs)
        res = self.provider.generate(
            system=system or self.state.mission,
            messages=[{"role": "user", "content": user_message}],
            context=turn.response_context,
            token_budget=self.config.active_context_budget_tokens,
        )
        self.metrics.observe_model(res.input_tokens, res.output_tokens)
        return turn, res

    # -- reporting --------------------------------------------------------
    def measurements(self) -> dict[str, Any]:
        counts = {"HOT": 0, "WARM": 0, "COLD": 0}
        for h in self.hexmap.all():
            counts[h.temperature.value] += 1
        self.metrics.hot_hex_count = counts["HOT"]
        self.metrics.warm_hex_count = counts["WARM"]
        self.metrics.cold_hex_count = counts["COLD"]
        self.metrics.pin_count = len(self.pins.live())
        self.metrics.source_store_tokens = self.sources.total_tokens(self.counter)
        self.metrics.observe_active_state(self.state.tokens(self.counter))
        d = self.metrics.to_dict()
        d.update({
            "project_total_tokens": d["source_store_tokens"],
            "hex_count": len(self.hexmap),
            "source_count": len(self.sources.all()),
            "relation_count": len(self.relations),
            "fragment_count": self.retriever.fragment_count,
            "hexmap_index_tokens": json_tokens(self.hexmap.index_view(), self.counter),
            "epoch": self.state.epoch,
        })
        return d
