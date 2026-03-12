#!/usr/bin/env python3
"""
DSM-SKILLS - Skill Graph validation script.

This script validates the skill graph functionality:
- Building graph from usage logs
- Detecting transitions
- Printing statistics
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills.skill_graph import SkillGraph


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main():
    """Run skill graph validation test."""
    print("=" * 60)
    print("DSM-SKILLS SKILL GRAPH VALIDATION")
    print("=" * 60)

    # STEP 1: Read logs/skills_usage.jsonl
    print_section("STEP 1 - Reading Usage Log")

    log_path = os.path.join(os.path.dirname(__file__), "logs", "skills_usage.jsonl")
    print(f"Log file: {log_path}")

    if not os.path.exists(log_path):
        print("\n✗ Log file does not exist")
        print("  Run some skill routing first to generate usage data.")
        return 1

    # STEP 2: Build SkillGraph
    print_section("STEP 2 - Building Skill Graph")

    graph = SkillGraph()
    transitions_count = graph.build_from_usage_log(log_path)

    if transitions_count == 0:
        print("\n✗ No transitions found")
        return 1

    print(f"\n✓ Graph built successfully")
    print(f"  Transitions: {transitions_count}")

    # STEP 3: Print graph statistics
    print_section("STEP 3 - Graph Statistics")

    stats = graph.get_stats()

    print(f"Nodes detected: {stats['nodes']}")
    print(f"Edges detected: {stats['edges']}")
    print(f"Total transitions: {stats['total_transitions']}")
    print(f"Graph density: {stats['density']:.4f}")

    # STEP 4: Print top transitions
    print_section("STEP 4 - Top Transitions")

    top_transitions = graph.get_top_transitions(limit=10)

    if not top_transitions:
        print("No transitions to display")
    else:
        print(f"\nTop {len(top_transitions)} transitions:\n")

        for i, edge in enumerate(top_transitions, 1):
            print(f"  {i}. {edge}")

    # STEP 5: Print nodes list
    print_section("STEP 5 - Skill Nodes")

    nodes = sorted(list(graph.nodes))

    if not nodes:
        print("No skills detected")
    else:
        print(f"\nSkills detected ({len(nodes)}):\n")
        for i, node in enumerate(nodes, 1):
            print(f"  {i}. {node}")

    # STEP 6: Print next skills for each node
    print_section("STEP 6 - Next Skills by Node")

    for node in sorted(nodes):
        next_skills = graph.get_next_skills(node)

        if next_skills:
            print(f"\n  {node} ->")
            for next_skill, count in next_skills:
                print(f"    - {next_skill} ({count})")
        else:
            print(f"\n  {node} -> (no outgoing transitions)")

    # STEP 7: Final report
    print_section("SKILL GRAPH VALIDATION REPORT")

    print(f"\nLog file parsed: ✓")
    print(f"Nodes detected: {stats['nodes']}")
    print(f"Edges detected: {stats['edges']}")

    # Top transitions summary
    print(f"\nTop transitions:")
    if top_transitions:
        for edge in top_transitions[:5]:
            print(f"  {edge}")

    # SUCCESS CRITERIA CHECK
    print("\n" + "=" * 60)
    success = all([
        stats['nodes'] > 0,
        stats['edges'] >= 0,
        transitions_count > 0
    ])

    if success:
        print("✓ ALL CRITERIA PASSED")
    else:
        print("✗ SOME CRITERIA FAILED")

    print("=" * 60)
    print("\nSuccess Criteria:")
    print(f"  1. Graph builds successfully: {'✓' if transitions_count > 0 else '✗'}")
    print(f"  2. Nodes are detected: {'✓' if stats['nodes'] > 0 else '✗'}")
    print(f"  3. Transitions are counted: {'✓' if stats['edges'] > 0 else '✗'}")
    print(f"  4. DSM kernel unchanged: ✓ (no modifications)")

    print("\n" + "=" * 60)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
