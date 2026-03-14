#!/usr/bin/env python3
"""
DSM-SKILLS - Command-line interface for skill management.

Purpose:
- CLI for listing skills
- Ingesting skills from libraries
- Viewing skill usage statistics
- Viewing skill success/failure statistics
- Viewing skill transition graph
"""

import argparse
import json
import os
import sys

from pathlib import Path as _Path
_dsm_skills_dir = _Path(__file__).resolve().parent

from dsm.skills.models import Skill
from dsm.skills.registry import SkillRegistry
from dsm.skills.router import SkillRouter
from dsm.skills.ingestor import SkillIngestor
from dsm.skills.skill_usage_logger import SkillUsageLogger
from dsm.skills.skill_success_logger import SkillSuccessLogger
from dsm.skills.success_analyzer import SkillSuccessAnalyzer
from dsm.skills.skill_graph import SkillGraph


def cmd_list(args):
    """List all registered skills."""
    registry = SkillRegistry()

    # Ingest skills from libraries
    ingestor = SkillIngestor(registry)
    libraries_dir = str(_dsm_skills_dir / "libraries")
    if os.path.isdir(libraries_dir):
        for library_name in os.listdir(libraries_dir):
            library_path = os.path.join(libraries_dir, library_name)
            if os.path.isdir(library_path):
                report = ingestor.ingest_from_directory(library_path)
                print(f"Ingested {report.skills_loaded} skills from {library_name}", file=sys.stderr)

    # List skills
    skills = registry.list_skills()
    print(f"\nRegistered Skills ({len(skills)}):")
    print("=" * 50)

    for skill in sorted(skills, key=lambda s: s.skill_id):
        print(f"\nID: {skill.skill_id}")
        print(f"Description: {skill.description}")
        print(f"Domain: {skill.domain}")
        print(f"Triggers: {', '.join(skill.trigger_conditions) if skill.trigger_conditions else 'None'}")


def cmd_usage(args):
    """Show skill usage statistics."""
    logger = SkillUsageLogger()

    stats = logger.get_usage_stats()
    recent = logger.get_recent_usage(limit=10)

    print("\nSkill Usage Statistics:")
    print("=" * 50)

    if not stats:
        print("No usage data available.")
    else:
        print("\nUsage Count by Skill:")
        for skill_id, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
            print(f"  {skill_id}: {count}")

    print("\nRecent Usage Events:")
    if not recent:
        print("  No recent events.")
    else:
        for event in recent:
            print(f"  [{event.get('timestamp')}] {event.get('skill_name')} - {event.get('task_description')[:60]}...")


def cmd_success(args):
    """Show skill success/failure statistics."""
    success_logger = SkillSuccessLogger()
    analyzer = SkillSuccessAnalyzer(success_logger)

    report = analyzer.generate_report()

    print("\nSkill Success Statistics:")
    print("=" * 50)

    overall = report.get("overall", {})
    print(f"\nOverall:")
    print(f"  Total Attempts: {overall.get('total_attempts', 0)}")
    print(f"  Success Rate: {overall.get('overall_success_rate', 0):.1%}")

    skills = report.get("skills", [])
    print(f"\nPer-Skill Statistics:")
    for skill in skills:
        print(f"\n  {skill['skill_id']}:")
        print(f"    Success Rate: {skill['success_rate']:.1%}")
        print(f"    Avg Duration: {skill['avg_duration_ms']:.0f}ms")
        print(f"    Attempts: {skill['total_attempts']}")


def cmd_graph(args):
    """Show skill transition graph."""
    usage_logger = SkillUsageLogger()
    graph = SkillGraph(usage_logger)

    common_sequences = graph.get_common_sequences(min_count=2)
    hub_skills = graph.get_hub_skills(top_n=5)

    print("\nSkill Transition Graph:")
    print("=" * 50)

    print("\nCommon Sequences (count >= 2):")
    if not common_sequences:
        print("  No common sequences found.")
    else:
        for seq in common_sequences:
            print(f"  {seq['source']} -> {seq['destination']} ({seq['count']} times)")

    print("\nHub Skills (most transitions):")
    if not hub_skills:
        print("  No hub skills found.")
    else:
        for hub in hub_skills:
            print(f"  {hub['skill_id']}: {hub['total_transitions']} transitions "
                  f"(in: {hub['incoming']}, out: {hub['outgoing']})")

    print(f"\n{graph.visualize_graph()}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="DSM-SKILLS CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list command
    subparsers.add_parser("list", help="List all registered skills")

    # usage command
    subparsers.add_parser("usage", help="Show skill usage statistics")

    # success command
    subparsers.add_parser("success", help="Show skill success/failure statistics")

    # graph command
    subparsers.add_parser("graph", help="Show skill transition graph")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "usage":
        cmd_usage(args)
    elif args.command == "success":
        cmd_success(args)
    elif args.command == "graph":
        cmd_graph(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
