"""
DSM-SKILLS — Skill Registry.

Rôle: In-memory registry of available skills (Skill objects). Used by the
router to resolve task descriptions to skills. No persistence; registration
is process-local.

API principale (SkillRegistry):
  - register(skill): add a skill; raises ValueError if skill_id already exists.
  - get(skill_id) -> Skill | None
  - list_skills() -> list of Skill
  - search(query) -> list of Skill: simple match on id, description, trigger keywords.

Contraintes:
  - In-memory only; no disk or DSM writes. Skills must be registered after load.
  - Do not modify DSM core; this module is independent of the kernel.
"""

import os
from typing import Dict, List, Optional

from .models import Skill


class SkillRegistry:
    """Simple in-memory registry for DSM skills.

    This is a v0 implementation using an in-memory dictionary.
    Future versions may include persistence and more advanced features.
    """

    def __init__(self):
        """Initialize an empty skill registry."""
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a new skill in the registry.

        Args:
            skill: The Skill object to register

        Raises:
            ValueError: If a skill with the same ID already exists

        """
        if skill.skill_id in self._skills:
            raise ValueError(f"Skill '{skill.skill_id}' already registered")

        self._skills[skill.skill_id] = skill

    def get(self, skill_id: str) -> Optional[Skill]:
        """Get a skill by ID.

        Args:
            skill_id: The ID of the skill to retrieve

        Returns:
            The Skill object, or None if not found
        """
        return self._skills.get(skill_id)

    def list_skills(self) -> List[Skill]:
        """List all registered skills.

        Returns:
            List of all Skill objects in the registry
        """
        return list(self._skills.values())

    def search(self, query: str) -> List[Skill]:
        """Search for skills matching a query.

        This is a simple implementation that searches skill IDs,
        names, descriptions, and trigger keywords.

        Args:
            query: Search query string

        Returns:
            List of matching Skill objects
        """
        query_lower = query.lower()
        results = []

        for skill in self._skills.values():
            # Search in skill ID
            if query_lower in skill.skill_id.lower():
                results.append(skill)
                continue

            # Search in description
            if query_lower in (skill.description or "").lower():
                results.append(skill)
                continue

            # Search in triggers
            for trigger in skill.trigger_conditions:
                if query_lower in trigger.lower():
                    results.append(skill)
                    break

        return results

    def count(self) -> int:
        """Get the total number of registered skills.

        Returns:
            Number of skills in the registry
        """
        return len(self._skills)

    def clear(self) -> None:
        """Clear all skills from the registry."""
        self._skills.clear()
