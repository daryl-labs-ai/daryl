"""HexaShard Adapter v0.1 — chat runtime over frozen Core.

The model, the visible transcript, and this adapter do not own project truth.
Core does.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from hexashard import (
    HexType,
    Project,
    RetrievalFilters,
    SourceStatus,
)
from hexashard.models import PinStatus
from hexashard.tokens import estimate_tokens

from .config import AdapterConfig
from .context import assemble
from .errors import MalformedProviderResponse, ProjectNotFound
from .metrics import append_metric
from .models import ChatTurnResult
from .provider import ChatProvider, make_provider


ADAPTER_CONFIG_NAME = "adapter_config.json"
ADAPTER_METRICS_NAME = "adapter_metrics.jsonl"


#: Keys of ``response_context`` that Core hands back as live references into its
#: own ActiveState.  The Adapter copies them so that nothing downstream can
#: mutate Core state by editing the context it was given.
_ALIASED_CONTEXT_KEYS = (
    "active_pins",
    "active_hex_refs",
    "recent_decisions",
    "open_questions",
    "retrieved",
    "ambiguities",
    "pin_warnings",
    "unloaded_addresses",
)


def _harden_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Detach the turn context from Core state and surface non-ACTIVE pins.

    Two adapter-level guarantees, neither of which changes Core semantics:

    1. ``Project.handle_turn`` returns live references into ``ActiveState``.
       Copying them means a caller editing the returned context cannot corrupt
       Core state or have that corruption persisted on the next save.
    2. ``Project.check_pins`` re-resolves a pin against its *current* pointer,
       so a pin that supersession repointed and stamped ``NEEDS_REVIEW``
       resolves as ``ACTIVE`` and never reaches ``pin_warnings``.  The stored
       status is still carried on the pin record, so the Adapter reports any
       pin whose status is not ACTIVE that Core did not already flag.
    """
    ctx = dict(ctx)
    for key in _ALIASED_CONTEXT_KEYS:
        value = ctx.get(key)
        if isinstance(value, list):
            ctx[key] = list(value)

    warnings = list(ctx.get("pin_warnings") or [])
    already = {w.get("pin_id") for w in warnings}
    for pin in ctx.get("active_pins") or []:
        status = pin.get("status")
        if status in (None, "ACTIVE") or pin.get("pin_id") in already:
            continue
        warnings.append({
            "pin_id": pin.get("pin_id"),
            "key": pin.get("key"),
            "value": pin.get("value"),
            "source_ref": pin.get("source_ref"),
            "status": status,
            "detail": f"pin is stamped {status}; confirm against the cited source",
        })
    ctx["pin_warnings"] = warnings
    return ctx


#: Fields the Adapter reads off whatever a provider returns.
_PROVIDER_RESULT_FIELDS = ("text", "input_tokens", "output_tokens", "provider")


def _require_provider_result(result: Any, provider: ChatProvider) -> None:
    """Fail with a typed adapter error, not an AttributeError, on a bad reply.

    A third-party provider is ordinary untrusted code.  Without this check a
    provider that returns the wrong shape surfaces deep inside result assembly
    as an ``AttributeError``, which reads like an Adapter bug rather than a
    provider one.
    """
    missing = [f for f in _PROVIDER_RESULT_FIELDS if not hasattr(result, f)]
    if missing:
        raise MalformedProviderResponse(
            f"provider {getattr(provider, 'name', type(provider).__name__)!r} "
            f"returned {type(result).__name__} missing {missing}"
        )
    if not isinstance(result.text, str):
        raise MalformedProviderResponse(
            f"provider {getattr(provider, 'name', type(provider).__name__)!r} "
            f"returned non-string text of type {type(result.text).__name__}"
        )


#: Files ``Project.save()`` writes. A chat turn can dirty these and nothing
#: else — in particular it never writes ``sources/``, so the cost of snapshotting
#: a turn is independent of how large the project store is.
_TURN_STATE_FILES = (
    "project.json",
    "active_state.json",
    "hexmap.jsonl",
    "pins.jsonl",
    "relations.jsonl",
)


