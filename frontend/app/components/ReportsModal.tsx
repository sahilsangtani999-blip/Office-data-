"use client";

import React, { useEffect, useState } from "react";
import { getAuthHeaders } from "../auth";
import { AuthUser, ReportDetail, ReportItem, ReportType } from "../types";
import styles from "./ReportsModal.module.css";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface ReportsModalProps {
  isOpen: boolean;
  onClose: () => void;
  user: AuthUser | null;
}

export default function ReportsModal({ isOpen, onClose, user }: ReportsModalProps) {
  const [activeTab, setActiveTab] = useState<"generate" | "archive">("generate");

  // Form states
  const [reportType, setReportType] = useState<ReportType>("monthly");
  const [reportName, setReportName] = useState("");
  const [startDate, setStartDate] = useState("2026-09-01");
  const [endDate, setEndDate] = useState("2026-09-30");
  const [satsangGhar, setSatsangGhar] = useState("");
  const [includeXlsx, setIncludeXlsx] = useState(true);
  const [includeCsv, setIncludeCsv] = useState(true);

  // Operation states
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastGenerated, setLastGenerated] = useState<ReportDetail | null>(null);

  // Archive states
  const [archiveList, setArchiveList] = useState<ReportItem[]>([]);
  const [isLoadingArchive, setIsLoadingArchive] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const canGenerate = user?.role === "admin" || user?.role === "reviewer";

  useEffect(() => {
    if (isOpen) {
      loadArchive();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const loadArchive = async () => {
    setIsLoadingArchive(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/reports`, {
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setArchiveList(data.reports || []);
      }
    } catch {
      // Quiet fail in background
    } finally {
      setIsLoadingArchive(false);
    }
  };

  const handleDownload = async (reportId: string, format: "xlsx" | "csv", defaultName?: string) => {
    setDownloadingId(`${reportId}-${format}`);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/reports/${reportId}/download?format=${format}`, {
        headers: getAuthHeaders(),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `Download failed with status ${res.status}`);
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = defaultName ? `${defaultName}.${format}` : `office_report_${reportId.slice(0, 8)}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(`Could not download file: ${err.message}`);
    } finally {
      setDownloadingId(null);
    }
  };

  const handleGenerateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canGenerate) return;

    const formats: string[] = [];
    if (includeXlsx) formats.push("xlsx");
    if (includeCsv) formats.push("csv");

    if (formats.length === 0) {
      setErrorMessage("Please select at least one export format (Excel or CSV).");
      return;
    }

    setIsGenerating(true);
    setErrorMessage(null);
    setLastGenerated(null);

    try {
      const payload = {
        report_type: reportType,
        name: reportName.trim() || undefined,
        reporting_period_start: startDate || undefined,
        reporting_period_end: endDate || undefined,
        formats: formats,
      };

      const res = await fetch(`${API_BASE_URL}/api/v1/reports/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `Report generation failed (${res.status})`);
      }

      const reportDetail: ReportDetail = await res.json();
      setLastGenerated(reportDetail);
      loadArchive();
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to generate office report.");
    } finally {
      setIsGenerating(false);
    }
  };

  const formatPeriod = (start?: string | null, end?: string | null) => {
    if (!start && !end) return "All time";
    if (start && end) return `${start} to ${end}`;
    return start || end || "All time";
  };

  return (
    <div className={styles.overlay} onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="reports-modal-title">
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className={styles.header}>
          <div className={styles.titleArea}>
            <h2 id="reports-modal-title" className={styles.title}>
              Office Reports & Data Exports
            </h2>
            <p className={styles.subtitle}>
              Generate executive summaries, attendance rosters, and vehicle logs in formatted Excel or CSV.
            </p>
          </div>
          <button
            type="button"
            className={styles.closeButton}
            onClick={onClose}
            aria-label="Close Reports Modal"
          >
            &times;
          </button>
        </div>

        {/* Tab Bar */}
        <div className={styles.tabBar}>
          <button
            type="button"
            className={`${styles.tabButton} ${activeTab === "generate" ? styles.tabButtonActive : ""}`}
            onClick={() => setActiveTab("generate")}
          >
            Generate Report
          </button>
          <button
            type="button"
            className={`${styles.tabButton} ${activeTab === "archive" ? styles.tabButtonActive : ""}`}
            onClick={() => {
              setActiveTab("archive");
              loadArchive();
            }}
          >
            Report Archive
            <span className={styles.tabBadge}>{archiveList.length}</span>
          </button>
        </div>

        {/* Modal Content */}
        <div className={styles.body}>
          {errorMessage && (
            <div className={styles.errorBanner} role="alert">
              <strong>Error:</strong> {errorMessage}
            </div>
          )}

          {activeTab === "generate" && (
            <div>
              {!canGenerate && (
                <div className={styles.permissionNotice}>
                  <span className={styles.noticeIcon} aria-hidden="true">&#9432;</span>
                  <div>
                    <strong>View-Only Access:</strong> Report generation requires <em>Reviewer</em> or <em>Admin</em> permissions. You can inspect and download existing reports in the <strong>Report Archive</strong> tab, or ask an administrator to generate custom reports.
                  </div>
                </div>
              )}

              <form onSubmit={handleGenerateSubmit} className={styles.form}>
                <div className={styles.formGroup}>
                  <label className={styles.label} htmlFor="report-type-select">
                    Report Type
                  </label>
                  <select
                    id="report-type-select"
                    className={styles.select}
                    value={reportType}
                    onChange={(e) => setReportType(e.target.value as ReportType)}
                    disabled={!canGenerate || isGenerating}
                  >
                    <option value="monthly">Monthly Summary Report (Attendance, Duties & Vehicles)</option>
                    <option value="attendance_summary">Attendance Summary Report (Dates, Counts & Averages)</option>
                    <option value="duty_summary">Duty Rosters & Sewadar Summary Report</option>
                    <option value="vehicle_report">Transportation & Vehicle Movement Report</option>
                  </select>
                  <span className={styles.helperText}>
                    {reportType === "monthly" && "Comprehensive multi-sheet report consolidating attendance figures, duty assignments, and vehicle records."}
                    {reportType === "attendance_summary" && "Detailed breakdown of male, female, children, and total attendance across centres."}
                    {reportType === "duty_summary" && "Roster records of seva assignments, departments, shifts, and sewadars."}
                    {reportType === "vehicle_report" && "Gate pass and transportation log of inward/outward vehicles."}
                  </span>
                </div>

                <div className={styles.formGroup}>
                  <label className={styles.label} htmlFor="report-name-input">
                    Custom Report Title (Optional)
                  </label>
                  <input
                    id="report-name-input"
                    type="text"
                    className={styles.input}
                    placeholder="e.g. Indore Centre - September 2026 General Report"
                    value={reportName}
                    onChange={(e) => setReportName(e.target.value)}
                    disabled={!canGenerate || isGenerating}
                  />
                </div>

                <div className={styles.formGrid}>
                  <div className={styles.formGroup}>
                    <label className={styles.label} htmlFor="report-start-date">
                      Period Start Date
                    </label>
                    <input
                      id="report-start-date"
                      type="date"
                      className={styles.input}
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      disabled={!canGenerate || isGenerating}
                    />
                  </div>

                  <div className={styles.formGroup}>
                    <label className={styles.label} htmlFor="report-end-date">
                      Period End Date
                    </label>
                    <input
                      id="report-end-date"
                      type="date"
                      className={styles.input}
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      disabled={!canGenerate || isGenerating}
                    />
                  </div>
                </div>

                <div className={styles.formGroup}>
                  <label className={styles.label}>Export Formats to Generate</label>
                  <div className={styles.checkboxGroup}>
                    <label className={styles.checkboxLabel}>
                      <input
                        type="checkbox"
                        checked={includeXlsx}
                        onChange={(e) => setIncludeXlsx(e.target.checked)}
                        disabled={!canGenerate || isGenerating}
                      />
                      Formatted Excel (.xlsx)
                    </label>
                    <label className={styles.checkboxLabel}>
                      <input
                        type="checkbox"
                        checked={includeCsv}
                        onChange={(e) => setIncludeCsv(e.target.checked)}
                        disabled={!canGenerate || isGenerating}
                      />
                      Comma-Separated Values (.csv)
                    </label>
                  </div>
                </div>

                {canGenerate && (
                  <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                    <button
                      type="submit"
                      className={styles.generateBtn}
                      disabled={isGenerating}
                    >
                      {isGenerating ? (
                        <>
                          <span>Generating Report...</span>
                        </>
                      ) : (
                        <>
                          <span>Compile & Generate Report</span>
                        </>
                      )}
                    </button>
                  </div>
                )}
              </form>

              {/* Generated Result Card */}
              {lastGenerated && (
                <div className={styles.successCard}>
                  <div className={styles.successHeader}>
                    <h3 className={styles.successTitle}>
                      <span>&#10003;</span> {lastGenerated.name}
                    </h3>
                    <span className={styles.badgeStatus}>Generated Successfully</span>
                  </div>

                  {(lastGenerated.summary_kpis || (lastGenerated as any).summary_metrics) && (
                    <div className={styles.kpiGrid}>
                      <div className={styles.kpiCard}>
                        <div className={styles.kpiValue}>
                          {lastGenerated.summary_kpis?.total_attendance ?? (lastGenerated as any).summary_metrics?.total_attendance ?? 0}
                        </div>
                        <div className={styles.kpiLabel}>Total Attendance</div>
                      </div>
                      <div className={styles.kpiCard}>
                        <div className={styles.kpiValue}>
                          {lastGenerated.summary_kpis?.avg_attendance ?? (lastGenerated as any).summary_metrics?.avg_attendance ?? (lastGenerated as any).summary_metrics?.average_attendance ?? 0}
                        </div>
                        <div className={styles.kpiLabel}>Avg / Session</div>
                      </div>
                      <div className={styles.kpiCard}>
                        <div className={styles.kpiValue}>
                          {lastGenerated.summary_kpis?.total_duty_assignments ?? (lastGenerated as any).summary_metrics?.total_duty_assignments ?? (lastGenerated as any).summary_metrics?.total_duties_assigned ?? 0}
                        </div>
                        <div className={styles.kpiLabel}>Duty Rosters</div>
                      </div>
                      <div className={styles.kpiCard}>
                        <div className={styles.kpiValue}>
                          {lastGenerated.summary_kpis?.total_vehicles ?? (lastGenerated as any).summary_metrics?.total_vehicles ?? (lastGenerated as any).summary_metrics?.total_vehicles_recorded ?? 0}
                        </div>
                        <div className={styles.kpiLabel}>Vehicles Logged</div>
                      </div>
                    </div>
                  )}

                  <div className={styles.exportButtons}>
                    <button
                      type="button"
                      className={styles.downloadXlsxBtn}
                      onClick={() => handleDownload(lastGenerated.id, "xlsx", lastGenerated.name)}
                      disabled={downloadingId === `${lastGenerated.id}-xlsx`}
                    >
                      {downloadingId === `${lastGenerated.id}-xlsx` ? "Downloading..." : "Download Excel (.xlsx)"}
                    </button>
                    <button
                      type="button"
                      className={styles.downloadCsvBtn}
                      onClick={() => handleDownload(lastGenerated.id, "csv", lastGenerated.name)}
                      disabled={downloadingId === `${lastGenerated.id}-csv`}
                    >
                      {downloadingId === `${lastGenerated.id}-csv` ? "Downloading..." : "Download CSV (.csv)"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "archive" && (
            <div>
              {isLoadingArchive ? (
                <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)" }}>
                  Loading archived reports...
                </div>
              ) : archiveList.length === 0 ? (
                <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-secondary)" }}>
                  <p style={{ fontWeight: 600, margin: "0 0 6px 0" }}>No reports generated yet</p>
                  <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", margin: 0 }}>
                    Use the "Generate Report" tab to compile an official office report.
                  </p>
                </div>
              ) : (
                <div className={styles.archiveTableWrapper}>
                  <table className={styles.archiveTable}>
                    <thead>
                      <tr>
                        <th>Report Name</th>
                        <th>Type</th>
                        <th>Period</th>
                        <th>Created By</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {archiveList.map((item) => (
                        <tr key={item.id} className={styles.archiveRow}>
                          <td>
                            <strong style={{ display: "block", color: "var(--text-primary)" }}>{item.name}</strong>
                            <small style={{ color: "var(--text-muted)" }}>
                              {item.created_at ? new Date(item.created_at).toLocaleDateString() : ""}
                            </small>
                          </td>
                          <td>
                            <span className={styles.badgeType}>{item.report_type}</span>
                          </td>
                          <td style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                            {formatPeriod(item.reporting_period_start, item.reporting_period_end)}
                          </td>
                          <td style={{ fontSize: "0.82rem" }}>
                            {item.created_by}
                          </td>
                          <td>
                            <div className={styles.actionLinks}>
                              <button
                                type="button"
                                className={styles.tableLink}
                                onClick={() => handleDownload(item.id, "xlsx", item.name)}
                                disabled={downloadingId === `${item.id}-xlsx`}
                              >
                                {downloadingId === `${item.id}-xlsx` ? "..." : "XLSX"}
                              </button>
                              <button
                                type="button"
                                className={styles.tableLink}
                                onClick={() => handleDownload(item.id, "csv", item.name)}
                                disabled={downloadingId === `${item.id}-csv`}
                              >
                                {downloadingId === `${item.id}-csv` ? "..." : "CSV"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className={styles.footer}>
          <button type="button" className={styles.cancelBtn} onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
