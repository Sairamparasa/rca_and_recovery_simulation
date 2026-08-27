# Authoritative System Architecture & Reference Guide
**Project:** AI-Assisted Schedule Driver Detection & Recovery Simulation System (`arth_rca`)

This document consolidates and indexes the authoritative architecture specifications and invariant rules established in:
- [`Complete_Implementation_Plan.md`](file:///c:/Users/saira/OneDrive/Desktop/arth_rca/docs/architecture/Complete_Implementation_Plan.md)
- [`Constraint_Classification_Implementation_Plan.md`](file:///c:/Users/saira/OneDrive/Desktop/arth_rca/docs/architecture/Constraint_Classification_Implementation_Plan.md)

---

## 1. Core Architecture Overview & Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. PRESENTATION LAYER                                                       │
│    - Driver Dashboard | What-If Workspace | PM Classification Queue UI      │
│    - Historical Trend Views | Graph Visualization (Cytoscape.js) | NL Query │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. AI REASONING LAYER (LLM - Anthropic/Claude)                              │
│    - Grounded narrative reports (never invents numbers)                     │
│    - NL to structured DB queries                                            │
│    - Certainty Tier Labels: FACT | INFERENCE | MODELED | SIMULATION_DEP     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. ANALYTICS & SIMULATION LAYER                                             │
│    - Driver Detection & Root-Cause Classifier                               │
│    - Impact Scoring & Convergence Node Flagging                             │
│    - DCMA 14-Point Health Checks (historical tracking)                      │
│    - Constraint Classification Pipeline (Hard vs Soft FS)                   │
│    - What-If Simulation Engine & Lever Generator                            │
│    - Combinatorial Optimization (ILP + Metaheuristic Pareto Frontier)       │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. DETERMINISTIC CPM CORE                                                   │
│    - Pure-function interface: (activities, relationships, calendars) -> CPM │
│    - Calendar-aware forward/backward pass                                   │
│    - Total Float & Free Float (matching source tool float mode)             │
│    - Driving-relationship detection & Longest Path                          │
│    - Retained Logic & Progress Override OOS handling                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ 5. DATA & INGESTION LAYER                                                   │
│    - Primavera XER parser & snapshot history store (PostgreSQL)             │
│    - Immutable snapshot versioning                                          │
│    - Stable relationship keys (`hash(pred_code, succ_code, rel_type)`)       │
│    - In-memory / derived graph representation (NetworkX)                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Invariant Rules & Structural Constraints

1. **Deterministic CPM as Ground Truth:**
   - The CPM engine is a **pure function** with zero side effects.
   - Calculations must match P6/source scheduling outputs to the exact day.
2. **Explicit Scope Exclusion (No ML Trend Forecasting):**
   - Trend data (float erosion, driver churn, DCMA scores) is strictly **historical reporting**.
   - No predictive extrapolation or ML-based forecasting.
3. **Hard vs. Soft FS Safety Gate:**
   - Fast-tracking (FS → SS conversion or lag reduction) is **only** permitted on relationships classified as `SOFT_RESOURCE` or `SOFT_COORDINATION`.
   - Relationships marked `HARD_PHYSICAL`, `HARD_REGULATORY`, `HARD_SAFETY`, or `UNCLASSIFIED` can **NEVER** be converted by the simulation or optimization engines.
4. **Stable Relationship Identity:**
   - Keys are computed as `hash(predecessor_task_code, successor_task_code, relationship_type)` to safely carry classifications and diffs across immutable snapshots.
5. **No Autonomous Schedule Writes:**
   - LLMs and engines do not alter schedules or baselines autonomously; all actions require human/PM review and audit attribution (`reviewed_by`, `approved_by`).
6. **Certainty Tier Grounding:**
   - Every generated report claim is tagged: `FACT`, `INFERENCE`, `MODELED`, or `SIMULATION_DEPENDENT`.

---

## 3. Authoritative Schema Reference

### 3.1 Relational Schema (PostgreSQL)
- **`Organization`**: `id`, `name`, `created_at`
- **`Project`**: `id`, `org_id`, `name`, `p6_project_id`, `calendar_default_id`, `created_at`
- **`Snapshot`** (Immutable): `id`, `project_id`, `imported_at`, `source_filename`, `data_date`, `is_baseline`, `baseline_revision_reason`, `raw_file_ref`
- **`Activity`**: `id`, `snapshot_id`, `task_code`, `name`, `wbs_path`, `calendar_id`, `original_duration`, `remaining_duration`, `percent_complete`, `status`, `early_start`, `early_finish`, `late_start`, `late_finish`, `total_float`, `free_float`, `constraint_type`, `constraint_date`, `is_milestone`
- **`Relationship`**: `id`, `snapshot_id`, `predecessor_activity_id`, `successor_activity_id`, `relationship_type` (FS/SS/FF/SF), `lag`, `is_driving`
- **`Calendar`**: `id`, `project_id`, `name`, `working_days_json`, `exceptions_json`
- **`DriverRecord`**: `id`, `snapshot_id`, `head_activity_id`, `root_cause_type` (constraint | logic_change | out_of_sequence | external_delay | unresolved), `float_days`, `downstream_activity_count`, `impact_score`, `milestones_blocked`
- **`DrivingChain`**: `id`, `driver_record_id`, `activity_id`, `parent_activity_id`, `direction` (backward_root_trace | forward_blast_radius), `relationship_type`, `lag`, `is_convergence_node`
- **`RelationshipClassification`**: `relationship_key`, `project_id`, `constraint_type` (`HARD_PHYSICAL`, `HARD_REGULATORY`, `HARD_SAFETY`, `SOFT_RESOURCE`, `SOFT_COORDINATION`, `UNCLASSIFIED`), `confidence`, `classification_source` (`HEURISTIC_KEYWORD`, `HEURISTIC_LAG`, `HEURISTIC_CSI_JUMP`, `LIBRARY_MATCH`, `PM_REVIEWED`), `rationale`, `reviewed_by`, `reviewed_at`, `library_pattern_id`
- **`ClassificationPattern`**: `id`, `org_id`, `project_id`, `match_type` (`NAME_PAIR_REGEX`, `NAME_PAIR_FUZZY`, `CSI_PAIR`), `predecessor_pattern`, `successor_pattern`, `constraint_type`, `min_lag_hrs`, `source`, `times_matched`, `times_overridden`, `org_scope`
- **`Scenario`**: `id`, `project_id`, `baseline_snapshot_id`, `created_by`, `created_at`, `levers_applied_json`, `status` (`proposed`, `approved`, `tracked`, `rejected`), `result_finish_date`, `result_float_summary_json`, `result_cost_delta`, `engine_version`
- **`DCMAHealthCheck`**: `id`, `snapshot_id`, `missing_logic_pct`, `negative_float_pct`, `high_float_outlier_pct`, `hard_constraint_count`, `negative_lag_count`, `critical_path_length_index`, `invalid_date_count`, `computed_at`
- **`EvidenceLedgerEntry`**: `id`, `driver_record_id` or `scenario_id`, `claim_text`, `certainty_tier`, `source_ref`

---

## 4. Recovery Levers & Constraints Matrix

| Lever | Operation | Guardrail / Pre-Condition |
|---|---|---|
| **Crash** | Reduce duration by $N$ days | Requires cost/resource curve if reporting cost delta |
| **Fast-Track** | FS &rarr; SS conversion, or lag reduction | **MUST** pass `is_fasttrack_candidate` (`SOFT_RESOURCE` / `SOFT_COORDINATION`) |
| **Logic Change** | Remove / modify a relationship | PM approval required |
| **Constraint Relaxation**| Remove / modify hard constraint date | PM approval required (often contract-bound) |
| **Resequencing** | Reorder non-dependent activities | Only between activities with no existing logic tie |
| **Calendar Change** | Extended shift / weekend work | Flags cost/resource-strain note |
| **Activity Split** | Divide activity into parallel sub-activities | Requires resource loading to validate feasibility |
