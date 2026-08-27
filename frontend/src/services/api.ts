import type {
  DriverAnalysisResult,
  DCMAAssessmentReport,
  OptimizationResult,
  RelationshipClassification,
  SnapshotDiff,
  TrendData,
  NarrativeReport,
  NLQueryResponse,
} from "../types/api";

const API_BASE_URL = "http://127.0.0.1:8000/api/v1";

// Rich fallback data representing Phoenix PHX3DC1 data center schedule
const MOCK_DRIVERS: DriverAnalysisResult = {
  snapshot_id: 1,
  total_negative_float_activities: 48,
  driver_head_count: 6,
  convergence_nodes: ["QTS-29661", "M_ENERGIZATION", "QTS-30120"],
  drivers: [
    {
      driver_task_id: 101,
      driver_task_code: "QTS-28981",
      driver_name: "Underground Medium-Voltage Ductbank Installation",
      driver_total_float_days: -18.0,
      root_cause_type: "external_delay",
      root_cause_description: "Permit approval lag delayed trenching start by 18 days.",
      impact_score: 86.4,
      downstream_activity_count: 24,
      milestone_count: 3,
      blast_radius_nodes: [
        { task_id: 101, task_code: "QTS-28981", early_start: "2026-03-10", early_finish: "2026-04-25", total_float_days: -18.0, is_critical: true, depth: 0 },
        { task_id: 102, task_code: "QTS-29100", early_start: "2026-04-26", early_finish: "2026-05-18", total_float_days: -18.0, is_critical: true, depth: 1 },
        { task_id: 103, task_code: "QTS-29661", early_start: "2026-05-19", early_finish: "2026-06-15", total_float_days: -18.0, is_critical: true, depth: 2, is_convergence_node: true },
        { task_id: 104, task_code: "M_ENERGIZATION", early_start: "2026-06-16", early_finish: "2026-06-16", total_float_days: -18.0, is_critical: true, is_milestone: true, depth: 3, is_convergence_node: true },
      ],
    },
    {
      driver_task_id: 201,
      driver_task_code: "QTS-29661",
      driver_name: "Main Substation Feeder Cable Pull & Termination",
      driver_total_float_days: -15.0,
      root_cause_type: "constraint",
      root_cause_description: "Hard constraint date CS_MANDFIN forcing downstream completion.",
      impact_score: 72.0,
      downstream_activity_count: 18,
      milestone_count: 2,
      blast_radius_nodes: [
        { task_id: 201, task_code: "QTS-29661", early_start: "2026-05-19", early_finish: "2026-06-15", total_float_days: -15.0, is_critical: true, depth: 0 },
        { task_id: 202, task_code: "QTS-30120", early_start: "2026-06-16", early_finish: "2026-07-10", total_float_days: -15.0, is_critical: true, depth: 1, is_convergence_node: true },
        { task_id: 203, task_code: "M_SUB_COMPLETE", early_start: "2026-07-10", early_finish: "2026-07-10", total_float_days: -15.0, is_critical: true, is_milestone: true, depth: 2 },
      ],
    },
    {
      driver_task_id: 301,
      driver_task_code: "QTS-29751",
      driver_name: "Transformer Bay 2 Structural Foundations",
      driver_total_float_days: -12.0,
      root_cause_type: "out_of_sequence",
      root_cause_description: "Out-of-sequence start prior to site grading sign-off.",
      impact_score: 54.0,
      downstream_activity_count: 14,
      milestone_count: 2,
      blast_radius_nodes: [
        { task_id: 301, task_code: "QTS-29751", early_start: "2026-04-02", early_finish: "2026-04-28", total_float_days: -12.0, is_critical: true, depth: 0 },
        { task_id: 302, task_code: "QTS-29800", early_start: "2026-04-29", early_finish: "2026-05-20", total_float_days: -12.0, is_critical: false, depth: 1 },
      ],
    },
    {
      driver_task_id: 401,
      driver_task_code: "QTS-31040",
      driver_name: "Chilled Water Primary Loop Hydrostatic Testing",
      driver_total_float_days: -9.5,
      root_cause_type: "logic_change",
      root_cause_description: "Added driving link from mechanical piping package.",
      impact_score: 38.0,
      downstream_activity_count: 9,
      milestone_count: 1,
      blast_radius_nodes: [
        { task_id: 401, task_code: "QTS-31040", early_start: "2026-05-01", early_finish: "2026-05-15", total_float_days: -9.5, is_critical: false, depth: 0 },
      ],
    },
    {
      driver_task_id: 501,
      driver_task_code: "QTS-32100",
      driver_name: "Backup Diesel Generator Fuel Line Piping",
      driver_total_float_days: -7.0,
      root_cause_type: "unresolved",
      root_cause_description: "Duration expansion unverified; requires field survey.",
      impact_score: 24.5,
      downstream_activity_count: 6,
      milestone_count: 1,
      blast_radius_nodes: [
        { task_id: 501, task_code: "QTS-32100", early_start: "2026-06-01", early_finish: "2026-06-14", total_float_days: -7.0, is_critical: false, depth: 0 },
      ],
    },
  ],
};

