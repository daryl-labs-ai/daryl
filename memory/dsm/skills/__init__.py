"""
DSM-SKILLS - A reusable skill system for DSM v2.
"""

import os
import sys

# Get to dsm_v2 directory (grandparent)
dsm_v2_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Add dsm_v2 to sys.path
sys.path.insert(0, dsm_v2_dir)

from dsm_v2.skills.models import Skill
from dsm_v2.skills.registry import SkillRegistry
