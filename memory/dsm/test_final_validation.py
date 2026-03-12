"""
DSM-SKILLS v0.1 - Final validation test.

Tests both JSON and Anthropic SKILL.md format support.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills import SkillRegistry, SkillRouter
from skills.ingestor import SkillIngestor


def main():
    """Run final validation test."""
    print("=" * 60)
    print("DSM-SKILLS v0.1 - FINAL VALIDATION")
    print("=" * 60)

    # Setup
    print("\n1. Setup registry and ingestor...")
    registry = SkillRegistry()
    ingestor = SkillIngestor(debug=True)
    libraries_path = os.path.join(os.path.dirname(__file__), 'skills', 'libraries')
    print(f"   Libraries path: {libraries_path}")

    # Load all skills
    print("\n2. Loading all skills (JSON + Anthropic)...")
    report = ingestor.load_all_skills(libraries_path, registry)

    print("\n" + "=" * 60)
    print(str(report))
    print("=" * 60)

    # Summary
    print("\n3. Summary:")
    print(f"   JSON skills loaded: {report.json_skills_loaded}")
    print(f"   Anthropic skills loaded: {report.anthropic_skills_loaded}")
    print(f"   Total skills: {report.skills_loaded}")

    # Test routing
    print("\n4. Testing routing with different formats...")
    router = SkillRouter(registry)

    test_cases = [
        ("solve a complex trading strategy", "task_decomposition", "anthropic"),
        ("break down this multi-step problem", "task_decomposition", "anthropic"),
        ("review this code for bugs", "code_review", "anthropic"),
        ("summarize the document", "text_summarization", "json"),
        ("analyze the data", "data_analysis", "json"),
    ]

    all_passed = True
    for task, expected_id, expected_source in test_cases:
        skill = router.route(task)

        if skill:
            actual_id = skill.skill_id
            actual_source = skill.source_type

            id_match = actual_id == expected_id
            source_match = actual_source == expected_source

            if id_match and source_match:
                status = "✓"
            else:
                status = "✗"
                all_passed = False

            print(f"\n{status} Task: '{task}'")
            print(f"   Expected: {expected_id} [{expected_source}]")
            print(f"   Selected: {actual_id} [{actual_source}]")
        else:
            print(f"\n✗ Task: '{task}'")
            print(f"   Expected: {expected_id} [{expected_source}]")
            print(f"   Selected: None (FAILED)")
            all_passed = False

    # Final report
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED")
    else:
        print("✗ SOME TESTS FAILED")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
