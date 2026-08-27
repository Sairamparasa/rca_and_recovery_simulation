import React, { useState } from "react";
import type { RelationshipClassification } from "../types/api";
import { Edit3, ArrowRight } from "lucide-react";

interface ClassificationQueueProps {
  queue: RelationshipClassification[];
  onSubmitClassification: (key: string, type: string, rationale: string) => void;
}

export const ClassificationQueue: React.FC<ClassificationQueueProps> = ({
  queue,
  onSubmitClassification,
}) => {
  const [filterType, setFilterType] = useState<string>("ALL");
  const [editingItem, setEditingItem] = useState<RelationshipClassification | null>(null);
  const [overrideRationale, setOverrideRationale] = useState<string>("");
  const [overrideType, setOverrideType] = useState<string>("SOFT_CONVENIENCE");

  const filteredQueue = queue.filter((item) => {
    if (filterType === "ALL") return true;
    return item.constraint_type === filterType;
  });

  const handleQuickAction = (item: RelationshipClassification, type: string) => {
    onSubmitClassification(item.relationship_key, type, `PM approved classification as ${type}`);
  };

  const handleOverrideSubmit = () => {
    if (!editingItem) return;
    onSubmitClassification(editingItem.relationship_key, overrideType, overrideRationale || "PM manual override");
    setEditingItem(null);
    setOverrideRationale("");
  };

  const getTypeBadge = (type: string) => {
    switch (type) {
      case "HARD_PHYSICAL":
        return <span className="tier-pill tier-fact" style={{ background: "rgba(244, 63, 94, 0.15)", color: "#fda4af", borderColor: "rgba(244, 63, 94, 0.4)" }}>Hard Physical</span>;
      case "HARD_REGULATORY":
        return <span className="tier-pill tier-fact" style={{ background: "rgba(239, 68, 68, 0.15)", color: "#fca5a5", borderColor: "rgba(239, 68, 68, 0.4)" }}>Hard Regulatory</span>;
      case "SOFT_CONVENIENCE":
        return <span className="tier-pill tier-simulation" style={{ background: "rgba(16, 185, 129, 0.15)", color: "#6ee7b7", borderColor: "rgba(16, 185, 129, 0.4)" }}>Soft Fast-Trackable</span>;
      case "SOFT_RESOURCE":
        return <span className="tier-pill tier-modeled" style={{ background: "rgba(59, 130, 246, 0.15)", color: "#93c5fd", borderColor: "rgba(59, 130, 246, 0.4)" }}>Soft Resource</span>;
      default:
        return <span className="tier-pill tier-hypothesis">Unclassified</span>;
    }
  };

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Top Banner */}
      <div className="glass-panel" style={{ padding: "20px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "4px" }}>
            <h2 style={{ fontSize: "1.2rem", fontWeight: 700, color: "#fff" }}>PM Constraint Classification & Safety Gate</h2>
            <span className="tier-pill tier-modeled">[MODELED] Heuristic Stack &ge; 0.80</span>
          </div>
          <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
            Review unverified Finish-to-Start relationships. Hard constraints strictly block automated fast-tracking.
          </p>
        </div>

        {/* Filter Pills */}
        <div style={{ display: "flex", gap: "8px" }}>
          {["ALL", "HARD_PHYSICAL", "HARD_REGULATORY", "SOFT_CONVENIENCE", "UNCLASSIFIED"].map((t) => (
            <button
              key={t}
              onClick={() => setFilterType(t)}
              style={{
                background: filterType === t ? "rgba(99, 102, 241, 0.25)" : "rgba(255, 255, 255, 0.04)",
                color: filterType === t ? "#fff" : "var(--text-muted)",
                border: `1px solid ${filterType === t ? "#818cf8" : "var(--border-subtle)"}`,
                padding: "6px 12px",
                borderRadius: "var(--radius-sm)",
                fontSize: "0.75rem",
                fontWeight: 600,
                cursor: "pointer"
              }}
            >
              {t.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>

      {/* Queue Items Table */}
      <div className="glass-panel" style={{ padding: "24px" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-subtle)", color: "var(--text-muted)" }}>
                <th style={{ padding: "10px 12px" }}>Predecessor &rarr; Successor</th>
                <th style={{ padding: "10px 12px" }}>Lag</th>
                <th style={{ padding: "10px 12px" }}>Classification</th>
                <th style={{ padding: "10px 12px" }}>Confidence</th>
                <th style={{ padding: "10px 12px" }}>Rationale & Heuristic Evidence</th>
                <th style={{ padding: "10px 12px", textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredQueue.map((item) => (
                <tr
                  key={item.relationship_key}
                  style={{ borderBottom: "1px solid var(--border-subtle)", transition: "background 0.2s ease" }}
                >
                  <td style={{ padding: "14px 12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <span className="mono-font" style={{ fontWeight: 700, color: "#fff" }}>
                        {item.predecessor_task_code}
                      </span>
                      <ArrowRight size={14} color="var(--text-muted)" />
                      <span className="mono-font" style={{ fontWeight: 700, color: "#38bdf8" }}>
                        {item.successor_task_code}
                      </span>
                    </div>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                      Proximity to Critical Path: L{item.longest_path_proximity || 1}
                    </span>
                  </td>

                  <td className="mono-font" style={{ padding: "14px 12px", color: "var(--text-secondary)" }}>
                    {item.lag_days || 0}d
                  </td>

                  <td style={{ padding: "14px 12px" }}>
                    {getTypeBadge(item.constraint_type)}
                  </td>

                  <td style={{ padding: "14px 12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <div style={{
                        width: "50px",
                        height: "6px",
                        background: "rgba(255, 255, 255, 0.1)",
                        borderRadius: "3px",
                        overflow: "hidden"
                      }}>
                        <div style={{
                          width: `${item.confidence * 100}%`,
                          height: "100%",
                          background: item.confidence >= 0.8 ? "var(--accent-emerald)" : "var(--accent-amber)"
                        }} />
                      </div>
                      <span className="mono-font" style={{ fontSize: "0.75rem", fontWeight: 700, color: item.confidence >= 0.8 ? "var(--accent-emerald)" : "var(--accent-amber)" }}>
                        {(item.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </td>

                  <td style={{ padding: "14px 12px", maxWidth: "340px", color: "var(--text-secondary)", fontSize: "0.82rem" }}>
                    {item.rationale}
                  </td>

                  <td style={{ padding: "14px 12px", textAlign: "right" }}>
                    <div style={{ display: "flex", justifyContent: "flex-end", gap: "6px" }}>
                      <button
                        onClick={() => handleQuickAction(item, "HARD_PHYSICAL")}
                        title="Approve as Hard Constraint"
                        style={{
                          background: "rgba(244, 63, 94, 0.15)",
                          border: "1px solid rgba(244, 63, 94, 0.4)",
                          color: "#fda4af",
                          padding: "4px 8px",
                          borderRadius: "4px",
                          cursor: "pointer",
                          fontSize: "0.72rem",
                          fontWeight: 600
                        }}
                      >
                        Lock Hard
                      </button>

                      <button
                        onClick={() => handleQuickAction(item, "SOFT_CONVENIENCE")}
                        title="Approve as Soft / Fast-Trackable"
                        style={{
                          background: "rgba(16, 185, 129, 0.15)",
                          border: "1px solid rgba(16, 185, 129, 0.4)",
                          color: "#6ee7b7",
                          padding: "4px 8px",
                          borderRadius: "4px",
                          cursor: "pointer",
                          fontSize: "0.72rem",
                          fontWeight: 600
                        }}
                      >
                        Allow Soft
                      </button>

                      <button
                        onClick={() => {
                          setEditingItem(item);
                          setOverrideType(item.constraint_type);
                        }}
                        title="Edit & Override"
                        style={{
                          background: "rgba(255, 255, 255, 0.05)",
                          border: "1px solid var(--border-subtle)",
                          color: "var(--text-secondary)",
                          padding: "4px 8px",
                          borderRadius: "4px",
                          cursor: "pointer"
                        }}
                      >
                        <Edit3 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Override Dialog Modal */}
      {editingItem && (
        <div style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: "rgba(0, 0, 0, 0.7)",
          backdropFilter: "blur(8px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 100
        }}>
          <div className="glass-panel" style={{ width: "480px", padding: "24px", background: "#0e131f" }}>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#fff", marginBottom: "12px" }}>
              Override Relationship Classification
            </h3>
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "16px" }}>
              Link: <strong className="mono-font" style={{ color: "#818cf8" }}>{editingItem.predecessor_task_code} &rarr; {editingItem.successor_task_code}</strong>
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "20px" }}>
              <div>
                <label style={{ fontSize: "0.75rem", textTransform: "uppercase", fontWeight: 600, color: "var(--text-muted)", display: "block", marginBottom: "6px" }}>
                  Assigned Type
                </label>
                <select
                  value={overrideType}
                  onChange={(e) => setOverrideType(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    background: "rgba(255, 255, 255, 0.05)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "var(--radius-sm)",
                    color: "#fff",
                    fontSize: "0.85rem"
                  }}
                >
                  <option value="HARD_PHYSICAL">HARD_PHYSICAL (E.g. Concrete cure, duct before pull)</option>
                  <option value="HARD_REGULATORY">HARD_REGULATORY (E.g. Permit inspection sign-off)</option>
                  <option value="SOFT_CONVENIENCE">SOFT_CONVENIENCE (Fast-Trackable / Staggered start)</option>
                  <option value="SOFT_RESOURCE">SOFT_RESOURCE (Shared crew / Equipment trade preference)</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: "0.75rem", textTransform: "uppercase", fontWeight: 600, color: "var(--text-muted)", display: "block", marginBottom: "6px" }}>
                  PM Rationale / Engineering Justification
                </label>
                <textarea
                  rows={3}
                  value={overrideRationale}
                  onChange={(e) => setOverrideRationale(e.target.value)}
                  placeholder="Enter reason for overriding the heuristic recommendation..."
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    background: "rgba(255, 255, 255, 0.05)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "var(--radius-sm)",
                    color: "#fff",
                    fontSize: "0.85rem",
                    resize: "none"
                  }}
                />
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
              <button
                onClick={() => setEditingItem(null)}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleOverrideSubmit}
                className="btn-primary"
              >
                Save Override
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
