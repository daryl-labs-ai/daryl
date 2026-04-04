"""
Tests for skills/registry.py and skills/router.py — targeting uncovered lines.

Covers:
  - SkillRegistry: register, get, list_skills, search, count, clear
  - SkillRouter: route, route_to
"""

import pytest

from dsm.skills.models import Skill
from dsm.skills.registry import SkillRegistry
from dsm.skills.router import SkillRouter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry():
    return SkillRegistry()


@pytest.fixture
def sample_skills():
    return [
        Skill(
            skill_id="task_decomposition",
            domain="reasoning",
            description="Break a complex task into smaller logical steps.",
            trigger_conditions=["complex", "multi-step", "decompose"],
            prompt_template="Break the task into steps.",
            tags=["planning"],
        ),
        Skill(
            skill_id="summarization",
            domain="writing",
            description="Summarize content into concise form.",
            trigger_conditions=["summarize", "summary", "condense"],
            prompt_template="Summarize the following.",
            tags=["writing"],
        ),
        Skill(
            skill_id="code_review",
            domain="engineering",
            description="Review code for bugs and best practices.",
            trigger_conditions=["review", "code quality"],
            prompt_template="Review this code.",
            tags=["engineering"],
        ),
    ]


# ---------------------------------------------------------------------------
# SkillRegistry
# ---------------------------------------------------------------------------

class TestSkillRegistry:
    def test_register_and_get(self, registry, sample_skills):
        registry.register(sample_skills[0])
        result = registry.get("task_decomposition")
        assert result is not None
        assert result.skill_id == "task_decomposition"

    def test_get_nonexistent(self, registry):
        assert registry.get("nonexistent") is None

    def test_register_duplicate_raises(self, registry, sample_skills):
        registry.register(sample_skills[0])
        with pytest.raises(ValueError, match="already registered"):
            registry.register(sample_skills[0])

    def test_list_skills(self, registry, sample_skills):
        for s in sample_skills:
            registry.register(s)
        listed = registry.list_skills()
        assert len(listed) == 3

    def test_count(self, registry, sample_skills):
        assert registry.count() == 0
        registry.register(sample_skills[0])
        assert registry.count() == 1

    def test_clear(self, registry, sample_skills):
        for s in sample_skills:
            registry.register(s)
        assert registry.count() == 3
        registry.clear()
        assert registry.count() == 0

    def test_search_by_id(self, registry, sample_skills):
        for s in sample_skills:
            registry.register(s)
        results = registry.search("summarization")
        assert len(results) == 1
        assert results[0].skill_id == "summarization"

    def test_search_by_description(self, registry, sample_skills):
        for s in sample_skills:
            registry.register(s)
        results = registry.search("bugs")
        assert len(results) == 1
        assert results[0].skill_id == "code_review"

    def test_search_by_trigger(self, registry, sample_skills):
        for s in sample_skills:
            registry.register(s)
        results = registry.search("decompose")
        assert len(results) == 1
        assert results[0].skill_id == "task_decomposition"

    def test_search_no_match(self, registry, sample_skills):
        for s in sample_skills:
            registry.register(s)
        results = registry.search("zzzznotfound")
        assert results == []

    def test_search_case_insensitive(self, registry, sample_skills):
        for s in sample_skills:
            registry.register(s)
        results = registry.search("SUMMARIZE")
        assert len(results) >= 1


# ---------------------------------------------------------------------------
# SkillRouter
# ---------------------------------------------------------------------------

class TestSkillRouter:
    def test_route_returns_skill_id(self, registry, sample_skills):
        for s in sample_skills:
            registry.register(s)
        router = SkillRouter(registry)
        result = router.route("I need to summarize this document")
        assert result == "summarization"

    def test_route_returns_none_no_match(self, registry, sample_skills):
        for s in sample_skills:
            registry.register(s)
        router = SkillRouter(registry)
        assert router.route("hello world") is None

    def test_route_to_returns_skill_object(self, registry, sample_skills):
        for s in sample_skills:
            registry.register(s)
        router = SkillRouter(registry)
        skill = router.route_to("this is a complex problem")
        assert skill is not None
        assert skill.skill_id == "task_decomposition"

    def test_route_to_returns_none(self, registry, sample_skills):
        for s in sample_skills:
            registry.register(s)
        router = SkillRouter(registry)
        assert router.route_to("nothing matches here") is None

    def test_route_case_insensitive(self, registry, sample_skills):
        for s in sample_skills:
            registry.register(s)
        router = SkillRouter(registry)
        assert router.route("REVIEW this code please") is not None

    def test_route_first_match_wins(self, registry):
        s1 = Skill(skill_id="first", domain="d", description="d", trigger_conditions=["test"])
        s2 = Skill(skill_id="second", domain="d", description="d", trigger_conditions=["test"])
        registry.register(s1)
        registry.register(s2)
        router = SkillRouter(registry)
        result = router.route("run the test")
        assert result == "first"
