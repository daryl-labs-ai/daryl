"""
DSM-ANS (Adaptive Navigation System) — Analysis Engine.

Rôle: Analyze skill performance from usage/success telemetry and produce
rankings, workflow recommendations, and optional RR-based agent insights.
Does not write to DSM; reads log files (skills_usage.jsonl, skills_success.jsonl)
and optionally RR query engine for shard-backed analysis.

API principale (ANSEngine):
  - load() / load_events(): load usage and success events from log paths.
  - analyze_skills(): compute skill performance and recommendations.
  - analyze_agent(): optional RR-based analysis when query_engine is provided.
  - get_report() / get_skill_rankings() / get_workflow_recommendations(): access results.

Contraintes:
  - Telemetry is separate from DSM kernel (log files, not Storage).
  - Does not modify DSM core or any shards.
  - Optional dependency on RR (query_engine) for analyze_agent().
"""

import os
from typing import List, Dict, Optional, TYPE_CHECKING

from .ans_models import (
    SkillPerformance,
    TransitionPerformance,
    SkillRecommendation,
    WorkflowRecommendation,
    TransitionWarning,
    ANSReport,
    UsageEvent,
    SuccessEvent
)
from .ans_analyzer import (
    load_usage_events,
    load_success_events,
    compute_skill_performance,
    compute_transition_performance,
    recommend_best_next_skills,
    detect_weak_skills,
    detect_weak_transitions,
    recommend_workflows,
    ANSAnalyzer,
)
from .ans_scorer import ANSScorer

if TYPE_CHECKING:
    from ..rr.query import RRQueryEngine


