import copy
import json
from pathlib import Path

import pytest

from dsm.memory.report import render_explain_markdown


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
DANGEROUS_WORDING = ("tamper-proof", "verified truth", "proof of truth")


def _load_json_fixture(name: str):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _load_text_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_render_explain_markdown_matches_golden_report():
    payload = _load_json_fixture("agent_memory_explain_v1_ok.json")
    expected = _load_text_fixture("agent_memory_explain_v1_report.md")

    rendered = render_explain_markdown(payload)

    assert rendered == expected
    assert "# Agent Memory Audit Report" in rendered
    assert "## Trust Model / Limitations" in rendered
    assert "local tamper-evident" in rendered
    assert "does not prove factual truth" in rendered
    assert "not external anchoring" in rendered
    assert "v1:" in rendered
    assert "## Supporting Facts" in rendered
    assert "## Hypotheses" in rendered
    assert "## Inferences" in rendered
    assert "## Decision" in rendered
    assert all(wording not in rendered.lower() for wording in DANGEROUS_WORDING)


def test_render_explain_markdown_error_report_is_clean():
    payload = _load_json_fixture("agent_memory_explain_v1_error.json")

    rendered = render_explain_markdown(payload)

    assert "# Agent Memory Audit Report" in rendered
    assert "## Error" in rendered
    assert "- Code: `decision_not_found`" in rendered
    assert "- Message: Decision not found" in rendered
    assert "traceback" not in rendered.lower()
    assert "## Trust Model / Limitations" in rendered
    assert all(wording not in rendered.lower() for wording in DANGEROUS_WORDING)


def test_render_explain_markdown_displays_warnings():
    payload = _load_json_fixture("agent_memory_explain_v1_ok.json")
    payload["warnings"] = [
        {
            "code": "missing_dependency",
            "message": "Dependency not found: v1:missing",
            "ref": "v1:missing",
        },
        {
            "code": "depth_limit_reached",
            "message": "Traversal stopped at depth 1; some dependencies may remain unexplored.",
            "entry_hashes": ["v1:<hash>"],
        },
        {
            "code": "cycle_detected",
            "message": "Decision appears in its supporting chain; traversal stopped at requested depth.",
            "entry_hash": "v1:<hash>",
        },
    ]

    rendered = render_explain_markdown(payload)

    assert "`missing_dependency`" in rendered
    assert "`depth_limit_reached`" in rendered
    assert "`cycle_detected`" in rendered
    assert "Dependency not found" in rendered
    assert "Traversal stopped at depth 1" in rendered


def test_render_explain_markdown_confidence_none_is_explicit():
    payload = _load_json_fixture("agent_memory_explain_v1_ok.json")
    payload = copy.deepcopy(payload)
    payload["decision"]["confidence"] = None

    rendered = render_explain_markdown(payload)

    assert "- Confidence: not provided" in rendered
    assert "0.8 (self-estimate, not calibrated)" not in rendered


def test_render_explain_markdown_rejects_wrong_schema():
    payload = _load_json_fixture("agent_memory_explain_v1_ok.json")
    payload["schema_version"] = "agent_memory.explain.v2"

    with pytest.raises(ValueError, match="unsupported Agent Memory explain schema"):
        render_explain_markdown(payload)


def test_report_renderer_is_pure_json_to_markdown():
    source = (REPO_ROOT / "src/dsm/memory/report.py").read_text(encoding="utf-8")

    forbidden_fragments = (
        "Storage",
        "DSMReadRelay",
        "read_recent",
        "core.storage",
        "rr.relay",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source
