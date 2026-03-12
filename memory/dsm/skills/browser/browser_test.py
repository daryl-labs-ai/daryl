#!/usr/bin/env python3
"""
Browser Skill Test Script

Tests the browser_search skill integration with SkillRouter.

Flow:
1. Create task: "search web for python asyncio tutorial"
2. Router selects: browser_search
3. BrowserClient executes: search
4. Print first extracted results
"""

import os
import sys

# Get to skills directory (grandparent)
skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__))))

# Add skills directory to sys.path
sys.path.insert(0, skills_dir)

# Import from modules
from models import Skill
from registry import SkillRegistry
from router import SkillRouter
from browser.browser_client import BrowserClient
from browser.browser_skill import BrowserSearchSkill


def main():
    """Test browser_search skill integration."""

    # Create registry
    registry = SkillRegistry()

    # Create router
    router = SkillRouter(registry)

    # Create and register browser_search skill
    browser_search_skill = BrowserSearchSkill()

    try:
        registry.register(browser_search_skill)
        print("✅ Registered browser_search skill")
        print(f"   Skill ID: {browser_search_skill.skill_id}")
        print(f"   Name: {browser_search_skill.name}")
        print(f"   Category: {browser_search_skill.category}")
        print(f"   Description: {browser_search_skill.description}")
        print(f"   Triggers: {browser_search_skill.trigger_conditions}")
        print(f"   Total skills: {registry.count()}")
    except ValueError as e:
        print(f"❌ Failed to register skill: {e}")
        return

    # Test routing with sample task
    task = "search web for python asyncio tutorial"

    print(f"\n🔍 Routing task: {task}")
    skill_id = router.route(task)

    if skill_id:
        print(f"✅ Router selected skill: {skill_id}")

        skill = registry.get(skill_id)

        if skill:
            print(f"   Skill Name: {skill.name}")
            print(f"   Description: {skill.description}")

            # Execute skill (simulate)
            print(f"\n🌐 Executing skill: {skill.skill_id}")

            # Create browser client
            try:
                browser = BrowserClient()

                # Extract search query from task
                # Simple extraction: take everything after "search"
                query = task.replace("search web for", "")
                query = query.replace("python asyncio tutorial", "")
                query = query.strip()

                # Limit query length
                if len(query) > 100:
                    query = query[:100]

                print(f"🔍 Search query: {query}")

                # Perform search
                result = browser.search(query)

                print(f"\n✅ Search Results:")
                print(f"   Raw result: {str(result)[:200]}")

            except Exception as e:
                print(f"❌ Browser execution failed: {e}")
        else:
            print(f"❌ Skill not found in registry")
    else:
        print(f"❌ Router could not find matching skill for task: {task}")


if __name__ == "__main__":
    main()
