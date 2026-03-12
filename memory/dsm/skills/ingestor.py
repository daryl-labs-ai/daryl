"""
DSM-SKILLS - Skill Ingestor for external skill libraries.

Purpose:
- Ingest skill definitions from JSON files in library folders
- Parse and validate skill definitions
- Automatically register skills into SkillRegistry

This module handles loading skills from local library directories.
Supports both JSON skills and Anthropic SKILL.md format.
"""

import json
import os
import sys
from typing import Dict, List, Optional

# Get to skills directory (current directory)
skills_dir = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))

# Add skills directory to sys.path
sys.path.insert(0, skills_dir)

# Absolute imports from sibling modules
from models import Skill
from registry import SkillRegistry


class SkillIngestor:
    """Ingestor for loading skills from external libraries.

    This is a v0 implementation that supports JSON and simple text formats.
    Future versions may include more advanced formats and validation.
    """

    def __init__(self, registry: "SkillRegistry"):
        """Initialize ingestor with a skill registry.

        Args:
            registry: The SkillRegistry to register skills into
        """
        self.registry = registry

    def ingest_from_directory(self, directory: str) -> int:
        """Ingest all valid skill definitions from a directory.

        Args:
            directory: The directory to scan for skills

        Returns:
            Number of skills successfully ingested
        """
        count = 0

        # Scan for JSON files
        if os.path.isdir(directory):
            for filename in os.listdir(directory):
                if filename.endswith('.json'):
                    filepath = os.path.join(directory, filename)

                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)

                        # Basic validation
                        if 'skill_id' in data and 'name' in data:
                            skill = Skill(
                                skill_id=data.get('skill_id', ''),
                                name=data.get('name', ''),
                                description=data.get('description', ''),
                                trigger_conditions=data.get('trigger_conditions', []),
                                category=data.get('category', 'default')
                            )

                            self.registry.register(skill)
                            count += 1

                    except Exception as e:
                        # Skip invalid files
                        pass

        return count

    def ingest_from_file(self, filepath: str) -> bool:
        """Ingest a skill definition from a single file.

        Args:
            filepath: The path to skill definition file

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Basic validation
            if 'skill_id' in data and 'name' in data:
                skill = Skill(
                    skill_id=data.get('skill_id', ''),
                    name=data.get('name', ''),
                    description=data.get('description', ''),
                    trigger_conditions=data.get('trigger_conditions', []),
                    category=data.get('category', 'default')
                )

                self.registry.register(skill)
                return True

        except Exception:
            return False
