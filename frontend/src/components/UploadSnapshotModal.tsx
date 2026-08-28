import React, { useState, useRef, useEffect } from "react";
import { Upload, X, CheckCircle, AlertTriangle, FileText, Loader2, ArrowRight, Trash2, Shield, Layers } from "lucide-react";
import { api } from "../services/api";
import type { IngestionSummaryResponse, SnapshotListItem } from "../types/api";

interface UploadSnapshotModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSnapshotIngested: (summary: IngestionSummaryResponse) => void;
  onSnapshotDeleted?: (deletedId: number) => void;
  activeSnapshotId?: number;
}

export const UploadSnapshotModal: React.FC<UploadSnapshotModalProps> = ({
  isOpen,
  onClose,
  onSnapshotIngested,
  onSnapshotDeleted,
  activeSnapshotId = 1,
}) => {
  const [activeTab, setActiveTab] = useState<"upload" | "manage">("upload");
  const [file, setFile] = useState<File | null>(null);
  const [orgName, setOrgName] = useState("QTS Data Centers");
  const [projectName, setProjectName] = useState("");
  const [isBaseline, setIsBaseline] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IngestionSummaryResponse | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  // Management State
  const [snapshots, setSnapshots] = useState<SnapshotListItem[]>([]);
  const [loadingSnapshots, setLoadingSnapshots] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSnapshots = async () => {
    setLoadingSnapshots(true);
    try {
      const list = await api.listSnapshots();
      setSnapshots(list);
    } catch (_) {}
    finally {
      setLoadingSnapshots(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadSnapshots();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      if (!selected.name.toLowerCase().endsWith(".xer")) {
        setError("Invalid file format. Please select an Oracle Primavera P6 (.xer) file.");
        return;
      }
      setFile(selected);
      setError(null);
      if (!projectName) {
        setProjectName(selected.name.replace(/\.[^/.]+$/, ""));
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const dropped = e.dataTransfer.files[0];
      if (!dropped.name.toLowerCase().endsWith(".xer")) {
        setError("Invalid file format. Please drop an Oracle Primavera P6 (.xer) file.");
        return;
      }
      setFile(dropped);
      setError(null);
      if (!projectName) {
        setProjectName(dropped.name.replace(/\.[^/.]+$/, ""));
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Please select a .xer schedule file to upload.");
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const res = await api.uploadSnapshot(
        file,
        orgName,
        projectName || undefined,
        isBaseline
      );
      setResult(res);
      await loadSnapshots();
      onSnapshotIngested(res);
    } catch (err: any) {
      setError(err.message || "Failed to ingest schedule snapshot.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteSnapshot = async (id: number, filename: string) => {
    if (!window.confirm(`Are you sure you want to delete Snapshot #${id} ('${filename}')?\nAll activities, relationships, and DCMA check data for this snapshot will be removed.`)) {
      return;
    }

    setDeletingId(id);
    try {
      await api.deleteSnapshot(id);
      await loadSnapshots();
      if (onSnapshotDeleted) {
        onSnapshotDeleted(id);
      }
    } catch (err: any) {
      alert(err.message || "Failed to delete snapshot.");
    } finally {
      setDeletingId(null);
    }
  };

  const handleToggleBaseline = async (id: number, currentBaseline: boolean) => {
    try {
      await api.setSnapshotBaseline(id, !currentBaseline);
      await loadSnapshots();
    } catch (err: any) {
      alert(err.message || "Failed to update baseline status.");
    }
  };

  const resetForm = () => {
    setFile(null);
    setResult(null);
    setError(null);
    setIsUploading(false);
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0, 0, 0, 0.75)",
        backdropFilter: "blur(8px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
        padding: "20px",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "linear-gradient(180deg, #111827 0%, #0b0f19 100%)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          width: "100%",
          maxWidth: "680px",
          overflow: "hidden",
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.7)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: "18px 24px",
            borderBottom: "1px solid var(--border-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "8px",
                background: "rgba(99, 102, 241, 0.15)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#818cf8",
              }}
            >
              <Layers size={20} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: "1.15rem", fontWeight: 700, color: "#fff" }}>
                Schedule Snapshot Hub
              </h3>
              <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Upload new .XER schedules or manage/delete previously ingested snapshots
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
              padding: "6px",
              borderRadius: "6px",
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Tab Switcher */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--border-subtle)", background: "rgba(255, 255, 255, 0.02)" }}>
          <button
            onClick={() => { setActiveTab("upload"); resetForm(); }}
            style={{
              flex: 1,
              padding: "12px",
              background: "transparent",
              border: "none",
              borderBottom: activeTab === "upload" ? "2px solid #818cf8" : "2px solid transparent",
              color: activeTab === "upload" ? "#fff" : "var(--text-muted)",
              fontWeight: activeTab === "upload" ? 600 : 500,
              fontSize: "0.85rem",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px"
            }}
          >
            <Upload size={16} /> Upload New Snapshot
          </button>
          <button
            onClick={() => { setActiveTab("manage"); loadSnapshots(); }}
            style={{
              flex: 1,
              padding: "12px",
              background: "transparent",
              border: "none",
              borderBottom: activeTab === "manage" ? "2px solid #818cf8" : "2px solid transparent",
              color: activeTab === "manage" ? "#fff" : "var(--text-muted)",
              fontWeight: activeTab === "manage" ? 600 : 500,
              fontSize: "0.85rem",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px"
            }}
          >
            <Trash2 size={16} /> Manage & Delete Snapshots ({snapshots.length})
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: "24px" }}>
          {activeTab === "manage" ? (
            /* Snapshot Management / Deletion Tab */
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <div style={{ fontSize: "0.82rem", color: "var(--text-secondary)", marginBottom: "4px" }}>
                Uploaded schedules stored in the database. You can remove misplaced or out-of-order snapshots anytime:
              </div>

              {loadingSnapshots ? (
                <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)" }}>
                  <Loader2 size={24} className="animate-spin" style={{ margin: "0 auto 8px" }} />
                  Loading snapshot records...
                </div>
              ) : snapshots.length === 0 ? (
                <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)", background: "rgba(255, 255, 255, 0.02)", borderRadius: "8px" }}>
                  No snapshots currently in the database. Use the Upload tab to add one.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px", maxHeight: "320px", overflowY: "auto" }}>
                  {snapshots.map((s) => (
                    <div
                      key={s.snapshot_id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        padding: "12px 16px",
                        borderRadius: "var(--radius-md)",
                        background: s.snapshot_id === activeSnapshotId ? "rgba(99, 102, 241, 0.12)" : "rgba(255, 255, 255, 0.02)",
                        border: s.snapshot_id === activeSnapshotId ? "1px solid rgba(99, 102, 241, 0.4)" : "1px solid var(--border-subtle)",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                        <div
                          style={{
                            width: "32px",
                            height: "32px",
                            borderRadius: "6px",
                            background: s.is_baseline ? "rgba(245, 158, 11, 0.15)" : "rgba(56, 189, 248, 0.15)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            color: s.is_baseline ? "var(--accent-amber)" : "#38bdf8",
                            fontWeight: 700,
                            fontSize: "0.8rem",
                          }}
                        >
                          #{s.snapshot_id}
                        </div>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                            <span style={{ fontWeight: 600, color: "#fff", fontSize: "0.88rem" }}>
                              {s.project_name || s.source_filename}
                            </span>
                            {s.is_baseline ? (
                              <span style={{ fontSize: "0.68rem", fontWeight: 700, color: "var(--accent-amber)", background: "rgba(245, 158, 11, 0.15)", padding: "2px 6px", borderRadius: "4px" }}>
                                BASELINE
                              </span>
                            ) : (
                              <span style={{ fontSize: "0.68rem", fontWeight: 600, color: "#38bdf8", background: "rgba(56, 189, 248, 0.15)", padding: "2px 6px", borderRadius: "4px" }}>
                                UPDATE
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: "0.74rem", color: "var(--text-muted)", display: "flex", gap: "8px", marginTop: "2px" }}>
                            <span>Data Date: <strong style={{ color: "var(--text-secondary)" }}>{s.data_date}</strong></span>
                            <span>•</span>
                            <span>{s.activity_count?.toLocaleString()} tasks</span>
                            <span>•</span>
                            <span>{s.relationship_count?.toLocaleString()} links</span>
                          </div>
                        </div>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <button
                          onClick={() => handleToggleBaseline(s.snapshot_id, s.is_baseline)}
                          title={s.is_baseline ? "Unmark as baseline" : "Set as baseline reference"}
                          style={{
                            background: "transparent",
                            border: "1px solid var(--border-subtle)",
                            borderRadius: "6px",
                            padding: "6px 10px",
                            color: s.is_baseline ? "var(--accent-amber)" : "var(--text-muted)",
                            fontSize: "0.75rem",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: "4px",
                          }}
                        >
                          <Shield size={14} />
                          {s.is_baseline ? "Baseline" : "Make Baseline"}
                        </button>

                        <button
                          onClick={() => handleDeleteSnapshot(s.snapshot_id, s.source_filename)}
                          disabled={deletingId === s.snapshot_id}
                          title="Delete snapshot"
                          style={{
                            background: "rgba(244, 63, 94, 0.1)",
                            border: "1px solid rgba(244, 63, 94, 0.3)",
                            borderRadius: "6px",
                            padding: "6px 10px",
                            color: "var(--accent-rose)",
                            fontSize: "0.75rem",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: "4px",
                          }}
                        >
                          {deletingId === s.snapshot_id ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Trash2 size={14} />
                          )}
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "12px" }}>
                <button onClick={onClose} className="button-secondary" style={{ padding: "8px 20px" }}>
                  Close
                </button>
              </div>
            </div>
          ) : result ? (
            /* Success Summary View */
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              <div
                style={{
                  padding: "16px",
                  borderRadius: "var(--radius-md)",
                  background: "rgba(16, 185, 129, 0.1)",
                  border: "1px solid rgba(16, 185, 129, 0.3)",
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                }}
              >
                <CheckCircle size={28} color="#10b981" />
                <div>
                  <div style={{ fontWeight: 700, color: "#10b981", fontSize: "0.95rem" }}>
                    Snapshot Ingested & Verified Successfully!
                  </div>
                  <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                    {result.message}
                  </div>
                </div>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, 1fr)",
                  gap: "12px",
                  background: "rgba(255, 255, 255, 0.02)",
                  padding: "16px",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Snapshot ID</div>
                  <div className="mono-font" style={{ fontSize: "1rem", fontWeight: 700, color: "#818cf8" }}>
                    #{result.snapshot_id}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Data Date</div>
                  <div className="mono-font" style={{ fontSize: "1rem", fontWeight: 700, color: "#38bdf8" }}>
                    {result.data_date}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Activities Loaded</div>
                  <div className="mono-font" style={{ fontSize: "1rem", fontWeight: 700, color: "#fff" }}>
                    {result.activity_count.toLocaleString()} tasks
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Relationships</div>
                  <div className="mono-font" style={{ fontSize: "1rem", fontWeight: 700, color: "#fff" }}>
                    {result.relationship_count.toLocaleString()} links
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Schedule Type</div>
                  <div style={{ fontSize: "0.9rem", fontWeight: 600, color: result.is_baseline ? "var(--accent-amber)" : "var(--accent-emerald)" }}>
                    {result.is_baseline ? "Baseline Reference" : "Progress Update"}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Validation Status</div>
                  <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "#10b981" }}>
                    0 Fatal Errors (Passed)
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", gap: "12px", marginTop: "12px" }}>
                <button
                  onClick={resetForm}
                  className="button-secondary"
                  style={{ flex: 1, padding: "10px" }}
                >
                  Upload Another File
                </button>
                <button
                  onClick={onClose}
                  className="button-primary"
                  style={{ flex: 1, padding: "10px", display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}
                >
                  View Ingested Snapshot <ArrowRight size={16} />
                </button>
              </div>
            </div>
          ) : (
            /* Upload Form View */
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              {/* Drag and Drop Zone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragOver(true);
                }}
                onDragLeave={() => setIsDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                style={{
                  border: `2px dashed ${isDragOver ? "var(--accent-indigo)" : file ? "var(--accent-emerald)" : "rgba(255, 255, 255, 0.15)"}`,
                  borderRadius: "var(--radius-md)",
                  padding: "28px 20px",
                  textAlign: "center",
                  background: isDragOver ? "rgba(99, 102, 241, 0.08)" : file ? "rgba(16, 185, 129, 0.05)" : "rgba(255, 255, 255, 0.02)",
                  cursor: "pointer",
                  transition: "all 0.2s ease",
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xer"
                  onChange={handleFileChange}
                  style={{ display: "none" }}
                />

                {file ? (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" }}>
                    <FileText size={36} color="#10b981" />
                    <div>
                      <div style={{ fontWeight: 600, color: "#fff", fontSize: "0.95rem" }}>{file.name}</div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        {(file.size / (1024 * 1024)).toFixed(2)} MB • Ready for ingestion
                      </div>
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" }}>
                    <Upload size={32} color="var(--text-muted)" />
                    <div>
                      <span style={{ fontWeight: 600, color: "#818cf8" }}>Click to browse</span> or drag and drop your .XER schedule file here
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      Primavera P6 XER exports (up to 50MB)
                    </div>
                  </div>
                )}
              </div>

              {/* Form Fields */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "4px" }}>
                    Project Name
                  </label>
                  <input
                    type="text"
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    placeholder="e.g., PHX3DC1 Substation"
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      background: "rgba(255, 255, 255, 0.04)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "6px",
                      color: "#fff",
                      fontSize: "0.85rem",
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "4px" }}>
                    Organization / Client
                  </label>
                  <input
                    type="text"
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    placeholder="e.g., QTS Data Centers"
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      background: "rgba(255, 255, 255, 0.04)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "6px",
                      color: "#fff",
                      fontSize: "0.85rem",
                    }}
                  />
                </div>
              </div>

              {/* Baseline Toggle */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  background: "rgba(255, 255, 255, 0.02)",
                  padding: "10px 14px",
                  borderRadius: "6px",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <input
                  type="checkbox"
                  id="isBaseline"
                  checked={isBaseline}
                  onChange={(e) => setIsBaseline(e.target.checked)}
                  style={{ width: "16px", height: "16px", cursor: "pointer", accentColor: "#818cf8" }}
                />
                <label htmlFor="isBaseline" style={{ fontSize: "0.82rem", color: "var(--text-secondary)", cursor: "pointer" }}>
                  Flag as <strong style={{ color: "#fff" }}>Target Baseline Schedule</strong> (used for slippage variance checks)
                </label>
              </div>

              {/* Error Box */}
              {error && (
                <div
                  style={{
                    padding: "12px",
                    borderRadius: "6px",
                    background: "rgba(244, 63, 94, 0.1)",
                    border: "1px solid rgba(244, 63, 94, 0.3)",
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    color: "var(--accent-rose)",
                    fontSize: "0.82rem",
                  }}
                >
                  <AlertTriangle size={18} />
                  <span>{error}</span>
                </div>
              )}

              {/* Actions */}
              <div style={{ display: "flex", gap: "12px", marginTop: "8px" }}>
                <button
                  type="button"
                  onClick={onClose}
                  className="button-secondary"
                  disabled={isUploading}
                  style={{ flex: 1, padding: "10px" }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="button-primary"
                  disabled={!file || isUploading}
                  style={{
                    flex: 2,
                    padding: "10px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "8px",
                    opacity: !file || isUploading ? 0.6 : 1,
                  }}
                >
                  {isUploading ? (
                    <>
                      <Loader2 size={18} className="animate-spin" /> Ingesting & Computing CPM...
                    </>
                  ) : (
                    <>
                      <Upload size={18} /> Ingest Snapshot
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
