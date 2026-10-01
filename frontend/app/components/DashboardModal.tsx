"use client";

import React, { useEffect, useState } from "react";
import { getAuthHeaders } from "../auth";
import {
  AnalyticsDimensionsResponse,
  ExecutiveDashboardResponse,
  OperationalAnomaly,
  TrendAnalysisResponse,
} from "../types";
import styles from "./DashboardModal.module.css";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface DashboardModalProps {
  isOpen: boolean;
  onClose: () => void;
  user?: any;
  initialTab?: "overview" | "trends" | "anomalies";
}

export default function DashboardModal({
  isOpen,
  onClose,
  user,
  initialTab = "overview",
}: DashboardModalProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "trends" | "anomalies">(initialTab);
  const [loading, setLoading] = useState<boolean>(true);
  const [dashboardData, setDashboardData] = useState<ExecutiveDashboardResponse | null>(null);
  const [trendData, setTrendData] = useState<TrendAnalysisResponse | null>(null);
  const [anomalies, setAnomalies] = useState<OperationalAnomaly[]>([]);
  const [knownGhars, setKnownGhars] = useState<string[]>([]);

  // Filter controls for Trends tab
  const [selectedCenter, setSelectedCenter] = useState<string>("");
  const [selectedMetric, setSelectedMetric] = useState<string>("attendance");
  const [selectedInterval, setSelectedInterval] = useState<string>("month");
  const [showMovingAverage, setShowMovingAverage] = useState<boolean>(true);

  useEffect(() => {
    if (!isOpen) return;

    setLoading(true);

    // Fetch dashboard, initial trends, anomalies, and dimensions in parallel
    const p1 = fetch(`${API_BASE_URL}/api/v1/analytics/dashboard`, { headers: getAuthHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);

    const trendUrl = new URL(`${API_BASE_URL}/api/v1/analytics/trends`);
    trendUrl.searchParams.set("metric", selectedMetric);
    trendUrl.searchParams.set("interval", selectedInterval);
    if (selectedCenter) {
      trendUrl.searchParams.set("center", selectedCenter);
    }
    const p2 = fetch(trendUrl.toString(), { headers: getAuthHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);

    const p3 = fetch(`${API_BASE_URL}/api/v1/analytics/anomalies?threshold=25.0`, { headers: getAuthHeaders() })
      .then((r) => (r.ok ? r.json() : []))
      .catch(() => []);

    const p4 = fetch(`${API_BASE_URL}/api/v1/analytics/dimensions`, { headers: getAuthHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);

    Promise.all([p1, p2, p3, p4]).then(([dash, tr, anoms, dims]) => {
      setDashboardData(dash);
      setTrendData(tr);
      setAnomalies(anoms || []);
      if (dims && dims.known_satsang_ghars) {
        setKnownGhars(dims.known_satsang_ghars);
      }
      setLoading(false);
    });
  }, [isOpen]);

  // Refetch trends when filter controls change
  const handleFilterChange = (center: string, metric: string, interval: string) => {
    setSelectedCenter(center);
    setSelectedMetric(metric);
    setSelectedInterval(interval);

    const url = new URL(`${API_BASE_URL}/api/v1/analytics/trends`);
    url.searchParams.set("metric", metric);
    url.searchParams.set("interval", interval);
    if (center) {
      url.searchParams.set("center", center);
    }

    fetch(url.toString(), { headers: getAuthHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setTrendData(data);
      })
      .catch(() => {});
  };

  if (!isOpen) return null;

  return (
    <div className={styles.overlay} onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="dashboard-modal-title">
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerTitleGroup}>
            <div className={styles.headerIcon}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 20V10" />
                <path d="M12 20V4" />
                <path d="M6 20v-6" />
              </svg>
            </div>
            <div>
              <h2 id="dashboard-modal-title" className={styles.title}>
                Executive Operational Dashboard & Visual Analytics
              </h2>
              <div className={styles.subtitle}>
                Longitudinal trend trajectories, system KPIs, and operational variance analysis
              </div>
            </div>
          </div>
          <button className={styles.closeButton} onClick={onClose} aria-label="Close modal">
            &times;
          </button>
        </div>

        {/* Tab Navigation */}
        <div className={styles.tabBar} role="tablist">
          <button
            id="tab-overview"
            role="tab"
            aria-selected={activeTab === "overview"}
            className={`${styles.tabBtn} ${activeTab === "overview" ? styles.tabBtnActive : ""}`}
            onClick={() => setActiveTab("overview")}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </svg>
            Executive Overview
          </button>
          <button
            id="tab-trends"
            role="tab"
            aria-selected={activeTab === "trends"}
            className={`${styles.tabBtn} ${activeTab === "trends" ? styles.tabBtnActive : ""}`}
            onClick={() => setActiveTab("trends")}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
            Trend Trajectories
          </button>
          <button
            id="tab-anomalies"
            role="tab"
            aria-selected={activeTab === "anomalies"}
            className={`${styles.tabBtn} ${activeTab === "anomalies" ? styles.tabBtnActive : ""}`}
            onClick={() => setActiveTab("anomalies")}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            Operational Anomalies ({anomalies.length})
          </button>
        </div>

        {/* Modal Body */}
        <div className={styles.content}>
          {loading ? (
            <div className={styles.loadingSpinner}>
              <div className={styles.spinner} />
              <span>Compiling operational analytics and verified time-series data...</span>
            </div>
          ) : (
            <>
              {/* TAB 1: EXECUTIVE OVERVIEW */}
              {activeTab === "overview" && dashboardData && (
                <div>
                  {/* KPI Grid */}
                  <div className={styles.kpiGrid}>
                    <div className={styles.kpiCard}>
                      <span className={styles.kpiLabel}>Total Attendance</span>
                      <span className={styles.kpiValue}>
                        {dashboardData.summary_kpis.total_attendance.toLocaleString()}
                      </span>
                      <span className={styles.kpiSub}>
                        across {dashboardData.summary_kpis.total_meetings} meetings
                      </span>
                    </div>
                    <div className={styles.kpiCard}>
                      <span className={styles.kpiLabel}>Avg Session Attendance</span>
                      <span className={styles.kpiValue}>
                        {dashboardData.summary_kpis.average_session_attendance}
                      </span>
                      <span className={styles.kpiSub}>attendees per satsang</span>
                    </div>
                    <div className={styles.kpiCard}>
                      <span className={styles.kpiLabel}>Active Satsang Ghars</span>
                      <span className={styles.kpiValue}>
                        {dashboardData.summary_kpis.active_centers_count}
                      </span>
                      <span className={styles.kpiSub}>with verified records</span>
                    </div>
                    <div className={styles.kpiCard}>
                      <span className={styles.kpiLabel}>Duty Assignments</span>
                      <span className={styles.kpiValue}>
                        {dashboardData.summary_kpis.total_duty_assignments}
                      </span>
                      <span className={styles.kpiSub}>
                        {dashboardData.summary_kpis.unique_sevadars} unique sevadars
                      </span>
                    </div>
                    <div className={styles.kpiCard}>
                      <span className={styles.kpiLabel}>Vehicles Logged</span>
                      <span className={styles.kpiValue}>
                        {dashboardData.summary_kpis.total_vehicles_recorded.toLocaleString()}
                      </span>
                      <span className={styles.kpiSub}>total vehicle counts</span>
                    </div>
                  </div>

                  {/* Center Rankings Leaderboard */}
                  <div className={styles.sectionCard}>
                    <div className={styles.sectionHeader}>
                      <h3 className={styles.sectionTitle}>Satsang Ghar Volume & Attendance Leaderboard</h3>
                    </div>
                    <div className={styles.tableWrapper}>
                      <table className={styles.table}>
                        <thead>
                          <tr>
                            <th>Satsang Ghar</th>
                            <th>Sessions</th>
                            <th>Total Attendance</th>
                            <th>Average / Meeting</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dashboardData.center_rankings.map((c, i) => (
                            <tr key={i}>
                              <td style={{ fontWeight: 600 }}>{c.satsang_ghar}</td>
                              <td>{c.sessions}</td>
                              <td>{c.total_attendance.toLocaleString()}</td>
                              <td style={{ fontWeight: 700, color: "#941b1b" }}>
                                {c.average_attendance}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Operational Distribution Cards */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                    <div className={styles.sectionCard}>
                      <h3 className={styles.sectionTitle} style={{ marginBottom: "1rem" }}>
                        Vehicle Modal Split
                      </h3>
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                        {Object.entries(dashboardData.vehicle_breakdown).map(([vtype, count], i) => (
                          <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "0.4rem 0", borderBottom: "1px solid #f1f5f9" }}>
                            <span style={{ fontWeight: 500 }}>{vtype}</span>
                            <span style={{ fontWeight: 700, color: "#0f172a" }}>{count.toLocaleString()}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className={styles.sectionCard}>
                      <h3 className={styles.sectionTitle} style={{ marginBottom: "1rem" }}>
                        Sewa Role Distribution
                      </h3>
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                        {Object.entries(dashboardData.role_breakdown).map(([rcode, count], i) => (
                          <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "0.4rem 0", borderBottom: "1px solid #f1f5f9" }}>
                            <span style={{ fontWeight: 500 }}>{rcode}</span>
                            <span style={{ fontWeight: 700, color: "#941b1b" }}>{count} assignments</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: TREND TRAJECTORIES */}
              {activeTab === "trends" && (
                <div>
                  {/* Toolbar */}
                  <div className={styles.toolbar}>
                    <div className={styles.formGroup}>
                      <label htmlFor="trend-center-select" className={styles.formLabel}>
                        Satsang Ghar
                      </label>
                      <select
                        id="trend-center-select"
                        className={styles.selectInput}
                        value={selectedCenter}
                        onChange={(e) => handleFilterChange(e.target.value, selectedMetric, selectedInterval)}
                      >
                        <option value="">All Satsang Ghars</option>
                        {knownGhars.map((g, i) => (
                          <option key={i} value={g}>
                            {g}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className={styles.formGroup}>
                      <label htmlFor="trend-metric-select" className={styles.formLabel}>
                        Metric Domain
                      </label>
                      <select
                        id="trend-metric-select"
                        className={styles.selectInput}
                        value={selectedMetric}
                        onChange={(e) => handleFilterChange(selectedCenter, e.target.value, selectedInterval)}
                      >
                        <option value="attendance">Attendance</option>
                        <option value="vehicle_wheel">Vehicle Counts</option>
                        <option value="assignment">Duty Assignments</option>
                      </select>
                    </div>

                    <div className={styles.formGroup}>
                      <label htmlFor="trend-interval-select" className={styles.formLabel}>
                        Aggregation Interval
                      </label>
                      <select
                        id="trend-interval-select"
                        className={styles.selectInput}
                        value={selectedInterval}
                        onChange={(e) => handleFilterChange(selectedCenter, selectedMetric, e.target.value)}
                      >
                        <option value="month">Monthly</option>
                        <option value="day">Daily / Session</option>
                      </select>
                    </div>

                    <div className={styles.formGroup} style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: "0.5rem", marginTop: "1.6rem" }}>
                      <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer", fontSize: "0.85rem", fontWeight: 600, color: "#475569" }}>
                        <input
                          id="trend-ma-checkbox"
                          type="checkbox"
                          checked={showMovingAverage}
                          onChange={(e) => setShowMovingAverage(e.target.checked)}
                        />
                        Smooth (3-Period MA)
                      </label>
                    </div>
                  </div>

                  {trendData && trendData.data_points.length > 0 ? (
                    <div>
                      {/* Trajectory Overview Banner */}
                      <div className={styles.trajectoryBanner}>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
                            <span
                              className={`${styles.directionBadge} ${
                                trendData.overall_direction === "growth"
                                  ? styles.badgeGrowth
                                  : trendData.overall_direction === "decline"
                                  ? styles.badgeDecline
                                  : styles.badgeStable
                              }`}
                            >
                              {trendData.overall_direction === "growth" && "↑ GROWTH"}
                              {trendData.overall_direction === "decline" && "↓ DECLINE"}
                              {trendData.overall_direction === "stable" && "→ STABLE"}
                              {trendData.overall_direction === "neutral" && "• BASELINE"}
                            </span>
                            {trendData.growth_rate_overall !== null && trendData.growth_rate_overall !== undefined && (
                              <span style={{ fontWeight: 800, fontSize: "1.1rem", color: "#0f172a" }}>
                                {trendData.growth_rate_overall > 0 ? `+${trendData.growth_rate_overall}%` : `${trendData.growth_rate_overall}%`}
                              </span>
                            )}
                          </div>
                          <p className={styles.summaryText}>{trendData.summary_text}</p>
                        </div>

                        <div className={styles.trajectoryStats}>
                          {trendData.peak_value !== null && trendData.peak_value !== undefined && (
                            <div>
                              <div style={{ fontSize: "0.75rem", color: "#64748b", fontWeight: 700, textTransform: "uppercase" }}>
                                Peak Period
                              </div>
                              <div style={{ fontSize: "1.05rem", fontWeight: 800, color: "#166534" }}>
                                {trendData.peak_value}
                              </div>
                              <div style={{ fontSize: "0.75rem", color: "#475569" }}>{trendData.peak_period}</div>
                            </div>
                          )}
                          {trendData.lowest_value !== null && trendData.lowest_value !== undefined && (
                            <div>
                              <div style={{ fontSize: "0.75rem", color: "#64748b", fontWeight: 700, textTransform: "uppercase" }}>
                                Low Period
                              </div>
                              <div style={{ fontSize: "1.05rem", fontWeight: 800, color: "#991b1b" }}>
                                {trendData.lowest_value}
                              </div>
                              <div style={{ fontSize: "0.75rem", color: "#475569" }}>{trendData.lowest_period}</div>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Responsive Vector SVG Chart */}
                      <div className={styles.sectionCard}>
                        <h3 className={styles.sectionTitle}>Longitudinal Trajectory Chart</h3>
                        <div className={styles.chartContainer}>
                          <TrendSvgChart dataPoints={trendData.data_points} showMovingAverage={showMovingAverage} />
                        </div>
                        <div className={styles.chartLegend}>
                          <div className={styles.legendItem}>
                            <div className={styles.legendLinePrimary} />
                            <span>Observed Value</span>
                          </div>
                          <div className={styles.legendItem}>
                            <div className={styles.legendLineSecondary} />
                            <span>3-Period Simple Moving Average</span>
                          </div>
                        </div>
                      </div>

                      {/* Trajectory Data Table */}
                      <div className={styles.sectionCard}>
                        <h3 className={styles.sectionTitle}>Observation Records Table</h3>
                        <div className={styles.tableWrapper}>
                          <table className={styles.table}>
                            <thead>
                              <tr>
                                <th>Period / Date</th>
                                <th>Observed Value</th>
                                <th>3-Period Moving Avg</th>
                                <th>Growth Rate</th>
                                <th>Records Count</th>
                              </tr>
                            </thead>
                            <tbody>
                              {trendData.data_points.map((pt, idx) => (
                                <tr key={idx}>
                                  <td style={{ fontWeight: 600 }}>{pt.period_label}</td>
                                  <td style={{ fontWeight: 700, color: "#941b1b" }}>{pt.value}</td>
                                  <td>{pt.moving_average ?? "-"}</td>
                                  <td>
                                    {pt.percentage_change !== null && pt.percentage_change !== undefined ? (
                                      <span
                                        style={{
                                          fontWeight: 700,
                                          color: pt.percentage_change > 0 ? "#166534" : (pt.percentage_change < 0 ? "#b91c1c" : "#475569"),
                                        }}
                                      >
                                        {pt.percentage_change > 0 ? `+${pt.percentage_change}%` : `${pt.percentage_change}%`}
                                      </span>
                                    ) : (
                                      "-"
                                    )}
                                  </td>
                                  <td>{pt.record_count}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className={styles.emptyState}>
                      <div className={styles.emptyStateIcon}>📊</div>
                      <p>No verified trend records available for the selected center and metric criteria.</p>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: OPERATIONAL ANOMALIES */}
              {activeTab === "anomalies" && (
                <div>
                  <div className={styles.sectionHeader}>
                    <h3 className={styles.sectionTitle}>Detected Operational Variances & Scheduling Conflicts</h3>
                    <span style={{ fontSize: "0.825rem", color: "#64748b" }}>
                      Threshold: &plusmn;25% from center historical mean
                    </span>
                  </div>

                  {anomalies.length === 0 ? (
                    <div className={styles.emptyState}>
                      <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>✅</div>
                      <h4 style={{ margin: "0 0 0.5rem 0", color: "#0f172a" }}>Zero Operational Anomalies Detected</h4>
                      <p style={{ margin: 0 }}>
                        All attendance figures and sewadar schedules conform to historical averages with no double-assignment conflicts.
                      </p>
                    </div>
                  ) : (
                    <div className={styles.anomalyList}>
                      {anomalies.map((anom, idx) => (
                        <div
                          key={idx}
                          className={`${styles.anomalyCard} ${
                            anom.severity === "HIGH" ? styles.anomalyHigh : styles.anomalyMedium
                          }`}
                        >
                          <div className={styles.anomalyHeader}>
                            <span className={styles.anomalyTitle}>{anom.title}</span>
                            <span
                              className={`${styles.severityTag} ${
                                anom.severity === "HIGH" ? styles.severityTagHigh : styles.severityTagMed
                              }`}
                            >
                              {anom.severity} Priority
                            </span>
                          </div>
                          <p className={styles.anomalyDesc}>{anom.description}</p>
                          <div className={styles.anomalyMeta}>
                            {anom.date && <span>📅 Date: {anom.date}</span>}
                            {anom.entity && <span>📍 Entity: {anom.entity}</span>}
                            {anom.metric_value !== null && anom.metric_value !== undefined && (
                              <span>Observed: {anom.metric_value} (Baseline: {anom.baseline_value})</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Pure Vector SVG Line Chart Component
// ----------------------------------------------------------------------------

interface TrendSvgChartProps {
  dataPoints: Array<{
    period_label: string;
    value: number;
    moving_average?: number | null;
  }>;
  showMovingAverage?: boolean;
}

function TrendSvgChart({ dataPoints, showMovingAverage = true }: TrendSvgChartProps) {
  if (!dataPoints || dataPoints.length === 0) return null;

  const width = 800;
  const height = 240;
  const padLeft = 60;
  const padRight = 30;
  const padTop = 30;
  const padBottom = 40;

  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const allVals = dataPoints.map((p) => p.value);
  dataPoints.forEach((p) => {
    if (p.moving_average !== null && p.moving_average !== undefined) {
      allVals.push(p.moving_average);
    }
  });

  const minV = Math.min(...allVals);
  const maxV = Math.max(...allVals);
  const range = maxV === minV ? maxV || 10 : maxV - minV;
  const yMin = Math.max(0, Math.floor(minV - range * 0.15));
  const yMax = Math.ceil(maxV + range * 0.15);

  const getX = (idx: number) => {
    if (dataPoints.length === 1) return padLeft + chartW / 2;
    return padLeft + (idx / (dataPoints.length - 1)) * chartW;
  };

  const getY = (val: number) => {
    return padTop + chartH - ((val - yMin) / (yMax - yMin)) * chartH;
  };

  const primaryPolyline = dataPoints.map((p, i) => `${getX(i)},${getY(p.value)}`).join(" ");

  const maPoints = dataPoints
    .map((p, i) => ({ val: p.moving_average, i }))
    .filter((pt) => pt.val !== null && pt.val !== undefined);
  const maPolyline = maPoints.map((pt) => `${getX(pt.i)},${getY(pt.val!)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={styles.chartSvg}>
      {/* Background horizontal grid lines */}
      {[0, 0.25, 0.5, 0.75, 1].map((pct, idx) => {
        const yVal = Math.round(yMin + pct * (yMax - yMin));
        const yPos = padTop + chartH - pct * chartH;
        return (
          <g key={idx}>
            <line x1={padLeft} y1={yPos} x2={width - padRight} y2={yPos} stroke="#e2e8f0" strokeDasharray="3 3" />
            <text x={padLeft - 10} y={yPos + 4} textAnchor="end" fontSize="11" fill="#64748b" fontWeight="500">
              {yVal}
            </text>
          </g>
        );
      })}

      {/* Primary Value Polyline */}
      {dataPoints.length > 1 && (
        <polyline fill="none" stroke="#941b1b" strokeWidth="3" points={primaryPolyline} strokeLinecap="round" strokeLinejoin="round" />
      )}

      {/* Moving Average Polyline */}
      {showMovingAverage && maPoints.length > 1 && (
        <polyline fill="none" stroke="#2563eb" strokeWidth="2" strokeDasharray="5 5" points={maPolyline} />
      )}

      {/* Primary Points and Value Labels */}
      {dataPoints.map((p, i) => {
        const cx = getX(i);
        const cy = getY(p.value);
        return (
          <g key={i}>
            <circle cx={cx} cy={cy} r="6" fill="#941b1b" stroke="#ffffff" strokeWidth="2" />
            <text x={cx} y={cy - 12} textAnchor="middle" fontSize="11" fontWeight="700" fill="#0f172a">
              {p.value}
            </text>
            <text x={cx} y={height - 12} textAnchor="middle" fontSize="11" fill="#475569" fontWeight="600">
              {p.period_label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
