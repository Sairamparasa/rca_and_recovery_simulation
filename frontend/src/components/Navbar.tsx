import React from "react";
import { Activity, ShieldCheck, Cpu, GitCommit, Bot, Sliders } from "lucide-react";

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  dcmaScore: number;
  criticalFloat: number;
  driverCount: number;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  dcmaScore,
  criticalFloat,
  driverCount,
}) => {
  const navItems = [
    { id: "drivers", label: "Driver Diagnostics", icon: Activity },
    { id: "recovery", label: "Recovery & Pareto", icon: Sliders },
    { id: "classification", label: "Constraint Queue", icon: ShieldCheck },
    { id: "trends", label: "Historical Trends", icon: GitCommit },
    { id: "ai", label: "AI Reasoning & NL", icon: Bot },
  ];

  return (
    <header style={{
      borderBottom: "1px solid var(--border-subtle)",
      background: "rgba(8, 11, 17, 0.85)",
      backdropFilter: "blur(16px)",
      position: "sticky",
      top: 0,
      zIndex: 50,
      padding: "12px 24px"
    }}>
      <div style={{
        maxWidth: "1600px",
        margin: "0 auto",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "24px"
      }}>
        {/* Brand & Active Schedule */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            background: "linear-gradient(135deg, rgba(99, 102, 241, 0.2) 0%, rgba(139, 92, 246, 0.1) 100%)",
            border: "1px solid rgba(99, 102, 241, 0.4)",
            padding: "8px 14px",
            borderRadius: "var(--radius-md)"
          }}>
            <Cpu size={20} color="#818cf8" />
            <div>
              <div className="brand-font" style={{ fontWeight: 800, fontSize: "1.05rem", letterSpacing: "0.02em", color: "#fff" }}>
                ARTH <span style={{ color: "#818cf8", fontWeight: 400 }}>RCA & Simulation</span>
              </div>
              <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "flex", gap: "6px" }}>
                <span>PHX3 Data Center Phase 1</span> • <span style={{ color: "#38bdf8" }}>2026-01-14 (Baseline)</span>
              </div>
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div style={{ display: "flex", alignItems: "center", gap: "12px", borderLeft: "1px solid var(--border-subtle)", paddingLeft: "16px" }}>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: "0.68rem", textTransform: "uppercase", color: "var(--text-muted)", fontWeight: 600 }}>Crit. Float</span>
              <span className="mono-font" style={{ fontSize: "0.95rem", fontWeight: 700, color: criticalFloat < 0 ? "var(--accent-rose)" : "var(--accent-emerald)" }}>
                {criticalFloat.toFixed(1)}d
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: "0.68rem", textTransform: "uppercase", color: "var(--text-muted)", fontWeight: 600 }}>Drivers</span>
              <span className="mono-font" style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--accent-amber)" }}>
                {driverCount} Heads
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: "0.68rem", textTransform: "uppercase", color: "var(--text-muted)", fontWeight: 600 }}>DCMA Health</span>
              <span className="mono-font" style={{ fontSize: "0.95rem", fontWeight: 700, color: dcmaScore >= 90 ? "var(--accent-emerald)" : "var(--accent-amber)" }}>
                {dcmaScore.toFixed(1)}%
              </span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav style={{ display: "flex", alignItems: "center", gap: "6px", background: "rgba(255, 255, 255, 0.03)", padding: "4px", borderRadius: "var(--radius-md)", border: "1px solid var(--border-subtle)" }}>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "8px 14px",
                  borderRadius: "var(--radius-sm)",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                  fontWeight: isActive ? 600 : 500,
                  transition: "all 0.2s ease",
                  background: isActive ? "linear-gradient(135deg, rgba(99, 102, 241, 0.3) 0%, rgba(79, 70, 229, 0.2) 100%)" : "transparent",
                  color: isActive ? "#fff" : "var(--text-secondary)",
                  boxShadow: isActive ? "0 2px 8px rgba(0, 0, 0, 0.4)" : "none",
                  borderBottom: isActive ? "2px solid #818cf8" : "2px solid transparent"
                }}
              >
                <Icon size={16} color={isActive ? "#818cf8" : "currentColor"} />
                {item.label}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
};
