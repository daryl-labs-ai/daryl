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
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import Skill
from .registry import SkillRegistry


@dataclass
class SkillIngestionReport:
    """Minimal report for ingestion runs."""
    total_files: int
    skills_loaded: int
    errors: list = field(default_factory=list)
    # Optional aggregate fields for load_all_skills
    libraries_scanned: int = 0
    skill_files_found: int = 0
    skills_skipped: int = 0


class SkillIngestor:
    """Ingestor for loading skills from external libraries.

    This is a v0 implementation that supports JSON and simple text formats.
    Future versions may include more advanced formats and validation.
    """

    def __init__(self, registry: Optional["SkillRegistry"] = None):
        """Initialize ingestor with an optional skill registry.

        Args:
            registry: The SkillRegistry to register skills into (can be set later via load_all_skills).
        """
        self.registry = registry

    def ingest_from_directory(self, directory: str) -> SkillIngestionReport:
        """Ingest all valid skill definitions from a directory.

        Args:
            directory: The directory to scan for skills

        Returns:
            SkillIngestionReport with total_files, skills_loaded, errors
        """
        total_files = 0
        skills_loaded = 0
        errors: List[str] = []

        if not os.path.isdir(directory):
            return SkillIngestionReport(total_files=0, skills_loaded=0, errors=errors)

        for filename in os.listdir(directory):
            if not filename.endswith('.json'):
                continue
            filepath = os.path.join(directory, filename)
            total_files += 1
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Map JSON fields to Skill: name -> description, category -> domain
                skill_id = data.get('skill_id', '')
                description = data.get('description') or data.get('name', '')
                if not skill_id or not description:
                    errors.append(f"{filename}: missing skill_id or name/description")
                    continue
                skill = Skill(
                    skill_id=skill_id,
                    domain=data.get('domain') or data.get('category', 'default'),
                    description=description,
                    trigger_conditions=data.get('trigger_conditions', []),
                )
                self.registry.register(skill)
                skills_loaded += 1
            except Exception as e:
                errors.append(f"{filename}: {e!s}")

        return SkillIngestionReport(total_files=total_files, skills_loaded=skills_loaded, errors=errors)

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
            # Map JSON fields to Skill: name -> description, category -> domain
            skill_id = data.get('skill_id', '')
            description = data.get('description') or data.get('name', '')
            if not skill_id or not description:
                return False
            skill = Skill(
                skill_id=skill_id,
                domain=data.get('domain') or data.get('category', 'default'),
                description=description,
                trigger_conditions=data.get('trigger_conditions', []),
            )
            self.registry.register(skill)
            return True
        except Exception:
            return False

    def load_all_skills(self, libraries_path: str, registry: Optional["SkillRegistry"] = None) -> SkillIngestionReport:
        """Scan library subdirs under libraries_path and ingest all JSON skills.

        Args:
            libraries_path: Directory containing one subdir per library
            registry: Registry to register into (uses self.registry if None; can set self.registry when provided)

        Returns:
            Aggregate SkillIngestionReport with libraries_scanned, skill_files_found, skills_loaded, skills_skipped
        """
        if registry is not None:
            self.registry = registry
        reg = self.registry
        if reg is None:
            return SkillIngestionReport(
                total_files=0, skills_loaded=0, errors=["no registry set"],
                libraries_scanned=0, skill_files_found=0, skills_skipped=0,
            )
        libraries_scanned = 0
        skill_files_found = 0
        skills_loaded = 0
        skills_skipped = 0
        all_errors: List[str] = []

        if not os.path.isdir(libraries_path):
            return SkillIngestionReport(
                total_files=0, skills_loaded=0, errors=all_errors,
                libraries_scanned=0, skill_files_found=0, skills_skipped=0,
            )

        for name in os.listdir(libraries_path):
            lib_path = os.path.join(libraries_path, name)
            if not os.path.isdir(lib_path):
                continue
            libraries_scanned += 1
            # Prefer library_name/skills/*.json if present, else scan library dir
            skills_subdir = os.path.join(lib_path, "skills")
            dir_to_scan = skills_subdir if os.path.isdir(skills_subdir) else lib_path
            report = self.ingest_from_directory(dir_to_scan)  # uses self.registry
            skill_files_found += report.total_files
            skills_loaded += report.skills_loaded
            skills_skipped += report.total_files - report.skills_loaded
            all_errors.extend(report.errors)

        return SkillIngestionReport(
            total_files=skill_files_found,
            skills_loaded=skills_loaded,
            errors=all_errors,
            libraries_scanned=libraries_scanned,
            skill_files_found=skill_files_found,
            skills_skipped=skills_skipped,
        )
