"""
DSM-SKILLS - Validation script for the skills module.

This script validates that:
1. The module structure is correct
2. Imports work properly
3. The registry can register skills
4. The router can match tasks to skills

Expected output:
Selected skill: task_decomposition
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills import Skill, SkillRegistry, SkillRouter


def main():
    """Run the validation test."""
    print("DSM-SKILLS Validation Test")
    print("=" * 50)

    # Step 1: Create registry
    print("\n1. Creating SkillRegistry...")
    registry = SkillRegistry()
    print("   ✓ Registry created")

    # Step 2: Create a test skill
    print("\n2. Creating test skill (task_decomposition)...")
    test_skill = Skill(
        skill_id="task_decomposition",
        domain="reasoning",
        description="Break a complex task into smaller logical steps.",
        trigger_conditions=["complex", "multi-step"],
        prompt_template="Break the task into logical steps.",
        tags=["planning", "reasoning"]
    )
    print(f"   ✓ Skill created: {test_skill.skill_id}")

    # Step 3: Register the skill
    print("\n3. Registering skill...")
    registry.register(test_skill)
    print(f"   ✓ Skill registered")

    # Step 4: Create router
    print("\n4. Creating SkillRouter...")
    router = SkillRouter(registry)
    print("   ✓ Router created")

    # Step 5: Test routing
    print("\n5. Testing routing with task: 'solve a complex trading strategy'...")
    task_description = "solve a complex trading strategy"
    selected_skill = router.route(task_description)

    if selected_skill:
        print(f"   ✓ Selected skill: {selected_skill.skill_id}")
        print(f"   ✓ Domain: {selected_skill.domain}")
        print(f"   ✓ Description: {selected_skill.description}")
    else:
        print("   ✗ No skill selected - TEST FAILED")
        return False

    # Step 6: Test non-matching task
    print("\n6. Testing routing with non-matching task: 'hello world'...")
    no_match_skill = router.route("hello world")
    if no_match_skill is None:
        print("   ✓ Correctly returned None for non-matching task")
    else:
        print(f"   ✗ Unexpectedly selected: {no_match_skill.skill_id} - TEST FAILED")
        return False

    print("\n" + "=" * 50)
    print("✓ ALL TESTS PASSED")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
