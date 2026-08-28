import { useState, useEffect, useCallback } from "react";
import { Navbar } from "./components/Navbar";
import { DriverDashboard } from "./components/DriverDashboard";
import { RecoveryWorkspace } from "./components/RecoveryWorkspace";
import { ClassificationQueue } from "./components/ClassificationQueue";
import { HistoricalTrendView } from "./components/HistoricalTrendView";
import { AIReasoningAssistant } from "./components/AIReasoningAssistant";
import { UploadSnapshotModal } from "./components/UploadSnapshotModal";
import { apiService } from "./services/api";
import type {
  DriverAnalysisResult,
  DCMAAssessmentReport,
  OptimizationResult,
  RelationshipClassification,
  SnapshotDiff,
  TrendData,
  NarrativeReport,
  IngestionSummaryResponse,
  SnapshotListItem,
} from "./types/api";

export function App() {
  const [activeTab, setActiveTab] = useState<string>("drivers");
  const [activeSnapshotId, setActiveSnapshotId] = useState<number>(1);
  const [snapshots, setSnapshots] = useState<SnapshotListItem[]>([]);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState<boolean>(false);

  const [driversData, setDriversData] = useState<DriverAnalysisResult | null>(null);
  const [dcmaData, setDcmaData] = useState<DCMAAssessmentReport | null>(null);
  const [optimizationData, setOptimizationData] = useState<OptimizationResult | null>(null);
  const [classificationQueue, setClassificationQueue] = useState<RelationshipClassification[]>([]);
  const [trendData, setTrendData] = useState<TrendData | null>(null);
  const [diffData, setDiffData] = useState<SnapshotDiff | null>(null);
  const [narrativeReport, setNarrativeReport] = useState<NarrativeReport | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const loadDashboardData = useCallback(async (snapId: number) => {
    setLoading(true);
    try {
      const [drivers, dcma, opt, queue, trends, diff, report, snapList] = await Promise.all([
        apiService.getDrivers(snapId),
        apiService.getDCMA(snapId),
        apiService.runOptimization(100000),
        apiService.getClassificationQueue(),
        apiService.getTrends(snapId),
        apiService.getSnapshotDiff(snapId, snapId + 1),
        apiService.getNarrativeReport(snapId),
        apiService.listSnapshots(),
      ]);
      setDriversData(drivers);
      setDcmaData(dcma);
      setOptimizationData(opt);
      setClassificationQueue(queue);
      setTrendData(trends);
      setDiffData(diff);
      setNarrativeReport(report);
      setSnapshots(snapList);
    } catch (err) {
      console.error("Error loading dashboard data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboardData(activeSnapshotId);
  }, [activeSnapshotId, loadDashboardData]);

  const handleSnapshotIngested = (summary: IngestionSummaryResponse) => {
    setActiveSnapshotId(summary.snapshot_id);
    loadDashboardData(summary.snapshot_id);
  };

  const handleSnapshotDeleted = (deletedId: number) => {
    if (activeSnapshotId === deletedId) {
      const remaining = snapshots.filter((s) => s.snapshot_id !== deletedId);
      const nextId = remaining.length > 0 ? remaining[0].snapshot_id : 1;
      setActiveSnapshotId(nextId);
      loadDashboardData(nextId);
    } else {
      loadDashboardData(activeSnapshotId);
    }
  };

  const handleReoptimize = async (budget: number) => {
    const res = await apiService.runOptimization(budget);
    setOptimizationData(res);
  };

  const handleSubmitClassification = async (key: string, type: string, rationale: string) => {
    await apiService.submitClassification(key, type, rationale);
    setClassificationQueue((prev) =>
      prev.map((item) =>
        item.relationship_key === key
          ? { ...item, constraint_type: type as any, rationale }
          : item
      )
    );
  };

  if (loading || !driversData || !dcmaData || !optimizationData || !trendData || !diffData) {
    return (
      <div style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "16px",
        background: "var(--bg-main)",
        color: "var(--text-primary)"
      }}>
        <div style={{
          width: "40px",
          height: "40px",
          border: "3px solid rgba(99, 102, 241, 0.2)",
          borderTopColor: "#818cf8",
          borderRadius: "50%",
          animation: "spin 0.8s linear infinite"
        }} />
        <span className="mono-font" style={{ fontSize: "0.9rem", color: "var(--text-secondary)" }}>
          Loading ARTH Schedule Intelligence Engine...
        </span>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-main)" }}>
      {/* Sticky Header */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        dcmaScore={dcmaData.overall_health_score}
        criticalFloat={driversData.drivers[0]?.driver_total_float_days || 0}
        driverCount={driversData.driver_head_count}
        onOpenUploadModal={() => setIsUploadModalOpen(true)}
        activeSnapshotId={activeSnapshotId}
        onSelectSnapshot={(id) => setActiveSnapshotId(id)}
        snapshots={snapshots}
      />

      {/* Main Workspace View Container */}
      <main style={{ maxWidth: "1600px", margin: "0 auto", padding: "28px 24px 60px" }}>
        {activeTab === "drivers" && (
          <DriverDashboard driversData={driversData} dcmaData={dcmaData} />
        )}

        {activeTab === "recovery" && (
          <RecoveryWorkspace
            optimizationData={optimizationData}
            onReoptimize={handleReoptimize}
          />
        )}

        {activeTab === "classification" && (
          <ClassificationQueue
            queue={classificationQueue}
            onSubmitClassification={handleSubmitClassification}
          />
        )}

        {activeTab === "trends" && (
          <HistoricalTrendView
            trendData={trendData}
            diffData={diffData}
          />
        )}

        {activeTab === "ai" && (
          <AIReasoningAssistant initialReport={narrativeReport} />
        )}
      </main>

      {/* Ingestion & Upload Modal */}
      <UploadSnapshotModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onSnapshotIngested={handleSnapshotIngested}
        onSnapshotDeleted={handleSnapshotDeleted}
        activeSnapshotId={activeSnapshotId}
      />
    </div>
  );
}

export default App;
