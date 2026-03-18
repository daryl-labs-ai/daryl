"""
DSM-SKILLS - Skill Success Logger for tracking skill outcomes.

Purpose:
- Track not only which skill was used, but also whether it succeeded
- Track execution duration (how long a skill took)
- Store optional notes for context
- Write to JSONL log file

This is a v0 implementation for skill outcome tracking.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Dict, List

from .models import Skill

logger = logging.getLogger(__name__)


class SkillSuccessLogger:
    """Logger for tracking skill success/failure outcomes.

    This is a separate logging system that does not touch DSM kernel.
    It writes to a separate JSONL file for skill success analytics.
    """

    def __init__(self, log_file: str = "logs/skills_success.jsonl"):
        """Initialize success logger with log file path.

        Args:
            log_file: Path to success log file (default logs/skills_success.jsonl)

        Raises:
            OSError: If log file directory cannot be created
        """
        self.log_file = log_file

        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    def log_success(self, task_description: str, skill_id: str, skill_name: str,
                    success: bool, duration_ms: float, notes: Optional[str] = None) -> None:
        """Log a skill success/failure event.

        Args:
            task_description: The task description that triggered the skill
            skill_id: The ID of the skill that was used
            skill_name: The name of the skill that was used
            success: Whether the skill execution succeeded
            duration_ms: Duration of skill execution in milliseconds
            notes: Optional notes for context (error messages, etc.)

        Returns:
            None

        Success Event Structure:
        {
            "timestamp": "2026-03-11T19:00:00Z",
            "event_type": "skill_success",
            "task_description": "search web for python examples",
            "skill_id": "browser_search",
            "skill_name": "Browser Search",
            "success": true,
            "duration_ms": 1234.5,
            "notes": null
        }
        """
        # Create success event
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event_type": "skill_success",
            "task_description": task_description,
            "skill_id": skill_id,
            "skill_name": skill_name,
            "success": success,
            "duration_ms": duration_ms,
            "notes": notes
        }

        # Write event to log file
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            logger.debug("skill success log write failed: %s", e)

    def get_success_stats(self, skill_id: Optional[str] = None) -> Dict[str, Dict]:
        """Get success statistics for a specific skill or all skills.

        Args:
            skill_id: Optional skill ID to filter by (None for all skills)

        Returns:
            Dictionary mapping skill IDs to success statistics:
            {
                "skill_id": {
                    "success_count": 10,
                    "failure_count": 2,
                    "success_rate": 0.833,
                    "avg_duration_ms": 1234.5
                }
            }
        """
        stats = {}

        if not os.path.exists(self.log_file):
            return stats

        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())

                        if event.get("event_type") == "skill_success":
                            sid = event.get("skill_id")
                            if skill_id is None or sid == skill_id:
                                if sid not in stats:
                                    stats[sid] = {
                                        "success_count": 0,
                                        "failure_count": 0,
                                        "total_duration_ms": 0,
                                        "count": 0
                                    }

                                stats[sid]["count"] += 1
                                if event.get("success"):
                                    stats[sid]["success_count"] += 1
                                else:
                                    stats[sid]["failure_count"] += 1

                                duration = event.get("duration_ms", 0)
                                stats[sid]["total_duration_ms"] += duration

                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue
        except Exception:
            # If file read fails, return empty stats
            return stats

        # Calculate rates and averages
        for sid, data in stats.items():
            if data["count"] > 0:
                data["success_rate"] = data["success_count"] / data["count"]
                data["avg_duration_ms"] = data["total_duration_ms"] / data["count"]

        return stats

    def get_recent_outcomes(self, limit: int = 10) -> List[Dict]:
        """Get recent skill success/failure events.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of recent success/failure events
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

                        if event.get("event_type") == "skill_success":
                            events.append(event)

                    except json.JSONDecodeError:
                        continue
        except Exception:
            # If file read fails, return empty events
            return events

        return events
