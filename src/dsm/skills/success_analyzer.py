"""
DSM-SKILLS - Skill Success Analyzer for analyzing skill performance.

Purpose:
- Calculate success rates by skill
- Calculate average durations by skill
- Identify patterns in skill performance
- Provide actionable insights

This is an optional analyzer module for skill outcome analysis.
"""

import json
import os
from typing import Dict, List

from .skill_success_logger import SkillSuccessLogger


class SkillSuccessAnalyzer:
    """Analyzer for skill success/failure metrics.

    This module provides analytics on skill performance
    using data from SkillSuccessLogger.
    """

    def __init__(self, logger: SkillSuccessLogger):
        """Initialize analyzer with a success logger.

        Args:
            logger: The SkillSuccessLogger to analyze
        """
        self.logger = logger

    def get_success_rate(self, skill_id: str) -> float:
        """Get success rate for a specific skill.

        Args:
            skill_id: The skill ID to analyze

        Returns:
            Success rate between 0.0 and 1.0
        """
        stats = self.logger.get_success_stats(skill_id)
        skill_stats = stats.get(skill_id, {})
        return skill_stats.get("success_rate", 0.0)

    def get_avg_duration(self, skill_id: str) -> float:
        """Get average duration for a specific skill.

        Args:
            skill_id: The skill ID to analyze

        Returns:
            Average duration in milliseconds
        """
        stats = self.logger.get_success_stats(skill_id)
        skill_stats = stats.get(skill_id, {})
        return skill_stats.get("avg_duration_ms", 0.0)

    def get_all_success_rates(self) -> Dict[str, float]:
        """Get success rates for all skills.

        Returns:
            Dictionary mapping skill IDs to success rates
        """
        stats = self.logger.get_success_stats()
        result = {}
        for skill_id, data in stats.items():
            result[skill_id] = data.get("success_rate", 0.0)
        return result

    def identify_slow_skills(self, threshold_ms: float = 5000.0) -> List[Dict]:
        """Identify skills that are consistently slow.

        Args:
            threshold_ms: Duration threshold in milliseconds

        Returns:
            List of slow skill statistics
        """
        stats = self.logger.get_success_stats()
        slow_skills = []

        for skill_id, data in stats.items():
            avg_duration = data.get("avg_duration_ms", 0)
            if avg_duration > threshold_ms:
                slow_skills.append({
                    "skill_id": skill_id,
                    "avg_duration_ms": avg_duration,
                    "success_rate": data.get("success_rate", 0.0)
                })

        return sorted(slow_skills, key=lambda x: x["avg_duration_ms"], reverse=True)

    def identify_low_success_skills(self, threshold: float = 0.7) -> List[Dict]:
        """Identify skills with low success rates.

        Args:
            threshold: Success rate threshold (0.0 to 1.0)

        Returns:
            List of low-success skill statistics
        """
        stats = self.logger.get_success_stats()
        low_success = []

        for skill_id, data in stats.items():
            success_rate = data.get("success_rate", 0.0)
            if success_rate < threshold:
                low_success.append({
                    "skill_id": skill_id,
                    "success_rate": success_rate,
                    "avg_duration_ms": data.get("avg_duration_ms", 0.0)
                })

        return sorted(low_success, key=lambda x: x["success_rate"])

    def generate_report(self) -> Dict:
        """Generate a comprehensive success report.

        Returns:
            Dictionary with overall and per-skill metrics
        """
        stats = self.logger.get_success_stats()

        # Overall metrics
        total_success = sum(data.get("success_count", 0) for data in stats.values())
        total_failure = sum(data.get("failure_count", 0) for data in stats.values())
        total_attempts = total_success + total_failure

        overall_success_rate = (total_success / total_attempts) if total_attempts > 0 else 0.0

        # Per-skill metrics
        skills_report = []
        for skill_id, data in stats.items():
            skills_report.append({
                "skill_id": skill_id,
                "success_rate": data.get("success_rate", 0.0),
                "avg_duration_ms": data.get("avg_duration_ms", 0.0),
                "total_attempts": data.get("count", 0),
                "success_count": data.get("success_count", 0),
                "failure_count": data.get("failure_count", 0)
            })

        return {
            "overall": {
                "total_attempts": total_attempts,
                "total_success": total_success,
                "total_failure": total_failure,
                "overall_success_rate": overall_success_rate
            },
            "skills": sorted(skills_report, key=lambda x: x["skill_id"]),
            "insights": {
                "slow_skills": self.identify_slow_skills(),
                "low_success_skills": self.identify_low_success_skills()
            }
        }
