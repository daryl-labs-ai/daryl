"""Deterministic DSM reasoning dataset evaluator v0.2."""

from .scorer import (
    MAX_SCORE,
    golden_candidate_for_record,
    load_records,
    score_record,
    score_user_isolation,
    user_scoped_records,
)

__all__ = [
    "MAX_SCORE",
    "golden_candidate_for_record",
    "load_records",
    "score_record",
    "score_user_isolation",
    "user_scoped_records",
]
