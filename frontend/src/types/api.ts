export type CertaintyTier = "FACT" | "INFERENCE" | "MODELED" | "SIMULATION_DEPENDENT" | "HYPOTHESIS";

export interface EvidenceLedgerEntry {
  id: number;
  claim_text: string;
  certainty_tier: CertaintyTier;
  source_entity: string;
  metric_name: string;
  metric_value: any;
  created_at: string;
}

export interface BlastRadiusNode {
  task_id: number;
  task_code: string;
  early_start: string;
  early_finish: string;
  total_float_days: number;
  is_critical: boolean;
  is_milestone?: boolean;
  depth: number;
  is_convergence_node?: boolean;
}

export interface DriverRecord {
  driver_task_id: number;
  driver_task_code: string;
  driver_name?: string;
  driver_total_float_days: number;
  root_cause_type: "constraint" | "out_of_sequence" | "logic_change" | "external_delay" | "unresolved";
  root_cause_description: string;
  impact_score: number;
  downstream_activity_count: number;
  milestone_count: number;
  blast_radius_nodes: BlastRadiusNode[];
}

export interface DriverAnalysisResult {
  snapshot_id: number;
  total_negative_float_activities: number;
  driver_head_count: number;
  convergence_nodes: string[];
  drivers: DriverRecord[];
}

export interface DCMAAssessmentReport {
  snapshot_id: number;
  data_date: string;
  total_tasks_evaluated: number;
  total_relationships_evaluated: number;
  overall_health_score: number;
  metrics: {
    check_number: number;
    name: string;
    target: string;
    actual_value: number;
    failed_count: number;
    passed: boolean;
    failing_task_codes?: string[];
  }[];
}

export interface CandidateLever {
  candidate_id: string;
  lever_type: string;
  target_entity: string;
  estimated_cost: number;
  estimated_time_savings_days: number;
  is_safety_cleared: boolean;
  cost_source: string;
  lever: any;
}

export interface ParetoPoint {
  scenario_name: string;
  cost_delta: number;
  days_recovered: number;
  simulated_finish_date: string;
  remaining_discrete_delayed_count: number;
  discrete_delayed_recovered_count: number;
  critical_path_shifted: boolean;
  levers_applied: any[];
  cost_source: string;
}

export interface OptimizationResult {
  project_id: number;
  snapshot_id: number;
  solver_used: string;
  budget_limit: number;
  pareto_frontier: ParetoPoint[];
  total_scenarios_evaluated: number;
  total_infeasible_rejected: number;
  execution_time_ms: number;
  cost_source_note: string;
}

export interface RelationshipClassification {
  id: number;
  relationship_key: string;
  project_id: number;
  constraint_type: "HARD_PHYSICAL" | "HARD_REGULATORY" | "SOFT_CONVENIENCE" | "SOFT_RESOURCE" | "UNCLASSIFIED";
  confidence: number;
  classification_source: string;
  rationale: string;
  reviewed_by?: string;
  reviewed_at?: string;
  library_pattern_id?: number;
  predecessor_task_code?: string;
  successor_task_code?: string;
  relationship_type?: string;
  lag_days?: number;
  longest_path_proximity?: number;
}

export interface SnapshotDiff {
  snapshot_id_a: number;
  snapshot_id_b: number;
  added_relationships: any[];
  removed_relationships: any[];
  modified_relationships: any[];
  duration_changes: {
    task_code: string;
    old_duration: number;
    new_duration: number;
    delta_days: number;
  }[];
  constraint_changes: {
    task_code: string;
    old_constraint: string | null;
    new_constraint: string | null;
    old_date: string | null;
    new_date: string | null;
  }[];
  driver_churn: {
    new_drivers: string[];
    resolved_drivers: string[];
    persistent_drivers: string[];
  };
}

export interface TrendData {
  project_id: number;
  snapshots: {
    snapshot_id: number;
    data_date: string;
    driver_count: number;
    dcma_health_score: number;
    critical_path_float_days: number;
  }[];
  float_trends: {
    task_code: string;
    name: string;
    history: { snapshot_id: number; data_date: string; total_float_days: number }[];
  }[];
  milestone_slippage: {
    milestone_code: string;
    name: string;
    baseline_finish: string;
    current_finish: string;
    slippage_days: number;
    trend_history: { snapshot_id: number; data_date: string; forecast_finish: string; slippage_days: number }[];
  }[];
}

export interface NarrativeReport {
  snapshot_id: number;
  data_date: string;
  project_name: string;
  executive_summary: string;
  drivers_narrative: string;
  dcma_narrative: string;
  unresolved_hypotheses: {
    task_code: string;
    task_name?: string;
    float_days: number;
    hypothesis: string;
    certainty_tier: CertaintyTier;
  }[];
  evidence_ledger: EvidenceLedgerEntry[];
}

export interface NLQueryResponse {
  query: string;
  intent: string;
  answer_markdown: string;
  retrieved_facts: any;
  evidence_ledger: EvidenceLedgerEntry[];
  primary_certainty_tier: CertaintyTier;
}

export interface IngestionSummaryResponse {
  snapshot_id: number;
  project_id: number;
  project_name: string;
  data_date: string;
  source_filename: string;
  is_baseline: boolean;
  activity_count: number;
  relationship_count: number;
  calendar_count: number;
  is_valid: boolean;
  validation_errors_count: number;
  validation_warnings_count: number;
  message: string;
}

export interface SnapshotListItem {
  snapshot_id: number;
  project_id: number;
  project_name: string;
  data_date: string;
  source_filename: string;
  is_baseline: boolean;
  activity_count: number;
  relationship_count: number;
  created_at: string;
}
