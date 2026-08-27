"""
Configuration parameters for Phase 4 Combinatorial Optimization & Pareto Analysis.
All thresholds, cost rates, and solver limits are configurable constants.
"""

from pydantic import BaseModel, Field


class OptimizationConfig(BaseModel):
    # Solver threshold: candidate sets <= this threshold use exact ILP solver; larger sets use Metaheuristic (GA)
    ilp_exact_solver_max_candidates: int = Field(
        default=15,
        description="Maximum number of candidate levers to solve via exact ILP (PuLP). Sets > 15 use Genetic Algorithm.",
    )

    # Standardized Cost Heuristics (labeled ASSUMED_HEURISTIC when XER lacks TASKRSRC records)
    default_crash_cost_per_day: float = Field(
        default=2500.0,
        description="Standard assumed cost per work-day crushed (overtime / expedited trade shift).",
    )
    default_fasttrack_coordination_cost: float = Field(
        default=1500.0,
        description="Assumed trade coordination and supervision overhead per fast-tracked relationship link.",
    )
    default_admin_logic_cost: float = Field(
        default=500.0,
        description="Administrative and engineering review cost per logic modification / constraint relaxation.",
    )

    # Genetic Algorithm Parameters
    ga_population_size: int = Field(default=40, description="Population size for GA search.")
    ga_generations: int = Field(default=25, description="Number of generations to evolve.")
    ga_crossover_prob: float = Field(default=0.8, description="Crossover probability.")
    ga_mutation_prob: float = Field(default=0.2, description="Mutation probability per gene.")

    # Budget & Objective Defaults
    default_budget_limit: float = Field(
        default=100000.0,
        description="Default maximum budget limit for recovery levers ($).",
    )


DEFAULT_OPTIMIZATION_CONFIG = OptimizationConfig()
