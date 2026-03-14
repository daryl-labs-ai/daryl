# -*- coding: utf-8 -*-
"""
Pytest fixtures for DSM-ANS tests.

Fixtures provide usage_events and success_events in the exact format
expected by load_usage_events / load_success_events (UsageEvent and SuccessEvent).
"""

import pytest

from dsm.ans.ans_models import UsageEvent, SuccessEvent


@pytest.fixture
def usage_events():
    """List of UsageEvent matching the structure expected by compute_skill_performance and compute_transition_performance."""
    return [
        UsageEvent(
            timestamp="2026-03-14T10:00:00Z",
            event_type="skill_usage",
            task_description="Decompose task into steps",
            skill_id="task_decomposition",
            skill_name="reasoning",
        ),
        UsageEvent(
            timestamp="2026-03-14T10:01:00Z",
            event_type="skill_usage",
            task_description="Summarize content",
            skill_id="summarization",
            skill_name="writing",
        ),
    ]


@pytest.fixture
def success_events():
    """List of SuccessEvent matching the structure expected by compute_skill_performance and compute_transition_performance."""
    return [
        SuccessEvent(
            timestamp="2026-03-14T10:00:01Z",
            event_type="skill_success",
            task_description="Decompose task into steps",
            skill_id="task_decomposition",
            skill_name="reasoning",
            success=True,
            duration_ms=150.0,
            notes=None,
        ),
        SuccessEvent(
            timestamp="2026-03-14T10:01:01Z",
            event_type="skill_success",
            task_description="Summarize content",
            skill_id="summarization",
            skill_name="writing",
            success=True,
            duration_ms=200.0,
            notes=None,
        ),
    ]
