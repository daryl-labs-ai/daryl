"""Context builder — daryl port of ``dsm_v0.context.context``.

Faithful port. Routing rules, budget strategy, section order,
provenance rebuild semantics, and ``build_prompt_context`` rendering
are identical to dsm_v0. Only backend calls change:

- ``dsm_v0.recall.search_memory`` → :func:`dsm.recall.search_memory`
- ``dsm_v0.provenance.build_provenance`` → :func:`dsm.provenance.build_provenance`

Section semantics, trim order, and the rationale for the two trim
invariants (provenance rebuild post-trim via :func:`dsm.provenance.build_provenance`,
and "drop just enough" rather than "fully drain") are documented
inline in :func:`_trim_to_budget` and :func:`_bucket_matches`.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    # Phase 7c.3 (B2): Storage is referenced ONLY for type annotations
    # in the public API (build_context, build_prompt_context). No runtime
    # use — instantiation is delegated to downstream readers
    # (search_memory, build_provenance), which receive `data_dir` and
    # handle the fallback themselves. The lint (B3) is TYPE_CHECKING-aware
    # and does not flag this import.
    from ..core.storage import Storage

from ..provenance import build_provenance
from ..recall import (
    STATUS_OUTDATED,
    STATUS_STILL_RELEVANT,
    STATUS_SUPERSEDED,
    STATUS_UNCERTAIN,
    search_memory,
)

__all__ = [
    "build_context",
    "build_prompt_context",
    "SECTION_ORDER",
    "DEFAULT_MAX_TOKENS",
]

DEFAULT_MAX_TOKENS = 8000
_PROMPT_DEFAULT_MAX_TOKENS = 4000

SECTION_ORDER: tuple[str, ...] = (
    "verified_facts",
    "working_state",
    "recent_relevant_events",
    "past_session_recall",
    "uncertain_or_superseded",
    "provenance",
)

_TRIM_PRIORITY: dict[str, int] = {
    "uncertain_or_superseded": 5,
    "past_session_recall": 4,
    "recent_relevant_events": 3,
    "working_state": 2,
    "verified_facts": 1,
    "provenance": 0,  # never dropped
}

_RECENT_WINDOW_SECONDS = 24 * 3600


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def _approx_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _item_tokens(item: dict[str, Any]) -> int:
    content = item.get("content") or ""
    meta_overhead = 20
    return _approx_tokens(content) + meta_overhead


def _provenance_tokens(prov: dict[str, Any]) -> int:
    if not prov:
        return 0
    total = 0
    for v in prov.values():
        if isinstance(v, (list, tuple)):
            total += sum(_approx_tokens(str(x)) for x in v)
        else:
            total += _approx_tokens(str(v))
    return total + 30


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------


def _bucket_matches(
    recall_result: dict[str, Any],
    now_seconds: float,
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "verified_facts": list(recall_result.get("verified_claims") or []),
        "working_state": [],
        "recent_relevant_events": [],
        "past_session_recall": [],
        "uncertain_or_superseded": [],
    }

    def is_unreliable(status: str) -> bool:
        return status in (STATUS_SUPERSEDED, STATUS_OUTDATED, STATUS_UNCERTAIN)

    current = recall_result.get("current_session") or {}
    for m in current.get("matches") or []:
        status = m.get("time_status") or STATUS_STILL_RELEVANT
        if is_unreliable(status):
            buckets["uncertain_or_superseded"].append(m)
        else:
            buckets["working_state"].append(m)

    for m in recall_result.get("past_session_recall") or []:
        status = m.get("time_status") or STATUS_STILL_RELEVANT
        if is_unreliable(status):
            buckets["uncertain_or_superseded"].append(m)
            continue
        ts = float(m.get("timestamp") or 0.0)
        age = max(0.0, now_seconds - ts) if ts > 0 else float("inf")
        if age <= _RECENT_WINDOW_SECONDS:
            buckets["recent_relevant_events"].append(m)
        else:
            buckets["past_session_recall"].append(m)

    return buckets


# ---------------------------------------------------------------------------
# Budget trimming
# ---------------------------------------------------------------------------


def _count_tokens(
    buckets: dict[str, list[dict[str, Any]]],
    provenance: Optional[dict[str, Any]],
) -> int:
    total = 0
    for items in buckets.values():
        total += 15
        for item in items:
            total += _item_tokens(item)
    if provenance:
        total += _provenance_tokens(provenance)
    return total


def _all_items(buckets: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for items in buckets.values():
        out.extend(items)
    return out


def _trim_to_budget(
    buckets: dict[str, list[dict[str, Any]]],
    include_provenance: bool,
    storage: Optional[Storage],
    data_dir: str,
    max_tokens: int,
    now_seconds: float,
) -> tuple[dict[str, list[dict[str, Any]]], Optional[dict[str, Any]], int, bool]:
    hard_cap = max(0, int(max_tokens * 0.95))
    trimmed = {k: list(v) for k, v in buckets.items()}
    was_trimmed = False

    def current_prov() -> Optional[dict[str, Any]]:
        if not include_provenance:
            return None
        return build_provenance(
            items=_all_items(trimmed),
            storage=storage,
            data_dir=data_dir,
            verify=False,
            now=now_seconds,
        )

    drop_order = sorted(
        trimmed.keys(),
        key=lambda k: _TRIM_PRIORITY.get(k, 99),
        reverse=True,
    )

    for section in drop_order:
        while (
            _count_tokens(trimmed, current_prov()) > hard_cap
            and trimmed[section]
        ):
            trimmed[section].pop()
            was_trimmed = True
        if _count_tokens(trimmed, current_prov()) <= hard_cap:
            break

    final_prov = current_prov()
    return trimmed, final_prov, _count_tokens(trimmed, final_prov), was_trimmed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_context(
    query: str,
    storage: Optional[Storage] = None,
    data_dir: str = "data",
    session_id: Optional[str] = None,
    shard_ids: Optional[list[str]] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    include_current_session: bool = False,
    include_provenance: bool = True,
    max_results: int = 50,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """Build a structured context pack from daryl memory.

    Same output shape as :func:`dsm_v0.context.build_context`. Only the
    backend (recall + provenance) changes.
    """
    now_seconds = float(now) if now is not None else time.time()

    # Phase 7c.3 (B2): Storage instantiation is delegated to downstream
    # readers (search_memory, build_provenance). Both already perform the
    # `if storage is None: storage = Storage(data_dir=data_dir)` fallback
    # internally, so we propagate `data_dir` alongside `storage`. When
    # `storage` is None, this may result in two Storage instances per call
    # (one in search_memory, one in build_provenance) — but they share the
    # same data_dir and remain functionally equivalent. This trade-off
    # eliminates the runtime Storage import from context/builder.py and
    # lets it leave KNOWN_READER_VIOLATIONS.

    recall_result = search_memory(
        query,
        storage=storage,
        data_dir=data_dir,
        session_id=session_id,
        shard_ids=shard_ids,
        across_sessions=True,
        max_results=max_results,
        include_current_session=include_current_session,
        include_provenance=include_provenance,
        now=now_seconds,
    )

    buckets = _bucket_matches(recall_result, now_seconds)
    trimmed_buckets, provenance, token_estimate, was_trimmed = _trim_to_budget(
        buckets,
        include_provenance=include_provenance,
        storage=storage,
        data_dir=data_dir,
        max_tokens=max_tokens,
        now_seconds=now_seconds,
    )

    sections = {
        name: trimmed_buckets.get(name, [])
        for name in SECTION_ORDER
        if name != "provenance"
    }

    total_items = sum(len(v) for v in sections.values())
    current = recall_result.get("current_session") or {}
    current_sid = current.get("session_id")
    digest = (
        f"{total_items} item(s) across {len(sections)} section(s) "
        f"for query={query!r}"
        + (f" (current={current_sid})" if current_sid else "")
        + (" [trimmed]" if was_trimmed else "")
    )

    return {
        "query": query,
        "sections": sections,
        "provenance": provenance,
        "token_estimate": token_estimate,
        "trimmed": was_trimmed,
        "digest": digest,
    }


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


_SECTION_LABELS: dict[str, str] = {
    "verified_facts": "## Verified facts",
    "working_state": "## Working state (current session)",
    "recent_relevant_events": "## Recent relevant events (\u226424h)",
    "past_session_recall": "## Past session recall",
    "uncertain_or_superseded": "## Uncertain / superseded",
}


def _render_item(item: dict[str, Any]) -> str:
    sid = item.get("session_id") or "?"
    etype = item.get("event_type") or "?"
    itype = item.get("type") or "?"
    status = item.get("time_status") or "?"
    score = item.get("relevance_score")
    content = (item.get("content") or "").strip()
    header = f"- [{sid}] {etype} \u00b7 {itype}/{status}"
    if score is not None:
        header += f" \u00b7 score={score}"
    return f"{header}\n  {content}" if content else header


def _render_provenance(prov: dict[str, Any]) -> str:
    lines = ["## Provenance"]
    lines.append(f"- integrity: {prov.get('integrity')}")
    lines.append(f"- trust_level: {prov.get('trust_level')}")
    lines.append(f"- record_count: {prov.get('record_count')}")
    lines.append(f"- broken_chains: {prov.get('broken_chains')}")
    oldest = prov.get("oldest_entry_age_days")
    if oldest is not None:
        lines.append(f"- oldest_entry_age_days: {oldest}")
    shards = prov.get("source_shards") or []
    if shards:
        lines.append(f"- source_shards: {', '.join(shards)}")
    hint = prov.get("verification_hint")
    if hint:
        lines.append(f"- verification_hint: {hint}")
    return "\n".join(lines)


def build_prompt_context(
    query: str,
    storage: Optional[Storage] = None,
    data_dir: str = "data",
    session_id: Optional[str] = None,
    shard_ids: Optional[list[str]] = None,
    max_tokens: int = _PROMPT_DEFAULT_MAX_TOKENS,
    style: str = "assistant",
    audience: str = "agent",
    include_current_session: bool = False,
    include_provenance: bool = True,
    max_results: int = 50,
    now: Optional[float] = None,
) -> str:
    """Render a compact prompt-ready context string.

    ``style`` and ``audience`` are accepted for forward compat but do
    not branch in V0 (same as dsm_v0).
    """
    _ = style, audience

    ctx = build_context(
        query,
        storage=storage,
        data_dir=data_dir,
        session_id=session_id,
        shard_ids=shard_ids,
        max_tokens=max_tokens,
        include_current_session=include_current_session,
        include_provenance=include_provenance,
        max_results=max_results,
        now=now,
    )

    lines: list[str] = [f"# DSM context for query: {query!r}"]
    for name in SECTION_ORDER:
        if name == "provenance":
            continue
        items = ctx["sections"].get(name) or []
        if not items:
            continue
        lines.append("")
        lines.append(_SECTION_LABELS.get(name, f"## {name}"))
        for it in items:
            lines.append(_render_item(it))

    if include_provenance and ctx.get("provenance"):
        lines.append("")
        lines.append(_render_provenance(ctx["provenance"]))

    if ctx.get("trimmed"):
        lines.append("")
        lines.append("_[context trimmed to fit token budget]_")

    rendered = "\n".join(lines)

    char_cap = max_tokens * 4
    if len(rendered) > char_cap:
        rendered = rendered[:char_cap].rstrip() + "\n_[truncated]_"

    return rendered
