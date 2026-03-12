"""
DSM-ANS (Audience Neural System) - Data Models.

This module defines data structures for audience and skill performance analysis.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class UsageEvent:
    """Represents a skill usage event from log.

    Attributes:
        timestamp: When the skill was used
        event_type: Type of event (should be "skill_usage")
        task_description: The task that triggered the skill
        skill_id: ID of the skill used
        skill_name: Domain name of the skill
    """
    timestamp: str
    event_type: str
    task_description: str
    skill_id: str
    skill_name: str


@dataclass
class SuccessEvent:
    """Represents a skill success/failure event from log.

    Attributes:
        timestamp: When the event was recorded
        event_type: Type of event (should be "skill_success")
        task_description: The task that was attempted
        skill_id: ID of the skill
        skill_name: Domain name of the skill
        success: Whether the execution succeeded
        duration_ms: Execution duration in milliseconds
        notes: Optional notes about the execution
    """
    timestamp: str
    event_type: str
    task_description: str
    skill_id: str
    skill_name: str
    success: bool
    duration_ms: float
    notes: Optional[str]


@dataclass
class SkillPerformance:
    """Performance metrics for a single skill.

    Attributes:
        skill_id: ID of the skill
        usage_count: Total number of times the skill was used
        success_count: Number of successful executions
        failure_count: Number of failed executions
        success_rate: Success rate (0.0 to 1.0)
        avg_duration_ms: Average execution duration in milliseconds
    """
    skill_id: str
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    success_rate: float = 0.0
    avg_duration_ms: float = 0.0


@dataclass
class TransitionPerformance:
    """Performance metrics for skill transitions.

    Attributes:
        from_skill: Source skill ID
        to_skill: Destination skill ID
        transition_count: Number of times this transition occurred
        success_rate: Success rate of the destination skill after this transition
    """
    from_skill: str
    to_skill: str
    transition_count: int = 0
    success_rate: float = 0.0


@dataclass
class SkillRecommendation:
    """Recommendation for next skill to use.

    Attributes:
        skill_id: ID of the recommended skill
        skill_name: Name of the recommended skill
        score: Recommendation score (0.0 to 1.0)
        rationale: Explanation for the recommendation
        priority: Recommendation priority (high/medium/low)
    """
    skill_id: str
    skill_name: str
    score: float
    rationale: str
    priority: str = "medium"
    score: float = 0.0


@dataclass
class WorkflowRecommendation:
    """Recommendation for a complete skill workflow.

    Attributes:
        sequence: List of skill IDs in recommended order
        score: Overall workflow score (0.0 to 1.0)
        reason: Explanation for the recommendation
    """
    sequence: List[str] = field(default_factory=list)
    score: float = 0.0
    reason: str = ""


@dataclass
class TransitionWarning:
    """Warning about a weak transition.

    Attributes:
        from_skill: Source skill ID
        to_skill: Destination skill ID
        issue: Description of the issue
        score: Success rate of the transition (0.0 to 1.0)
        recommendation_type: Type of recommendation (best_next_skill/avoid_skill/recommended_workflow)
    """
    from_skill: str
    to_skill: str
    issue: str
    score: float
    recommendation_type: str


@dataclass
class ANSReport:
    """Complete audience neural system analysis report.

    Attributes:
        generated_at: Timestamp when report was generated
        top_skills: List of best-performing skills
        weakest_skills: List of worst-performing skills
        transition_rankings: List of ranked skill transitions
        notes: Additional observations or recommendations
        recommendations: List of skill recommendations (Phase 2)
        workflow_recommendations: List of workflow recommendations (Phase 2)
        transition_warnings: List of transition warnings (Phase 2)
    """
    generated_at: str
    top_skills: List[SkillPerformance] = field(default_factory=list)
    weakest_skills: List[SkillPerformance] = field(default_factory=list)
    transition_rankings: List[TransitionPerformance] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    recommendations: List[SkillRecommendation] = field(default_factory=list)
    workflow_recommendations: List[WorkflowRecommendation] = field(default_factory=list)
    transition_warnings: List[TransitionWarning] = field(default_factory=list)
