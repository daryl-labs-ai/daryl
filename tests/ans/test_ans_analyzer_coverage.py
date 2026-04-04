"""
Tests for ans_analyzer.py — targeting uncovered lines.

Covers:
  - load_usage_events / load_success_events (file I/O, error handling)
  - compute_skill_performance (failure tracking, duration)
  - recommend_best_next_skills (scoring logic)
  - detect_weak_skills / detect_weak_transitions
  - recommend_workflows (chain reconstruction)
  - ANSAnalyzer.analyze (RR metadata grouping)
"""

import json
import os
import tempfile

import pytest

from dsm.ans.ans_models import (
    UsageEvent,
    SuccessEvent,
    SkillPerformance,
    TransitionPerformance,
)
from dsm.ans.ans_analyzer import (
    load_usage_events,
    load_success_events,
    compute_skill_performance,
    compute_transition_performance,
    recommend_best_next_skills,
    detect_weak_skills,
    detect_weak_transitions,
    recommend_workflows,
    ANSAnalyzer,
)


# ---------------------------------------------------------------------------
# load_usage_events
# ---------------------------------------------------------------------------

class TestLoadUsageEvents:
    def test_load_from_valid_jsonl(self, tmp_path):
        p = tmp_path / "usage.jsonl"
        events = [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "event_type": "skill_usage",
                "task_description": "do stuff",
                "skill_id": "s1",
                "skill_name": "domain1",
            },
            {
                "timestamp": "2026-01-01T00:01:00Z",
                "event_type": "skill_usage",
                "task_description": "do more",
                "skill_id": "s2",
                "skill_name": "domain2",
            },
        ]
        p.write_text("\n".join(json.dumps(e) for e in events) + "\n")

        result = load_usage_events(str(p))
        assert len(result) == 2
        assert isinstance(result[0], UsageEvent)
        assert result[0].skill_id == "s1"
        assert result[1].skill_id == "s2"

    def test_returns_empty_for_missing_file(self):
        result = load_usage_events("/nonexistent/path/usage.jsonl")
        assert result == []

    def test_skips_invalid_json_lines(self, tmp_path):
        p = tmp_path / "usage.jsonl"
        good = json.dumps({
            "timestamp": "t",
            "event_type": "skill_usage",
            "task_description": "d",
            "skill_id": "s1",
            "skill_name": "n",
        })
        p.write_text(good + "\nNOT_JSON\n" + good + "\n")
        result = load_usage_events(str(p))
        assert len(result) == 2

    def test_skips_unexpected_structure(self, tmp_path):
        p = tmp_path / "usage.jsonl"
        bad = json.dumps({"unexpected": True})
        good = json.dumps({
            "timestamp": "t",
            "event_type": "skill_usage",
            "task_description": "d",
            "skill_id": "s1",
            "skill_name": "n",
        })
        p.write_text(bad + "\n" + good + "\n")
        result = load_usage_events(str(p))
        # Should have at least the good one
        assert len(result) >= 1

    def test_empty_file(self, tmp_path):
        p = tmp_path / "usage.jsonl"
        p.write_text("")
        result = load_usage_events(str(p))
        assert result == []


# ---------------------------------------------------------------------------
# load_success_events
# ---------------------------------------------------------------------------