class _TurnSnapshot:
    """The conversational state a turn is allowed to change, captured before it.

    ``Project.handle_turn`` advances state and persists it *before* the caller
    can call a provider, because it is what produces the context the provider is
    given. A turn that then fails to produce a response would otherwise leave the
    project looking as though a conversation had happened.

    This captures only what such a turn can write. Project truth — sources, pins,
    open questions — is not copied, because nothing on the failing path writes it;
    that is asserted by test instead, which keeps the per-turn cost flat.

    Adapter-local. Core is not modified, and a successful turn never touches this.
    """

    __slots__ = ("_root", "_files", "_epoch_artifacts")

    def __init__(self, root: Path) -> None:
        self._root = root
        self._files = {
            name: (root / name).read_bytes()
            for name in _TURN_STATE_FILES
            if (root / name).is_file()
        }
        epochs = root / "epochs"
        self._epoch_artifacts = (
            {p.name for p in epochs.iterdir() if p.is_file()} if epochs.is_dir() else set()
        )

    def restore(self) -> None:
        """Put the recorded state back and drop anything the failed turn added."""
        for name, blob in self._files.items():
            path = self._root / name
            if not path.is_file() or path.read_bytes() != blob:
                path.write_bytes(blob)
        epochs = self._root / "epochs"
        if epochs.is_dir():
            for path in epochs.iterdir():
                if path.is_file() and path.name not in self._epoch_artifacts:
                    path.unlink()


