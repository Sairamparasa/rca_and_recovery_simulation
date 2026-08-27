from arth_rca.parser.xer_parser import XERParser
from arth_rca.analytics.driver_detection import detect_negative_float_drivers
from arth_rca.analytics.classification import classify_relationship, is_fasttrack_candidate
from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.cpm.calendar import parse_p6_clndr_data
from pathlib import Path
from collections import Counter

# 1. Reconcile 844 vs 837 vs 836 in File 2
p2 = XERParser().parse_file(Path('xer_files/247011 08-18 (1).xer'))
p6_neg_all = [t for t in p2.tasks.values() if t.status_code != 'TK_Complete' and t.total_float_hr_cnt < 0]
p6_neg_loe = [t for t in p6_neg_all if t.task_type == 'TT_LOE']
p6_neg_wbs = [t for t in p6_neg_all if t.task_type == 'TT_WBS']
p6_neg_discrete = [t for t in p6_neg_all if t.task_type not in ('TT_LOE', 'TT_WBS')]

print("=================================================================")
print(f"FILE 2 P6 NEGATIVE FLOAT POPULATION RECONCILIATION:")
print(f"Total non-completed negative-float tasks in P6: {len(p6_neg_all)}")
print(f"  - Level of Effort (TT_LOE) tasks: {len(p6_neg_loe)} ({[t.task_code for t in p6_neg_loe]})")
print(f"  - WBS Summary (TT_WBS) tasks: {len(p6_neg_wbs)}")
print(f"  - Discrete Activities (participating in driver analysis): {len(p6_neg_discrete)}")
print("=================================================================")

# 2. Check QTS-42391 and QTS-42371 in XER
t_map = {t.task_code: t for t in p2.tasks.values()}
t_391 = t_map.get('QTS-42391')
t_371 = t_map.get('QTS-42371')

print(f"\nRELATIONSHIP CHECK FOR QTS-42391 ('{t_391.task_name}'):")
preds_391 = [pr for pr in p2.predecessors if pr.task_id == t_391.task_id]
for pr in preds_391:
    pt = p2.tasks.get(pr.pred_task_id)
    print(f"  <- Pred in XER: {pt.task_code} - '{pt.task_name}' (type={pr.pred_type}, lag={pr.lag_hr_cnt/8}d)")

# 3. Check bare 'set' / 'setting' false positives across schedule
all_names_with_set = [
    t for t in p2.tasks.values() 
    if 'set' in (t.task_name or '').lower().split() or 'setting' in (t.task_name or '').lower().split()
]
print(f"\nBARE 'SET'/'SETTING' POPULATION IN FILE 2: {len(all_names_with_set)} tasks")
for t in all_names_with_set[:10]:
    print(f"  - {t.task_code}: '{t.task_name}'")