class TestLoadSuccessEvents:
    def test_load_from_valid_jsonl(self, tmp_path):
        p = tmp_path / "success.jsonl"
        events = [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "event_type": "skill_success",
                "task_description": "do stuff",
                "skill_id": "s1",
                "skill_name": "domain1",
                "success": True,
                "duration_ms": 100,
                "notes": None,
            },
            {
                "timestamp": "2026-01-01T00:01:00Z",
                "event_type": "skill_success",
                "task_description": "do more",
                "skill_id": "s2",
                "skill_name": "domain2",
                "success": False,
                "duration_ms": 300,
                "notes": "timeout",
            },
        ]
        p.write_text("\n".join(json.dumps(e) for e in events) + "\n")

        result = load_success_events(str(p))
        assert len(result) == 2
        assert isinstance(result[0], SuccessEvent)
        assert result[0].success is True
        assert result[1].success is False

    def test_returns_empty_for_missing_file(self):
        result = load_success_events("/nonexistent/success.jsonl")
        assert result == []

    def test_skips_invalid_json_lines(self, tmp_path):
        p = tmp_path / "success.jsonl"
        good = json.dumps({
            "timestamp": "t",
            "event_type": "skill_success",
            "task_description": "d",
            "skill_id": "s1",
            "skill_name": "n",
            "success": True,
            "duration_ms": 50,
            "notes": None,
        })
        p.write_text("BAD_LINE\n" + good + "\n")
        result = load_success_events(str(p))
        assert len(result) == 1

    def test_empty_file(self, tmp_path):
        p = tmp_path / "success.jsonl"
        p.write_text("")
        result = load_success_events(str(p))
        assert result == []


# ---------------------------------------------------------------------------
# compute_skill_performance — failure tracking, duration averaging
# ---------------------------------------------------------------------------

class TestComputeSkillPerformance:
    def test_mixed_success_and_failure(self):
        usage = [
            UsageEvent("t1", "skill_usage", "d", "s1", "n"),
            UsageEvent("t2", "skill_usage", "d", "s1", "n"),
            UsageEvent("t3", "skill_usage", "d", "s1", "n"),
        ]
        success = [
            SuccessEvent("t1", "skill_success", "d", "s1", "n", True, 100, None),
            SuccessEvent("t2", "skill_success", "d", "s1", "n", False, 200, None),
            SuccessEvent("t3", "skill_success", "d", "s1", "n", True, 300, None),
        ]
        perf = compute_skill_performance(usage, success)
        assert "s1" in perf
        s = perf["s1"]
        assert s.usage_count == 3
        assert s.success_count == 2
        assert s.failure_count == 1
        assert abs(s.success_rate - 2 / 3) < 0.01

    def test_empty_inputs(self):
        perf = compute_skill_performance([], [])
        assert perf == {}

    def test_multiple_skills(self):
        usage = [
            UsageEvent("t1", "skill_usage", "d", "s1", "n"),
            UsageEvent("t2", "skill_usage", "d", "s2", "n"),
        ]
        success = [
            SuccessEvent("t1", "skill_success", "d", "s1", "n", True, 100, None),
            SuccessEvent("t2", "skill_success", "d", "s2", "n", False, 200, None),
        ]
        perf = compute_skill_performance(usage, success)
        assert len(perf) >= 2
        assert perf["s1"].success_rate == 1.0
        assert perf["s2"].failure_count >= 1


# ---------------------------------------------------------------------------
# recommend_best_next_skills
# ---------------------------------------------------------------------------

class TestRecommendBestNextSkills:
    def _build_perf_and_transitions(self):
        perf = {
            "s1": SkillPerformance("s1", 10, 9, 1, 0.9, 100),
            "s2": SkillPerformance("s2", 8, 6, 2, 0.75, 150),
            "s3": SkillPerformance("s3", 5, 1, 4, 0.2, 300),
        }
        transitions = [
            TransitionPerformance("s1", "s2", 5, 0.8),
            TransitionPerformance("s2", "s3", 3, 0.4),
            TransitionPerformance("s1", "s3", 2, 0.3),
        ]
        return perf, transitions

    def test_returns_recommendations(self):
        perf, trans = self._build_perf_and_transitions()
        recs = recommend_best_next_skills(perf, trans)
        assert isinstance(recs, list)
        assert len(recs) > 0

    def test_recommendations_have_required_fields(self):
        perf, trans = self._build_perf_and_transitions()
        recs = recommend_best_next_skills(perf, trans)
        for r in recs:
            assert hasattr(r, "skill_id")
            assert hasattr(r, "score")
            assert hasattr(r, "priority")
            assert r.priority in ("high", "medium", "low")

    def test_empty_inputs(self):
        recs = recommend_best_next_skills({}, [])
        assert recs == []


