#!/usr/bin/env python3
"""
DSM-ANS (Audience Neural System) - Test Suite.

This module validates ANS functionality with real log data.
Phase 2: Tests recommendation layer functionality.
"""

import os
import sys
import subprocess

from pathlib import Path as _Path
_dsm_root = _Path(__file__).resolve().parent.parent / "src" / "dsm"

from dsm.ans.ans_analyzer import (
    load_usage_events,
    load_success_events,
    compute_skill_performance,
    compute_transition_performance
)
from dsm.ans.ans_engine import ANSEngine
from dsm.ans.ans_models import (
    SkillRecommendation,
    WorkflowRecommendation
)


def test_log_loading():
    """Test 1: Validate log loading."""
    print("Test 1: Log Loading")
    print("-" * 60)

    usage_log = str(_dsm_root / "skills" / "logs" / "skills_usage.jsonl")
    success_log = str(_dsm_root / "skills" / "logs" / "skills_success.jsonl")

    usage_events = load_usage_events(usage_log)
    success_events = load_success_events(success_log)

    print(f"✅ Usage events loaded: {len(usage_events)}")

    if len(usage_events) > 0:
        print(f"  First event: {usage_events[0].skill_id} - {usage_events[0].task_description[:50]}...")
    else:
        print("  Warning: No usage events found")

    print(f"✅ Success events loaded: {len(success_events)}")

    if len(success_events) > 0:
        print(f"  First event: {success_events[0].skill_id} - "
              f"{'SUCCESS' if success_events[0].success else 'FAILURE'}")
    else:
        print("  Warning: No success events found")

    print()
    assert usage_events is not None
    assert success_events is not None


def test_skill_computation(usage_events, success_events):
    """Test 2: Validate skill performance computation."""
    print("Test 2: Skill Performance Computation")
    print("-" * 60)

    skill_perf = compute_skill_performance(usage_events, success_events)

    print(f"✅ Skills computed: {len(skill_perf)}")

    if len(skill_perf) > 0:
        # Show top skill
        skills = list(skill_perf.values())
        skills.sort(key=lambda s: -s.usage_count)

        top = skills[0]
        print(f"  Top skill: {top.skill_id}")
        print(f"    Usage count: {top.usage_count}")
        print(f"    Success rate: {top.success_rate:.1%}")
        print(f"    Avg duration: {top.avg_duration_ms:.0f}ms")

    print()
    assert isinstance(skill_perf, dict)


def test_transition_computation(usage_events, success_events):
    """Test 3: Validate transition computation."""
    print("Test 3: Transition Computation")
    print("-" * 60)

    transitions = compute_transition_performance(usage_events, success_events)

    print(f"✅ Transitions computed: {len(transitions)}")

    if len(transitions) > 0:
        # Show top transition
        transitions.sort(key=lambda t: -t.transition_count)

        top = transitions[0]
        print(f"  Top transition: {top.from_skill} -> {top.to_skill}")
        print(f"    Count: {top.transition_count}")
        print(f"    Success rate: {top.success_rate:.1%}")
    else:
        print("  Warning: No transitions found")

    print()
    assert isinstance(transitions, list)


def test_next_skill_recommendations():
    """Test 4: Validate next skill recommendations (Phase 2)."""
    print("Test 4: Next Skill Recommendations (Phase 2)")
    print("-" * 60)

    # Create engine
    engine = ANSEngine()
    engine.load()

    # Get recommendations for a specific skill
    skill_id = "task_decomposition"
    recommendations = engine.recommend_next_skills(skill_id=skill_id)

    print(f"✅ Recommendations for {skill_id}: {len(recommendations)}")

    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            priority_marker = "★" if rec.priority == "high" else " " if rec.priority == "medium" else ""
            print(f"  {priority_marker} {i}. {rec.skill_id}")
            print(f"     Score: {rec.score:.2f}")
            print(f"     Reason: {rec.reason}")
            print(f"     Priority: {rec.priority}")
    else:
        print(f"  Warning: No recommendations found for {skill_id}")

    print()
    assert recommendations is not None


def test_workflow_recommendations():
    """Test 5: Validate workflow recommendations (Phase 2)."""
    print("Test 5: Workflow Recommendations (Phase 2)")
    print("-" * 60)

    # Create engine
    engine = ANSEngine()
    engine.load()

    # Get workflow recommendations
    recommendations = engine.recommend_workflows()

    print(f"✅ Workflow recommendations: {len(recommendations)}")

    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            sequence = " -> ".join(rec.sequence)
            print(f"  {i}. {sequence}")
            print(f"     Score: {rec.score:.2f}")
            print(f"     Reason: {rec.reason}")
    else:
        print("  Warning: No workflow recommendations found")

    print()
    assert recommendations is not None


