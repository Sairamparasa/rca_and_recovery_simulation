import React, { useState } from "react";
import type { DriverAnalysisResult, DCMAAssessmentReport, DriverRecord } from "../types/api";
import { AlertTriangle, CheckCircle2, Layers, Network } from "lucide-react";

interface DriverDashboardProps {
  driversData: DriverAnalysisResult;
  dcmaData: DCMAAssessmentReport;
}

export const DriverDashboard: React.FC<DriverDashboardProps> = ({ driversData, dcmaData }) => {
  const [selectedDriver, setSelectedDriver] = useState<DriverRecord | null>(driversData.drivers[0] || null);

  const getRootCauseBadge = (category: string) => {
    switch (category) {
      case "constraint":
        return <span className="tier-pill tier-modeled">Constraint Date</span>;
      case "out_of_sequence":
        return <span className="tier-pill tier-simulation">Out of Sequence</span>;
      case "logic_change":
        return <span className="tier-pill tier-inference">Logic Change</span>;
      case "external_delay":
        return <span className="tier-pill tier-fact">External Delay</span>;
      default:
        return <span className="tier-pill tier-hypothesis">Unresolved Hypothesis</span>;
    }
  };

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Top Rollup Metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "16px" }}>
        <div className="glass-panel" style={{ padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>Critical Float Floor</span>
            <AlertTriangle size={18} color="var(--accent-rose)" />
          </div>
          <div className="mono-font" style={{ fontSize: "1.8rem", fontWeight: 800, color: "var(--accent-rose)" }}>
            {(driversData.drivers[0]?.driver_total_float_days ?? 0).toFixed(1)}d
          </div>
          <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
            {driversData.drivers[0] ? `Critical path driver: ${driversData.drivers[0].driver_task_code}` : "No negative float delay detected"}
          </span>
        </div>

        <div className="glass-panel" style={{ padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>Negative-Float Tasks</span>
            <Layers size={18} color="var(--accent-amber)" />
          </div>
          <div className="mono-font" style={{ fontSize: "1.8rem", fontWeight: 800, color: "var(--accent-amber)" }}>
            {driversData.total_negative_float_activities} <span style={{ fontSize: "0.9rem", color: "var(--text-muted)", fontWeight: 400 }}>/ {dcmaData.total_tasks_evaluated || 0}</span>
          </div>
          <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
            Discrete tasks with TF &lt; 0.0d
          </span>
        </div>

        <div className="glass-panel" style={{ padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>Driver Heads</span>
            <Network size={18} color="#818cf8" />
          </div>
          <div className="mono-font" style={{ fontSize: "1.8rem", fontWeight: 800, color: "#818cf8" }}>
            {driversData.driver_head_count} <span style={{ fontSize: "0.9rem", color: "var(--text-muted)", fontWeight: 400 }}>Roots</span>
          </div>
          <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
            {driversData.driver_head_count > 0 ? `Identified ${driversData.driver_head_count} root delay drivers` : "Zero driver bottlenecks"}
          </span>
        </div>

        <div className="glass-panel" style={{ padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>DCMA 14-Point Health</span>
            <CheckCircle2 size={18} color="var(--accent-emerald)" />
          </div>
          <div className="mono-font" style={{ fontSize: "1.8rem", fontWeight: 800, color: "var(--accent-emerald)" }}>
            {(dcmaData.overall_health_score ?? 100).toFixed(1)}%
          </div>
          <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
            {dcmaData.metrics.filter((m) => m.passed).length} / {dcmaData.metrics.length || 14} checks passing
          </span>
        </div>
      </div>

      {/* Main Content Split: Ranked Drivers Table & Blast Radius Inspector */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 0.8fr", gap: "24px" }}>
        {/* Ranked Drivers Table */}
        <div className="glass-panel" style={{ padding: "24px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <div>
              <h2 style={{ fontSize: "1.15rem", fontWeight: 700, color: "#fff" }}>Ranked Delay Driver Heads</h2>
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Deterministic root-cause clusters ranked by impact score & float magnitude
              </p>
            </div>
            <span className="tier-pill tier-fact">[FACT] Deterministic Backward Trace</span>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle)", color: "var(--text-muted)" }}>
                  <th style={{ padding: "10px 12px" }}>Rank & Code</th>
                  <th style={{ padding: "10px 12px" }}>Activity Description</th>
                  <th style={{ padding: "10px 12px" }}>Float</th>
                  <th style={{ padding: "10px 12px" }}>Blast Radius</th>
                  <th style={{ padding: "10px 12px" }}>Root Cause</th>
                  <th style={{ padding: "10px 12px", textAlign: "right" }}>Impact</th>
                </tr>
              </thead>
              <tbody>
                {driversData.drivers.map((driver, idx) => {
                  const isSelected = selectedDriver?.driver_task_code === driver.driver_task_code;
                  return (
                    <tr
                      key={driver.driver_task_code}
                      onClick={() => setSelectedDriver(driver)}
                      style={{
                        borderBottom: "1px solid var(--border-subtle)",
                        cursor: "pointer",
                        background: isSelected ? "rgba(99, 102, 241, 0.12)" : "transparent",
                        transition: "background 0.2s ease"
                      }}
                    >
                      <td style={{ padding: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
                        <span style={{ fontSize: "0.75rem", fontWeight: 700, color: isSelected ? "#818cf8" : "var(--text-muted)" }}>#{idx + 1}</span>
                        <span className="mono-font" style={{ fontWeight: 700, color: "#fff" }}>{driver.driver_task_code}</span>
                      </td>
                      <td style={{ padding: "12px", maxWidth: "240px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text-primary)" }}>
                        {driver.driver_name || driver.driver_task_code}
                      </td>
                      <td className="mono-font" style={{ padding: "12px", fontWeight: 700, color: "var(--accent-rose)" }}>
                        {driver.driver_total_float_days.toFixed(1)}d
                      </td>
                      <td style={{ padding: "12px", color: "var(--text-secondary)" }}>
                        <span className="mono-font" style={{ fontWeight: 600 }}>{driver.downstream_activity_count}</span> tasks
                      </td>
                      <td style={{ padding: "12px" }}>
                        {getRootCauseBadge(driver.root_cause_type)}
                      </td>
                      <td className="mono-font" style={{ padding: "12px", textAlign: "right", fontWeight: 700, color: "#a5b4fc" }}>
                        {driver.impact_score.toFixed(1)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Blast Radius & Tree Drill-Down Drawer */}
        <div className="glass-panel" style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "16px" }}>
          {selectedDriver ? (
            <>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                  <span className="mono-font" style={{ fontSize: "1.1rem", fontWeight: 800, color: "#818cf8" }}>
                    {selectedDriver.driver_task_code}
                  </span>
                  {getRootCauseBadge(selectedDriver.root_cause_type)}
                </div>
                <h3 style={{ fontSize: "0.95rem", fontWeight: 600, color: "#fff", marginBottom: "4px" }}>
                  {selectedDriver.driver_name}
                </h3>
                <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                  {selectedDriver.root_cause_description}
                </p>
              </div>

              {/* Driving Chain & Downstream Blast Radius Tree */}
              <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                  <span style={{ fontSize: "0.8rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)" }}>
                    Downstream Blast Radius ({selectedDriver.blast_radius_nodes?.length || 0} Nodes)
                  </span>
                  <span style={{ fontSize: "0.72rem", color: "#38bdf8" }}>Forward Driving Pass</span>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "8px", maxHeight: "380px", overflowY: "auto", paddingRight: "4px" }}>
                  {(selectedDriver.blast_radius_nodes || []).map((node) => (
                    <div
                      key={node.task_code}
                      style={{
                        padding: "10px 14px",
                        background: node.is_convergence_node ? "rgba(245, 158, 11, 0.08)" : "rgba(255, 255, 255, 0.02)",
                        border: `1px solid ${node.is_convergence_node ? "rgba(245, 158, 11, 0.3)" : "var(--border-subtle)"}`,
                        borderRadius: "var(--radius-sm)",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center"
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                        <div style={{
                          width: "20px",
                          height: "20px",
                          borderRadius: "50%",
                          background: node.is_critical ? "rgba(244, 63, 94, 0.2)" : "rgba(255, 255, 255, 0.05)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: "0.68rem",
                          fontWeight: 700,
                          color: node.is_critical ? "var(--accent-rose)" : "var(--text-muted)"
                        }}>
                          D{node.depth}
                        </div>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                            <span className="mono-font" style={{ fontSize: "0.82rem", fontWeight: 700, color: "#fff" }}>
                              {node.task_code}
                            </span>
                            {node.is_convergence_node && (
                              <span style={{ fontSize: "0.68rem", background: "rgba(245, 158, 11, 0.2)", color: "#fcd34d", padding: "1px 6px", borderRadius: "4px", fontWeight: 600 }}>
                                Convergence Bottleneck
                              </span>
                            )}
                            {node.is_milestone && (
                              <span style={{ fontSize: "0.68rem", background: "rgba(16, 185, 129, 0.2)", color: "#34d399", padding: "1px 6px", borderRadius: "4px", fontWeight: 600 }}>
                                Milestone
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                            Early: {node.early_start} → {node.early_finish}
                          </div>
                        </div>
                      </div>

                      <span className="mono-font" style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--accent-rose)" }}>
                        {(node.total_float_days ?? 0).toFixed(1)}d
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
              {driversData.drivers.length === 0
                ? "No delay drivers found for this snapshot."
                : "Select a driver to view the forward blast radius"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
