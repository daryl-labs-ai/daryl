"""
DSM-SKILLS - Skill Graph for tracking skill usage patterns.

Purpose:
- Build a graph of skill transitions from usage logs
- Detect which skills are commonly used in sequence
- Provide insights into skill usage patterns

This is a simple v0 implementation using in-memory data structures.
"""

import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

# Get to skills directory (current directory)
skills_dir = os.path.dirname(os.path.abspath(__file__))

# Add skills directory to sys.path
sys.path.insert(0, skills_dir)

# Direct imports from sibling modules
from skill_usage_logger import SkillUsageLogger


class SkillGraph:
    """Graph for tracking skill transition patterns.

    This module builds a directed graph where nodes are skills
    and edges represent transitions between skills in sequence.
    """

    def __init__(self, usage_logger: SkillUsageLogger):
        """Initialize graph with a usage logger.

        Args:
            usage_logger: The SkillUsageLogger to analyze
        """
        self.usage_logger = usage_logger
        self._graph: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._built = False

    def _build_graph(self) -> None:
        """Build the transition graph from usage logs.

        This method parses usage events and creates edges
        between skills that are used in sequence.
        """
        # Get all usage events ordered by timestamp
        events = self.usage_logger.get_recent_usage(limit=1000)

        # Sort by timestamp to get proper sequence
        events.sort(key=lambda x: x.get("timestamp", ""))

        # Build transition graph
        prev_skill = None
        for event in events:
            skill_id = event.get("skill_id")
            if prev_skill and skill_id and prev_skill != skill_id:
                self._graph[prev_skill][skill_id] += 1
            prev_skill = skill_id

        self._built = True

    def get_transitions(self, skill_id: str) -> Dict[str, int]:
        """Get outgoing transitions for a specific skill.

        Args:
            skill_id: The source skill ID

        Returns:
            Dictionary mapping destination skills to transition counts
        """
        if not self._built:
            self._build_graph()

        return dict(self._graph.get(skill_id, {}))

    def get_common_sequences(self, min_count: int = 2) -> List[Dict]:
        """Get commonly occurring skill sequences.

        Args:
            min_count: Minimum transition count to include

        Returns:
            List of common sequences with counts
        """
        if not self._built:
            self._build_graph()

        sequences = []
        for source, destinations in self._graph.items():
            for dest, count in destinations.items():
                if count >= min_count:
                    sequences.append({
                        "source": source,
                        "destination": dest,
                        "count": count
                    })

        return sorted(sequences, key=lambda x: x["count"], reverse=True)

    def get_hub_skills(self, top_n: int = 5) -> List[Dict]:
        """Identify skills that are hubs (many incoming/outgoing transitions).

        Args:
            top_n: Number of top hubs to return

        Returns:
            List of hub skills with transition counts
        """
        if not self._built:
            self._build_graph()

        # Calculate incoming and outgoing counts
        incoming = defaultdict(int)
        outgoing = defaultdict(int)

        for source, destinations in self._graph.items():
            outgoing[source] = sum(destinations.values())
            for dest, count in destinations.items():
                incoming[dest] += count

        # Calculate total activity
        activity = {}
        for skill in set(incoming.keys()) | set(outgoing.keys()):
            activity[skill] = incoming.get(skill, 0) + outgoing.get(skill, 0)

        # Get top hubs
        sorted_hubs = sorted(activity.items(), key=lambda x: x[1], reverse=True)
        return [
            {
                "skill_id": skill,
                "total_transitions": count,
                "incoming": incoming.get(skill, 0),
                "outgoing": outgoing.get(skill, 0)
            }
            for skill, count in sorted_hubs[:top_n]
        ]

    def get_path_suggestions(self, current_skill: str) -> List[str]:
        """Suggest likely next skills based on patterns.

        Args:
            current_skill: The current skill ID

        Returns:
            List of suggested next skill IDs (ordered by frequency)
        """
        transitions = self.get_transitions(current_skill)

        # Sort by count and return skill IDs
        sorted_transitions = sorted(
            transitions.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return [skill for skill, count in sorted_transitions]

    def visualize_graph(self) -> str:
        """Generate a simple text representation of the graph.

        Returns:
            String representation of the graph
        """
        if not self._built:
            self._build_graph()

        lines = ["Skill Transition Graph:", "=" * 40]

        for source, destinations in sorted(self._graph.items()):
            lines.append(f"\n{source}:")
            for dest, count in sorted(destinations.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  -> {dest} ({count})")

        return "\n".join(lines)