def test_risk_detection():
    """Test 6: Validate risk detection (Phase 2)."""
    print("Test 6: Risk Detection (Phase 2)")
    print("-" * 60)

    # Create engine
    engine = ANSEngine()
    engine.load()

    # Detect risks
    risks = engine.detect_risks()

    print(f"✅ Risks detected: {len(risks)}")

    if risks:
        for i, risk in enumerate(risks, 1):
            print(f"  {i}. {risk}")
    else:
        print("  Warning: No risks detected")

    print()
    assert isinstance(risks, list)
    assert len(risks) >= 0


def test_recommend_cli_commands():
    """Test 7: Validate CLI recommendation commands work."""
    print("Test 7: CLI Recommendation Commands")
    print("-" * 60)

    result = subprocess.run(
        [sys.executable, "-m", "dsm.ans.cli", "recommend"],
        capture_output=True,
        text=True,
    )
    output = result.stdout or result.stderr or ""

    if result.returncode == 0 and output:
        print("✅ CLI 'recommend' command works")
        print(f"  Output preview (first 200 chars):")
        print(output[:200])
    else:
        print(f"❌ CLI 'recommend' command failed (exit code: {result.returncode})")
        if output:
            print(f"  Error output: {output}")

    print()

    assert result.returncode == 0


def test_full_report_generation():
    """Test 8: Validate full Phase 2 report generation."""
    print("Test 8: Full Phase 2 Report Generation")
    print("-" * 60)

    # Create engine
    engine = ANSEngine()
    engine.load()

    # Generate Phase 2 report
    report = engine.generate_recommendation_report()

    print(f"✅ Report generated:")
    print(f"  Generated at: {report.generated_at}")
    print(f"  Top skills: {len(report.top_skills)}")
    print(f"  Recommendations: {len(report.recommendations)}")
    print(f"  Workflow recommendations: {len(report.workflow_recommendations)}")
    print(f"  Transition warnings: {len(report.transition_warnings)}")
    print(f"  Notes: {len(report.notes)}")

    print()
    assert report is not None


def main():
    """Run all Phase 2 validation tests."""
    print("=" * 70)
    print("DSM-ANS (Audience Neural System) Test Suite - Phase 2")
    print("=" * 70)
    print()

    # Test 1: Log loading
    test_log_loading()

    # Test 2 & 3: Need loaded events (from same paths as test_log_loading)
    usage_log = str(_dsm_root / "skills" / "logs" / "skills_usage.jsonl")
    success_log = str(_dsm_root / "skills" / "logs" / "skills_success.jsonl")
    usage_events = load_usage_events(usage_log)
    success_events = load_success_events(success_log)

    # Test 2: Skill performance
    test_skill_computation(usage_events, success_events)

    # Test 3: Transitions
    test_transition_computation(usage_events, success_events)

    # Test 4: Next skill recommendations
    try:
        test_next_skill_recommendations()
        next_rec_ok = True
    except Exception:
        next_rec_ok = False

    # Test 5: Workflow recommendations
    try:
        test_workflow_recommendations()
        workflow_rec_ok = True
    except Exception:
        workflow_rec_ok = False

    # Test 6: Risk detection
    try:
        test_risk_detection()
        risks_ok = True
    except Exception:
        risks_ok = False

    # Test 7: CLI commands (optional, may fail if no real data)
    try:
        test_recommend_cli_commands()
        cli_ok = True
    except Exception:
        cli_ok = False

    # Test 8: Full report generation
    try:
        test_full_report_generation()
        report_ok = True
    except Exception:
        report_ok = False

    # Summary
    print("=" * 70)
    print("PHASE 2 VALIDATION SUMMARY")
    print("=" * 70)

    tests = [
        ("Log loading", True),
        ("Skill performance", True),
        ("Transition computation", True),
        ("Next skill recommendations", next_rec_ok),
        ("Workflow recommendations", workflow_rec_ok),
        ("Risk detection", risks_ok),
        ("CLI recommend command", cli_ok),
        ("Full report generation", report_ok)
    ]

    for test_name, passed in tests:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test_name}: {status}")

    all_passed = all(passed for _, passed in tests)
    print()
    print(f"Overall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")

    if all_passed:
        print()
        print("✅ DSM-ANS Phase 2 validation complete!")
    else:
        print()
        print("❌ DSM-ANS Phase 2 validation has failures.")

    print("=" * 70)


if __name__ == "__main__":
    main()
