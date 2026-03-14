"""
DSM-SKILLS — Skill Router.

Rôle: Match task descriptions to skills using trigger conditions. Used by
agents to select which skill to invoke for a given task. Requires a
SkillRegistry; does not write to DSM.

API principale (SkillRouter):
  - route(task_description) -> skill_id | None: first skill whose trigger matches.
  - route_to(task_description) -> Skill | None: same as route but returns Skill object.

Contraintes:
  - Simple keyword matching: trigger in task_description (case-insensitive).
  - First match wins; order of registration/list_skills() matters.
  - Do not modify DSM core; this module is independent of the kernel.
"""

from typing import Optional


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
