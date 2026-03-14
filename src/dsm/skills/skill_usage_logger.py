"""
DSM-SKILLS - Skill Usage Logger.

Purpose:
- Track which skills are used on which tasks
- Log skill selection events to JSONL
- Provide usage analytics

This is a separate logging system that does not touch the DSM kernel.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from .models import Skill


class SkillUsageLogger:
    """Logger for tracking skill usage events.

    This is a separate logging system that does not touch DSM kernel.
    It writes to a separate JSONL file for skill usage analytics.
    """

    def __init__(self, log_file: str = "logs/skills_usage.jsonl"):
        """Initialize usage logger with log file path.

        Args:
            log_file: Path to usage log file (default logs/skills_usage.jsonl)

        Raises:
            OSError: If log file directory cannot be created
        """
        self.log_file = log_file

        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    def log_usage(self, task_description: str, skill_id: str, skill_name: str) -> None:
        """Log a skill usage event.

        Args:
            task_description: The task description that triggered the skill
            skill_id: The ID of the skill that was used
            skill_name: The name of the skill that was used

        Returns:
            None

        Usage Event Structure:
        {
            "timestamp": "2026-03-11T19:00:00Z",
            "event_type": "skill_usage",
            "task_description": "search web for python examples",
            "skill_id": "browser_search",
            "skill_name": "Browser Search"
        }
        """
        # Create usage event
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": "skill_usage",
            "task_description": task_description,
            "skill_id": skill_id,
            "skill_name": skill_name
        }

        # Write event to log file
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            # Silent fail - don't break flow if logging fails
            pass

    def get_usage_stats(self, skill_id: Optional[str] = None) -> Dict[str, int]:
        """Get usage statistics for a specific skill or all skills.

        Args:
            skill_id: Optional skill ID to filter by (None for all skills)

        Returns:
            Dictionary mapping skill IDs to usage counts
        """
        stats = {}

        if not os.path.exists(self.log_file):
            return stats

        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())

                        if event.get("event_type") == "skill_usage":
                            sid = event.get("skill_id")
                            if skill_id is None or sid == skill_id:
                                stats[sid] = stats.get(sid, 0) + 1

                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue
        except Exception:
            # If file read fails, return empty stats
            return stats

        return stats

    def get_recent_usage(self, limit: int = 10) -> List[Dict]:
        """Get recent skill usage events.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of recent usage events
        """
        events = []

        if not os.path.exists(self.log_file):
            return events

        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in reversed(f.readlines()):
                    if len(events) >= limit:
                        break

                    try:
                        event = json.loads(line.strip())

                        if event.get("event_type") == "skill_usage":
                            events.append(event)

                    except json.JSONDecodeError:
                        continue
        except Exception:
            # If file read fails, return empty events
            return events

        return events
