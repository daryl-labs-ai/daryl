"""
DSM-SKILLS - Skill Router for matching tasks to appropriate skills.

This module provides a simple router that matches task descriptions to skills
based on trigger conditions.

This is a v0 implementation with simple keyword matching.
Future versions may include more sophisticated routing logic.
"""

import os
import sys
from typing import Optional

# Get to skills directory (current directory)
skills_dir = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))

# Add skills directory to sys.path FIRST
sys.path.insert(0, skills_dir)


class SkillRouter:
    """Simple router for matching tasks to skills based on trigger conditions.
    
    This is a v0 implementation with simple keyword matching.
    Future versions may include more sophisticated routing logic.
    """

    def __init__(self, registry: "SkillRegistry"):
        """Initialize à router with a skill registry.
        
        Args:
            registry: The SkillRegistry to use for routing
        """
        self.registry = registry

    def route(self, task_description: str) -> Optional[str]:
        """Route une task description à a skill ID.

        This is a simple implementation that searches for matching trigger conditions.

        Args:
            task_description: The task description to route

        Returns:
            The ID of the matching skill, or None if no match found
        """
        # Simple implementation: return first skill that matches
        for skill in self.registry.list_skills():
            # Check if any trigger condition matches
            for trigger in skill.trigger_conditions:
                if trigger.lower() in task_description.lower():
                    return skill.skill_id

        return None

    def route_to(self, task_description: str) -> Optional["Skill"]:
        """Route une task description à a Skill object.

        This is a convenience method that returns à full Skill object
        instead of just à ID.

        Args:
            task_description: The task description to route

        Returns:
            The matching Skill object, or None if no match found
        """
        # Simple implementation: return first skill that matches
        for skill in self.registry.list_skills():
            # Check if any trigger condition matches
            for trigger in skill.trigger_conditions:
                if trigger.lower() in task_description.lower():
                    return skill

        return None