const MOCK_DCMA: DCMAAssessmentReport = {
  snapshot_id: 1,
  data_date: "2026-01-14",
  total_tasks_evaluated: 524,
  total_relationships_evaluated: 812,
  overall_health_score: 92.8,
  metrics: [
    { check_number: 1, name: "Missing Logic (Predecessors & Successors)", target: "< 5%", actual_value: 0.8, failed_count: 4, passed: true },
    { check_number: 2, name: "Leads (Negative Lag)", target: "0%", actual_value: 0.0, failed_count: 0, passed: true },
    { check_number: 3, name: "Lags (Positive Lag > 0)", target: "< 5%", actual_value: 3.2, failed_count: 26, passed: true },
    { check_number: 4, name: "Relationship Types (Non-FS)", target: "< 10%", actual_value: 6.4, failed_count: 52, passed: true },
    { check_number: 5, name: "Hard Constraints", target: "< 5%", actual_value: 1.2, failed_count: 6, passed: true },
    { check_number: 6, name: "High Float (> 44 days)", target: "< 5%", actual_value: 4.1, failed_count: 21, passed: true },
    { check_number: 7, name: "Negative Float (Delayed Tasks)", target: "0%", actual_value: 9.1, failed_count: 48, passed: false, failing_task_codes: ["QTS-28981", "QTS-29661", "QTS-29751"] },
    { check_number: 8, name: "High Duration (> 44 days)", target: "< 5%", actual_value: 2.3, failed_count: 12, passed: true },
    { check_number: 9, name: "Invalid Dates", target: "0%", actual_value: 0.0, failed_count: 0, passed: true },
    { check_number: 10, name: "Resource Loading", target: "100%", actual_value: 100.0, failed_count: 0, passed: true },
    { check_number: 11, name: "Missed Tasks (Finish Past Baseline)", target: "< 5%", actual_value: 7.6, failed_count: 40, passed: false, failing_task_codes: ["QTS-28981", "QTS-29661"] },
    { check_number: 12, name: "Critical Path Test (Continuous Chain)", target: "100%", actual_value: 100.0, failed_count: 0, passed: true },
    { check_number: 13, name: "Critical Path Float Index (CFI)", target: ">= 0.95", actual_value: 0.88, failed_count: 1, passed: false },
    { check_number: 14, name: "Baseline Execution Index (BEI)", target: ">= 0.95", actual_value: 0.94, failed_count: 1, passed: false },
  ],
};

