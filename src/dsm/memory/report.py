"""Markdown renderer for Agent Memory explain reports.

This module is a pure transform from the stable
``agent_memory.explain.v1`` JSON contract to Markdown. It intentionally does
not import or read DSM storage.
"""

from __future__ import annotations

from typing import Any


EXPLAIN_REPORT_SCHEMA_VERSION = "agent_memory.explain.v1"
TRUST_LIMITATIONS = [
    "This report is local tamper-evident only.",
    "It does not prove factual truth.",
    "It does not prove reasoning validity.",
    "It does not replace `dsm verify`.",
    "It is not external anchoring.",
    "It includes no witness, MMR, STH, or anchoring mechanism.",
]


def render_explain_markdown(explain_json: dict) -> str:
    """Render an ``agent_memory.explain.v1`` object as Markdown."""
    _validate_explain_json(explain_json)

    status = explain_json.get("status")
    if status == "ok":
        lines = _render_ok_report(explain_json)
    elif status == "error":
        lines = _render_error_report(explain_json)
    else:
        raise ValueError(f"unsupported explain status: {status!r}")

    return "\n".join(lines).rstrip() + "\n"


def _validate_explain_json(explain_json: dict) -> None:
    if not isinstance(explain_json, dict):
        raise TypeError("explain_json must be a dict")
    schema_version = explain_json.get("schema_version")
    if schema_version != EXPLAIN_REPORT_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported Agent Memory explain schema: {schema_version!r}"
        )


def _render_ok_report(report: dict[str, Any]) -> list[str]:
    query = report.get("query") or {}
    decision = report.get("decision") or {}
    chain = report.get("supporting_chain") or {}
    source_refs = report.get("source_refs") or []
    warnings = report.get("warnings") or []
    verification = report.get("verification") or {}

    lines = _render_header("ok") + [
        "## Query",
        f"- Decision hash: {_code(query.get('decision_hash'))}",
        f"- Shard: {_code(query.get('shard'))}",
        f"- Depth: {query.get('depth', 'not provided')}",
        "",
        "## Decision",
    ]
    lines.extend(_render_record_details(decision))
    lines.extend([
        "",
        "## Supporting Facts",
    ])
    lines.extend(_render_record_list(chain.get("facts") or [], "Fact"))
    lines.extend([
        "",
        "## Hypotheses",
    ])
    lines.extend(_render_record_list(chain.get("hypotheses") or [], "Hypothesis"))
    lines.extend([
        "",
        "## Inferences",
    ])
    lines.extend(_render_record_list(chain.get("inferences") or [], "Inference"))
    lines.extend([
        "",
        "## Source References",
    ])
    lines.extend(_render_source_refs(source_refs))
    lines.extend([
        "",
        "## Warnings",
    ])
    lines.extend(_render_warnings(warnings))
    lines.extend([
        "",
        "## Verification",
        f"- Local status: {verification.get('local_status', 'not provided')}",
        f"- Verification hint: {_code(verification.get('hint'))}",
        f"- Scope: {verification.get('scope', 'not provided')}",
        "",
        "## Trust Model / Limitations",
    ])
    lines.extend(f"- {item}" for item in TRUST_LIMITATIONS)
    return lines


def _render_error_report(report: dict[str, Any]) -> list[str]:
    query = report.get("query") or {}
    error = report.get("error") or {}

    lines = _render_header("error") + [
        "## Query",
        f"- Decision hash: {_code(query.get('decision_hash'))}",
        f"- Shard: {_code(query.get('shard'))}",
        f"- Depth: {query.get('depth', 'not provided')}",
        "",
        "## Error",
        f"- Error code: {_code(error.get('code'))}",
        f"- Error message: {error.get('message', 'not provided')}",
        "",
        "## Trust Model / Limitations",
    ]
    lines.extend(f"- {item}" for item in TRUST_LIMITATIONS)
    return lines


def _render_header(status: str) -> list[str]:
    return [
        "# Agent Memory Audit Report",
        "",
        f"- Contract: {_code(EXPLAIN_REPORT_SCHEMA_VERSION)}",
        f"- Status: {_code(status)}",
        "",
    ]


def _render_record_list(records: list[dict[str, Any]], label: str) -> list[str]:
    if not records:
        return ["- None"]

    lines: list[str] = []
    for index, record in enumerate(records, start=1):
        lines.append(f"### {label} {index}")
        lines.extend(_render_record_details(record))
        if index < len(records):
            lines.append("")
    return lines


def _render_record_details(record: dict[str, Any]) -> list[str]:
    lines = _render_statement(record.get("statement"))
    lines.extend([
        f"- Entry hash: {_code(record.get('entry_hash'))}",
        f"- Confidence: {_format_confidence(record.get('confidence'))}",
    ])

    depends_on = record.get("depends_on") or []
    lines.append("- Depends on:")
    if depends_on:
        lines.extend(f"  - {_code(ref)}" for ref in depends_on)
    else:
        lines.append("  - none")

    source_refs = record.get("source_refs") or []
    lines.append("- Source refs:")
    if source_refs:
        for ref in source_refs:
            lines.append(
                f"  - shard={_code(ref.get('shard'))} entry_hash={_code(ref.get('entry_hash'))}"
            )
    else:
        lines.append("  - none")
    return lines


def _render_statement(statement: Any) -> list[str]:
    text = "not provided" if statement is None or statement == "" else str(statement)
    escaped = text.replace("```", "`\u200b``")
    lines = ["- Statement:", "  ```text"]
    lines.extend(f"  {line}" for line in escaped.splitlines() or [""])
    lines.append("  ```")
    return lines


def _render_source_refs(source_refs: list[dict[str, Any]]) -> list[str]:
    if not source_refs:
        return ["- None"]
    return [
        (
            f"- {ref.get('owner_kind', 'entry')} {_code(ref.get('owner_entry_hash'))} "
            f"-> shard={_code(ref.get('shard'))} entry_hash={_code(ref.get('entry_hash'))}"
        )
        for ref in source_refs
    ]


def _render_warnings(warnings: list[dict[str, Any]]) -> list[str]:
    if not warnings:
        return ["- None"]

    lines: list[str] = []
    for warning in warnings:
        code = warning.get("code", "unknown_warning")
        message = warning.get("message", "not provided")
        lines.append(f"- {_code(code)}: {message}")
        for key in sorted(k for k in warning if k not in {"code", "message"}):
            value = warning[key]
            if isinstance(value, list):
                lines.append(f"  - {key}:")
                lines.extend(f"    - {_format_value(item)}" for item in value)
            else:
                lines.append(f"  - {key}: {_format_value(value)}")
    return lines


def _format_confidence(confidence: Any) -> str:
    if confidence is None:
        return "not provided"
    return f"{confidence} (self-estimate, not calibrated)"


def _format_value(value: Any) -> str:
    if isinstance(value, str) and value.startswith("v1:"):
        return _code(value)
    return str(value)


def _code(value: Any) -> str:
    if value is None or value == "":
        return "`not provided`"
    return f"`{value}`"
