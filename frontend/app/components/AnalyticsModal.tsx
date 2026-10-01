"use client";

import React, { useEffect, useState } from "react";
import { getAuthHeaders } from "../auth";
import {
  AnalyticsDimensionsResponse,
  AuthUser,
  ComparisonDimension,
  ComparisonMetric,
  ComparisonRequest,
  ComparisonResponse,
  MultiDocSummaryResponse,
} from "../types";
import styles from "./AnalyticsModal.module.css";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface AnalyticsModalProps {
  isOpen: boolean;
  onClose: () => void;
  user: AuthUser | null;
  onViewSource?: (sourceId: string) => void;
}

export default function AnalyticsModal({
  isOpen,
  onClose,
  user,
  onViewSource,
}: AnalyticsModalProps) {
  const [activeTab, setActiveTab] = useState<"compare" | "overview">("compare");

  // Dimension & Metadata
  const [dimensionsData, setDimensionsData] = useState<AnalyticsDimensionsResponse | null>(null);

  // Comparison form state
  const [dimension, setDimension] = useState<ComparisonDimension>("location");
  const [metric, setMetric] = useState<ComparisonMetric>("attendance");
  const [subMetric, setSubMetric] = useState<string>("average");

  // Location comparison inputs
  const [entityA, setEntityA] = useState("Sukhliya");
  const [entityB, setEntityB] = useState("Bicholi");
  const [sharedStartDate, setSharedStartDate] = useState("2026-09-01");
  const [sharedEndDate, setSharedEndDate] = useState("2026-09-30");

  // Period comparison inputs
  const [targetGhar, setTargetGhar] = useState("Sukhliya");
  const [periodAStart, setPeriodAStart] = useState("2026-09-01");
  const [periodAEnd, setPeriodAEnd] = useState("2026-09-30");
  const [periodBStart, setPeriodBStart] = useState("2026-10-01");
  const [periodBEnd, setPeriodBEnd] = useState("2026-10-31");

  // Operation states
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [comparisonResult, setComparisonResult] = useState<ComparisonResponse | null>(null);

  // Overview Tab states
  const [overviewStartDate, setOverviewStartDate] = useState("2026-09-01");
  const [overviewEndDate, setOverviewEndDate] = useState("2026-10-31");
  const [overviewResult, setOverviewResult] = useState<MultiDocSummaryResponse | null>(null);
  const [isLoadingOverview, setIsLoadingOverview] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadDimensions();
      if (activeTab === "overview") {
        loadOverview();
      }
    }
  }, [isOpen, activeTab]);

  if (!isOpen) return null;

  const loadDimensions = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/analytics/dimensions`, {
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setDimensionsData(data);
      }
    } catch {
      // Graceful fallback
    }
  };

  const handleRunComparison = async () => {
    setIsLoading(true);
    setErrorMessage(null);

    const payload: ComparisonRequest = {
      dimension,
      metric,
      sub_metric: subMetric || null,
    };

    if (dimension === "location") {
      payload.entity_a = entityA;
      payload.entity_b = entityB;
      payload.shared_period_start = sharedStartDate || null;
      payload.shared_period_end = sharedEndDate || null;
    } else {
      payload.satsang_ghar = targetGhar || null;
      payload.period_a_start = periodAStart;
      payload.period_a_end = periodAEnd;
      payload.period_b_start = periodBStart;
      payload.period_b_end = periodBEnd;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/analytics/compare`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `Comparison failed with status ${res.status}`);
      }

      const data: ComparisonResponse = await res.json();
      setComparisonResult(data);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to execute comparison.");
    } finally {
      setIsLoading(false);
    }
  };

  const loadOverview = async () => {
    setIsLoadingOverview(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/analytics/multi-document-summary`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          date_start: overviewStartDate || null,
          date_end: overviewEndDate || null,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setOverviewResult(data);
      }
    } catch {
      // Quiet fail
    } finally {
      setIsLoadingOverview(false);
    }
  };

  const knownGhars = dimensionsData?.known_satsang_ghars || [
    "Sukhliya",
    "Bicholi",
    "Pithampur",
    "Indore",
    "Model Town",
  ];

  return (
    <div className={styles.backdrop} onClick={onClose} role="dialog" aria-modal="true">
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className={styles.header}>
          <div className={styles.titleArea}>
            <div className={styles.titleIcon}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="20" x2="18" y2="10" />
                <line x1="12" y1="20" x2="12" y2="4" />
                <line x1="6" y1="20" x2="6" y2="14" />
              </svg>
            </div>
            <div>
              <h3 id="analytics-modal-title" className={styles.title}>
                Multi-Document Analytics & Comparison
              </h3>
              <p className={styles.subtitle}>
                Compare metrics across locations, evaluate period trends, and analyze cross-file aggregates.
              </p>
            </div>
          </div>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close analytics modal"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Tab Navigation */}
        <div className={styles.tabBar} role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "compare"}
            className={`${styles.tabBtn} ${activeTab === "compare" ? styles.activeTabBtn : ""}`}
            onClick={() => setActiveTab("compare")}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M16 3h5v5" />
              <path d="M4 20L21 3" />
              <path d="M21 16v5h-5" />
              <path d="M15 15l6 6" />
              <path d="M4 4l5 5" />
            </svg>
            Comparative Analytics
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "overview"}
            className={`${styles.tabBtn} ${activeTab === "overview" ? styles.activeTabBtn : ""}`}
            onClick={() => setActiveTab("overview")}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
            Multi-Document Overview
          </button>
        </div>

        {/* Modal Content */}
        <div className={styles.content}>
          {activeTab === "compare" ? (
            <div>
              {/* Controls Card */}
              <div className={styles.controlCard}>
                <div className={styles.formGrid}>
                  {/* Dimension Selector */}
                  <div className={styles.formGroup}>
                    <label className={styles.label}>Comparison Dimension</label>
                    <select
                      id="dimension-select"
                      className={styles.select}
                      value={dimension}
                      onChange={(e) => setDimension(e.target.value as ComparisonDimension)}
                    >
                      <option value="location">Centre vs. Centre (Same Period)</option>
                      <option value="period">Period vs. Period (Month-over-Month)</option>
                    </select>
                  </div>

                  {/* Metric Domain Selector */}
                  <div className={styles.formGroup}>
                    <label className={styles.label}>Metric Domain</label>
                    <select
                      id="metric-select"
                      className={styles.select}
                      value={metric}
                      onChange={(e) => {
                        const m = e.target.value as ComparisonMetric;
                        setMetric(m);
                        if (m === "attendance") setSubMetric("average");
                        else if (m === "vehicle_wheel") setSubMetric("all");
                        else if (m === "assignment") setSubMetric("all");
                      }}
                    >
                      <option value="attendance">Attendance Records</option>
                      <option value="vehicle_wheel">Vehicle Logs (Transportation)</option>
                      <option value="assignment">Duty Rosters (Sewadar Duties)</option>
                    </select>
                  </div>

                  {/* Sub-Metric / Filter */}
                  <div className={styles.formGroup}>
                    <label className={styles.label}>Calculation / Filter</label>
                    {metric === "attendance" ? (
                      <select
                        className={styles.select}
                        value={subMetric}
                        onChange={(e) => setSubMetric(e.target.value)}
                      >
                        <option value="average">Average Attendance / Session</option>
                        <option value="total">Total Attendance Sum</option>
                      </select>
                    ) : metric === "vehicle_wheel" ? (
                      <select
                        className={styles.select}
                        value={subMetric}
                        onChange={(e) => setSubMetric(e.target.value)}
                      >
                        <option value="all">All Vehicles (Total)</option>
                        <option value="2_wheeler">2-Wheeler Only</option>
                        <option value="4_wheeler">4-Wheeler Only</option>
                      </select>
                    ) : (
                      <select
                        className={styles.select}
                        value={subMetric}
                        onChange={(e) => setSubMetric(e.target.value)}
                      >
                        <option value="all">All Duty Roles</option>
                        <option value="SK">Satsang Karta (SK)</option>
                        <option value="SR">Satsang Reader (SR)</option>
                      </select>
                    )}
                  </div>
                </div>

                {/* Dimension-specific input row */}
                {dimension === "location" ? (
                  <div className={styles.formGrid}>
                    <div className={styles.formGroup}>
                      <label className={styles.label}>Centre A (Baseline)</label>
                      <select
                        id="centre-a-select"
                        className={styles.select}
                        value={entityA}
                        onChange={(e) => setEntityA(e.target.value)}
                      >
                        {knownGhars.map((g) => (
                          <option key={g} value={g}>{g}</option>
                        ))}
                      </select>
                    </div>

                    <div className={styles.formGroup}>
                      <label className={styles.label}>Centre B (Comparison)</label>
                      <select
                        id="centre-b-select"
                        className={styles.select}
                        value={entityB}
                        onChange={(e) => setEntityB(e.target.value)}
                      >
                        {knownGhars.map((g) => (
                          <option key={g} value={g}>{g}</option>
                        ))}
                      </select>
                    </div>

                    <div className={styles.formGroup}>
                      <label className={styles.label}>Period Start Date</label>
                      <input
                        type="date"
                        className={styles.input}
                        value={sharedStartDate}
                        onChange={(e) => setSharedStartDate(e.target.value)}
                      />
                    </div>

                    <div className={styles.formGroup}>
                      <label className={styles.label}>Period End Date</label>
                      <input
                        type="date"
                        className={styles.input}
                        value={sharedEndDate}
                        onChange={(e) => setSharedEndDate(e.target.value)}
                      />
                    </div>
                  </div>
                ) : (
                  <div className={styles.formGrid}>
                    <div className={styles.formGroup}>
                      <label className={styles.label}>Target Centre</label>
                      <select
                        id="period-centre-select"
                        className={styles.select}
                        value={targetGhar}
                        onChange={(e) => setTargetGhar(e.target.value)}
                      >
                        <option value="">All Centres Combined</option>
                        {knownGhars.map((g) => (
                          <option key={g} value={g}>{g}</option>
                        ))}
                      </select>
                    </div>

                    <div className={styles.formGroup}>
                      <label className={styles.label}>Period A (Baseline)</label>
                      <div style={{ display: "flex", gap: "6px" }}>
                        <input
                          type="date"
                          className={styles.input}
                          value={periodAStart}
                          onChange={(e) => setPeriodAStart(e.target.value)}
                        />
                        <input
                          type="date"
                          className={styles.input}
                          value={periodAEnd}
                          onChange={(e) => setPeriodAEnd(e.target.value)}
                        />
                      </div>
                    </div>

                    <div className={styles.formGroup}>
                      <label className={styles.label}>Period B (Comparison)</label>
                      <div style={{ display: "flex", gap: "6px" }}>
                        <input
                          type="date"
                          className={styles.input}
                          value={periodBStart}
                          onChange={(e) => setPeriodBStart(e.target.value)}
                        />
                        <input
                          type="date"
                          className={styles.input}
                          value={periodBEnd}
                          onChange={(e) => setPeriodBEnd(e.target.value)}
                        />
                      </div>
                    </div>
                  </div>
                )}

                <div className={styles.actionRow}>
                  <span style={{ fontSize: "0.82rem", color: "#64748b" }}>
                    Deterministic relational calculations computed across verified document records.
                  </span>
                  <button
                    id="run-comparison-btn"
                    type="button"
                    className={styles.primaryBtn}
                    onClick={handleRunComparison}
                    disabled={isLoading}
                  >
                    {isLoading ? "Calculating..." : "Run Comparison"}
                  </button>
                </div>
              </div>

              {/* Error Notice */}
              {errorMessage && (
                <div className={styles.errorBanner} role="alert">
                  {errorMessage}
                </div>
              )}

              {/* Comparison Results Card */}
              {comparisonResult && (
                <div className={styles.resultsSection}>
                  {/* Warnings if any */}
                  {comparisonResult.warnings && comparisonResult.warnings.length > 0 && (
                    <div className={styles.warningBanner}>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                        <line x1="12" y1="9" x2="12" y2="13" />
                        <line x1="12" y1="17" x2="12.01" y2="17" />
                      </svg>
                      <span>{comparisonResult.warnings[0]}</span>
                    </div>
                  )}

                  {/* Summary Banner */}
                  <div className={styles.summaryBanner}>
                    {comparisonResult.summary_sentence}
                  </div>

                  {/* Side-by-side KPI Grid */}
                  <div className={styles.comparisonCardsGrid}>
                    {/* Entity A */}
                    <div className={styles.sideCard}>
                      <div className={styles.sideCardHeader}>
                        <span className={styles.sideEntityName}>
                          {comparisonResult.entity_a.label}
                        </span>
                        <span className={styles.badgeSessions}>
                          {comparisonResult.entity_a.record_count} record(s)
                        </span>
                      </div>
                      <div className={styles.sideMetricMain}>
                        {comparisonResult.entity_a.primary_value}
                        <span className={styles.sideMetricUnit}>{comparisonResult.unit}</span>
                      </div>
                      {comparisonResult.entity_a.secondary_value !== null && comparisonResult.entity_a.secondary_value !== undefined && (
                        <div className={styles.sideSecondaryMetric}>
                          Total Attendance: <strong>{comparisonResult.entity_a.secondary_value}</strong>
                        </div>
                      )}
                      <div className={styles.sideDocList}>
                        Contributing file(s):{" "}
                        <strong>{comparisonResult.entity_a.document_names.join(", ") || "None"}</strong>
                      </div>
                    </div>

                    {/* Delta Badge */}
                    <div className={styles.deltaCard}>
                      <div className={styles.deltaTitle}>Delta (B - A)</div>
                      <div
                        className={`${styles.deltaValue} ${
                          comparisonResult.delta > 0
                            ? styles.deltaPositive
                            : comparisonResult.delta < 0
                            ? styles.deltaNegative
                            : styles.deltaNeutral
                        }`}
                      >
                        {comparisonResult.delta > 0 ? `+${comparisonResult.delta}` : comparisonResult.delta}
                      </div>
                      {comparisonResult.percentage_change !== null && comparisonResult.percentage_change !== undefined && (
                        <div
                          className={`${styles.pctBadge} ${
                            comparisonResult.percentage_change > 0
                              ? styles.pctPositive
                              : comparisonResult.percentage_change < 0
                              ? styles.pctNegative
                              : styles.pctNeutral
                          }`}
                        >
                          {comparisonResult.percentage_change > 0
                            ? `+${comparisonResult.percentage_change}%`
                            : `${comparisonResult.percentage_change}%`}
                        </div>
                      )}
                    </div>

                    {/* Entity B */}
                    <div className={styles.sideCard}>
                      <div className={styles.sideCardHeader}>
                        <span className={styles.sideEntityName}>
                          {comparisonResult.entity_b.label}
                        </span>
                        <span className={styles.badgeSessions}>
                          {comparisonResult.entity_b.record_count} record(s)
                        </span>
                      </div>
                      <div className={styles.sideMetricMain}>
                        {comparisonResult.entity_b.primary_value}
                        <span className={styles.sideMetricUnit}>{comparisonResult.unit}</span>
                      </div>
                      {comparisonResult.entity_b.secondary_value !== null && comparisonResult.entity_b.secondary_value !== undefined && (
                        <div className={styles.sideSecondaryMetric}>
                          Total Attendance: <strong>{comparisonResult.entity_b.secondary_value}</strong>
                        </div>
                      )}
                      <div className={styles.sideDocList}>
                        Contributing file(s):{" "}
                        <strong>{comparisonResult.entity_b.document_names.join(", ") || "None"}</strong>
                      </div>
                    </div>
                  </div>

                  {/* Supporting Multi-Document Provenance Table */}
                  {comparisonResult.source_references && comparisonResult.source_references.length > 0 && (
                    <div className={styles.detailSection}>
                      <div className={styles.detailTitle}>
                        Cross-Document Provenance Evidence ({comparisonResult.source_references.length} references)
                      </div>
                      <div className={styles.tableContainer}>
                        <table className={styles.table}>
                          <thead>
                            <tr>
                              <th>Document Name</th>
                              <th>Type</th>
                              <th>Location / Sheet</th>
                              <th>Row / Page</th>
                              <th>Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {comparisonResult.source_references.map((sr, idx) => (
                              <tr key={sr.id || idx}>
                                <td>
                                  <strong>{sr.document_name || "Unknown Document"}</strong>
                                  {sr.document_version ? ` (v${sr.document_version})` : ""}
                                </td>
                                <td>{sr.document_type || "Sheet"}</td>
                                <td>{sr.sheet_name || "—"}</td>
                                <td>{sr.row_number ? `Row ${sr.row_number}` : sr.page_number ? `Page ${sr.page_number}` : "—"}</td>
                                <td>
                                  {sr.id && onViewSource && (
                                    <button
                                      type="button"
                                      className={styles.inspectBtn}
                                      onClick={() => onViewSource(sr.id!)}
                                    >
                                      Inspect Source
                                    </button>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            /* Multi-Document Overview Tab */
            <div>
              {/* Filter controls */}
              <div className={styles.controlCard}>
                <div style={{ display: "flex", gap: "16px", alignItems: "flex-end" }}>
                  <div className={styles.formGroup} style={{ flex: 1 }}>
                    <label className={styles.label}>Overview Period Start</label>
                    <input
                      type="date"
                      className={styles.input}
                      value={overviewStartDate}
                      onChange={(e) => setOverviewStartDate(e.target.value)}
                    />
                  </div>
                  <div className={styles.formGroup} style={{ flex: 1 }}>
                    <label className={styles.label}>Overview Period End</label>
                    <input
                      type="date"
                      className={styles.input}
                      value={overviewEndDate}
                      onChange={(e) => setOverviewEndDate(e.target.value)}
                    />
                  </div>
                  <button
                    type="button"
                    className={styles.primaryBtn}
                    onClick={loadOverview}
                    disabled={isLoadingOverview}
                  >
                    {isLoadingOverview ? "Loading..." : "Update Overview"}
                  </button>
                </div>
              </div>

              {overviewResult && (
                <div>
                  <div className={styles.overviewStatsGrid}>
                    <div className={styles.statCard}>
                      <div className={styles.statLabel}>Documents Analyzed</div>
                      <div className={styles.statNumber}>{overviewResult.total_documents}</div>
                    </div>
                    <div className={styles.statCard}>
                      <div className={styles.statLabel}>Total Attendance</div>
                      <div className={styles.statNumber}>{overviewResult.total_attendance}</div>
                    </div>
                    <div className={styles.statCard}>
                      <div className={styles.statLabel}>Average / Session</div>
                      <div className={styles.statNumber}>{overviewResult.average_attendance}</div>
                    </div>
                    <div className={styles.statCard}>
                      <div className={styles.statLabel}>Duty Rosters</div>
                      <div className={styles.statNumber}>{overviewResult.total_assignments}</div>
                    </div>
                    <div className={styles.statCard}>
                      <div className={styles.statLabel}>Vehicles Logged</div>
                      <div className={styles.statNumber}>{overviewResult.total_vehicles}</div>
                    </div>
                  </div>

                  <div className={styles.detailTitle}>
                    Contributing Files Breakdown ({overviewResult.per_document_breakdown.length})
                  </div>
                  <div className={styles.tableContainer}>
                    <table className={styles.table}>
                      <thead>
                        <tr>
                          <th>Document Filename</th>
                          <th>Status</th>
                          <th>Attendance Records</th>
                          <th>Duty Assignments</th>
                          <th>Vehicle Logs</th>
                        </tr>
                      </thead>
                      <tbody>
                        {overviewResult.per_document_breakdown.map((doc) => (
                          <tr key={doc.document_id}>
                            <td><strong>{doc.filename}</strong></td>
                            <td>
                              <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "#16a34a" }}>
                                {doc.status}
                              </span>
                            </td>
                            <td>{doc.attendance_count}</td>
                            <td>{doc.assignment_count}</td>
                            <td>{doc.vehicle_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