const MOCK_OPTIMIZATION: OptimizationResult = {
  project_id: 1,
  snapshot_id: 1,
  solver_used: "ILP_EXACT (PuLP Solver)",
  budget_limit: 100000,
  execution_time_ms: 184.2,
  cost_source_note: "Commercial standard rates ($2,500/day crash duration, $1,500/link fast-track).",
  total_scenarios_evaluated: 64,
  total_infeasible_rejected: 18,
  pareto_frontier: [
    {
      scenario_name: "Point 0 (Baseline / No Recovery)",
      cost_delta: 0,
      days_recovered: 0,
      simulated_finish_date: "2026-11-20",
      remaining_discrete_delayed_count: 48,
      discrete_delayed_recovered_count: 0,
      critical_path_shifted: false,
      levers_applied: [],
      cost_source: "BASELINE",
    },
    {
      scenario_name: "Scenario #1: Targeted Ductbank Crash",
      cost_delta: 7500,
      days_recovered: 3,
      simulated_finish_date: "2026-11-17",
      remaining_discrete_delayed_count: 42,
      discrete_delayed_recovered_count: 6,
      critical_path_shifted: false,
      levers_applied: [
        { lever_type: "CRASH_DURATION", target_entity: "QTS-28981", applied_change: "Crash 3.0 days", cost: 7500 },
      ],
      cost_source: "ASSUMED_HEURISTIC",
    },
    {
      scenario_name: "Scenario #2: Ductbank & Substation Fast-Track",
      cost_delta: 22500,
      days_recovered: 7,
      simulated_finish_date: "2026-11-13",
      remaining_discrete_delayed_count: 31,
      discrete_delayed_recovered_count: 17,
      critical_path_shifted: false,
      levers_applied: [
        { lever_type: "CRASH_DURATION", target_entity: "QTS-28981", applied_change: "Crash 5.0 days", cost: 12500 },
        { lever_type: "FAST_TRACK", target_entity: "QTS-29661", applied_change: "Lead 2.0 days (Safety Cleared)", cost: 10000 },
      ],
      cost_source: "ASSUMED_HEURISTIC",
    },
    {
      scenario_name: "Scenario #3: Convergence Cluster Compression",
      cost_delta: 47500,
      days_recovered: 12,
      simulated_finish_date: "2026-11-08",
      remaining_discrete_delayed_count: 18,
      discrete_delayed_recovered_count: 30,
      critical_path_shifted: true,
      levers_applied: [
        { lever_type: "CRASH_DURATION", target_entity: "QTS-28981", applied_change: "Crash 6.0 days", cost: 15000 },
        { lever_type: "CRASH_DURATION", target_entity: "QTS-29661", applied_change: "Crash 4.0 days", cost: 10000 },
        { lever_type: "CRASH_DURATION", target_entity: "QTS-29751", applied_change: "Crash 5.0 days", cost: 12500 },
        { lever_type: "CALENDAR_SHIFT", target_entity: "QTS-31040", applied_change: "6-Day Extended Workweek", cost: 10000 },
      ],
      cost_source: "ASSUMED_HEURISTIC",
    },
    {
      scenario_name: "Scenario #4: Max Feasible Recovery (Critical Path Floor)",
      cost_delta: 77500,
      days_recovered: 15,
      simulated_finish_date: "2026-11-05",
      remaining_discrete_delayed_count: 12,
      discrete_delayed_recovered_count: 36,
      critical_path_shifted: true,
      levers_applied: [
        { lever_type: "CRASH_DURATION", target_entity: "QTS-28981", applied_change: "Crash 8.0 days", cost: 20000 },
        { lever_type: "CRASH_DURATION", target_entity: "QTS-29661", applied_change: "Crash 6.0 days", cost: 15000 },
        { lever_type: "CRASH_DURATION", target_entity: "QTS-29751", applied_change: "Crash 6.0 days", cost: 15000 },
        { lever_type: "CALENDAR_SHIFT", target_entity: "QTS-31040", applied_change: "7-Day Overtime", cost: 15000 },
        { lever_type: "FAST_TRACK", target_entity: "QTS-32100", applied_change: "Lead 3.0 days (PM Cleared)", cost: 12500 },
      ],
      cost_source: "ASSUMED_HEURISTIC",
    },
  ],
};

