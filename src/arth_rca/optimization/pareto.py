"""
Pareto frontier extraction and 2D non-dominated sorting algorithms.
Computes the trade-off curve between implementation cost ($) and schedule days recovered.
"""

from typing import List
from arth_rca.optimization.models import ParetoPoint


def dominates(p1: ParetoPoint, p2: ParetoPoint) -> bool:
    """
    Returns True if p1 dominates p2:
    - p1 cost <= p2 cost AND p1 days_recovered >= p2 days_recovered
    - With at least one strict inequality (strictly cheaper or strictly more days recovered).
    """
    cost_better_or_equal = p1.cost_delta <= p2.cost_delta
    days_better_or_equal = p1.days_recovered >= p2.days_recovered
    strict_improvement = (p1.cost_delta < p2.cost_delta) or (p1.days_recovered > p2.days_recovered)

    return cost_better_or_equal and days_better_or_equal and strict_improvement


def extract_pareto_frontier(points: List[ParetoPoint]) -> List[ParetoPoint]:
    """
    Extract the non-dominated Pareto frontier from a set of evaluated scenario points.
    Sorts the resulting frontier by ascending cost (and ascending days recovered).
    """
    if not points:
        return []

    # Filter out dominated points
    frontier: List[ParetoPoint] = []

    for cand in points:
        is_cand_dominated = False
        # Check against existing frontier
        for existing in list(frontier):
            if dominates(existing, cand):
                is_cand_dominated = True
                break
            elif dominates(cand, existing):
                frontier.remove(existing)
            elif (
                abs(cand.cost_delta - existing.cost_delta) < 1e-3
                and abs(cand.days_recovered - existing.days_recovered) < 1e-3
                and cand.remaining_discrete_delayed_count == existing.remaining_discrete_delayed_count
            ):
                # Duplicate point, keep the one with shorter lever set or first seen
                is_cand_dominated = True
                break

        if not is_cand_dominated:
            frontier.append(cand)

    # Sort frontier by increasing cost
    frontier.sort(key=lambda p: (p.cost_delta, -p.days_recovered))
    return frontier
