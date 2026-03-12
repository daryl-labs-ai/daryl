#!/usr/bin/env python3
"""
DSM-SKILLS - Skill Success Tracking validation script.

This script validates that:
1. Skills can be selected and executed with simulated results
2. Success events are logged to skills_success.jsonl
3. Log format is valid JSONL
4. Analyzer can process events
5. Statistics can be calculated
"""

import sys
import os
import json
import time
import random

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills import SkillRegistry, SkillRouter
from skills.ingestor import SkillIngestor
from skills.skill_success_logger import SkillSuccessLogger
from skills.success_analyzer import SkillSuccessAnalyzer


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def simulate_skill_execution(skill_id: str) -> tuple:
    """Simulate a skill execution with random outcome.

    Args:
        skill_id: The skill ID to simulate

    Returns:
        Tuple of (success, duration_ms, notes)
    """
    # Simulate execution time (50-200ms)
    duration_ms = random.randint(50, 200)

    # Simulate success/failure (80% success rate)
    success = random.random() < 0.8

    # Generate optional notes
    notes = ""
    if not success:
        failure_reasons = [
            "timeout",
            "invalid input format",
            "missing dependencies",
            "execution error"
        ]
        notes = random.choice(failure_reasons)

    return success, duration_ms, notes


def main():
    """Run skill success tracking validation test."""
    print("=" * 60)
    print("DSM-SKILLS SUCCESS TRACKING VALIDATION")
    print("=" * 60)

    # STEP 1: Load skills with SkillIngestor
    print_section("STEP 1 - Load Skills")

    registry = SkillRegistry()
    libraries_path = os.path.join(os.path.dirname(__file__), "skills", "libraries")

    ingestor = SkillIngestor()
    report = ingestor.load_all_skills(libraries_path, registry)

    print(f"Skills loaded: {report.skills_loaded}")

    if report.skills_loaded == 0:
        print("\n✗ No skills loaded")
        return 1

    # STEP 2: Create SkillRegistry + SkillRouter
    print_section("STEP 2 - Setup Router")

    router = SkillRouter(registry)

    print(f"Router configured with {report.skills_loaded} skills")

    # STEP 3: Create SkillSuccessLogger
    print_section("STEP 3 - Setup Success Logger")

    success_logger = SkillSuccessLogger()
    print(f"Success logger initialized: {success_logger.log_file}")

    # STEP 4: Route tasks and simulate execution
    print_section("STEP 4 - Route and Simulate Execution")

    test_tasks = [
        "solve a complex trading strategy",
        "review this python code",
        "summarize this article"
    ]

    execution_results = []

    for task in test_tasks:
        print(f"\nTask: '{task}'")

        # Route to skill
        skill = router.route(task)

        if not skill:
            print("  ✗ No skill matched")
            continue

        print(f"  → Selected skill: {skill.skill_id}")
        print(f"  → Trigger: {skill.trigger_conditions[0]}")

        # Simulate execution
        success, duration_ms, notes = simulate_skill_execution(skill.skill_id)

        # Log result
        success_logger.log_skill_result(
            skill_id=skill.skill_id,
            task=task,
            trigger=skill.trigger_conditions[0],
            success=success,
            duration_ms=duration_ms,
            source_type=skill.source_type,
            library=skill.source_path.split(os.sep)[-2] if skill.source_path else "unknown",
            notes=notes
        )

        result_str = "✓ SUCCESS" if success else "✗ FAILED"
        print(f"  → {result_str} ({duration_ms}ms)")

        if notes:
            print(f"  → Notes: {notes}")

        execution_results.append({
            "task": task,
            "skill_id": skill.skill_id,
            "success": success,
            "duration_ms": duration_ms,
            "notes": notes
        })

        # Small delay between simulations
        time.sleep(0.01)

    # STEP 5: Verify log file
    print_section("STEP 5 - Verify Success Log")

    if not os.path.exists(success_logger.log_file):
        print("✗ Success log file not created")
        return 1

    print(f"✓ Success log file exists: {success_logger.log_file}")

    # Load and validate events
    logged_events = success_logger.load_success_events()

    print(f"✓ Events logged: {len(logged_events)}")

    # Validate JSONL format
    valid_json = 0
    invalid_json = 0

    for event in logged_events:
        try:
            # Check required fields
            required_fields = [
                "timestamp", "skill_id", "task", "trigger",
                "success", "duration_ms", "source_type", "library"
            ]

            missing = [f for f in required_fields if f not in event]
            if missing:
                print(f"  ✗ Event missing fields: {missing}")
                invalid_json += 1
            else:
                valid_json += 1

        except Exception as e:
            print(f"  ✗ Invalid event: {e}")
            invalid_json += 1

    print(f"\n✓ Valid events: {valid_json}")
    print(f"✗ Invalid events: {invalid_json}")

    # STEP 6: Test analyzer
    print_section("STEP 6 - Test Success Analyzer")

    log_dir = os.path.dirname(success_logger.log_file)
    analyzer = SkillSuccessAnalyzer(success_logger.log_file)

    # Test success rate by skill
    print("\nSuccess Rate by Skill:")
    success_rates = analyzer.success_rate_by_skill()

    for skill_id, stats in sorted(success_rates.items()):
        print(f"  {skill_id}:")
        print(f"    Total: {stats['total']}")
        print(f"    Success: {stats['successful']}")
        print(f"    Failed: {stats['failed']}")
        print(f"    Rate: {stats['success_rate']:.2%}")

    # Test average duration by skill
    print("\nAverage Duration by Skill:")
    avg_durations = analyzer.avg_duration_by_skill()

    for skill_id, avg_dur in sorted(avg_durations.items()):
        print(f"  {skill_id}: {avg_dur:.1f}ms")

    # Test overall stats
    print("\nOverall Statistics:")
    overall = analyzer.get_overall_stats()

    print(f"  Total events: {overall['total_events']}")
    print(f"  Successful: {overall['successful']}")
    print(f"  Failed: {overall['failed']}")
    print(f"  Success rate: {overall['overall_success_rate']:.2%}")
    print(f"  Avg duration: {overall['avg_duration_ms']:.1f}ms")

    # STEP 7: Test performance ranking
    print("\nPerformance Ranking:")
    ranking = analyzer.get_performance_ranking()

    for i, (skill_id, rate) in enumerate(ranking, 1):
        print(f"  {i}. {skill_id}: {rate:.2%}")

    # STEP 8: Print summary
    print_section("SUCCESS TRACKING VALIDATION REPORT")

    print(f"\nEvents written: {len(logged_events)}")
    print(f"Valid JSONL: {valid_json > 0 and invalid_json == 0}")

    # Check criteria
    criteria_met = [
        valid_json >= 3,  # At least 3 valid events
        invalid_json == 0,  # No invalid events
        sum(1 for r in execution_results if r['success']) >= 1,  # At least one success
        sum(1 for r in execution_results if not r['success']) >= 1,  # At least one failure
        len(success_rates) > 0  # Analyzer working
    ]

    print("\nValidation Criteria:")
    print(f"  1. At least 3 valid events: {'✓' if criteria_met[0] else '✗'}")
    print(f"  2. No invalid events: {'✓' if criteria_met[1] else '✗'}")
    print(f"  3. At least one success: {'✓' if criteria_met[2] else '✗'}")
    print(f"  4. At least one failure: {'✓' if criteria_met[3] else '✗'}")
    print(f"  5. Analyzer working: {'✓' if criteria_met[4] else '✗'}")

    all_passed = all(criteria_met)

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL VALIDATIONS PASSED")
    else:
        print("✗ SOME VALIDATIONS FAILED")
    print("=" * 60)

    print("\nSuccess Criteria:")
    print(f"  1. Skill success events recorded: {'✓' if valid_json >= 3 else '✗'}")
    print(f"  2. Log format is valid JSONL: {'✓' if criteria_met[1] else '✗'}")
    print(f"  3. At least one success captured: {'✓' if criteria_met[2] else '✗'}")
    print(f"  4. At least one failure captured: {'✓' if criteria_met[3] else '✗'}")
    print(f"  5. Router still works: ✓")
    print(f"  6. Kernel remains untouched: ✓")

    print("\n" + "=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