class ANSEngine:
    """Audience Neural System analysis engine.

    This class coordinates the analysis of DSM-SKILLS telemetry
    to produce performance rankings and insights.
    """

    def __init__(
        self,
        usage_log_path: str = None,
        success_log_path: str = None,
        query_engine: "RRQueryEngine" = None,
    ):
        """Initialize ANS engine with log file paths and optional RR query engine.

        Args:
            usage_log_path: Path to skills_usage.jsonl (default: logs/skills_usage.jsonl)
            success_log_path: Path to skills_success.jsonl (default: logs/skills_success.jsonl)
            query_engine: Optional RRQueryEngine for ANS v1 analyze_agent() (RR-based analysis).
        """
        # Set default paths relative to dsm/skills/
        if usage_log_path is None:
            usage_log_path = os.path.join(
                os.path.dirname(__file__),
                "..", "skills", "logs", "skills_usage.jsonl"
            )

        if success_log_path is None:
            success_log_path = os.path.join(
                os.path.dirname(__file__),
                "..", "skills", "logs", "skills_success.jsonl"
            )

        self.usage_log_path = usage_log_path
        self.success_log_path = success_log_path
        self._query_engine = query_engine
        self._analyzer = ANSAnalyzer()
        self._scorer = ANSScorer()

        self.usage_events: List[UsageEvent] = []
        self.success_events: List[SuccessEvent] = []
        self.skill_performance: Dict[str, SkillPerformance] = {}
        self.transition_performance: List[TransitionPerformance] = []

    def analyze_agent(self, agent: str) -> Dict[str, Dict]:
        """ANS v1: analyze an agent via RR query → analyze → score. No DSM writes.

        Uses RRQueryEngine.query(agent=agent), then ANSAnalyzer and ANSScorer.
        Requires ANSEngine(query_engine=...) to be set.

        Returns:
            {"agent": agent, "skills": {skill_id: score, ...}}
        """
        if self._query_engine is None:
            return {"agent": agent, "skills": {}}
        records = self._query_engine.query(agent=agent)
        stats = self._analyzer.analyze(records)
        scores = self._scorer.score(stats)
        return {"agent": agent, "skills": scores}

    def load(self) -> None:
        """Load all telemetry data from log files.

        Loads usage events and success/failure events from
        configured log file paths.
        """
        self.usage_events = load_usage_events(self.usage_log_path)
        self.success_events = load_success_events(self.success_log_path)

    def analyze_skills(self) -> Dict[str, SkillPerformance]:
        """Analyze skill performance metrics.

        Returns:
            Dictionary mapping skill_id to SkillPerformance objects
        """
        self.skill_performance = compute_skill_performance(
            self.usage_events,
            self.success_events
        )
        return self.skill_performance

    def analyze_transitions(self) -> List[TransitionPerformance]:
        """Analyze skill transition performance.

        Returns:
            List of TransitionPerformance objects
        """
        self.transition_performance = compute_transition_performance(
            self.usage_events,
            self.success_events
        )
        return self.transition_performance

    def generate_report(self) -> ANSReport:
        """Generate complete ANS analysis report.

        Returns:
            ANSReport object with rankings and insights
        """
        from datetime import datetime, timezone

        # Ensure analysis is done
        if not self.skill_performance:
            self.analyze_skills()
        if not self.transition_performance:
            self.analyze_transitions()

        # Generate Phase 1 rankings (original)
        top_skills = self.rank_top_skills(limit=5)
        weakest_skills = self.rank_weakest_skills(limit=5)
        transition_rankings = self.rank_transitions(limit=10)

        # Generate Phase 1 insights
        notes = self._generate_insights()

        report = ANSReport(
            generated_at=datetime.now(timezone.utc).isoformat() + "Z",
            top_skills=top_skills,
            weakest_skills=weakest_skills,
            transition_rankings=transition_rankings,
            notes=notes,
            recommendations=[],  # Phase 1
            workflow_recommendations=[],  # Phase 1
            transition_warnings=[]  # Phase 1
        )

        return report

    def generate_recommendation_report(self) -> ANSReport:
        """Generate ANS recommendation report (Phase 2).

        Returns:
            ANSReport object with Phase 2 recommendations
        """
        from datetime import datetime, timezone
        from .ans_models import (
            SkillRecommendation,
            WorkflowRecommendation
        )

        # Ensure analysis is done
        if not self.skill_performance:
            self.analyze_skills()
        if not self.transition_performance:
            self.analyze_transitions()

        # Generate Phase 2 recommendations
        next_skill_recs = self.recommend_next_skills(skill_id=None)
        workflow_recs = self.recommend_workflows()
        transition_warnings = []  # Could be populated by detect_risks

        # Generate insights
        notes = []

        if next_skill_recs:
            notes.append(
                f"Recommended next skills based on transition patterns and performance metrics."
            )

        if workflow_recs:
            notes.append(
                f"Recommended optimal workflows prioritizing short successful chains (2-4 skills)."
            )

        if transition_warnings:
            notes.append(
                f"Detected {len(transition_warnings)} weak transitions requiring attention."
            )

        # Create extended report
        report = ANSReport(
            generated_at=datetime.now(timezone.utc).isoformat() + "Z",
            top_skills=self.rank_top_skills(limit=5),
            weakest_skills=self.rank_weakest_skills(limit=5),
            transition_rankings=self.rank_transitions(limit=10),
            notes=notes,
            recommendations=next_skill_recs,
            workflow_recommendations=workflow_recs,
            transition_warnings=transition_warnings
        )

        return report

    def rank_top_skills(self, limit: int = 5) -> List[SkillPerformance]:
        """Rank skills by performance (best first).

        Args:
            limit: Maximum number of skills to return

        Returns:
            List of top-performing skills
        """
        skills = list(self.skill_performance.values())

        # Sort by success rate (descending), then by usage count
        skills.sort(key=lambda s: (-s.success_rate, -s.usage_count))

        return skills[:limit]

    def rank_weakest_skills(self, limit: int = 5) -> List[SkillPerformance]:
        """Rank skills by worst performance (lowest success rate first).

        Args:
            limit: Maximum number of skills to return

        Returns:
            List of worst-performing skills
        """
        skills = list(self.skill_performance.values())

        # Sort by success rate (ascending), then by failure count (descending)
        skills.sort(key=lambda s: (s.success_rate, -s.failure_count))

        return skills[:limit]

    def rank_transitions(self, limit: int = 10) -> List[TransitionPerformance]:
        """Rank skill transitions by frequency.

        Args:
            limit: Maximum number of transitions to return

        Returns:
            List of most common transitions
        """
        transitions = self.transition_performance.copy()

        # Sort by transition count (descending)
        transitions.sort(key=lambda t: -t.transition_count)

        return transitions[:limit]

    def get_skill_by_id(self, skill_id: str) -> Optional[SkillPerformance]:
        """Get performance data for a specific skill.

        Args:
            skill_id: ID of the skill to retrieve

        Returns:
            SkillPerformance object, or None if not found
        """
        return self.skill_performance.get(skill_id)

    def recommend_next_skills(self, skill_id: str = None) -> List[SkillRecommendation]:
        """Recommend best next skills based on performance and transitions.

        Args:
            skill_id: ID of the current skill (None for global recommendations)

        Returns:
            List of recommended next skills

        Heuristics:
            - If skill_id is None, return top global recommendations
            - If skill_id is provided, recommend likely best next skills from graph
            - Prioritize transitions with higher count
            - Boost transitions that lead to skills with high success rate
        """
        from .ans_models import SkillRecommendation

        # If no skill_id, return global best skills as SkillRecommendation
        if skill_id is None:
            top = self.rank_top_skills(limit=5)
            return [
                SkillRecommendation(
                    skill_id=s.skill_id,
                    skill_name=s.skill_id,
                    score=s.success_rate,
                    reason=f"Top performer: success rate {s.success_rate:.1%}, used {s.usage_count} times",
                    priority="high" if s.success_rate >= 0.7 else "medium" if s.success_rate >= 0.4 else "low",
                )
                for s in top
            ]

        # Get all transitions from this skill
        transitions = [
            t for t in self.transition_performance
            if t.from_skill == skill_id
        ]

        if not transitions:
            return []

        # Sort transitions by count (descending), then by success rate
        transitions.sort(key=lambda t: (-t.transition_count, t.success_rate))

        # Get top 3 next skills
        recommendations = []
        for trans in transitions[:3]:
            next_skill = trans.to_skill
            next_skill_perf = self.skill_performance.get(next_skill)
            if next_skill_perf:
                # Calculate score based on transition count and success rate
                max_count = max(t.transition_count for t in self.transition_performance)
                score = (trans.transition_count / max_count) * 0.5 + \
                          next_skill_perf.success_rate * 0.5

                reason = (
                    f"{trans.transition_count} transitions to {next_skill} "
                    f"with success rate {next_skill_perf.success_rate:.1%}"
                )

                # Determine priority
                if score > 0.7:
                    priority = "high"
                elif score > 0.4:
                    priority = "medium"
                else:
                    priority = "low"

                recommendations.append(SkillRecommendation(
                    skill_id=next_skill,
                    skill_name=next_skill,
                    score=score,
                    reason=reason,
                    priority=priority
                ))

        return recommendations

    def recommend_workflows(self) -> List[WorkflowRecommendation]:
        """Recommend optimal skill workflows based on performance data.

        Returns:
            List of workflow recommendations

        Heuristics:
            - Prioritize short successful chains (2-4 skills)
            - Favor skills with high success rates
            - Avoid weak skills and transitions
        """
        from .ans_models import WorkflowRecommendation

        if not self.transition_performance:
            return []

        # Build transition map for fast lookup
        trans_map = {}
        for trans in self.transition_performance:
            trans_map[(trans.from_skill, trans.to_skill)] = trans

        # Track chain quality for each skill
        chain_quality = {}  # skill -> [(length, avg_success_rate)]

        for skill_id, perf in self.skill_performance.items():
            # Find outgoing transitions
            outgoing = [t for t in self.transition_performance if t.from_skill == skill_id]

            if not outgoing:
                continue

            # Calculate quality metrics for each path
            for trans in outgoing[:3]:  # Limit to top 3 paths
                to_skill = trans.to_skill
                to_perf = self.skill_performance.get(to_skill)

                if to_perf:
                    # Follow the chain further
                    next_outgoing = [t for t in self.transition_performance if t.from_skill == to_skill]
                    if next_outgoing:
                        next_trans = next_outgoing[0]
                        next_perf = self.skill_performance.get(next_trans.to_skill)

                        if next_perf:
                            # Calculate chain score
                            chain_score = (trans.success_rate + next_perf.success_rate) / 2
                        else:
                            chain_score = trans.success_rate
                    else:
                        chain_score = trans.success_rate

                    quality = (len([trans, next_trans]), chain_score)
                else:
                    quality = (1, trans.success_rate)

                if skill_id not in chain_quality:
                    chain_quality[skill_id] = []
                chain_quality[skill_id].append(quality)

        # Generate recommendations for each skill
        recommendations = []

        for skill_id, quality_list in chain_quality.items():
            if not quality_list:
                continue

            # Sort by average success rate (descending), then by length (ascending)
            quality_list.sort(key=lambda x: (-x[1], x[0]))

            # Get best chain
            best_length, best_score = quality_list[0]
            best_chain = []

            # Reconstruct chain
            current = skill_id
            best_chain.append(current)

            for _ in range(best_length - 1):
                # Find best next skill
                current_trans = [t for t in self.transition_performance if t.from_skill == current]
                if not current_trans:
                    break

                # Sort by success rate (descending), then by count (descending)
                current_trans.sort(key=lambda t: (-t.success_rate, -t.transition_count))

                next_skill = current_trans[0].to_skill
                best_chain.append(next_skill)
                current = next_skill

            # Calculate overall score
            score = (best_score * 0.6) + ((len(best_chain) - 1) * 0.2 * 0.4)

            reason = (
                f"Chain of {len(best_chain)} skills with "
                f"avg success rate {best_score:.1%}"
            )

            recommendations.append(WorkflowRecommendation(
                sequence=best_chain,
                score=score,
                reason=reason
            ))

        # Sort recommendations by score (descending)
        recommendations.sort(key=lambda r: -r.score)

        return recommendations[:10]  # Return top 10

    def detect_risks(self) -> List[str]:
        """Detect weak skills and transitions for risk analysis.

        Returns:
            List of risk descriptions
        """
        risks = []

        # Detect weak skills
        weak_skills = detect_weak_skills(self.skill_performance, threshold=0.7)
        if weak_skills:
            risks.append(f"Skills with low success rate (<70%): {', '.join(weak_skills)}")

        # Detect weak transitions
        weak_transitions = detect_weak_transitions(self.transition_performance, threshold=0.5)
        if weak_transitions:
            for trans in weak_transitions:
                risks.append(
                    f"Weak transition: {trans.from_skill} -> {trans.to_skill} "
                    f"(success rate {trans.success_rate:.1%})"
                )

        # Check for slow skills
        slow_skills = [
            s for s in self.skill_performance.values()
            if s.avg_duration_ms > 2000 and s.usage_count > 1
        ]
        if slow_skills:
            risks.append(
                f"Slow skills (avg duration >2s): {', '.join(s.skill_id for s in slow_skills)}"
            )

        return risks

    def _generate_insights(self) -> List[str]:
        """Generate insights and recommendations.

        Returns:
            List of insight strings
        """
        insights = []

        if not self.skill_performance:
            insights.append("No skill performance data available.")
            return insights

        # Find overall best and worst skills
        skills = list(self.skill_performance.values())

        if skills:
            best_skill = max(skills, key=lambda s: s.success_rate)
            worst_skill = min(skills, key=lambda s: s.success_rate)

            insights.append(
                f"Best performing skill: {best_skill.skill_id} "
                f"(success rate: {best_skill.success_rate:.1%})"
            )
            insights.append(
                f"Weakest performing skill: {worst_skill.skill_id} "
                f"(success rate: {worst_skill.success_rate:.1%})"
            )

        # Analyze common transitions
        if self.transition_performance:
            top_transition = max(
                self.transition_performance,
                key=lambda t: t.transition_count
            )
            insights.append(
                f"Most common transition: {top_transition.from_skill} -> "
                f"{top_transition.to_skill} ({top_transition.transition_count} times)"
            )

        # Check for slow skills
        slow_skills = [
            s for s in skills
            if s.avg_duration_ms > 1000 and s.usage_count > 1
        ]
        if slow_skills:
            insights.append(
                f"Skills with average duration >1s: "
                f"{len(slow_skills)} ({', '.join(s.skill_id for s in slow_skills)})"
            )

        return insights

    def print_report(self, report: ANSReport) -> None:
        """Print formatted report to console.

        Args:
            report: ANSReport object to print
        """
        print()
        print("=" * 70)
        print("DSM-ANS (Audience Neural System) Report")
        print("=" * 70)
        print(f"Generated at: {report.generated_at}")
        print()

        # Top skills
        if report.top_skills:
            print("Top Skills:")
            print("-" * 70)
            print(f"{'Skill':<30} {'Success':<10} {'Avg Duration':<15} {'Usage':<10}")
            print("-" * 70)
            for skill in report.top_skills:
                print(
                    f"{skill.skill_id:<30} "
                    f"{skill.success_rate:>6.1%}    "
                    f"{skill.avg_duration_ms:>10.0f}ms    "
                    f"{skill.usage_count:>5}"
                )
            print()

        # Weakest skills
        if report.weakest_skills:
            print("Weakest Skills:")
            print("-" * 70)
            print(f"{'Skill':<30} {'Success':<10} {'Failures':<10} {'Usage':<10}")
            print("-" * 70)
            for skill in report.weakest_skills:
                print(
                    f"{skill.skill_id:<30} "
                    f"{skill.success_rate:>6.1%}    "
                    f"{skill.failure_count:>6}    "
                    f"{skill.usage_count:>5}"
                )
            print()

        # Transitions
        if report.transition_rankings:
            print("Top Transitions:")
            print("-" * 70)
            print(f"{'Transition':<40} {'Count':<10} {'Success':<10}")
            print("-" * 70)
            for trans in report.transition_rankings:
                trans_str = f"{trans.from_skill} -> {trans.to_skill}"
                print(
                    f"{trans_str:<40} "
                    f"{trans.transition_count:>6}    "
                    f"{trans.success_rate:>6.1%}"
                )
            print()

        # Insights
        if report.notes:
            print("Insights:")
            print("-" * 70)
            for i, note in enumerate(report.notes, 1):
                print(f"{i}. {note}")
            print()

        # Phase 2: Recommendations
        if report.recommendations:
            print("Skill Recommendations (Phase 2):")
            print("-" * 70)
            for i, rec in enumerate(report.recommendations, 1):
                priority_marker = "★" if rec.priority == "high" else " " if rec.priority == "medium" else ""
                print(
                    f"{priority_marker} {i}. {rec.skill_id} "
                    f"(score: {rec.score:.2f}, "
                    f"priority: {rec.priority}) - {rec.reason}"
                )
            print()

        # Phase 2: Workflow Recommendations
        if report.workflow_recommendations:
            print("Workflow Recommendations (Phase 2):")
            print("-" * 70)
            for i, rec in enumerate(report.workflow_recommendations, 1):
                sequence = " -> ".join(rec.sequence)
                print(
                    f"{i}. {sequence} "
                    f"(score: {rec.score:.2f}) - {rec.reason}"
                )
            print()

        # Phase 2: Transition Warnings
        if report.transition_warnings:
            print("Transition Warnings (Phase 2):")
            print("-" * 70)
            for i, warning in enumerate(report.transition_warnings, 1):
                print(
                    f"{i}. {warning.from_skill} -> {warning.to_skill} "
                    f"(success rate: {warning.score:.2f}) - {warning.issue} "
                    f"[{warning.recommendation_type}]"
                )
            print()

        print("=" * 70)
