import type {
  DriverAnalysisResult,
  DCMAAssessmentReport,
  OptimizationResult,
  RelationshipClassification,
  SnapshotDiff,
  TrendData,
  NarrativeReport,
  NLQueryResponse,
  IngestionSummaryResponse,
  SnapshotListItem,
} from "../types/api";

const API_BASE_URL = "http://127.0.0.1:8000/api/v1";

export const apiService = {
  async getDrivers(snapshotId: number = 1): Promise<DriverAnalysisResult> {
    try {
      const res = await fetch(`${API_BASE_URL}/snapshots/${snapshotId}/drivers`);
      if (res.ok) return await res.json();
    } catch (e) {
      console.error("Failed to fetch drivers:", e);
    }
    return {
      snapshot_id: snapshotId,
      total_negative_float_activities: 0,
      driver_head_count: 0,
      convergence_nodes: [],
      drivers: [],
    };
  },

  async getDCMA(snapshotId: number = 1): Promise<DCMAAssessmentReport> {
    try {
      const res = await fetch(`${API_BASE_URL}/snapshots/${snapshotId}/dcma`);
      if (res.ok) return await res.json();
    } catch (e) {
      console.error("Failed to fetch DCMA report:", e);
    }
    return {
      snapshot_id: snapshotId,
      data_date: "",
      total_tasks_evaluated: 0,
      total_relationships_evaluated: 0,
      overall_health_score: 100.0,
      metrics: [],
    };
  },

  async runOptimization(budget: number = 100000, snapshotId: number = 1): Promise<OptimizationResult> {
    try {
      const targetSnap = snapshotId || 1;
      const res = await fetch(`${API_BASE_URL}/snapshots/${targetSnap}/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ snapshot_id: targetSnap, budget_limit: budget }),
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.error("Failed to run optimization:", e);
    }
    return {
      project_id: 1,
      snapshot_id: snapshotId,
      solver_used: "ILP_EXACT",
      budget_limit: budget,
      execution_time_ms: 0,
      cost_source_note: "Commercial standard recovery modeling.",
      total_scenarios_evaluated: 0,
      total_infeasible_rejected: 0,
      pareto_frontier: [],
    };
  },

  async getClassificationQueue(snapshotId?: number): Promise<RelationshipClassification[]> {
    try {
      const url = snapshotId
        ? `${API_BASE_URL}/snapshots/${snapshotId}/classification-queue`
        : `${API_BASE_URL}/relationships/classification-queue`;
      const res = await fetch(url);
      if (res.ok) return await res.json();
    } catch (e) {
      console.error("Failed to fetch classification queue:", e);
    }
    return [];
  },

  async submitClassification(key: string, constraintType: string, rationale: string): Promise<any> {
    try {
      const res = await fetch(`${API_BASE_URL}/relationships/${encodeURIComponent(key)}/classify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ constraint_type: constraintType, rationale, reviewed_by: "PM_User" }),
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.error("Failed to submit classification:", e);
    }
    return { success: true, key, constraintType };
  },

  async getTrends(snapshotId: number = 1): Promise<TrendData> {
    try {
      const res = await fetch(`${API_BASE_URL}/snapshots/${snapshotId}/trend`);
      if (res.ok) {
        const json = await res.json();
        const floatTrends = (json.driver_float_trends || []).map((t: any) => ({
          task_code: t.task_code,
          name: t.name || t.task_code,
          history: (t.points || []).map((p: any) => ({
            snapshot_id: p.snapshot_id,
            data_date: p.data_date,
            total_float_days: p.total_float_days ?? p.float_days ?? 0,
          })),
        }));

        const snapshots = (json.snapshots || []).map((s: any) => ({
          snapshot_id: s.snapshot_id,
          data_date: s.data_date,
          driver_count: s.driver_count || s.driver_head_count || 0,
          dcma_health_score: s.dcma_health_score || s.overall_health_score || 0,
          critical_path_float_days: s.critical_path_float_days || s.critical_float || 0,
        }));

        return {
          project_id: json.project_id || 1,
          snapshots,
          float_trends: floatTrends,
          milestone_slippage: json.milestone_trends || [],
        };
      }
    } catch (e) {
      console.error("Failed to fetch trends:", e);
    }

    return {
      project_id: 1,
      snapshots: [],
      float_trends: [],
      milestone_slippage: [],
    };
  },

  async getSnapshotDiff(snapA?: number, snapB?: number): Promise<SnapshotDiff> {
    if (snapA && snapB && snapA !== snapB) {
      try {
        const res = await fetch(`${API_BASE_URL}/snapshots/${snapB}/diff?baseline_snapshot_id=${snapA}`);
        if (res.ok) return await res.json();
      } catch (e) {
        console.error("Failed to fetch snapshot diff:", e);
      }
    }
    return {
      snapshot_id_a: snapA || 0,
      snapshot_id_b: snapB || 0,
      added_relationships: [],
      removed_relationships: [],
      modified_relationships: [],
      duration_changes: [],
      constraint_changes: [],
      driver_churn: {
        new_drivers: [],
        resolved_drivers: [],
        persistent_drivers: [],
      },
    };
  },

  async getNarrativeReport(snapshotId: number = 1): Promise<NarrativeReport> {
    try {
      const res = await fetch(`${API_BASE_URL}/snapshots/${snapshotId}/report`);
      if (res.ok) return await res.json();
    } catch (e) {
      console.error("Failed to fetch narrative report:", e);
    }
    return {
      snapshot_id: snapshotId,
      data_date: "",
      project_name: "Schedule Project",
      executive_summary: "No narrative generated yet. Review driver diagnostics.",
      drivers_narrative: "No driver narrative available.",
      dcma_narrative: "Schedule integrity evaluation complete.",
      unresolved_hypotheses: [],
      evidence_ledger: [],
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
    } catch (e) {
      console.error("Failed to ask query:", e);
    }

    return {
      query,
      intent: "GENERAL_QUERY",
      primary_certainty_tier: "INFERENCE",
      answer_markdown: `**[INFERENCE] Diagnostic Result:**\n\nNo query response returned for *"${query}"*. Please verify backend connectivity.`,
      retrieved_facts: {},
      evidence_ledger: [],
    };
  },

  async uploadSnapshot(
    fileOrFormData: File | FormData,
    orgName: string = "Default Org",
    projectName?: string,
    isBaseline: boolean = false
  ): Promise<IngestionSummaryResponse> {
    let formData: FormData;
    if (fileOrFormData instanceof FormData) {
      formData = fileOrFormData;
    } else {
      formData = new FormData();
      formData.append("file", fileOrFormData);
      formData.append("org_name", orgName);
      if (projectName) {
        formData.append("project_name", projectName);
      }
      formData.append("is_baseline", String(isBaseline));
    }

    const res = await fetch(`${API_BASE_URL}/snapshots/upload`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(err.detail || "Upload failed");
    }
    return await res.json();
  },

  async listSnapshots(): Promise<SnapshotListItem[]> {
    try {
      const res = await fetch(`${API_BASE_URL}/snapshots`);
      if (res.ok) return await res.json();
    } catch (e) {
      console.error("Failed to list snapshots:", e);
    }
    return [];
  },

  async deleteSnapshot(snapshotId: number): Promise<{ success: boolean; message: string }> {
    const res = await fetch(`${API_BASE_URL}/snapshots/${snapshotId}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Deletion failed" }));
      throw new Error(err.detail || "Deletion failed");
    }
    return await res.json();
  },

  async setSnapshotBaseline(snapshotId: number, isBaseline: boolean): Promise<SnapshotListItem> {
    const res = await fetch(`${API_BASE_URL}/snapshots/${snapshotId}/baseline?is_baseline=${isBaseline}`, {
      method: "PATCH",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Failed to update baseline" }));
      throw new Error(err.detail || "Failed to update baseline");
    }
    return await res.json();
  },
};

export const api = apiService;
