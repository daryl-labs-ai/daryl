"""
DSM-ANS (Audience Neural System) - Analyzer.

This module provides functions to load and analyze DSM-SKILLS telemetry logs.
"""

import json
import os
from typing import List, Optional

from .ans_models import UsageEvent, SuccessEvent


def load_usage_events(path: str) -> List[UsageEvent]:
    """Load skill usage events from JSONL log file.

    Args:
        path: Path to skills_usage.jsonl

    Returns:
        List of UsageEvent objects

    Skips invalid lines without crashing.
    """
    events = []

    if not os.path.exists(path):
        return events

    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)

                    # Validate event type
                    if data.get("event_type") != "skill_usage":
                        continue

                    event = UsageEvent(
                        timestamp=data.get("timestamp", ""),
                        event_type=data.get("event_type", ""),
                        task_description=data.get("task_description", ""),
                        skill_id=data.get("skill_id", ""),
                        skill_name=data.get("skill_name", "")
                    )
                    events.append(event)

                except json.JSONDecodeError:
                    # Skip malformed JSON lines
                    continue
                except Exception:
                    # Skip lines with unexpected structure
                    continue

    except Exception:
        # Return empty list if file can't be read
        return events

    return events


def load_success_events(path: str) -> List[SuccessEvent]:
    """Load skill success/failure events from JSONL log file.

    Args:
        path: Path to skills_success.jsonl

    Returns:
        List of SuccessEvent objects

    Skips invalid lines without crashing.
    """
    events = []

    if not os.path.exists(path):
        return events

    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f,1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)

                    # Validate event type
                    if data.get("event_type") != "skill_success":
                        continue

                    event = SuccessEvent(
                        timestamp=data.get("timestamp", ""),
                        event_type=data.get("event_type", ""),
                        task_description=data.get("task_description", ""),
                        skill_id=data.get("skill_id", ""),
                        skill_name=data.get("skill_name", ""),
                        success=data.get("success", False),
                        duration_ms=data.get("duration_ms", 0),
                        notes=data.get("notes")
                    )
                    events.append(event)

                except json.JSONDecodeError:
                    # Skip malformed JSON lines
                    continue
                except Exception:
                    # Skip lines with unexpected structure
                    continue

    except Exception:
        # Return empty list if file can't be read
        return events

    return events


def compute_skill_performance(
    usage_events: List[UsageEvent],
    success_events: List[SuccessEvent]
) -> dict:
    """Compute performance metrics for each skill.

    Args:
        usage_events: List of usage events
        success_events: List of success/failure events

    Returns:
        Dictionary mapping skill_id to SkillPerformance objects
    """
    from .ans_models import SkillPerformance

    # Initialize performance dict
    performance = {}

    # Count usage by skill
    for event in usage_events:
        skill_id = event.skill_id
        if skill_id not in performance:
            performance[skill_id] = SkillPerformance(skill_id=skill_id)

        performance[skill_id].usage_count += 1

    # Process success/failure events
    durations_by_skill = {}

    for event in success_events:
        skill_id = event.skill_id

        if skill_id not in performance:
            performance[skill_id] = SkillPerformance(skill_id=skill_id)

        if event.success:
            performance[skill_id].success_count += 1

            # Track duration for averaging
            if skill_id not in durations_by_skill:
                durations_by_skill[skill_id] = []
            durations_by_skill[skill_id].append(event.duration_ms)
        else:
            performance[skill_id].failure_count += 1

    # Compute success rates and averages
    for skill_id, perf in performance.items():
        total = perf.success_count + perf.failure_count
        if total > 0:
            perf.success_rate = perf.success_count / total

        # Compute average duration
        if skill_id in durations_by_skill:
            durations = durations_by_skill[skill_id]
            if durations:
                perf.avg_duration_ms = sum(durations) / len(durations)

    return performance


def compute_transition_performance(
    usage_events: List[UsageEvent],
    success_events: List[SuccessEvent]
) -> List:
    """Compute performance metrics for skill transitions.

    Args:
        usage_events: List of usage events (in chronological order)
        success_events: List of success/failure events

    Returns:
        List of TransitionPerformance objects
    """
    from .ans_models import TransitionPerformance

    # Build skill performance dict for success rate lookup
    skill_perf = compute_skill_performance(usage_events, success_events)

    # Extract transitions from usage events
    transitions = {}
    prev_skill_id = None

    for event in usage_events:
        skill_id = event.skill_id

        if prev_skill_id is not None and skill_id != prev_skill_id:
            # Create transition key
            key = f"{prev_skill_id} -> {skill_id}"

            if key not in transitions:
                transitions[key] = TransitionPerformance(
                    from_skill=prev_skill_id,
                    to_skill=skill_id
                )

            transitions[key].transition_count += 1

        prev_skill_id = skill_id

    # Compute success rates for transitions
    for trans in transitions.values():
        # Use destination skill's success rate as proxy
        if trans.to_skill in skill_perf:
            trans.success_rate = skill_perf[trans.to_skill].success_rate

    return list(transitions.values())