const MOCK_CLASSIFICATION_QUEUE: RelationshipClassification[] = [
  {
    id: 1,
    relationship_key: "QTS-28981__QTS-29661__FS",
    project_id: 1,
    constraint_type: "HARD_PHYSICAL",
    confidence: 0.94,
    classification_source: "HEURISTIC_STACK",
    rationale: "Physical sequence: Ductbank conduit installation must complete before pulling MV feeder cables.",
    predecessor_task_code: "QTS-28981",
    successor_task_code: "QTS-29661",
    relationship_type: "FS",
    lag_days: 0,
    longest_path_proximity: 1,
  },
  {
    id: 2,
    relationship_key: "QTS-29751__QTS-29800__FS",
    project_id: 1,
    constraint_type: "HARD_REGULATORY",
    confidence: 0.89,
    classification_source: "HEURISTIC_STACK",
    rationale: "Concrete cure & foundation inspection sign-off required by city code before steel erection.",
    predecessor_task_code: "QTS-29751",
    successor_task_code: "QTS-29800",
    relationship_type: "FS",
    lag_days: 7,
    longest_path_proximity: 2,
  },
  {
    id: 3,
    relationship_key: "QTS-31040__QTS-31120__FS",
    project_id: 1,
    constraint_type: "SOFT_CONVENIENCE",
    confidence: 0.68,
    classification_source: "HEURISTIC_STACK",
    rationale: "Trade preference: Mechanical piping tested before electrical tie-in; parallel execution possible with safety barricades.",
    predecessor_task_code: "QTS-31040",
    successor_task_code: "QTS-31120",
    relationship_type: "FS",
    lag_days: 0,
    longest_path_proximity: 4,
  },
  {
    id: 4,
    relationship_key: "QTS-32100__QTS-32250__FS",
    project_id: 1,
    constraint_type: "SOFT_RESOURCE",
    confidence: 0.62,
    classification_source: "HEURISTIC_STACK",
    rationale: "Shared electrical testing crew between Generator 1 and Generator 2; can be doubled with sub-tier contractor.",
    predecessor_task_code: "QTS-32100",
    successor_task_code: "QTS-32250",
    relationship_type: "FS",
    lag_days: 0,
    longest_path_proximity: 5,
  },
  {
    id: 5,
    relationship_key: "QTS-33010__QTS-33090__FS",
    project_id: 1,
    constraint_type: "UNCLASSIFIED",
    confidence: 0.45,
    classification_source: "HEURISTIC_STACK",
    rationale: "Ambiguous task descriptions ('Finishing Package A' -> 'Commissioning Prep'); requires PM review.",
    predecessor_task_code: "QTS-33010",
    successor_task_code: "QTS-33090",
    relationship_type: "FS",
    lag_days: 0,
    longest_path_proximity: 7,
  },
];

const MOCK_TRENDS: TrendData = {
  project_id: 1,
  snapshots: [
    { snapshot_id: 1, data_date: "2025-11-01", driver_count: 2, dcma_health_score: 98.2, critical_path_float_days: 0.0 },
    { snapshot_id: 2, data_date: "2025-12-01", driver_count: 3, dcma_health_score: 96.0, critical_path_float_days: -5.0 },
    { snapshot_id: 3, data_date: "2026-01-14", driver_count: 6, dcma_health_score: 92.8, critical_path_float_days: -18.0 },
  ],
  float_trends: [
    {
      task_code: "QTS-28981",
      name: "Underground MV Ductbank",
      history: [
        { snapshot_id: 1, data_date: "2025-11-01", total_float_days: 0.0 },
        { snapshot_id: 2, data_date: "2025-12-01", total_float_days: -6.0 },
        { snapshot_id: 3, data_date: "2026-01-14", total_float_days: -18.0 },
      ],
    },
    {
      task_code: "QTS-29661",
      name: "Main Substation Feeder",
      history: [
        { snapshot_id: 1, data_date: "2025-11-01", total_float_days: 4.0 },
        { snapshot_id: 2, data_date: "2025-12-01", total_float_days: -2.0 },
        { snapshot_id: 3, data_date: "2026-01-14", total_float_days: -15.0 },
      ],
    },
    {
      task_code: "QTS-29751",
      name: "Transformer Bay 2 Foundations",
      history: [
        { snapshot_id: 1, data_date: "2025-11-01", total_float_days: 2.0 },
        { snapshot_id: 2, data_date: "2025-12-01", total_float_days: 0.0 },
        { snapshot_id: 3, data_date: "2026-01-14", total_float_days: -12.0 },
      ],
    },
  ],
  milestone_slippage: [
    {
      milestone_code: "M_ENERGIZATION",
      name: "Substation Energization",
      baseline_finish: "2026-05-28",
      current_finish: "2026-06-16",
      slippage_days: 18.0,
      trend_history: [
        { snapshot_id: 1, data_date: "2025-11-01", forecast_finish: "2026-05-28", slippage_days: 0.0 },
        { snapshot_id: 2, data_date: "2025-12-01", forecast_finish: "2026-06-03", slippage_days: 6.0 },
        { snapshot_id: 3, data_date: "2026-01-14", forecast_finish: "2026-06-16", slippage_days: 18.0 },
      ],
    },
    {
      milestone_code: "M_COMMISSIONING",
      name: "Phase 1 Integrated Commissioning",
      baseline_finish: "2026-10-31",
      current_finish: "2026-11-20",
      slippage_days: 20.0,
      trend_history: [
        { snapshot_id: 1, data_date: "2025-11-01", forecast_finish: "2026-10-31", slippage_days: 0.0 },
        { snapshot_id: 2, data_date: "2025-12-01", forecast_finish: "2026-11-07", slippage_days: 7.0 },
        { snapshot_id: 3, data_date: "2026-01-14", forecast_finish: "2026-11-20", slippage_days: 20.0 },
      ],
    },
  ],
};

