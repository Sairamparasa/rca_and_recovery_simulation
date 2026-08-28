import React, { useState } from "react";
import type { TrendData, SnapshotDiff } from "../types/api";
import { ArrowRight, GitCommit, Info } from "lucide-react";

interface HistoricalTrendViewProps {
  trendData: TrendData;
  diffData: SnapshotDiff;
}

export const HistoricalTrendView: React.FC<HistoricalTrendViewProps> = ({
  trendData,
  diffData,
}) => {
  const [activeTab, setActiveTab] = useState<"diff" | "churn" | "erosion">("diff");

  const snapshotCount = trendData?.snapshots?.length || 0;
  const snapshotDates = (trendData?.snapshots || []).map((s) => s.data_date).join(" → ");

  if (snapshotCount < 2) {
    return (
      <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
        <div className="glass-panel" style={{ padding: "20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "4px" }}>
              <h2 style={{ fontSize: "1.2rem", fontWeight: 700, color: "#fff" }}>Historical Snapshot Comparison & Trend Display</h2>
              <span className="tier-pill tier-fact">[FACT] Historical Ingestion Only — Zero Forecasting</span>
            </div>
            <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
              Strictly historical point-to-point variance analysis across sequential schedule updates.
            </p>
          </div>
        </div>

        <div className="glass-panel" style={{ padding: "48px 24px", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: "16px" }}>
          <div style={{
            width: "56px",
            height: "56px",
            borderRadius: "50%",
            background: "rgba(99, 102, 241, 0.15)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#818cf8",
          }}>
            <GitCommit size={28} />
          </div>
          <div>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#fff", marginBottom: "8px" }}>
              {snapshotCount === 0 ? "No Schedule Snapshots Ingested" : "Single Snapshot Loaded — Need ≥ 2 Snapshots for Trend Analysis"}
            </h3>
            <p style={{ fontSize: "0.88rem", color: "var(--text-muted)", maxWidth: "560px", margin: "0 auto", lineHeight: "1.5" }}>
              {snapshotCount === 0
                ? "Please upload schedule snapshots using the 'Upload .XER' button to begin variance and driver analysis."
                : `Currently tracking Snapshot #${trendData.snapshots[0]?.snapshot_id} (${trendData.snapshots[0]?.data_date}). Historical snapshot diffing, driver churn classification, and float erosion curves require at least two sequential schedule updates.`}
            </p>
          </div>
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "10px 16px",
            background: "rgba(255, 255, 255, 0.02)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--border-subtle)",
            fontSize: "0.8rem",
            color: "var(--text-secondary)"
          }}>
            <Info size={16} color="#818cf8" />
            <span>Upload an updated progress snapshot via the top bar to calculate point-to-point variances.</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Top Banner & Zero Prediction Compliance Badge */}
      <div className="glass-panel" style={{ padding: "20px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "4px" }}>
            <h2 style={{ fontSize: "1.2rem", fontWeight: 700, color: "#fff" }}>Historical Snapshot Comparison & Trend Display</h2>
            <span className="tier-pill tier-fact">[FACT] Historical Ingestion Only — Zero Forecasting</span>
          </div>
          <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
            Tracking schedule evolution across {snapshotCount} snapshots ({snapshotDates}).
          </p>
        </div>

        {/* View Switcher Tabs */}
        <div style={{ display: "flex", gap: "8px" }}>
          {[
            { id: "diff", label: "Snapshot Diff" },
            { id: "churn", label: "Driver Churn" },
            { id: "erosion", label: "Float Erosion History" },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id as any)}
              style={{
                background: activeTab === t.id ? "rgba(99, 102, 241, 0.25)" : "rgba(255, 255, 255, 0.04)",
                color: activeTab === t.id ? "#fff" : "var(--text-muted)",
                border: `1px solid ${activeTab === t.id ? "#818cf8" : "var(--border-subtle)"}`,
                padding: "6px 14px",
                borderRadius: "var(--radius-sm)",
                fontSize: "0.78rem",
                fontWeight: 600,
                cursor: "pointer"
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* VIEW 1: SNAPSHOT DIFF MATRIX */}
      {activeTab === "diff" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px" }}>
          {/* Duration Variance */}
          <div className="glass-panel" style={{ padding: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 700, color: "#fff" }}>Duration Expansion</h3>
              <span className="mono-font" style={{ fontSize: "0.75rem", color: "var(--accent-rose)", fontWeight: 700 }}>
                {diffData.duration_changes.length} Tasks Expanded
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {diffData.duration_changes.length === 0 ? (
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", padding: "12px 0" }}>No task duration changes detected between snapshots.</div>
              ) : (
                diffData.duration_changes.map((d) => (
                  <div
                    key={d.task_code}
                    style={{
                      padding: "10px 12px",
                      background: "rgba(255, 255, 255, 0.02)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-sm)",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center"
                    }}
                  >
                    <span className="mono-font" style={{ fontWeight: 700, color: "#fff", fontSize: "0.85rem" }}>
                      {d.task_code}
                    </span>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.8rem" }}>
                      <span style={{ color: "var(--text-muted)" }}>{d.old_duration}d</span>
                      <ArrowRight size={12} color="var(--text-muted)" />
                      <span style={{ color: "#38bdf8", fontWeight: 600 }}>{d.new_duration}d</span>
                      <span className="mono-font" style={{ color: "var(--accent-rose)", fontWeight: 700 }}>
                        (+{d.delta_days}d)
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Constraint Changes */}
          <div className="glass-panel" style={{ padding: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 700, color: "#fff" }}>Added Constraints</h3>
              <span className="mono-font" style={{ fontSize: "0.75rem", color: "var(--accent-amber)", fontWeight: 700 }}>
                {diffData.constraint_changes.length} Logic Constraints
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {diffData.constraint_changes.length === 0 ? (
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", padding: "12px 0" }}>No constraint changes detected.</div>
              ) : (
                diffData.constraint_changes.map((c) => (
                  <div
                    key={c.task_code}
                    style={{
                      padding: "10px 12px",
                      background: "rgba(255, 255, 255, 0.02)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-sm)",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center"
                    }}
                  >
                    <div>
                      <span className="mono-font" style={{ fontWeight: 700, color: "#fff", fontSize: "0.85rem" }}>
                        {c.task_code}
                      </span>
                      <div style={{ fontSize: "0.72rem", color: "var(--accent-amber)", marginTop: "2px" }}>
                        {c.new_constraint}
                      </div>
                    </div>
                    <span className="mono-font" style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                      {c.new_date}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Logic Rel Changes */}
          <div className="glass-panel" style={{ padding: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 700, color: "#fff" }}>Relationship Modifications</h3>
              <span className="mono-font" style={{ fontSize: "0.75rem", color: "#38bdf8", fontWeight: 700 }}>
                {diffData.added_relationships.length + diffData.modified_relationships.length} Links
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {diffData.added_relationships.length === 0 && diffData.modified_relationships.length === 0 ? (
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", padding: "12px 0" }}>No relationship link additions or lag changes.</div>
              ) : (
                <>
                  {diffData.added_relationships.map((r, i) => (
                    <div
                      key={`add-${i}`}
                      style={{
                        padding: "8px 12px",
                        background: "rgba(16, 185, 129, 0.05)",
                        border: "1px solid rgba(16, 185, 129, 0.2)",
                        borderRadius: "var(--radius-sm)",
                        fontSize: "0.8rem",
                        color: "#fff"
                      }}
                    >
                      <span style={{ color: "#10b981", fontWeight: 700 }}>+ ADDED: </span>
                      <span className="mono-font">{r.predecessor_code} &rarr; {r.successor_code} ({r.relationship_type})</span>
                    </div>
                  ))}
                  {diffData.modified_relationships.map((m, i) => (
                    <div
                      key={`mod-${i}`}
                      style={{
                        padding: "8px 12px",
                        background: "rgba(56, 189, 248, 0.05)",
                        border: "1px solid rgba(56, 189, 248, 0.2)",
                        borderRadius: "var(--radius-sm)",
                        fontSize: "0.8rem",
                        color: "#fff"
                      }}
                    >
                      <span style={{ color: "#38bdf8", fontWeight: 700 }}>LAG MOD: </span>
                      <span className="mono-font">{m.predecessor_code} &rarr; {m.successor_code} (Lag: {m.old_lag}d &rarr; {m.new_lag}d)</span>
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* VIEW 2: DRIVER CHURN CLASSIFICATION */}
      {activeTab === "churn" && (
        <div className="glass-panel" style={{ padding: "24px" }}>
          <div style={{ marginBottom: "20px" }}>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#fff" }}>Driver Churn & Persistence Matrix</h3>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
              Classifying bottlenecks across snapshot transition
            </p>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px" }}>
            {/* New Drivers */}
            <div style={{
              background: "rgba(244, 63, 94, 0.05)",
              border: "1px solid rgba(244, 63, 94, 0.25)",
              borderRadius: "var(--radius-md)",
              padding: "16px"
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "#fda4af" }}>New Emergent Drivers</span>
                <span className="mono-font" style={{ fontWeight: 800, color: "var(--accent-rose)" }}>
                  +{diffData.driver_churn.new_drivers.length}
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {diffData.driver_churn.new_drivers.length === 0 ? (
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>None</div>
                ) : (
                  diffData.driver_churn.new_drivers.map((d) => (
                    <div key={d} className="mono-font" style={{ padding: "8px 12px", background: "rgba(0, 0, 0, 0.3)", borderRadius: "4px", fontSize: "0.85rem", color: "#fff", fontWeight: 600 }}>
                      {d}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Persistent Drivers */}
            <div style={{
              background: "rgba(245, 158, 11, 0.05)",
              border: "1px solid rgba(245, 158, 11, 0.25)",
              borderRadius: "var(--radius-md)",
              padding: "16px"
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "#fde68a" }}>Persistent Bottlenecks</span>
                <span className="mono-font" style={{ fontWeight: 800, color: "var(--accent-amber)" }}>
                  {diffData.driver_churn.persistent_drivers.length}
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {diffData.driver_churn.persistent_drivers.length === 0 ? (
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>None</div>
                ) : (
                  diffData.driver_churn.persistent_drivers.map((d) => (
                    <div key={d} className="mono-font" style={{ padding: "8px 12px", background: "rgba(0, 0, 0, 0.3)", borderRadius: "4px", fontSize: "0.85rem", color: "#fff", fontWeight: 600 }}>
                      {d}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Resolved Drivers */}
            <div style={{
              background: "rgba(16, 185, 129, 0.05)",
              border: "1px solid rgba(16, 185, 129, 0.25)",
              borderRadius: "var(--radius-md)",
              padding: "16px"
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "#6ee7b7" }}>Resolved / Floated Back</span>
                <span className="mono-font" style={{ fontWeight: 800, color: "var(--accent-emerald)" }}>
                  {diffData.driver_churn.resolved_drivers.length}
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {diffData.driver_churn.resolved_drivers.length === 0 ? (
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>None</div>
                ) : (
                  diffData.driver_churn.resolved_drivers.map((d) => (
                    <div key={d} className="mono-font" style={{ padding: "8px 12px", background: "rgba(0, 0, 0, 0.3)", borderRadius: "4px", fontSize: "0.85rem", color: "#fff", fontWeight: 600 }}>
                      {d}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* VIEW 3: FLOAT EROSION HISTORY */}
      {activeTab === "erosion" && (
        <div className="glass-panel" style={{ padding: "24px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
            <div>
              <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#fff" }}>Historical Float Progression (No Extrapolation)</h3>
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Total float erosion across {snapshotCount} ingested snapshots
              </p>
            </div>
            <span className="tier-pill tier-fact">[FACT] Historical Data Dates</span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {trendData.float_trends.length === 0 ? (
              <div style={{ fontSize: "0.85rem", color: "var(--text-muted)", padding: "16px 0" }}>No multi-snapshot float trend data available.</div>
            ) : (
              trendData.float_trends.map((item) => (
                <div
                  key={item.task_code}
                  style={{
                    padding: "16px",
                    background: "rgba(255, 255, 255, 0.02)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "var(--radius-md)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center"
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span className="mono-font" style={{ fontWeight: 800, color: "#fff", fontSize: "0.95rem" }}>
                        {item.task_code}
                      </span>
                      <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                        {item.name}
                      </span>
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "24px" }}>
                    {item.history.map((h) => (
                      <div key={h.snapshot_id} style={{ textAlign: "center" }}>
                        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: "2px" }}>
                          {h.data_date}
                        </div>
                        <div className="mono-font" style={{
                          fontSize: "0.95rem",
                          fontWeight: 700,
                          color: h.total_float_days < 0 ? "var(--accent-rose)" : "var(--accent-emerald)"
                        }}>
                          {h.total_float_days.toFixed(1)}d
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