def recommend_best_next_skills(
    skill_performance: dict,
    transitions: list
) -> list:
    """Recommend best next skills based on performance and transitions.

    Args:
        skill_performance: Dictionary mapping skill_id to SkillPerformance
        transitions: List of TransitionPerformance objects

    Returns:
        List of recommended next skills

    Heuristics:
        - Prioritize transitions with higher count
        - Boost transitions that lead to skills with high success rate
        - Consider overall skill performance
    """
    from .ans_models import SkillRecommendation

    recommendations = []

    # Get all transitions grouped by source skill
    transitions_by_source = {}
    for trans in transitions:
        source = trans.from_skill
        if source not in transitions_by_source:
            transitions_by_source[source] = []
        transitions_by_source[source].append(trans)

    # For each skill with transitions, recommend next skill
    for source_skill, source_transitions in transitions_by_source.items():
        # Sort transitions by count (descending)
        source_transitions.sort(key=lambda t: -t.transition_count)

        if not source_transitions:
            continue

        # Get best next skill
        best_transition = source_transitions[0]
        best_next_skill = best_transition.to_skill

        # Get performance of best next skill
        next_skill_perf = skill_performance.get(best_next_skill)
        if next_skill_perf:
            # Calculate score based on transition count and success rate
            score = (
                (best_transition.transition_count / max(t.transition_count for t in transitions)) * 0.5 +
                next_skill_perf.success_rate * 0.5
            )
        else:
            # Default score if no performance data
            score = best_transition.transition_count / max(t.transition_count for t in transitions)

        reason = (
            f"{best_transition.transition_count} transitions to {best_next_skill} "
            f"with success rate {next_skill_perf.success_rate:.1%}"
            if next_skill_perf else "no performance data"
        )

        # Determine priority
        if score > 0.7:
            priority = "high"
        elif score > 0.4:
            priority = "medium"
        else:
            priority = "low"

        recommendations.append(SkillRecommendation(
            skill_id=best_next_skill,
            skill_name=best_next_skill,
            score=score,
            reason=reason,
            priority=priority
        ))

    return recommendations


def detect_weak_skills(skill_performance: dict, threshold: float = 0.7) -> list:
    """Detect weak skills based on success rate and failures.

    Args:
        skill_performance: Dictionary mapping skill_id to SkillPerformance
        threshold: Success rate threshold (default 0.7)

    Returns:
        List of weak skill IDs
    """
    weak_skills = []

    for skill_id, perf in skill_performance.items():
        if perf.success_rate < threshold and perf.failure_count > 0:
            weak_skills.append(skill_id)

    return weak_skills


def detect_weak_transitions(transitions: list, threshold: float = 0.5) -> list:
    """Detect weak transitions based on success rate.

    Args:
        transitions: List of TransitionPerformance objects
        threshold: Success rate threshold (default 0.5)

    Returns:
        List of weak TransitionWarning objects
    """
    from .ans_models import TransitionWarning

    weak_transitions = []

    for trans in transitions:
        if trans.success_rate < threshold:
            issue = f"Low success rate ({trans.success_rate:.1%}) after {trans.from_skill}"

            # Determine recommendation type
            if trans.success_rate < 0.3:
                recommendation_type = "avoid_skill"
            else:
                recommendation_type = "best_next_skill"

            weak_transitions.append(TransitionWarning(
                from_skill=trans.from_skill,
                to_skill=trans.to_skill,
                issue=issue,
                score=trans.success_rate,
                recommendation_type=recommendation_type
            ))

    return weak_transitions


def recommend_workflows(skill_performance: dict, transitions: list) -> list:
    """Recommend optimal skill workflows based on performance data.

    Args:
        skill_performance: Dictionary mapping skill_id to SkillPerformance
        transitions: List of TransitionPerformance objects

    Returns:
        List of WorkflowRecommendation objects

    Heuristics:
        - Prioritize short successful chains (2-4 skills)
        - Favor skills with high success rates
        - Avoid weak skills and transitions
    """
    from .ans_models import WorkflowRecommendation

    # Build transition map for fast lookup
    trans_map = {}
    for trans in transitions:
        trans_map[(trans.from_skill, trans.to_skill)] = trans

    # Track chain quality for each skill
    chain_quality = {}  # skill -> [(length, avg_success_rate)]

    for from_skill, perf in skill_performance.items():
        # Find outgoing transitions
        outgoing = [t for t in transitions if t.from_skill == from_skill]

        if not outgoing:
            continue

        # Calculate quality metrics for each path
        for trans in outgoing[:3]:  # Limit to top 3 paths
            to_skill = trans.to_skill
            to_perf = skill_performance.get(to_skill)

            if to_perf:
                # Follow the chain further
                next_outgoing = [t for t in transitions if t.from_skill == to_skill]
                if next_outgoing:
                    next_trans = next_outgoing[0]
                    next_perf = skill_performance.get(next_trans.to_skill)

                    # Calculate chain score
                    if next_perf:
                        chain_score = (trans.success_rate + next_perf.success_rate) / 2
                    else:
                        chain_score = trans.success_rate

                    quality = (len([trans, next_trans]), chain_score)
                else:
                    quality = (1, trans.success_rate)

                if from_skill not in chain_quality:
                    chain_quality[from_skill] = []
                chain_quality[from_skill].append(quality)

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
            current_trans = [t for t in transitions if t.from_skill == current]
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
