"""
DSM-SKILLS - Anthropic SKILL.md parser.

Purpose:
- Parse Anthropic-style SKILL.md files
- Extract YAML frontmatter and instructions
- Convert to DSM Skill objects

Expected SKILL.md format:
---
name: task-decomposition
description: Break a task into steps
triggers:
  - complex task
  - multi-step problem
---

Skill instructions here.
"""

import os
import re

from .models import Skill


class AnthropicSkillParser:
    """Parser for Anthropic-style SKILL.md files."""

    FRONTMatter_PATTERN = re.compile(r'^---\n(.*?)\n---\n(.*)$', re.DOTALL)

    def __init__(self, debug: bool = False):
        """Initialize the parser.

        Args:
            debug: Enable debug logging
        """
        self.debug = debug

    def _log(self, message: str) -> None:
        """Print debug message if enabled."""
        if self.debug:
            print(f"[AnthropicParser] {message}")

    def _parse_yaml_frontmatter(self, frontmatter_text: str) -> dict:
        """Simple YAML frontmatter parser.

        Args:
            frontmatter_text: The YAML frontmatter text

        Returns:
            Dictionary of parsed values
        """
        result = {}

        for line in frontmatter_text.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Simple key: value parsing
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()

                # Handle list values (with dash)
                value = value.strip()
                if value.startswith('-'):
                    # This is the first item in a list
                    # Collect all subsequent list items
                    pass  # Will handle in multi-line parsing below

                result[key] = value

        return result

    def _parse_yaml_frontmatter_with_lists(self, frontmatter_text: str) -> dict:
        """Parse YAML frontmatter with support for lists.

        Args:
            frontmatter_text: The YAML frontmatter text

        Returns:
            Dictionary of parsed values
        """
        result = {}
        lines = frontmatter_text.strip().split('\n')

        current_key = None
        in_list = False

        for line in lines:
            line = line.rstrip()
            if not line or line.startswith('#'):
                continue

            # List item (dash)
            if line.strip().startswith('- '):
                if current_key:
                    value = line.strip()[2:].strip()
                    if current_key not in result:
                        result[current_key] = []
                    # Handle case where key was set to string, need to convert to list
                    if isinstance(result[current_key], str):
                        result[current_key] = [result[current_key]]
                    result[current_key].append(value)
                    in_list = True
                    self._log(f"  List item for {current_key}: {value}")
                continue

            # Key-value pair
            if ':' in line:
                current_key = line.split(':', 1)[0].strip().lower()
                value = line.split(':', 1)[1].strip()

                # If there's a value after colon, it's not a list header
                if value:
                    result[current_key] = value
                    in_list = False
                else:
                    # Empty value, expect list items next
                    result[current_key] = []
                    in_list = True

                self._log(f"  Key: {current_key} = {value}")

        return result

    def parse_skill_file(self, skill_path: str) -> Optional[Skill]:
        """Parse an Anthropic-style SKILL.md file.

        Args:
            skill_path: Path to the SKILL.md file

        Returns:
            Skill object if successful, None otherwise
        """
        self._log(f"Parsing skill file: {skill_path}")

        if not os.path.exists(skill_path):
            self._log(f"  File not found")
            return None

        try:
            with open(skill_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract frontmatter and instructions
            match = self.FRONTMatter_PATTERN.match(content)

            if not match:
                self._log(f"  No valid frontmatter found")
                return None

            frontmatter_text = match.group(1)
            instructions = match.group(2).strip()

            # Parse YAML frontmatter
            metadata = self._parse_yaml_frontmatter_with_lists(frontmatter_text)

            # Extract required fields
            skill_id = metadata.get('name', '')
            description = metadata.get('description', '')

            if not skill_id or not description:
                self._log(f"  Missing required fields: name={skill_id}, description={description}")
                return None

            # Extract optional fields with defaults
            domain = metadata.get('domain', 'general')
            triggers = metadata.get('triggers', [])
            if isinstance(triggers, str):
                triggers = [triggers]
            tags = metadata.get('tags', [])
            if isinstance(tags, str):
                tags = [tags]

            # Normalize skill_id (replace spaces with underscores)
            skill_id = skill_id.lower().replace(' ', '_').replace('-', '_')

            # Build prompt_template from instructions
            prompt_template = instructions if instructions else ""

            # Create Skill object
            skill = Skill(
                skill_id=skill_id,
                domain=domain,
                description=description,
                trigger_conditions=triggers,
                prompt_template=prompt_template,
                tags=tags,
                source_type="anthropic",
                source_path=skill_path,
                instructions=instructions
            )

            self._log(f"  Parsed skill: {skill_id}")
            self._log(f"    Domain: {domain}")
            self._log(f"    Triggers: {triggers}")
            self._log(f"    Instructions length: {len(instructions)}")

            return skill

        except Exception as e:
            self._log(f"  Error parsing file: {e}")
            return None

    def parse_skill_folder(self, folder_path: str) -> Optional[Skill]:
        """Parse an Anthropic-style skill folder.

        Args:
            folder_path: Path to the skill folder containing SKILL.md

        Returns:
            Skill object if successful, None otherwise
        """
        self._log(f"Parsing skill folder: {folder_path}")

        skill_md_path = os.path.join(folder_path, "SKILL.md")

        if not os.path.exists(skill_md_path):
            self._log(f"  SKILL.md not found in folder")
            return None

        skill = self.parse_skill_file(skill_md_path)

        if skill:
            # Update source_path to point to folder
            skill.source_path = folder_path
            self._log(f"  Skill folder parsed successfully")

        return skill
