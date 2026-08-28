"""Assemble a bounded model-visible working set. Does not mutate Core."""

from __future__ import annotations

import re
from typing import Any

from hexashard.tokens import estimate_tokens

from .errors import ContextBudgetExceeded
from .models import AssembledContext

SYSTEM_INSTRUCTIONS = (
    "You are answering questions about a persistent HexaShard project. "
    "Use only the project context in this turn. Cite [SOURCE id | status] when "
    "stating a project fact. PROJECT WARNINGs mean a pin or source is not CURRENT. "
    "If no project source was retrieved, do not invent project facts from prior "
    "knowledge. Your reply is not a project source, pin, or accepted decision."
)

NO_SOURCE_SENTENCE = "No project source was retrieved for this claim."
_CONTENT_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.\-]{4,}")


def retrieval_adequate(query: str, fragments: list[dict[str, Any]]) -> bool:
    """True when a retrieved fragment shares a content token with the query.

    Core BM25 can return stopword hits (``the`` / ``is``). Adapter does not
    rescore; it only decides whether to warn that no adequate source was found.
    """
    qtoks = set(_CONTENT_TOKEN.findall(query.lower()))
    if not qtoks:
        return bool(fragments)
    for f in fragments:
        text = (f.get("text") or "").lower()
        title = (f.get("source_title") or "").lower()
        blob = text + " " + title
        if any(t in blob for t in qtoks):
            return True
    return False

# Drop order when over budget (lowest first). Never drop system, user, critical pins.
DROP_ORDER = ("secondary", "state", "fragments")
PROTECTED = ("system", "user", "critical_pins", "warnings", "objective")


def _tok(text: str) -> int:
    return estimate_tokens(text) if text else 0


def _format_fragment(frag: dict[str, Any]) -> str:
    sid = frag.get("source_id") or "UNKNOWN"
    status = frag.get("source_status") or "UNKNOWN"
    title = frag.get("source_title") or ""
    text = frag.get("text") or ""
    head = f"[SOURCE {sid} | {status}]"
    if title:
        head += f" {title}"
    return f"{head}\n{text}"


def _critical_pins_block(pins: list[dict[str, Any]]) -> str:
    crit = [p for p in pins if p.get("critical")]
    if not crit:
        return ""
    lines = ["CRITICAL PINS:"]
    for p in crit:
        lines.append(
            f"- {p.get('key')} = {p.get('value')} "
            f"(source {p.get('source_ref')}, status {p.get('status')})"
        )
    return "\n".join(lines)


def _warnings_block(
    pin_warnings: list[dict[str, Any]],
    ambiguities: list[dict[str, Any]],
    *,
    no_source: bool,
) -> tuple[str, list[str]]:
    notes: list[str] = []
    for w in pin_warnings:
        key = w.get("key") or w.get("pin_id")
        status = w.get("status")
        src = w.get("source_ref")
        detail = w.get("detail") or ""
        successor = ""
        if "superseded by" in detail:
            successor = " " + detail
        notes.append(
            f"Pin {key} points to {status} source {src}.{successor}".strip()
        )
    for a in ambiguities:
        notes.append(
            f"Ambiguity on claim {a.get('claim_key')}: sources {a.get('source_ids')}."
        )
    if no_source:
        notes.append(NO_SOURCE_SENTENCE)
    if not notes:
        return "", []
    body = "PROJECT WARNING:\n" + "\n".join(notes)
    return body, notes


def _objective_block(ctx: dict[str, Any]) -> str:
    parts = []
    if ctx.get("mission"):
        parts.append(f"Mission: {ctx['mission']}")
    if ctx.get("current_objective"):
        parts.append(f"Current objective: {ctx['current_objective']}")
    return "\n".join(parts)


def _state_block(ctx: dict[str, Any]) -> str:
    parts = []
    noncrit = [p for p in ctx.get("active_pins") or [] if not p.get("critical")]
    if noncrit:
        parts.append("Other pins:")
        for p in noncrit:
            parts.append(f"- {p.get('key')} = {p.get('value')} (source {p.get('source_ref')})")
    if ctx.get("current_summary"):
        parts.append("Summary:\n" + str(ctx["current_summary"]))
    if ctx.get("recent_decisions"):
        parts.append("Recent decisions: " + json_brief(ctx["recent_decisions"]))
    if ctx.get("open_questions"):
        parts.append("Open questions: " + json_brief(ctx["open_questions"]))
    return "\n".join(parts)


def json_brief(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def assemble(
    *,
    user_message: str,
    response_context: dict[str, Any],
    budget: int,
    system: str = SYSTEM_INSTRUCTIONS,
) -> AssembledContext:
    retrieved = list(response_context.get("retrieved") or [])
    source_ids: list[str] = []
    for f in retrieved:
        sid = f.get("source_id")
        if sid and sid not in source_ids:
            source_ids.append(sid)
    no_source = not retrieval_adequate(user_message, retrieved)
    warn_text, warn_notes = _warnings_block(
        list(response_context.get("pin_warnings") or []),
        list(response_context.get("ambiguities") or []),
        no_source=no_source,
    )

    required_frags = retrieved[:2]
    secondary_frags = retrieved[2:]
    sections = {
        "system": system.strip(),
        "user": "User message:\n" + user_message,
        "critical_pins": _critical_pins_block(list(response_context.get("active_pins") or [])),
        "warnings": warn_text,
        "objective": _objective_block(response_context),
        "fragments": "\n\n".join(_format_fragment(f) for f in required_frags),
        "state": _state_block(response_context),
        "secondary": "\n\n".join(_format_fragment(f) for f in secondary_frags),
    }

    dropped: list[str] = []
    truncated = False

    def total() -> int:
        return sum(_tok(v) for v in sections.values())

    if total() > budget:
        truncated = True
        for name in DROP_ORDER:
            if total() <= budget:
                break
            if sections[name]:
                sections[name] = ""
                dropped.append(name)

    # Drop required fragments one by one from the tail if still over.
    if total() > budget and required_frags:
        truncated = True
        kept = list(required_frags)
        while kept and total() > budget:
            kept.pop()
            sections["fragments"] = "\n\n".join(_format_fragment(f) for f in kept)
            if "fragments" not in dropped:
                dropped.append("fragments")
        source_ids = []
        for f in kept:
            sid = f.get("source_id")
            if sid and sid not in source_ids:
                source_ids.append(sid)
        for f in secondary_frags if sections["secondary"] else []:
            sid = f.get("source_id")
            if sid and sid not in source_ids:
                source_ids.append(sid)

    protected_cost = sum(_tok(sections[k]) for k in PROTECTED)
    if protected_cost > budget:
        raise ContextBudgetExceeded(
            f"protected context {protected_cost} exceeds model_context_budget {budget}"
        )
    if total() > budget:
        raise ContextBudgetExceeded(
            f"assembled context {total()} still exceeds model_context_budget {budget}"
        )

    project_parts = [
        sections[k] for k in
        ("critical_pins", "warnings", "objective", "fragments", "state", "secondary")
        if sections[k]
    ]
    project_block = "\n\n".join(project_parts)
    return AssembledContext(
        system=sections["system"],
        user=user_message,
        project_block=project_block,
        sections=sections,
        tokens=total(),
        truncated=truncated,
        dropped_sections=dropped,
        retrieved_source_ids=source_ids,
        authority_warnings=warn_notes,
        no_source_retrieved=no_source,
    )
