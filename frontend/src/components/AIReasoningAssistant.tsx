import React, { useState, useEffect } from "react";
import type { NarrativeReport, NLQueryResponse, EvidenceLedgerEntry } from "../types/api";
import { apiService } from "../services/api";
import { Bot, Send, AlertTriangle, Database, FileText } from "lucide-react";

interface AIReasoningAssistantProps {
  initialReport?: NarrativeReport | null;
}

export const AIReasoningAssistant: React.FC<AIReasoningAssistantProps> = ({ initialReport }) => {
  const [report, setReport] = useState<NarrativeReport | null>(initialReport || null);
  const [query, setQuery] = useState<string>("");
  const [isQuerying, setIsQuerying] = useState<boolean>(false);
  const [chatHistory, setChatHistory] = useState<NLQueryResponse[]>([]);
  const [activeLedger, setActiveLedger] = useState<EvidenceLedgerEntry[] | null>(null);

  useEffect(() => {
    if (!report) {
      apiService.getNarrativeReport(1).then((r) => setReport(r));
    }
  }, [report]);

  const handleAsk = async (textToAsk?: string) => {
    const q = textToAsk || query;
    if (!q.trim()) return;
    setIsQuerying(true);
    try {
      const res = await apiService.askQuery(q);
      setChatHistory((prev) => [...prev, res]);
      setQuery("");
    } catch (_) {
    } finally {
      setIsQuerying(false);
    }
  };

  const sampleQuestions = [
    "Why is QTS-28981 delayed?",
    "What are the top 3 drivers on the critical path?",
    "What is the DCMA health score and missing logic count?",
    "What are the recovery options and budget trade-offs?",
  ];

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Top Banner */}
      <div className="glass-panel" style={{ padding: "20px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "4px" }}>
            <h2 style={{ fontSize: "1.2rem", fontWeight: 700, color: "#fff" }}>Grounded AI Reasoning & Natural Language Interface</h2>
            <span className="tier-pill tier-fact">[FACT] Zero Hallucination — Database Grounded</span>
          </div>
          <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
            Plain-language schedule intelligence strictly synthesized from deterministic CPM, driver, and DCMA facts.
          </p>
        </div>

        {/* Evidence Ledger Button */}
        {report && (
          <button
            onClick={() => setActiveLedger(report.evidence_ledger)}
            className="btn-secondary"
            style={{ fontSize: "0.8rem", padding: "6px 12px" }}
          >
            <Database size={15} color="#818cf8" />
            Inspect Evidence Ledger ({report.evidence_ledger.length} Claims)
          </button>
        )}
      </div>

      {/* Main Split: Executive Grounded Narrative Report vs Interactive Query Chat */}
      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: "24px" }}>
        {/* Executive Narrative Report */}
        <div className="glass-panel" style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "18px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <FileText size={18} color="#818cf8" />
              <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#fff" }}>Executive Diagnostic Report</h3>
            </div>
            <span className="mono-font" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              Data Date: 2026-01-14
            </span>
          </div>

          {report ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px", fontSize: "0.88rem", lineHeight: 1.6 }}>
              {/* Executive Summary */}
              <div>
                <h4 style={{ fontSize: "0.8rem", textTransform: "uppercase", fontWeight: 700, color: "var(--text-muted)", marginBottom: "6px" }}>
                  1. Executive Summary
                </h4>
                <p style={{ color: "var(--text-primary)" }}>
                  {report.executive_summary}
                </p>
              </div>

              {/* Drivers Narrative */}
              <div>
                <h4 style={{ fontSize: "0.8rem", textTransform: "uppercase", fontWeight: 700, color: "var(--text-muted)", marginBottom: "6px" }}>
                  2. Critical Drivers & Blast Radius Analysis
                </h4>
                <p style={{ color: "var(--text-secondary)" }}>
                  {report.drivers_narrative}
                </p>
              </div>

              {/* DCMA Health Narrative */}
              <div>
                <h4 style={{ fontSize: "0.8rem", textTransform: "uppercase", fontWeight: 700, color: "var(--text-muted)", marginBottom: "6px" }}>
                  3. DCMA 14-Point Health Assessment
                </h4>
                <p style={{ color: "var(--text-secondary)" }}>
                  {report.dcma_narrative}
                </p>
              </div>

              {/* Unresolved Hypotheses Warning Block */}
              {report.unresolved_hypotheses.length > 0 && (
                <div style={{
                  padding: "14px 16px",
                  background: "rgba(245, 158, 11, 0.08)",
                  border: "1px solid rgba(245, 158, 11, 0.35)",
                  borderRadius: "var(--radius-md)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px"
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "#fcd34d", fontWeight: 700, fontSize: "0.85rem" }}>
                    <AlertTriangle size={16} />
                    <span>HYPOTHESIS — UNRESOLVED ROOT CAUSES (Requires PM Verification)</span>
                  </div>
                  {report.unresolved_hypotheses.map((h) => (
                    <div key={h.task_code} style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                      <strong className="mono-font" style={{ color: "#fff" }}>{h.task_code}</strong> ({h.float_days.toFixed(1)}d): {h.hypothesis}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
              Loading executive narrative...
            </div>
          )}
        </div>

        {/* Interactive Natural Language Query Chat */}
        <div className="glass-panel" style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <Bot size={18} color="#818cf8" />
              <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#fff" }}>Natural Language Assistant</h3>
            </div>
            <span className="tier-pill tier-modeled">openai/gpt-oss-120b</span>
          </div>

          {/* Sample Chips */}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
              Suggested Inquiries:
            </span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {sampleQuestions.map((sq, i) => (
                <button
                  key={i}
                  onClick={() => handleAsk(sq)}
                  style={{
                    background: "rgba(255, 255, 255, 0.04)",
                    border: "1px solid var(--border-subtle)",
                    padding: "4px 10px",
                    borderRadius: "var(--radius-full)",
                    fontSize: "0.75rem",
                    color: "var(--text-secondary)",
                    cursor: "pointer",
                    transition: "all 0.2s ease"
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = "#818cf8";
                    e.currentTarget.style.color = "#fff";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "var(--border-subtle)";
                    e.currentTarget.style.color = "var(--text-secondary)";
                  }}
                >
                  {sq}
                </button>
              ))}
            </div>
          </div>

          {/* Chat Messages Stream */}
          <div style={{
            flex: 1,
            minHeight: "320px",
            maxHeight: "360px",
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
            paddingRight: "4px"
          }}>
            {chatHistory.length === 0 ? (
              <div style={{ textAlign: "center", padding: "50px 0", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                Ask any question regarding critical path delays, DCMA health checks, or recovery scenario trade-offs.
              </div>
            ) : (
              chatHistory.map((item, idx) => (
                <div key={idx} style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  {/* User Question */}
                  <div style={{
                    alignSelf: "flex-end",
                    background: "rgba(99, 102, 241, 0.2)",
                    border: "1px solid rgba(99, 102, 241, 0.4)",
                    padding: "8px 14px",
                    borderRadius: "12px 12px 2px 12px",
                    fontSize: "0.85rem",
                    color: "#fff",
                    maxWidth: "85%"
                  }}>
                    {item.query}
                  </div>

                  {/* Grounded AI Answer */}
                  <div style={{
                    alignSelf: "flex-start",
                    background: "rgba(255, 255, 255, 0.03)",
                    border: "1px solid var(--border-subtle)",
                    padding: "12px 16px",
                    borderRadius: "2px 12px 12px 12px",
                    fontSize: "0.85rem",
                    color: "var(--text-primary)",
                    maxWidth: "95%",
                    display: "flex",
                    flexDirection: "column",
                    gap: "6px"
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span className={`tier-pill ${item.primary_certainty_tier === "FACT" ? "tier-fact" : "tier-inference"}`}>
                        [{item.primary_certainty_tier}]
                      </span>
                      {item.evidence_ledger && (
                        <button
                          onClick={() => setActiveLedger(item.evidence_ledger)}
                          style={{
                            background: "transparent",
                            border: "none",
                            color: "#818cf8",
                            fontSize: "0.72rem",
                            cursor: "pointer",
                            textDecoration: "underline"
                          }}
                        >
                          Citations ({item.evidence_ledger.length})
                        </button>
                      )}
                    </div>
                    <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
                      {item.answer_markdown}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Input Box */}
          <div style={{ display: "flex", gap: "8px" }}>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAsk()}
              placeholder="Ask schedule intelligence assistant..."
              style={{
                flex: 1,
                padding: "10px 14px",
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-md)",
                color: "#fff",
                fontSize: "0.85rem",
                outline: "none"
              }}
            />
            <button
              onClick={() => handleAsk()}
              disabled={isQuerying || !query.trim()}
              className="btn-primary"
              style={{ padding: "0 18px" }}
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Evidence Ledger Drawer Modal */}
      {activeLedger && (
        <div style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: "rgba(0, 0, 0, 0.75)",
          backdropFilter: "blur(8px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 100
        }}>
          <div className="glass-panel" style={{ width: "640px", maxHeight: "80vh", padding: "24px", background: "#0e131f", display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "12px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <Database size={18} color="#818cf8" />
                <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#fff" }}>Audit Evidence Ledger</h3>
              </div>
              <button
                onClick={() => setActiveLedger(null)}
                className="btn-secondary"
                style={{ padding: "4px 8px" }}
              >
                Close
              </button>
            </div>

            <div style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: "10px" }}>
              {activeLedger.map((entry) => (
                <div
                  key={entry.id}
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
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                      <span className={`tier-pill ${entry.certainty_tier === "FACT" ? "tier-fact" : (entry.certainty_tier === "HYPOTHESIS" ? "tier-hypothesis" : "tier-inference")}`}>
                        [{entry.certainty_tier}]
                      </span>
                      <span className="mono-font" style={{ fontSize: "0.82rem", fontWeight: 700, color: "#fff" }}>
                        {entry.source_entity}
                      </span>
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                      {entry.claim_text}
                    </div>
                  </div>

                  <div className="mono-font" style={{ fontSize: "0.82rem", fontWeight: 700, color: "#38bdf8" }}>
                    {String(entry.metric_value)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
