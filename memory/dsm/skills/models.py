"""
DSM-SKILLS - Minimal skill models for skill system architecture.

This module defines core data structures for DSM skills system.
Currently minimal and intended for testing only.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Skill:
    """Represents a reusable skill in DSM system.

    Attributes:
        skill_id: Unique identifier for the skill
        domain: The domain or category the skill belongs to (e.g., "web", "reasoning", "planning")
        description: Human-readable description of what the skill does
        trigger_conditions: List of keywords or phrases that trigger this skill
        prompt_template: Template for generating prompts using this skill
        tags: Optional categorization tags
        source_type: Type of skill source ("json" or "anthropic")
        source_path: Path to skill source file/folder
    """
    skill_id: str
    domain: str
    description: str
    trigger_conditions: List[str] = field(default_factory=list)
    prompt_template: Optional[str] = None
    tags: Optional[List[str]] = None
    source_type: Optional[str] = None
    source_path: Optional[str] = None
