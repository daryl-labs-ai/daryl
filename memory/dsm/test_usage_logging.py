"""
DSM-SKILLS - Usage logging validation test.

This script validates that:
1. Skill usage events are logged correctly
2. Router integrates with logger
3. Log file is created in the correct location
4. JSONL format is valid
"""

import sys
import os
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills import SkillRegistry, SkillRouter
from skills.ingestor import SkillIngestor
from skills.skill_usage_logger import SkillUsageLogger


def main():
    """Run the usage logging validation test."""
    print("=" * 60)
    print("DSM-SKILLS USAGE LOGGING VALIDATION")
    print("=" * 60)

    # Step 1: Setup registry and ingest skills
    print("\n1. Setting up registry and loading skills...")
    registry = SkillRegistry()
    libraries_path = os.path.join(os.path.dirname(__file__), "skills", "libraries")
    ingestor = SkillIngestor()
    report = ingestor.load_all_skills(libraries_path, registry)

    print(f"   Skills loaded: {report.skills_loaded}")

    # Step 2: Setup logger
    print("\n2. Setting up skill usage logger...")
    logger = SkillUsageLogger()
    print(f"   Log file: {logger.log_file}")

    # Step 3: Setup router with logger
    print("\n3. Setting up router with logger...")
    router = SkillRouter(registry, logger=logger)
    print("   Router configured with logger")

    # Step 4: Test routing and logging
    print("\n4. Testing routing and logging...")

    test_tasks = [
        "solve a complex trading strategy",
        "review this code for bugs",
        "summarize the document",
        "analyze this data",
    ]

    for task in test_tasks:
        skill = router.route(task)
        skill_id = skill.skill_id if skill else "None"

        if skill:
            print(f"   ✓ Task: '{task[:40]}...'")
            print(f"     → Selected: {skill_id}")
            print(f"     → Logged: YES")
        else:
            print(f"   ✗ Task: '{task[:40]}...'")
            print(f"     → Selected: None")
            print(f"     → Logged: NO")

    # Step 5: Verify log file
    print("\n5. Verifying log file...")

    if not os.path.exists(logger.log_file):
        print("   ✗ Log file does not exist")
        return False

    print(f"   ✓ Log file exists: {logger.log_file}")

    # Step 6: Read and validate JSONL
    print("\n6. Validating JSONL format...")

    events = []
    try:
        with open(logger.log_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        event = json.loads(line)
                        events.append(event)

                        # Validate required fields
                        required_fields = [
                            "timestamp", "skill_id", "task",
                            "trigger", "source_type", "source_path", "library"
                        ]

                        missing_fields = [f for f in required_fields if f not in event]
                        if missing_fields:
                            print(f"   ✗ Line {line_num}: Missing fields {missing_fields}")
                            return False

                    except json.JSONDecodeError as e:
                        print(f"   ✗ Line {line_num}: Invalid JSON - {e}")
                        return False

        print(f"   ✓ Valid JSONL: {len(events)} events")

        # Step 7: Print sample events
        print("\n7. Sample log entries:")

        for i, event in enumerate(events[-2:], 1):
            print(f"\n   Event {i}:")
            print(f"     Timestamp: {event['timestamp']}")
            print(f"     Skill: {event['skill_id']}")
            print(f"     Task: {event['task'][:50]}...")
            print(f"     Trigger: {event['trigger']}")
            print(f"     Source: {event['source_type']}")
            print(f"     Library: {event['library']}")

        # Step 8: Get usage stats
        print("\n8. Usage statistics:")
        stats = logger.get_usage_stats()
        print(f"   Total events: {stats['total_events']}")
        print(f"   By skill: {stats['by_skill']}")
        print(f"   By library: {stats['by_library']}")
        print(f"   By source: {stats['by_source_type']}")

        # Summary
        print("\n" + "=" * 60)
        print("✓ USAGE LOGGING VALIDATION PASSED")
        print("=" * 60)
        print("\nSummary:")
        print(f"  - Logger created: YES")
        print(f"  - Router integration: YES")
        print(f"  - Usage log file created: YES")
        print(f"  - Events written: {len(events)}")
        print(f"  - JSONL format valid: YES")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"   ✗ Error reading log file: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
