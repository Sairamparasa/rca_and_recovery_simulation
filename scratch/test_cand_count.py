from pathlib import Path
from arth_rca.parser.xer_parser import XERParser
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput
from arth_rca.analytics.classification import classify_relationship
from arth_rca.db.models import RelationshipClassification
from arth_rca.optimization.optimizer import generate_candidate_levers_for_drivers

p1 = XERParser().parse_file(Path('xer_files/20260304-QTS-PHX3DC1-0114DD_TFO Baseline Schedule - Current (1).xer'))
acts1 = {
    t.task_id: CPMActivityInput(
        task_id=t.task_id, task_code=t.task_code, calendar_id=t.clndr_id or 1,
        original_duration_days=t.target_durn_hr_cnt / 8.0, remaining_duration_days=t.remain_durn_hr_cnt / 8.0,
        task_type=t.task_type
    ) for t in p1.tasks.values()
}
rels1 = [
    CPMRelationshipInput(
        rel_id=pr.task_pred_id, pred_task_id=pr.pred_task_id, succ_task_id=pr.task_id,
        rel_type='FS' if pr.pred_type == 'PR_FS' else ('SS' if pr.pred_type == 'PR_SS' else ('FF' if pr.pred_type == 'PR_FF' else 'SF')),
        lag_days=pr.lag_hr_cnt / 8.0,
    ) for pr in p1.predecessors
]

cands = generate_candidate_levers_for_drivers(acts1, rels1, {}, {"QTS-41811", "QTS-29341", "QTS-29711", "QTS-30141", "DC1-MECH-L4-Cx-1070", "DC1-MECH-L4-Cx-1060"})
print(f"Generated {len(cands)} candidates:")
for c in cands:
    print(f"  - {c.candidate_id}: Cost=${c.estimated_cost:,.0f}, Savings={c.estimated_time_savings_days}d")
