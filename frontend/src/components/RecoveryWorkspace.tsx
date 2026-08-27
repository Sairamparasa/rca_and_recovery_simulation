import React, { useState } from "react";
import type { OptimizationResult, ParetoPoint } from "../types/api";
import { Zap, RefreshCw } from "lucide-react";

interface RecoveryWorkspaceProps {
  optimizationData: OptimizationResult;
  onReoptimize?: (budget: number) => void;
}

export const RecoveryWorkspace: React.FC<RecoveryWorkspaceProps> = ({
  optimizationData,
  onReoptimize,
}) => {
  const [selectedPoint, setSelectedPoint] = useState<ParetoPoint>(
    optimizationData.pareto_frontier[optimizationData.pareto_frontier.length - 1] || optimizationData.pareto_frontier[0]
  );
  const [budgetLimit, setBudgetLimit] = useState<number>(optimizationData.budget_limit);
  const [isOptimizing, setIsOptimizing] = useState<boolean>(false);

  const handleSweep = () => {
    setIsOptimizing(true);
    if (onReoptimize) {
      onReoptimize(budgetLimit);
    }
    setTimeout(() => {
      setIsOptimizing(false);
    }, 600);
  };

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Top Banner & Solver Meta */}
      <div className="glass-panel" style={{ padding: "20px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "4px" }}>
            <h2 style={{ fontSize: "1.2rem", fontWeight: 700, color: "#fff" }}>Schedule Recovery Optimization</h2>
            <span className="tier-pill tier-simulation">[SIMULATION_DEPENDENT] Pareto Frontier</span>
          </div>
          <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
            Solver: <strong style={{ color: "#a5b4fc" }}>{optimizationData.solver_used}</strong> • Evaluated {optimizationData.total_scenarios_evaluated} combinations in {optimizationData.execution_time_ms.toFixed(1)}ms
          </p>
        </div>

        {/* Budget Sweep Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
              Budget Limit: <strong style={{ color: "var(--accent-emerald)" }}>${budgetLimit.toLocaleString()}</strong>
            </span>
            <input
              type="range"
              min="10000"
              max="150000"
              step="5000"
              value={budgetLimit}
              onChange={(e) => setBudgetLimit(Number(e.target.value))}
              style={{ width: "180px", accentColor: "#6366f1" }}
            />
          </div>
          <button
            onClick={handleSweep}
            disabled={isOptimizing}
            className="btn-primary"
            style={{ padding: "8px 14px" }}
          >
            <RefreshCw size={16} className={isOptimizing ? "spin" : ""} />
            {isOptimizing ? "Solving..." : "Run Sweep"}
          </button>
        </div>
      </div>

      {/* Main Split: Interactive Pareto Frontier Visualization & Selected Scenario Inspector */}
      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: "24px" }}>
        {/* Pareto Frontier Visualizer */}
        <div className="glass-panel" style={{ padding: "24px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#fff" }}>Time-Cost Pareto Trade-Off Frontier</h3>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Select a point to inspect scenario levers</span>
          </div>

          {/* SVG Scatter & Curve Representation */}
          <div style={{
            background: "rgba(0, 0, 0, 0.3)",
            borderRadius: "var(--radius-md)",
            padding: "20px",
            border: "1px solid var(--border-subtle)",
            position: "relative"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "8px" }}>
              <span>Days Recovered (Y) vs Investment Cost (X)</span>
              <span>Floor Ceiling: 15.0 Days</span>
            </div>

            {/* Custom SVG Curve */}
            <svg viewBox="0 0 500 220" style={{ width: "100%", height: "200px", overflow: "visible" }}>
              {/* Grid lines */}
              <line x1="40" y1="20" x2="480" y2="20" stroke="rgba(255,255,255,0.05)" strokeDasharray="4" />
              <line x1="40" y1="80" x2="480" y2="80" stroke="rgba(255,255,255,0.05)" strokeDasharray="4" />
              <line x1="40" y1="140" x2="480" y2="140" stroke="rgba(255,255,255,0.05)" strokeDasharray="4" />
              <line x1="40" y1="190" x2="480" y2="190" stroke="rgba(255,255,255,0.15)" />

              {/* Axes */}
              <line x1="40" y1="10" x2="40" y2="190" stroke="rgba(255,255,255,0.15)" />
              <text x="30" y="25" fill="#64748b" fontSize="10" textAnchor="end">15d</text>
              <text x="30" y="85" fill="#64748b" fontSize="10" textAnchor="end">10d</text>
              <text x="30" y="145" fill="#64748b" fontSize="10" textAnchor="end">5d</text>
              <text x="30" y="193" fill="#64748b" fontSize="10" textAnchor="end">0d</text>

              {/* Frontier Line Path */}
              <path
                d="M 50 190 L 120 156 L 220 110 L 340 54 L 460 20"
                fill="none"
                stroke="#818cf8"
                strokeWidth="3"
                strokeDasharray="2"
              />

              {/* Pareto Points */}
              {optimizationData.pareto_frontier.map((pt, idx) => {
                // Map coordinates
                const xCoords = [50, 120, 220, 340, 460];
                const yCoords = [190, 156, 110, 54, 20];
                const cx = xCoords[idx] || 50;
                const cy = yCoords[idx] || 190;
                const isSelected = selectedPoint.scenario_name === pt.scenario_name;

                return (
                  <g key={pt.scenario_name} onClick={() => setSelectedPoint(pt)} style={{ cursor: "pointer" }}>
                    <circle
                      cx={cx}
                      cy={cy}
                      r={isSelected ? 9 : 6}
                      fill={isSelected ? "#10b981" : "#6366f1"}
                      stroke="#fff"
                      strokeWidth={isSelected ? 3 : 1.5}
                    />
                    <text
                      x={cx}
                      y={cy - 12}
                      fill={isSelected ? "#34d399" : "#94a3b8"}
                      fontSize="10"
                      fontWeight={isSelected ? "bold" : "normal"}
                      textAnchor="middle"
                    >
                      {pt.days_recovered}d (${(pt.cost_delta / 1000).toFixed(1)}k)
                    </text>
                  </g>
                );
              })}
            </svg>

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "4px" }}>
              <span>$0 (Baseline)</span>
              <span>$25,000</span>
              <span>$50,000</span>
              <span>$75,000+ (Max Feasible)</span>
            </div>
          </div>

          {/* Scenario Selection Grid */}
          <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "8px" }}>
            {optimizationData.pareto_frontier.map((pt) => {
              const isSelected = selectedPoint.scenario_name === pt.scenario_name;
              return (
                <div
                  key={pt.scenario_name}
                  onClick={() => setSelectedPoint(pt)}
                  style={{
                    padding: "12px 16px",
                    background: isSelected ? "rgba(99, 102, 241, 0.15)" : "rgba(255, 255, 255, 0.02)",
                    border: `1px solid ${isSelected ? "#818cf8" : "var(--border-subtle)"}`,
                    borderRadius: "var(--radius-md)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    cursor: "pointer",
                    transition: "all 0.2s ease"
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontWeight: 700, fontSize: "0.88rem", color: isSelected ? "#fff" : "var(--text-primary)" }}>
                        {pt.scenario_name}
                      </span>
                      {pt.critical_path_shifted && (
                        <span style={{ fontSize: "0.68rem", background: "rgba(244, 63, 94, 0.2)", color: "#fda4af", padding: "1px 6px", borderRadius: "4px", fontWeight: 600 }}>
                          CP Shifted
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      Finish: <strong style={{ color: "#38bdf8" }}>{pt.simulated_finish_date}</strong> • Levers Applied: {pt.levers_applied.length}
                    </div>
                  </div>

                  <div style={{ textAlign: "right" }}>
                    <div className="mono-font" style={{ fontSize: "0.95rem", fontWeight: 800, color: "var(--accent-emerald)" }}>
                      +{pt.days_recovered}d Recovered
                    </div>
                    <div className="mono-font" style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      ${pt.cost_delta.toLocaleString()}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Selected Scenario Details & Applied Levers */}
        <div className="glass-panel" style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <span className="mono-font" style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--accent-emerald)" }}>
                +{selectedPoint.days_recovered}.0 Days Recovered
              </span>
              <span className="tier-pill tier-simulation">${selectedPoint.cost_delta.toLocaleString()} Delta</span>
            </div>
            <h3 style={{ fontSize: "0.98rem", fontWeight: 700, color: "#fff", marginBottom: "4px" }}>
              {selectedPoint.scenario_name}
            </h3>
            <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
              Project Finish moves from <strong>2026-11-20</strong> to <strong style={{ color: "#38bdf8" }}>{selectedPoint.simulated_finish_date}</strong>. {selectedPoint.discrete_delayed_recovered_count} delayed activities brought to TF &ge; 0.
            </p>
          </div>

          {/* Applied Levers List */}
          <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "16px" }}>
            <h4 style={{ fontSize: "0.8rem", textTransform: "uppercase", fontWeight: 700, color: "var(--text-muted)", marginBottom: "12px" }}>
              Applied Recovery Levers ({selectedPoint.levers_applied.length})
            </h4>

            <div style={{ display: "flex", flexDirection: "column", gap: "10px", maxHeight: "360px", overflowY: "auto" }}>
              {selectedPoint.levers_applied.length > 0 ? (
                selectedPoint.levers_applied.map((lev, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "12px 14px",
                      background: "rgba(255, 255, 255, 0.02)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-sm)",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center"
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <div style={{
                        padding: "6px",
                        background: "rgba(99, 102, 241, 0.15)",
                        borderRadius: "6px",
                        color: "#818cf8"
                      }}>
                        <Zap size={16} />
                      </div>
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <span className="mono-font" style={{ fontSize: "0.85rem", fontWeight: 700, color: "#fff" }}>
                            {lev.target_entity}
                          </span>
                          <span className="tier-pill tier-modeled">{lev.lever_type}</span>
                        </div>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                          {lev.applied_change}
                        </div>
                      </div>
                    </div>

                    <div className="mono-font" style={{ fontSize: "0.85rem", fontWeight: 700, color: "#38bdf8" }}>
                      ${lev.cost?.toLocaleString() || 0}
                    </div>
                  </div>
                ))
              ) : (
                <div style={{ textAlign: "center", padding: "20px 0", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                  Baseline condition — No recovery levers applied
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
