"""
Domain models and API contracts for Phase 4: Combinatorial Optimization & Pareto Analysis.
"""

from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime

from arth_rca.simulation.levers import AnyLever
from arth_rca.simulation.engine import SimulationDiffResult


class CandidateLeverOption(BaseModel):
    """An actionable candidate lever available to the optimizer."""
    candidate_id: str = Field(description="Unique identifier for the candidate lever option.")
    lever_type: str = Field(description="Type of lever: CRASH, FAST_TRACK, LOGIC_CHANGE, etc.")
    target_entity: str = Field(description="Target task code or relationship key.")
    lever: AnyLever = Field(description="Concrete typed recovery lever instance.")
    estimated_cost: float = Field(default=0.0, description="Estimated cost to execute this lever ($).")
    estimated_time_savings_days: float = Field(default=0.0, description="Nominal local duration reduction (days).")
    is_safety_cleared: bool = Field(default=True, description="Whether this candidate passes classification safety gates.")
    cost_source: str = Field(default="ASSUMED_HEURISTIC", description="ASSUMED_HEURISTIC or NATIVE_XER.")


class OptimizationRequest(BaseModel):
    """API payload to trigger schedule recovery optimization."""
    snapshot_id: int = Field(description="Snapshot ID to optimize against.")
    budget_limit: float = Field(default=100000.0, description="Total budget limit ($).")
    driver_ids: Optional[List[int]] = Field(default=None, description="Optional subset of driver record IDs to target.")
    strategy: Literal["AUTO", "ILP", "METAHEURISTIC"] = Field(default="AUTO", description="Optimization solver strategy.")
    max_pareto_points: int = Field(default=10, description="Maximum number of Pareto frontier solutions to return.")
    custom_levers: Optional[List[AnyLever]] = Field(default=None, description="Optional custom candidate levers to consider.")


class ParetoPoint(BaseModel):
    """An individual non-dominated solution point on the time-cost Pareto frontier."""
    scenario_name: str
    cost_delta: float
    days_recovered: float
    simulated_finish_date: str
    remaining_discrete_delayed_count: int = Field(
        description="Count of discrete delayed activities (TT_LOE and TT_WBS strictly excluded)."
    )
    discrete_delayed_recovered_count: int = Field(
        description="Count of discrete delayed activities brought to TF >= 0."
    )
    critical_path_shifted: bool
    levers_applied: List[Dict[str, Any]]
    cost_source: str = Field(default="ASSUMED_HEURISTIC")
    simulation_diff: Optional[SimulationDiffResult] = None


class OptimizationResult(BaseModel):
    """Full optimization result containing the Pareto frontier and search statistics."""
    project_id: int
    snapshot_id: int
    solver_used: str = Field(description="ILP_EXACT (PuLP) or METAHEURISTIC_GA (Genetic Algorithm).")
    budget_limit: float
    pareto_frontier: List[ParetoPoint]
    total_scenarios_evaluated: int
    total_infeasible_rejected: int
    execution_time_ms: float
    cost_source_note: str = Field(
        default="Assumed standard commercial rates ($2,500/day crash, $1,500/link fast-track) because source XER does not contain TASKRSRC cost records."
    )
