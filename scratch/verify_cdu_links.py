from pathlib import Path
from arth_rca.parser.xer_parser import XERParser
from arth_rca.analytics.classification import classify_relationship
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput

p1 = XERParser().parse_file(Path('xer_files/20260304-QTS-PHX3DC1-0114DD_TFO Baseline Schedule - Current (1).xer'))

cdu_links = []
for pr in p1.predecessors:
    pt = p1.tasks.get(pr.pred_task_id)
    st = p1.tasks.get(pr.task_id)
    if not pt or not st:
        continue
    if "CDU" in (pt.task_code or "") and "Cx" in (st.task_code or ""):
        c_res = classify_relationship(pt.task_code, pt.task_name or '', st.task_code, st.task_name or '', rel_type='FS', lag_days=pr.lag_hr_cnt/8.0)
        cdu_links.append((pt.task_code, pt.task_name, st.task_code, st.task_name, c_res.constraint_type, c_res.confidence, c_res.rationale))

print(f"Audited {len(cdu_links)} CDU feeder links to Level 4 Cx:")
for pt_code, pt_name, st_code, st_name, ctype, conf, rat in cdu_links[:5]:
    print(f"  - {pt_code} ('{pt_name}') -> {st_code} ('{st_name}')")
    print(f"      Type: {ctype} | Confidence: {conf:.2f} | Rationale: {rat}")