# ---------------------------------------------------------------------------
# detect_weak_skills / detect_weak_transitions
# ---------------------------------------------------------------------------

class TestDetectWeakSkills:
    def test_detects_below_threshold(self):
        perf = {
            "good": SkillPerformance("good", 10, 9, 1, 0.9, 100),
            "bad": SkillPerformance("bad", 10, 3, 7, 0.3, 200),
        }
        weak = detect_weak_skills(perf, threshold=0.7)
        assert "bad" in weak
        assert "good" not in weak

    def test_empty_input(self):
        assert detect_weak_skills({}) == []

    def test_custom_threshold(self):
        perf = {
            "mid": SkillPerformance("mid", 10, 6, 4, 0.6, 100),
        }
        assert detect_weak_skills(perf, threshold=0.5) == []
        assert "mid" in detect_weak_skills(perf, threshold=0.7)


class TestDetectWeakTransitions:
    def test_detects_weak_transitions(self):
        transitions = [
            TransitionPerformance("a", "b", 10, 0.2),
            TransitionPerformance("b", "c", 10, 0.8),
        ]
        warnings = detect_weak_transitions(transitions, threshold=0.5)
        assert len(warnings) >= 1
        w = warnings[0]
        assert hasattr(w, "from_skill")
        assert hasattr(w, "recommendation_type")

    def test_categorizes_avoid_vs_best_next(self):
        transitions = [
            TransitionPerformance("a", "b", 10, 0.1),  # < 0.3 → avoid
            TransitionPerformance("c", "d", 10, 0.4),  # >= 0.3 → best_next
        ]
        warnings = detect_weak_transitions(transitions, threshold=0.5)
        types = {w.recommendation_type for w in warnings}
        assert "avoid_skill" in types or "best_next_skill" in types

    def test_empty_input(self):
        assert detect_weak_transitions([]) == []


# ---------------------------------------------------------------------------
# recommend_workflows
# ---------------------------------------------------------------------------

class TestRecommendWorkflows:
    def test_returns_workflows(self):
        perf = {
            "s1": SkillPerformance("s1", 10, 9, 1, 0.9, 100),
            "s2": SkillPerformance("s2", 8, 7, 1, 0.875, 150),
            "s3": SkillPerformance("s3", 5, 4, 1, 0.8, 200),
        }
        transitions = [
            TransitionPerformance("s1", "s2", 5, 0.8),
            TransitionPerformance("s2", "s3", 4, 0.7),
        ]
        recs = recommend_workflows(perf, transitions)
        assert isinstance(recs, list)
        assert len(recs) > 0

    def test_workflow_has_sequence(self):
        perf = {
            "s1": SkillPerformance("s1", 10, 9, 1, 0.9, 100),
            "s2": SkillPerformance("s2", 8, 7, 1, 0.875, 150),
        }
        transitions = [
            TransitionPerformance("s1", "s2", 5, 0.9),
        ]
        recs = recommend_workflows(perf, transitions)
        for r in recs:
            assert hasattr(r, "sequence")
            assert len(r.sequence) >= 1
            assert hasattr(r, "score")

    def test_empty_inputs(self):
        recs = recommend_workflows({}, [])
        assert recs == []


# ---------------------------------------------------------------------------
# ANSAnalyzer
# ---------------------------------------------------------------------------

class TestANSAnalyzer:
    def test_analyze_groups_by_event_type(self):
        analyzer = ANSAnalyzer()
        records = [
            {"event_type": "skill_usage", "skill_id": "s1"},
            {"event_type": "skill_usage", "skill_id": "s2"},
            {"event_type": "skill_success", "skill_id": "s1"},
        ]
        result = analyzer.analyze(records)
        assert isinstance(result, dict)
        assert "skill_usage" in result
        assert "skill_success" in result

    def test_analyze_empty(self):
        analyzer = ANSAnalyzer()
        result = analyzer.analyze([])
        assert isinstance(result, dict)
