"""
Driver detection and blast radius analysis engine.
Collects negative float activities, traces backward along driving paths to identify driver heads,
and traverses forward along driving paths to construct downstream blast radius trees.
"""

from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import networkx as nx
from pydantic import BaseModel, Field

from arth_rca.cpm.types import CPMResult, CPMActivityResult, CPMRelationshipResult, DrivingStatus


class BlastRadiusNode(BaseModel):
    task_id: int
    task_code: str
    early_start: str
    early_finish: str
    total_float_days: float
    is_critical: bool
    is_milestone: bool = False
    depth: int = 0
    is_convergence_node: bool = False


class DrivingChainTree(BaseModel):
    driver_task_id: int
    driver_task_code: str
    driver_total_float_days: float
    root_cause_type: str = "unresolved"
    root_cause_description: str = ""
    impact_score: float = 0.0
    downstream_activity_count: int = 0
    milestone_count: int = 0
    blast_radius_nodes: List[BlastRadiusNode] = Field(default_factory=list)
    driving_relationships: List[int] = Field(default_factory=list)  # rel_ids


class DriverAnalysisResult(BaseModel):
    snapshot_id: int
    total_negative_float_activities: int
    driver_head_count: int
    convergence_nodes: List[str] = Field(default_factory=list)  # task_codes appearing in multiple trees
    drivers: List[DrivingChainTree] = Field(default_factory=list)


def detect_negative_float_drivers(
    cpm_result: CPMResult,
    raw_tasks: Dict[int, any],
    raw_relationships: List[any],
    snapshot_id: int = 0,
    negative_float_threshold_days: float = -0.01,
) -> DriverAnalysisResult:
    """
    Identify driver heads and construct forward blast-radius trees.

    1. Collect all non-completed activities with TF < threshold.
    2. Build driving dependency subgraph for negative float activities.
    3. Traverse backward to find driver heads (activities with no upstream negative float driving predecessor).
    4. Traverse forward from each driver head along driving paths to build the blast radius tree.
    5. Flag convergence nodes (activities reachable by >1 driver head).
    """
    # 1. Collect negative float activities (exclude COMPLETED tasks)
    neg_float_tasks: Dict[int, CPMActivityResult] = {}
    for task_id, res in cpm_result.activities.items():
        raw_t = raw_tasks.get(task_id)
        status = getattr(raw_t, "status_code", "") if raw_t else ""
        if status != "TK_Complete" and res.total_float_days < negative_float_threshold_days:
            neg_float_tasks[task_id] = res

    if not neg_float_tasks:
        return DriverAnalysisResult(
            snapshot_id=snapshot_id,
            total_negative_float_activities=0,
            driver_head_count=0,
            convergence_nodes=[],
            drivers=[],
        )

    # 2. Build driving predecessor & successor graphs among negative float activities
    driving_succs: Dict[int, List[Tuple[int, int]]] = defaultdict(list)  # pred -> [(succ, rel_id)]
    driving_preds: Dict[int, List[Tuple[int, int]]] = defaultdict(list)  # succ -> [(pred, rel_id)]

    for rel in raw_relationships:
        pred_id = getattr(rel, "pred_task_id", None)
        succ_id = getattr(rel, "succ_task_id", None)
        rel_id = getattr(rel, "rel_id", None) or getattr(rel, "task_pred_id", 0)

        if pred_id in neg_float_tasks and succ_id in neg_float_tasks:
            # Check if this relationship is driving in CPM result
            rel_res = cpm_result.relationships.get(rel_id)
            if rel_res and rel_res.is_driving:
                driving_succs[pred_id].append((succ_id, rel_id))
                driving_preds[succ_id].append((pred_id, rel_id))

    # 3. Find Driver Heads: activities with negative float that have NO driving predecessor with negative float
    driver_head_ids: List[int] = []
    for task_id in neg_float_tasks:
        preds = driving_preds.get(task_id, [])
        if not preds:
            driver_head_ids.append(task_id)

    # If circularity or fully closed graph, take the activity with minimum total float
    if not driver_head_ids and neg_float_tasks:
        min_tf_task_id = min(neg_float_tasks.keys(), key=lambda tid: neg_float_tasks[tid].total_float_days)
        driver_head_ids.append(min_tf_task_id)

    # 4. Traverse forward from each driver head to construct blast radius trees
    driver_trees: List[DrivingChainTree] = []
    node_appearance_count: Dict[int, int] = defaultdict(int)

    for head_id in driver_head_ids:
        head_act = neg_float_tasks[head_id]
        head_raw = raw_tasks.get(head_id)
        head_code = getattr(head_raw, "task_code", str(head_id)) if head_raw else str(head_id)

        # BFS / DFS forward traversal along driving edges
        visited: Set[int] = set()
        queue: List[Tuple[int, int]] = [(head_id, 0)]  # (task_id, depth)
        tree_nodes: List[BlastRadiusNode] = []
        tree_rel_ids: List[int] = []
        milestone_cnt = 0

        while queue:
            curr_id, depth = queue.pop(0)
            if curr_id in visited:
                continue
            visited.add(curr_id)
            node_appearance_count[curr_id] += 1

            cpm_act = cpm_result.activities.get(curr_id)
            curr_raw = raw_tasks.get(curr_id)
            is_mile = "Mile" in getattr(curr_raw, "task_type", "") if curr_raw else False
            if is_mile:
                milestone_cnt += 1

            tree_nodes.append(
                BlastRadiusNode(
                    task_id=curr_id,
                    task_code=getattr(curr_raw, "task_code", str(curr_id)) if curr_raw else str(curr_id),
                    early_start=cpm_act.early_start.strftime("%Y-%m-%d %H:%M") if cpm_act else "",
                    early_finish=cpm_act.early_finish.strftime("%Y-%m-%d %H:%M") if cpm_act else "",
                    total_float_days=cpm_act.total_float_days if cpm_act else 0.0,
                    is_critical=cpm_act.is_critical if cpm_act else False,
                    is_milestone=is_mile,
                    depth=depth,
                    is_convergence_node=False,  # Evaluated in step 5
                )
            )

            for succ_id, r_id in driving_succs.get(curr_id, []):
                tree_rel_ids.append(r_id)
                if succ_id not in visited:
                    queue.append((succ_id, depth + 1))

        tree = DrivingChainTree(
            driver_task_id=head_id,
            driver_task_code=head_code,
            driver_total_float_days=head_act.total_float_days,
            downstream_activity_count=len(tree_nodes),
            milestone_count=milestone_cnt,
            blast_radius_nodes=tree_nodes,
            driving_relationships=list(set(tree_rel_ids)),
        )
        driver_trees.append(tree)

    # 5. Flag Convergence Nodes (nodes appearing in more than 1 driver tree)
    convergence_task_ids = {tid for tid, cnt in node_appearance_count.items() if cnt > 1}
    convergence_codes: List[str] = []

    for tree in driver_trees:
        for node in tree.blast_radius_nodes:
            if node.task_id in convergence_task_ids:
                node.is_convergence_node = True
                if node.task_code not in convergence_codes:
                    convergence_codes.append(node.task_code)

    return DriverAnalysisResult(
        snapshot_id=snapshot_id,
        total_negative_float_activities=len(neg_float_tasks),
        driver_head_count=len(driver_trees),
        convergence_nodes=convergence_codes,
        drivers=driver_trees,
    )
