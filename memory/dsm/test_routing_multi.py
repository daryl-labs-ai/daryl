"""
DSM-SKILLS - Multi-skill routing test.

Test routing with multiple loaded skills.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills import SkillRegistry, SkillRouter
from skills.ingestor import SkillIngestor


def main():
    """Run multi-skill routing test."""
    print("DSM-SKILLS MULTI-SKILL ROUTING TEST")
    print("=" * 60)

    # Setup
    registry = SkillRegistry()
    libraries_path = os.path.join(os.path.dirname(__file__), "skills", "libraries")
    ingestor = SkillIngestor()
    ingestor.load_all_skills(libraries_path, registry)

    router = SkillRouter(registry)

    # Test cases
    test_cases = [
        ("solve a complex trading strategy", "task_decomposition"),
        ("create a multi-step workflow", "task_decomposition"),
        ("summarize this long text", "text_summarization"),
        ("give me a brief overview", "text_summarization"),
        ("hello world", None),
    ]

    print("\nTest Results:\n")

    all_passed = True
    for task, expected_skill in test_cases:
        selected = router.route(task)
        selected_id = selected.skill_id if selected else None

        status = "✓" if selected_id == expected_skill else "✗"
        result = f"{status} Task: '{task}'"
        result += f"\n   Expected: {expected_skill}"
        result += f"\n   Selected: {selected_id}\n"
        print(result)

        if selected_id != expected_skill:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("✓ ALL ROUTING TESTS PASSED")
    else:
        print("✗ SOME TESTS FAILED")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