class HexaShardAdapter:
    def __init__(self, project: Project, config: AdapterConfig, provider: ChatProvider) -> None:
        config.validate()
        self.project = project
        self.config = config
        self.provider = provider
        self._metrics_path = project.root / ADAPTER_METRICS_NAME

    @classmethod
    def create(
        cls,
        root: str | Path,
        *,
        name: str,
        mission: str = "",
        config: AdapterConfig | None = None,
        provider: ChatProvider | None = None,
        **project_kwargs: Any,
    ) -> "HexaShardAdapter":
        cfg = config or AdapterConfig()
        cfg.validate()
        project_kwargs.setdefault("retrieval_budget_tokens", cfg.retrieval_budget)
        project = Project.create(root, name=name, mission=mission, **project_kwargs)
        adapter = cls(project, cfg, provider or make_provider(cfg))
        adapter._persist_config()
        return adapter

    @classmethod
    def open(
        cls,
        root: str | Path,
        *,
        config: AdapterConfig | None = None,
        provider: ChatProvider | None = None,
    ) -> "HexaShardAdapter":
        root = Path(root)
        if not (root / "project.json").is_file():
            raise ProjectNotFound(str(root))
        cfg = config
        saved = root / ADAPTER_CONFIG_NAME
        if cfg is None and saved.is_file():
            cfg = AdapterConfig.load(saved)
        cfg = cfg or AdapterConfig()
        cfg.validate()
        project = Project.open(root)
        return cls(project, cfg, provider or make_provider(cfg))

    def close(self) -> None:
        self.project.close()
        self._persist_config()

    def __enter__(self) -> "HexaShardAdapter":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _persist_config(self) -> None:
        self.config.save(self.project.root / ADAPTER_CONFIG_NAME)

    def project_status(self) -> dict[str, Any]:
        m = self.project.measurements()
        return {
            "path": str(self.project.root),
            "name": self.project.config.name,
            "mission": self.project.config.mission,
            "epoch": self.project.state.epoch,
            "turn": self.project.state.turn,
            "objective": self.project.state.current_objective,
            "source_count": m.get("source_count"),
            "pin_count": m.get("pin_count"),
            "project_store_tokens": m.get("project_total_tokens"),
            "active_state_tokens": self.project.state.tokens(self.project.counter),
            "mode": self.config.mode,
            "provider": self.provider.name,
        }

    def add_source(self, source_type: str, title: str, content: str, **kwargs: Any):
        if self.config.mode == "READ_ONLY":
            raise PermissionError("READ_ONLY: add_source is not allowed")
        return self.project.add_source(source_type, title, content, **kwargs)

    def add_hex(self, title: str, type: HexType, **kwargs: Any):
        if self.config.mode == "READ_ONLY":
            raise PermissionError("READ_ONLY: add_hex is not allowed")
        return self.project.add_hex(title, type, **kwargs)

    def pin(self, key: str, value: str, source_ref: str | None, **kwargs: Any):
        if self.config.mode == "READ_ONLY":
            raise PermissionError("READ_ONLY: pin is not allowed")
        return self.project.pin(key, value, source_ref, **kwargs)

    def supersede(self, old_source_id: str, new_source_id: str, **kwargs: Any):
        if self.config.mode == "READ_ONLY":
            raise PermissionError("READ_ONLY: supersede is not allowed")
        return self.project.supersede(old_source_id, new_source_id, **kwargs)

    def _prepare_readonly(self, user_message: str, filters: RetrievalFilters | None):
        t0 = time.perf_counter()
        budget = self.config.retrieval_budget
        result = self.project.retrieve(user_message, filters, budget=budget)
        retrieval_ms = int((time.perf_counter() - t0) * 1000)
        pin_warnings = [
            r.to_dict() for r in self.project.check_pins() if r.status is not PinStatus.ACTIVE
        ]
        ctx = {
            "epoch": self.project.state.epoch,
            "turn": self.project.state.turn,
            "mission": self.project.state.mission,
            "current_objective": self.project.state.current_objective,
            "current_summary": self.project.state.current_summary,
            "active_pins": list(self.project.state.active_pins),
            "open_questions": self.project.state.unresolved_questions(),
            "active_hex_refs": list(self.project.state.active_hex_refs),
            "recent_decisions": list(self.project.state.recent_decisions),
            "retrieved": [f.to_dict() for f in result.fragments],
            "ambiguities": [a.to_dict() for a in result.ambiguities],
            "pin_warnings": pin_warnings,
            "unloaded_addresses": self.project.state.dropped_refs,
            "unloaded_ledger": self.project.state.unloaded_ledger,
        }
        state_update = {
            "signal": "read_only",
            "retrieval_tokens": result.tokens,
            "retrieval_truncated": result.truncated,
            "active_state_tokens": self.project.state.tokens(self.project.counter),
            "response_context_tokens": estimate_tokens(
                # cheap stand-in; assemble measures the real payload
                ""
            ),
        }
        return ctx, state_update, retrieval_ms, result.tokens

    def chat(
        self,
        user_message: str,
        *,
        filters: RetrievalFilters | None = None,
        objective: str | None = None,
    ) -> ChatTurnResult:
        """One visible chat turn. Model output is never written as a source."""
        wall0 = time.perf_counter()
        # home_hex_id is organisational only — never applied as hex_ids filter.
        _ = self.config.home_hex_id

        snapshot: _TurnSnapshot | None = None
        if self.config.mode == "READ_ONLY":
            ctx, state_update, retrieval_ms, retr_tokens = self._prepare_readonly(
                user_message, filters
            )
        else:
            # handle_turn advances and persists state before a provider can be
            # called, because it is what produces the context to send. Record
            # what it may change so a turn that never yields a response can be
            # undone. READ_ONLY mutates nothing and needs no snapshot.
            snapshot = _TurnSnapshot(self.project.root)
            t0 = time.perf_counter()
            turn = self.project.handle_turn(
                user_message, filters=filters, objective=objective
            )
            retrieval_ms = int((time.perf_counter() - t0) * 1000)
            ctx = turn.response_context
            state_update = turn.state_update
            retr_tokens = int(state_update.get("retrieval_tokens") or 0)

        # From here to a validated provider result the state has advanced but no
        # response exists yet. Any failure in that window rolls the turn back.
        try:
            ctx = _harden_context(ctx)

            assembled = assemble(
                user_message=user_message,
                response_context=ctx,
                budget=self.config.model_context_budget,
            )
            if assembled.tokens > self.config.provider_context_limit:
                from .errors import ContextBudgetExceeded
                raise ContextBudgetExceeded(
                    "assembled context exceeds provider_context_limit "
                    f"{self.config.provider_context_limit}"
                )

            t1 = time.perf_counter()
            result = self.provider.generate(
                messages=[{"role": "user", "content": user_message}],
                context=assembled.project_block,
                system=assembled.system,
                max_output_tokens=self.config.max_output_tokens,
                config=self.config,
            )
            _require_provider_result(result, self.provider)
        except BaseException as exc:
            self._abandon_turn(snapshot, user_message, exc)
            raise
        model_ms = int((time.perf_counter() - t1) * 1000)
        wall = int((time.perf_counter() - wall0) * 1000)
        overhead = max(0, wall - model_ms - retrieval_ms)

        store_tokens = self.project.sources.total_tokens(self.project.counter)
        out = ChatTurnResult(
            response_text=result.text,
            model_input_tokens=result.input_tokens,
            model_output_tokens=result.output_tokens,
            active_state_tokens=int(
                state_update.get("active_state_tokens")
                or self.project.state.tokens(self.project.counter)
            ),
            retrieved_context_tokens=retr_tokens,
            total_context_tokens=assembled.tokens,
            retrieved_source_ids=assembled.retrieved_source_ids,
            pin_warnings=list(ctx.get("pin_warnings") or []),
            authority_warnings=assembled.authority_warnings,
            epoch=int(ctx.get("epoch") or self.project.state.epoch),
            latency_ms=wall,
            retrieval_latency_ms=retrieval_ms,
            adapter_overhead_ms=overhead,
            state_update_summary={
                "signal": state_update.get("signal"),
                "mode": self.config.mode,
                "model_committed_as_source": False,
            },
            truncated=assembled.truncated,
            dropped_sections=assembled.dropped_sections,
            provider=result.provider,
            mode=self.config.mode,
            retrieval_count=len(ctx.get("retrieved") or []),
            project_store_tokens=store_tokens,
            turn=int(ctx.get("turn") or self.project.state.turn),
            no_source_retrieved=assembled.no_source_retrieved,
        )
        self._commit_turn(out)
        return out

    def _abandon_turn(
        self, snapshot: "_TurnSnapshot | None", user_message: str, exc: BaseException
    ) -> None:
        """Undo a turn that advanced state but produced no response.

        Project truth is untouched either way — a chat turn never writes sources,
        pins or open questions. What is undone is the conversational state:
        the turn counter, retrieval hints, hex references and any epoch the
        failed turn rotated into.

        The failure itself is *kept*. Observability is not project truth, so the
        metrics record survives the rollback and the attempt remains auditable.
        """
        self._record_failure(user_message, exc, rolled_back=snapshot is not None)
        if snapshot is None:
            return
        snapshot.restore()
        # Bytes on disk are back; the live object still holds the advanced state,
        # so rebuild it from what was just restored.
        self.project = Project.open(
            self.project.root,
            trust=self.project.trust,
            provider=self.project.provider,
            counter=self.project.counter,
        )

    def _record_failure(
        self, user_message: str, exc: BaseException, *, rolled_back: bool
    ) -> None:
        append_metric(self._metrics_path, {
            "outcome": "failed",
            "error": type(exc).__name__,
            "error_detail": str(exc)[:200],
            "turn_rolled_back": rolled_back,
            "mode": self.config.mode,
            "provider": self.provider.name,
            "user_message_tokens": estimate_tokens(user_message),
        })

    def _commit_turn(self, result: ChatTurnResult) -> None:
        """Persist adapter metrics only. Never ingest model prose as a source."""
        append_metric(self._metrics_path, {
            "project_store_tokens": result.project_store_tokens,
            "active_state_tokens": result.active_state_tokens,
            "retrieved_context_tokens": result.retrieved_context_tokens,
            "full_model_input_tokens": result.total_context_tokens,
            "provider_reported_input_tokens": result.model_input_tokens,
            "output_tokens": result.model_output_tokens,
            "retrieval_count": result.retrieval_count,
            "source_ids": result.retrieved_source_ids,
            "model_latency_ms": result.latency_ms - result.retrieval_latency_ms - result.adapter_overhead_ms,
            "retrieval_latency_ms": result.retrieval_latency_ms,
            "total_latency_ms": result.latency_ms,
            "adapter_overhead_ms": result.adapter_overhead_ms,
            "epoch": result.epoch,
            "provider": result.provider,
            "context_truncation": result.truncated,
            "mode": result.mode,
            "turn": result.turn,
        })
        self._persist_config()
        if self.config.mode != "READ_ONLY":
            self.project.save()
