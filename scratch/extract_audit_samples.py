from arth_rca.parser.xer_parser import XERParser
from arth_rca.analytics.classification import classify_relationship
from pathlib import Path
from collections import defaultdict

samples = defaultdict(list)

for xer_path in [Path('xer_files/247011 08-18 (1).xer'), Path('xer_files/20260304-QTS-PHX3DC1-0114DD_TFO Baseline Schedule - Current (1).xer')]:
    parsed = XERParser().parse_file(xer_path)
    tasks = parsed.tasks
    fs_rels = [p for p in parsed.predecessors if p.pred_type == 'PR_FS']
    for rel in fs_rels:
        pred_t = tasks.get(rel.pred_task_id)
        succ_t = tasks.get(rel.task_id)
        if not pred_t or not succ_t:
            continue
        res = classify_relationship(
            pred_task_code=pred_t.task_code,
            pred_task_name=pred_t.task_name or '',
            succ_task_code=succ_t.task_code,
            succ_task_name=succ_t.task_name or '',
            rel_type='FS',
            lag_days=rel.lag_hr_cnt / 8.0,
        )
        if res.is_auto_classified:
            if 0.80 <= res.confidence < 0.85:
                samples['0.80-0.85'].append((pred_t.task_code, pred_t.task_name, succ_t.task_code, succ_t.task_name, res.constraint_type, res.confidence, res.rationale))
            elif 0.85 <= res.confidence < 0.90:
                samples['0.85-0.90'].append((pred_t.task_code, pred_t.task_name, succ_t.task_code, succ_t.task_name, res.constraint_type, res.confidence, res.rationale))
            elif res.confidence >= 0.90:
                samples['0.90+'].append((pred_t.task_code, pred_t.task_name, succ_t.task_code, succ_t.task_name, res.constraint_type, res.confidence, res.rationale))

print(f"Collected samples counts: {{ {', '.join(f'{k}: {len(v)}' for k, v in samples.items())} }}")
for band in ['0.85-0.90', '0.90+']:
    items = samples[band]
    print(f"\n=======================================================")
    print(f"=== BAND {band} (showing top 20 of {len(items)}) ===")
    print(f"=======================================================")
    for i, it in enumerate(items[:20], 1):
        print(f"{i:2d}. [{it[4]}] (Conf={it[5]:.2f})\n    PRED: {it[0]} - '{it[1]}'\n    SUCC: {it[2]} - '{it[3]}'\n    WHY : {it[6]}\n")
