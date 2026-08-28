import React, { useState, useEffect } from "react";
import type { OptimizationResult, ParetoPoint } from "../types/api";
import { Zap, RefreshCw } from "lucide-react";

interface RecoveryWorkspaceProps {
  optimizationData: OptimizationResult | null;
  onReoptimize?: (budget: number) => void;
}

export const RecoveryWorkspace: React.FC<RecoveryWorkspaceProps> = ({
  optimizationData,
  onReoptimize,
}) => {
  const paretoPoints = optimizationData?.pareto_frontier || [];
  const [selectedPoint, setSelectedPoint] = useState<ParetoPoint | null>(
    paretoPoints.length > 0 ? paretoPoints[paretoPoints.length - 1] : null
  );
  const [budgetLimit, setBudgetLimit] = useState<number>(optimizationData?.budget_limit || 100000);
  const [isOptimizing, setIsOptimizing] = useState<boolean>(false);

  useEffect(() => {
    if (paretoPoints.length > 0 && (!selectedPoint || !paretoPoints.some(p => p.scenario_name === selectedPoint.scenario_name))) {
      setSelectedPoint(paretoPoints[paretoPoints.length - 1] || paretoPoints[0]);
    }
  }, [optimizationData, paretoPoints]);

  const handleSweep = () => {
    setIsOptimizing(true);
    if (onReoptimize) {
      onReoptimize(budgetLimit);
    }
    setTimeout(() => {
      setIsOptimizing(false);
    }, 1500);
  };

  if (!optimizationData || paretoPoints.length === 0) {
    return (
      <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
        <div className="glass-panel" style={{ padding: "20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "4px" }}>
              <h2 style={{ fontSize: "1.2rem", fontWeight: 700, color: "#fff" }}>Schedule Recovery Optimization</h2>
              <span className="tier-pill tier-simulation">[SIMULATION_DEPENDENT] Pareto Frontier</span>
            </div>
            <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
              Combinatorial search across crash durations, safe fast-tracking, and calendar shifts.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                Budget Limit: <strong style={{ color: "var(--accent-emerald)" }}>${budgetLimit.toLocaleString()}</strong>
              </span>
              <input
                type="range"
                min="10000"
                max="200000"
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
              style={{ padding: "8px 16px" }}
            >
              <RefreshCw size={16} className={isOptimizing ? "spin" : ""} />
              {isOptimizing ? "Optimizing..." : "Run Optimization Solver"}
            </button>
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
            <Zap size={28} />
          </div>
          <div>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#fff", marginBottom: "8px" }}>
              No Optimization Scenarios Generated Yet
            </h3>
            <p style={{ fontSize: "0.88rem", color: "var(--text-muted)", maxWidth: "560px", margin: "0 auto", lineHeight: "1.5" }}>
              Click <strong>Run Optimization Solver</strong> above to generate the Time-Cost Pareto trade-off curve across crashing and safety-cleared fast-tracking levers.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const activePoint = selectedPoint || paretoPoints[0];

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
            Solver: <strong style={{ color: "#a5b4fc" }}>{optimizationData.solver_used}</strong> • Evaluated {optimizationData.total_scenarios_evaluated} combinations in {(optimizationData.execution_time_ms || 0).toFixed(1)}ms
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
              max="200000"
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

          {/* Scenario Selection Grid */}
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {paretoPoints.map((pt, idx) => {
              const isSelected = activePoint?.scenario_name === pt.scenario_name;
              return (
                <div
                  key={pt.scenario_name || idx}
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
                      <span className="mono-font" style={{ fontWeight: 800, color: isSelected ? "#818cf8" : "#fff", fontSize: "0.95rem" }}>
                        Point #{idx}
                      </span>
                      <span style={{ fontSize: "0.85rem", color: "var(--text-primary)", fontWeight: 600 }}>
                        {pt.scenario_name}
                      </span>
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "2px" }}>
                      {pt.levers_applied.length} Levers Applied • Finish: <strong style={{ color: "#38bdf8" }}>{pt.simulated_finish_date}</strong>
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
                    <div style={{ textAlign: "right" }}>
                      <div className="mono-font" style={{ fontWeight: 800, color: "var(--accent-emerald)", fontSize: "0.95rem" }}>
                        +{pt.days_recovered}d Recovered
                      </div>
                      <div className="mono-font" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        Cost: ${(pt.cost_delta || 0).toLocaleString()}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Selected Scenario Lever Inspector */}
        <div className="glass-panel" style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <span className="tier-pill tier-simulation">Selected Scenario</span>
              <span className="mono-font" style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                Cost: <strong style={{ color: "var(--accent-emerald)" }}>${(activePoint.cost_delta || 0).toLocaleString()}</strong>
              </span>
            </div>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#fff", marginBottom: "4px" }}>
              {activePoint.scenario_name}
            </h3>
            <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
              Recovers <strong style={{ color: "var(--accent-emerald)" }}>{activePoint.days_recovered} days</strong> of critical path delay.
            </p>
          </div>

          <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "14px" }}>
            <span style={{ fontSize: "0.8rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)" }}>
              Levers Applied ({activePoint.levers_applied.length})
            </span>

            <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "10px", maxHeight: "320px", overflowY: "auto" }}>
              {activePoint.levers_applied.length === 0 ? (
                <div style={{ fontSize: "0.82rem", color: "var(--text-muted)", padding: "16px 0", textAlign: "center" }}>
                  No levers applied (Baseline / Zero recovery).
                </div>
              ) : (
                activePoint.levers_applied.map((lev: any, i: number) => (
                  <div
                    key={i}
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
                      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        <span className="tier-pill tier-fact" style={{ fontSize: "0.65rem" }}>
                          {lev.lever_type}
                        </span>
                        <span className="mono-font" style={{ fontWeight: 700, color: "#fff", fontSize: "0.82rem" }}>
                          {lev.target_entity}
                        </span>
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                        {lev.applied_change}
                      </div>
                    </div>
                    <span className="mono-font" style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--accent-emerald)" }}>
                      +${(lev.cost || 0).toLocaleString()}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
