"""
DSM-SKILLS - Ingestion validation script.

This script validates that:
1. JSON skill files can be loaded from library folders
2. Skills are registered in SkillRegistry
3. Router can select skills from loaded library data
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills import Skill, SkillRegistry, SkillRouter
from skills.ingestor import SkillIngestor


def main():
    """Run the ingestion validation test."""
    print("=" * 60)
    print("DSM-SKILLS INGESTION VALIDATION TEST")
    print("=" * 60)

    # Step 1: Create registry
    print("\n1. Creating SkillRegistry...")
    registry = SkillRegistry()
    print("   ✓ Registry created")

    # Step 2: Create ingestor
    print("\n2. Creating SkillIngestor...")
    ingestor = SkillIngestor()
    print("   ✓ Ingestor created")

    # Step 3: Get libraries path
    libraries_path = os.path.join(os.path.dirname(__file__), "skills", "libraries")
    print(f"\n3. Loading skills from: {libraries_path}")

    # Step 4: Load all skills
    report = ingestor.load_all_skills(libraries_path, registry)
    print(f"\n{report}")

    # Step 5: Verify skills were loaded
    print("\n4. Verifying loaded skills...")
    all_skills = registry.list_skills()
    print(f"   ✓ Registry contains {len(all_skills)} skills")

    if len(all_skills) == 0:
        print("   ✗ No skills loaded - TEST FAILED")
        return False

    for skill in all_skills:
        print(f"   - {skill.skill_id} ({skill.domain})")

    # Step 6: Create router
    print("\n5. Creating SkillRouter...")
    router = SkillRouter(registry)
    print("   ✓ Router created")

    # Step 7: Test routing with complex task
    print("\n6. Testing routing: 'solve a complex trading strategy'...")
    task1 = "solve a complex trading strategy"
    selected_skill1 = router.route(task1)

    if selected_skill1:
        print(f"   ✓ Selected skill: {selected_skill1.skill_id}")
        if selected_skill1.skill_id == "task_decomposition":
            print("   ✓ Correct skill matched!")
        else:
            print(f"   ✗ Unexpected skill selected - TEST FAILED")
            return False
    else:
        print("   ✗ No skill selected - TEST FAILED")
        return False

    # Step 8: Test routing with multi-step task
    print("\n7. Testing routing: 'create a multi-step automation workflow'...")
    task2 = "create a multi-step automation workflow"
    selected_skill2 = router.route(task2)

    if selected_skill2:
        print(f"   ✓ Selected skill: {selected_skill2.skill_id}")
    else:
        print("   ✗ No skill selected - TEST FAILED")
        return False

    # Step 9: Test non-matching task
    print("\n8. Testing non-matching task: 'hello world'...")
    no_match_skill = router.route("hello world")
    if no_match_skill is None:
        print("   ✓ Correctly returned None for non-matching task")
    else:
        print(f"   ✗ Unexpectedly selected: {no_match_skill.skill_id} - TEST FAILED")
        return False

    # Summary
    print("\n" + "=" * 60)
    print("✓ INGESTION TEST PASSED")
    print("=" * 60)
    print("\nSummary:")
    print(f"  - Libraries scanned: {report.libraries_scanned}")
    print(f"  - Skill files found: {report.skill_files_found}")
    print(f"  - Skills loaded: {report.skills_loaded}")
    print(f"  - Skills skipped: {report.skills_skipped}")
    print("=" * 60)

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
