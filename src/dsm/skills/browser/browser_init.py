"""
Browser Skill Initialization - Register browser_search skill in SkillRegistry.

This module initializes the SkillRegistry and registers the browser_search skill
to make it available for task routing.

Run this module directly to register the skill:
python -m dsm.skills.browser.browser_init
"""

import os
import sys

# Get to skills directory (parent directory)
skills_dir = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))

# Add skills directory to sys.path FIRST
sys.path.insert(0, skills_dir)

# Absolute imports from sibling modules
from models import Skill
from registry import SkillRegistry
from browser.browser_skill import BrowserSearchSkill


def main():
    """Initialize SkillRegistry and register browser_search skill.
    """
    # Create skill registry
    registry = SkillRegistry()

    # Create browser_search skill instance
    browser_search_skill = BrowserSearchSkill()

    # Register skill
    try:
        registry.register(browser_search_skill)
        print(f"✅ Successfully registered skill: {browser_search_skill.skill_id}")
        print(f"   Domain: {browser_search_skill.domain}")
        print(f"   Description: {browser_search_skill.description}")
        print(f"   Triggers: {browser_search_skill.trigger_conditions}")
        print(f"   Total skills in registry: {registry.count()}")
    except ValueError as e:
        print(f"❌ Failed to register skill: {e}")


if __name__ == "__main__":
    main()
