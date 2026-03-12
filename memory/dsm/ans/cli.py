#!/usr/bin/env python3
"""
DSM-ANS (Audience Neural System) - CLI Interface.

This module provides command-line interface for ANS analysis.
Phase 2: Adds recommendation commands
"""

import argparse
import os
import sys

# Get to dsm_v2 directory
dsm_v2_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, dsm_v2_dir)

from ans.ans_engine import ANSEngine
from ans.ans_models import UsageEvent, SuccessEvent


def cmd_report(args):
    """Generate and display ANS report."""
    # Create engine
    engine = ANSEngine(
        usage_log_path=args.usage_log,
        success_log_path=args.success_log
    )

    # Load and analyze
    engine.load()
    report = engine.generate_report()

    # Print report
    engine.print_report(report)


def cmd_recommend(args):
    """Generate and display skill recommendations."""
    # Create engine
    engine = ANSEngine(
        usage_log_path=args.usage_log,
        success_log_path=args.success_log
    )

    # Load and analyze
    engine.load()
    report = engine.generate_recommendation_report()

    # Print report
    engine.print_report(report)


def cmd_recommend_task(args):
    """Generate recommendations for a specific task type."""
    # Create engine
    engine = ANSEngine(
        usage_log_path=args.usage_log,
        success_log_path=args.success_log
    )

    # Load and analyze
    engine.load()

    # Get recommendations for specific task
    task = args.task_id
    recommendations = engine.recommend_next_skills(skill_id=task)

    # Print recommendations
    print(f"\nRecommendations for task: {task}")
    print("=" * 60)

    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            priority_marker = "★" if rec.priority == "high" else " " if rec.priority == "medium" else ""
            print(f"{priority_marker} {i}. {rec.skill_id} - {rec.explanation}")
            print(f"   Score: {rec.score:.2f}, Priority: {rec.priority}")
    else:
        print(f"No recommendations found for task: {task}")

    print("=" * 60)


def cmd_risks(args):
    """Detect and display weak skills and transitions."""
    # Create engine
    engine = ANSEngine(
        usage_log_path=args.usage_log,
        success_log_path=args.success_log
    )

    # Load and analyze
    engine.load()

    # Detect risks
    report = engine.generate_recommendation_report()

    # Print risks
    if report.transition_warnings:
        print("\nTransition Warnings:")
        print("=" * 60)

        for i, warning in enumerate(report.transition_warnings, 1):
            print(f"{i}. {warning.from_skill} -> {warning.to_skill}")
            print(f"   Issue: {warning.issue}")
            print(f"   Success Rate: {warning.score:.1%}")
            print(f"   Type: {warning.recommendation_type}")

        print("=" * 60)
    else:
        print("\nNo transition warnings detected.")

    # Print weak skills from recommendations
    weak_skills = [rec for rec in report.recommendations if "avoid" in rec.explanation.lower()]

    if weak_skills:
        print("\nSkills to Avoid:")
        print("=" * 60)

        for i, rec in enumerate(weak_skills, 1):
            print(f"{i}. {rec.skill_id} - {rec.explanation}")

        print("=" * 60)
    else:
        print("\nNo weak skills detected.")


def cmd_list(args):
    """List all available skills in telemetry."""
    # Create engine
    engine = ANSEngine(
        usage_log_path=args.usage_log,
        success_log_path=args.success_log
    )

    # Load
    engine.load()

    # List skills
    skills = list(engine.skill_performance.values())
    skills.sort(key=lambda s: s.skill_id)

    print(f"\nAvailable Skills ({len(skills)}):")
    print("=" * 50)

    for skill in skills:
        print(f"  {skill.skill_id:<25} usage: {skill.usage_count:>3}  "
              f"success: {skill.success_rate:>5.1%}  "
              f"duration: {skill.avg_duration_ms:>7.0f}ms")

    print("=" * 50)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="DSM-ANS (Audience Neural System) CLI"
    )

    parser.add_argument(
        '--usage-log',
        default=None,
        help='Path to skills_usage.jsonl'
    )
    parser.add_argument(
        '--success-log',
        default=None,
        help='Path to skills_success.jsonl'
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # report command (Phase 1)
    subparsers.add_parser(
        'report',
        help='Generate complete ANS analysis report'
    )

    # recommend command (Phase 2)
    subparsers.add_parser(
        'recommend',
        help='Generate skill and workflow recommendations'
    )

    # recommend task command (Phase 2)
    recommend_parser = subparsers.add_parser(
        'recommend-task',
        help='Generate recommendations for a specific task type'
    )
    recommend_parser.add_argument(
        'task_id',
        help='Task ID to get recommendations for (e.g., task_decomposition)'
    )

    # risks command (Phase 2)
    subparsers.add_parser(
        'risks',
        help='Detect weak skills and transitions'
    )

    # list command (Phase 1)
    subparsers.add_parser(
        'list',
        help='List all available skills in telemetry'
    )

    args = parser.parse_args()

    if args.command == 'report':
        cmd_report(args)
    elif args.command == 'recommend':
        cmd_recommend(args)
    elif args.command == 'recommend-task':
        cmd_recommend_task(args)
    elif args.command == 'risks':
        cmd_risks(args)
    elif args.command == 'list':
        cmd_list(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
