"""
DSM-SKILLS - Import validation test.

Verify that all DSM-SKILLS imports work correctly.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_imports():
    """Test that all DSM-SKILLS modules can be imported."""
    print("Testing DSM-SKILLS imports...")
    print("=" * 60)

    try:
        from skills import Skill, SkillRegistry, SkillRouter
        print("✓ skills.__init__ imported")

        from skills.models import Skill
        print("✓ skills.models imported")

        from skills.registry import SkillRegistry
        print("✓ skills.registry imported")

        from skills.router import SkillRouter
        print("✓ skills.router imported")

        from skills.ingestor import SkillIngestor, SkillIngestionReport
        print("✓ skills.ingestor imported")

        from skills import evaluator
        print("✓ skills.evaluator imported")

        from skills.cli import main as cli_main
        print("✓ skills.cli imported")

        print("=" * 60)
        print("✓ ALL IMPORTS PASSED")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"✗ Import failed: {e}")
        print("=" * 60)
        return False


if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