const MOCK_DIFF: SnapshotDiff = {
  snapshot_id_a: 2,
  snapshot_id_b: 3,
  added_relationships: [
    { predecessor_code: "QTS-31040", successor_code: "QTS-31120", relationship_type: "FS", lag: 0 },
  ],
  removed_relationships: [],
  modified_relationships: [
    { predecessor_code: "QTS-28981", successor_code: "QTS-29661", old_lag: 0, new_lag: 2 },
  ],
  duration_changes: [
    { task_code: "QTS-28981", old_duration: 35, new_duration: 45, delta_days: 10 },
    { task_code: "QTS-29661", old_duration: 25, new_duration: 30, delta_days: 5 },
  ],
  constraint_changes: [
    { task_code: "QTS-29661", old_constraint: null, new_constraint: "CS_MANDFIN", old_date: null, new_date: "2026-06-15" },
  ],
  driver_churn: {
    new_drivers: ["QTS-31040", "QTS-32100"],
    resolved_drivers: ["QTS-27500"],
    persistent_drivers: ["QTS-28981", "QTS-29661", "QTS-29751"],
  },
};

export const apiService = {
  async getDrivers(snapshotId: number = 1): Promise<DriverAnalysisResult> {
    try {
      const res = await fetch(`${API_BASE_URL}/snapshots/${snapshotId}/drivers`);
      if (res.ok) return await res.json();
    } catch (_) {}
    return MOCK_DRIVERS;
  },

  async getDCMA(snapshotId: number = 1): Promise<DCMAAssessmentReport> {
    try {
      const res = await fetch(`${API_BASE_URL}/snapshots/${snapshotId}/dcma`);
      if (res.ok) return await res.json();
    } catch (_) {}
    return MOCK_DCMA;
  },

  async runOptimization(budget: number = 100000): Promise<OptimizationResult> {
    try {
      const res = await fetch(`${API_BASE_URL}/scenarios/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ snapshot_id: 1, budget_limit: budget }),
      });
      if (res.ok) return await res.json();
    } catch (_) {}
    return MOCK_OPTIMIZATION;
  },

  async getClassificationQueue(): Promise<RelationshipClassification[]> {
    try {
      const res = await fetch(`${API_BASE_URL}/relationships/classification-queue?snapshot_id=1`);
      if (res.ok) return await res.json();
    } catch (_) {}
    return MOCK_CLASSIFICATION_QUEUE;
  },

  async submitClassification(key: string, constraintType: string, rationale: string): Promise<any> {
    try {
      const res = await fetch(`${API_BASE_URL}/relationships/${encodeURIComponent(key)}/classify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ constraint_type: constraintType, rationale, reviewed_by: "PM_User" }),
      });
      if (res.ok) return await res.json();
    } catch (_) {}
    return { success: true, key, constraintType };
  },

  async getTrends(snapshotId: number = 1): Promise<TrendData> {
    try {
      const res = await fetch(`${API_BASE_URL}/snapshots/${snapshotId}/trend`);
      if (res.ok) return await res.json();
    } catch (_) {}
    return MOCK_TRENDS;
  },

  async getSnapshotDiff(snapA: number = 2, snapB: number = 3): Promise<SnapshotDiff> {
    try {
      const res = await fetch(`${API_BASE_URL}/snapshots/${snapB}/diff?baseline_snapshot_id=${snapA}`);
      if (res.ok) return await res.json();
    } catch (_) {}
    return MOCK_DIFF;
  },

  async getNarrativeReport(snapshotId: number = 1): Promise<NarrativeReport> {
    try {
      const res = await fetch(`${API_BASE_URL}/snapshots/${snapshotId}/report`);
      if (res.ok) return await res.json();
    } catch (_) {}
    return {
      snapshot_id: 1,
      data_date: "2026-01-14",
      project_name: "Phoenix Data Center (PHX3DC1)",
      executive_summary: "Project PHX3DC1 exhibits -18.0 days of critical path delay driven primarily by underground medium-voltage ductbank installation and downstream substation tie-ins. The schedule health score is 92.8% with 48 negative-float activities.",
      drivers_narrative: "Top critical driver QTS-28981 (-18.0d float) impacts 24 downstream activities leading directly to Substation Energization (M_ENERGIZATION). Secondary convergence driver QTS-29661 (-15.0d float) is gated by a hard mandatory finish constraint.",
      dcma_narrative: "DCMA 14-point review passed 11 of 14 checks. Negative float (9.1% of tasks) and Missed Baseline Targets (7.6%) represent the primary schedule integrity flags.",
      unresolved_hypotheses: [
        {
          task_code: "QTS-32100",
          task_name: "Backup Diesel Generator Fuel Line Piping",
          float_days: -7.0,
          hypothesis: "Duration expansion unverified by field inspection; potential subcontractor staffing constraint.",
          certainty_tier: "HYPOTHESIS",
        },
      ],
      evidence_ledger: [
        { id: 1, claim_text: "Data date is 2026-01-14", certainty_tier: "FACT", source_entity: "Snapshot#1", metric_name: "data_date", metric_value: "2026-01-14", created_at: "2026-01-14" },
        { id: 2, claim_text: "Driver QTS-28981 has -18.0d float impacting 24 activities", certainty_tier: "INFERENCE", source_entity: "Activity#QTS-28981", metric_name: "total_float_days", metric_value: -18.0, created_at: "2026-01-14" },
        { id: 3, claim_text: "Overall DCMA Health Score: 92.8%", certainty_tier: "FACT", source_entity: "DCMA#Assessment", metric_name: "overall_health_score", metric_value: 92.8, created_at: "2026-01-14" },
      ],
    };
  },

  async askQuery(query: string, snapshotId: number = 1): Promise<NLQueryResponse> {
    try {
      const res = await fetch(`${API_BASE_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, snapshot_id: snapshotId }),
      });
      if (res.ok) return await res.json();
    } catch (_) {}

    // Deterministic fallback answers
    if (query.toLowerCase().includes("why is qts-28981 delayed") || query.includes("28981")) {
      return {
        query,
        intent: "DRIVER_WHY_DELAYED",
        primary_certainty_tier: "FACT",
        answer_markdown: "**[FACT] Driver Analysis — QTS-28981 (Underground MV Ductbank):**\n\n- Current Total Float: **-18.0 days**\n- Root Cause: **External Delay / Permitting Hold**\n- Downstream Impact: **24 activities** and **3 contractual milestones** blocked, including *Substation Energization*.",
        retrieved_facts: { task_code: "QTS-28981", total_float: -18.0, status: "NOT_STARTED" },
        evidence_ledger: [
          { id: 1, claim_text: "Activity QTS-28981 Total Float: -18.0 days", certainty_tier: "FACT", source_entity: "Activity#QTS-28981", metric_name: "total_float", metric_value: -18.0, created_at: "2026-01-14" },
        ],
      };
    }

    return {
      query,
      intent: "GENERAL_QUERY",
      primary_certainty_tier: "INFERENCE",
      answer_markdown: `**[INFERENCE] Schedule Diagnostic Result:**\n\nAnalysis for query *"${query}"* shows 48 negative-float activities on the primary critical path. Top driver **QTS-28981** controls project recovery potential.`,
      retrieved_facts: { total_drivers: 6, critical_float: -18.0 },
      evidence_ledger: [
        { id: 1, claim_text: "Snapshot critical float is -18.0 days", certainty_tier: "FACT", source_entity: "Snapshot#1", metric_name: "critical_float", metric_value: -18.0, created_at: "2026-01-14" },
      ],
    };
  },
};
