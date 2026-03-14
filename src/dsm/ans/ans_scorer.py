"""
ANS v1 (RR-based) scorer: turns analyzer stats into per-skill scores.
"""

from typing import Dict, Any


class ANSScorer:
    """Scores skills from ANSAnalyzer stats. v1 rule: score = usage count."""

    def score(self, stats: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
        """Return a score per skill/event_type. Input = stats from ANSAnalyzer.analyze()."""
        return {
            k: (v.get("count") or 0)
            for k, v in stats.items()
        }
