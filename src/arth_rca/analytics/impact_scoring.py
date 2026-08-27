"""
Impact Scoring Engine.
Calculates driver impact score using configurable project scoring weights:
impact_score = downstream_activity_count * (float_magnitude * float_magnitude_weight) * (1.0 + milestone_count * milestone_weight)
"""

from typing import Optional
from pydantic import BaseModel, Field


class ScoringConfig(BaseModel):
    project_id: Optional[int] = None
    float_magnitude_weight: float = 1.0
    milestone_weight: float = 2.0
    downstream_count_weight: float = 1.0
    negative_float_threshold_days: float = 0.0
    high_float_threshold_days: float = 44.0


def calculate_driver_impact_score(
    downstream_activity_count: int,
    total_float_days: float,
    milestone_count: int,
    config: Optional[ScoringConfig] = None,
) -> float:
    """
    Calculate normalized impact score for a delay driver tree.
    """
    cfg = config or ScoringConfig()

    float_magnitude = abs(total_float_days)
    float_factor = max(1.0, float_magnitude * cfg.float_magnitude_weight)
    milestone_factor = 1.0 + (milestone_count * cfg.milestone_weight)
    activity_factor = max(1, downstream_activity_count) * cfg.downstream_count_weight

    score = activity_factor * (float_factor / 10.0) * milestone_factor
    return round(score, 2)
