"""
Multi-Objective Genetic Algorithm (GA) Metaheuristic Solver for large combinatorial spaces.
Explores multi-driver and convergence-node recovery combinations with full mid-search re-validation.
"""

from typing import List, Dict, Tuple, Optional, Any, Set
import time
import random

from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.db.models import RelationshipClassification
from arth_rca.simulation.engine import run_simulation, validate_lever_set
from arth_rca.optimization.models import CandidateLeverOption, ParetoPoint, OptimizationResult
from arth_rca.optimization.ilp_solver import filter_safety_cleared_candidates
from arth_rca.optimization.pareto import extract_pareto_frontier, dominates
from arth_rca.optimization.config import DEFAULT_OPTIMIZATION_CONFIG, OptimizationConfig


def solve_metaheuristic_pareto(
    candidates: List[CandidateLeverOption],
    activities: Dict[int, CPMActivityInput],
    relationships: List[CPMRelationshipInput],
    calendars: Dict[int, CPMCalendarInput],
    options: CPMOptions,
    classifications: Dict[str, RelationshipClassification],
    budget_limit: float,
    project_id: int,
    snapshot_id: int,
    project_data_dates: Optional[Dict[int, Any]] = None,
    project_late_anchors: Optional[Dict[int, Any]] = None,
    config: Optional[OptimizationConfig] = None,
) -> OptimizationResult:
    """
    Multi-objective Genetic Algorithm exploring recovery lever combinations.
    Guarantees every explored candidate passes classification gates and full combinatorial re-validation.
    """
    cfg = config or DEFAULT_OPTIMIZATION_CONFIG
    start_time = time.time()

    # 1. Strict pre-search gate
    cleared_candidates, initial_rejected = filter_safety_cleared_candidates(
        candidates, activities, relationships, classifications
    )

    evaluated_points: List[ParetoPoint] = []
    infeasible_count = initial_rejected
    evaluated_chromosomes: Set[Tuple[int, ...]] = set()

    # 2. Baseline point
    sim_base, diff_base = run_simulation(
        activities, relationships, calendars, options, [], classifications,
        project_data_dates=project_data_dates, project_late_anchors=project_late_anchors,
        scenario_name="Baseline",
    )
    evaluated_points.append(
        ParetoPoint(
            scenario_name="Baseline (No Action)",
            cost_delta=0.0,
            days_recovered=0.0,
            simulated_finish_date=diff_base.simulated_finish_date,
            remaining_discrete_delayed_count=diff_base.simulated_discrete_delayed_count,
            discrete_delayed_recovered_count=0,
            critical_path_shifted=False,
            levers_applied=[],
            cost_source="ASSUMED_HEURISTIC",
            simulation_diff=diff_base,
        )
    )

    num_genes = len(cleared_candidates)
    if num_genes == 0:
        exec_ms = (time.time() - start_time) * 1000.0
        return OptimizationResult(
            project_id=project_id,
            snapshot_id=snapshot_id,
            solver_used="METAHEURISTIC_GA",
            budget_limit=budget_limit,
            pareto_frontier=evaluated_points,
            total_scenarios_evaluated=1,
            total_infeasible_rejected=infeasible_count,
            execution_time_ms=exec_ms,
        )

    # 3. Helper: evaluate a chromosome
    def evaluate_chromosome(chromo: List[int]) -> Optional[ParetoPoint]:
        nonlocal infeasible_count
        chromo_key = tuple(chromo)
        if chromo_key in evaluated_chromosomes:
            return None
        evaluated_chromosomes.add(chromo_key)

        active_indices = [i for i, bit in enumerate(chromo) if bit == 1]
        if not active_indices:
            return None

        active_cands = [cleared_candidates[i] for i in active_indices]
        total_cost = sum(c.estimated_cost for c in active_cands)
        if total_cost > budget_limit:
            infeasible_count += 1
            return None

        active_levers = [c.lever for c in active_cands]
        try:
            # Full combinatorial mid-search re-validation
            validate_lever_set(active_levers, activities, relationships, classifications)
        except Exception:
            infeasible_count += 1
            return None

        sc_name = f"GA Scenario ({len(active_cands)} Levers, Cost ${total_cost:,.0f})"
        sim_res, diff = run_simulation(
            activities, relationships, calendars, options, active_levers, classifications,
            project_data_dates=project_data_dates, project_late_anchors=project_late_anchors,
            scenario_name=sc_name,
        )

        levers_summary = [
            {"candidate_id": c.candidate_id, "type": c.lever_type, "target": c.target_entity, "cost": c.estimated_cost}
            for c in active_cands
        ]

        point = ParetoPoint(
            scenario_name=sc_name,
            cost_delta=total_cost,
            days_recovered=diff.days_recovered,
            simulated_finish_date=diff.simulated_finish_date,
            remaining_discrete_delayed_count=diff.simulated_discrete_delayed_count,
            discrete_delayed_recovered_count=diff.discrete_delayed_recovered_count,
            critical_path_shifted=diff.critical_path_shifted,
            levers_applied=levers_summary,
            cost_source=active_cands[0].cost_source if active_cands else "ASSUMED_HEURISTIC",
            simulation_diff=diff,
        )
        return point

    # 4. Initialize Population
    population: List[List[int]] = []
    # Seed singletons
    for i in range(num_genes):
        c = [0] * num_genes
        c[i] = 1
        population.append(c)

    # Seed random sparse combinations
    while len(population) < cfg.ga_population_size:
        k = random.randint(1, min(num_genes, 4))
        indices = random.sample(range(num_genes), k)
        c = [0] * num_genes
        for idx in indices:
            c[idx] = 1
        population.append(c)

    # 5. Evolution Loop
    for gen in range(cfg.ga_generations):
        # Evaluate current population
        gen_points: List[Tuple[List[int], ParetoPoint]] = []
        for chromo in population:
            pt = evaluate_chromosome(chromo)
            if pt is not None:
                evaluated_points.append(pt)
                gen_points.append((chromo, pt))

        # Genetic Operators: Selection, Crossover, Mutation
        next_population: List[List[int]] = []
        if gen_points:
            # Sort by fitness (days_recovered / (1 + cost/10000))
            gen_points.sort(key=lambda item: item[1].days_recovered - 0.0001 * item[1].cost_delta, reverse=True)
            elites = [item[0] for item in gen_points[:max(2, len(gen_points) // 4)]]
            next_population.extend(elites)

        while len(next_population) < cfg.ga_population_size:
            # Tournament selection
            parent1 = random.choice(population)
            parent2 = random.choice(population)

            # Crossover
            child = list(parent1)
            if random.random() < cfg.ga_crossover_prob:
                cx_point = random.randint(1, max(1, num_genes - 1))
                child = parent1[:cx_point] + parent2[cx_point:]

            # Mutation
            for bit_idx in range(num_genes):
                if random.random() < cfg.ga_mutation_prob:
                    child[bit_idx] = 1 - child[bit_idx]

            # Budget check / repair
            tot_c = sum(cleared_candidates[i].estimated_cost for i, b in enumerate(child) if b == 1)
            while tot_c > budget_limit:
                active = [i for i, b in enumerate(child) if b == 1]
                if not active:
                    break
                rem_idx = random.choice(active)
                child[rem_idx] = 0
                tot_c = sum(cleared_candidates[i].estimated_cost for i, b in enumerate(child) if b == 1)

            next_population.append(child)

        population = next_population

    # 6. Extract final Pareto frontier
    pareto_frontier = extract_pareto_frontier(evaluated_points)
    exec_ms = (time.time() - start_time) * 1000.0

    return OptimizationResult(
        project_id=project_id,
        snapshot_id=snapshot_id,
        solver_used="METAHEURISTIC_GA",
        budget_limit=budget_limit,
        pareto_frontier=pareto_frontier,
        total_scenarios_evaluated=len(evaluated_points),
        total_infeasible_rejected=infeasible_count,
        execution_time_ms=exec_ms,
    )
