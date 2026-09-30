"use client";

import React, { useEffect, useMemo, useState } from "react";
import { getAuthHeaders } from "../auth";
import {
  AuthUser,
  DocumentItem,
  DocumentRecordItem,
  ReviewHistoryItem,
  ValidationIssueItem,
  ValidationResultData,
} from "../types";
import SourcePreviewModal from "./SourcePreviewModal";
import styles from "./ReviewWorkspaceModal.module.css";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface ReviewWorkspaceModalProps {
  isOpen: boolean;
  onClose: () => void;
  user: AuthUser | null;
}

type PromptType = "approve" | "reject" | "correction" | null;

export default function ReviewWorkspaceModal({
  isOpen,
  onClose,
  user,
}: ReviewWorkspaceModalProps) {
  // Document selection and list
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>("all");
  const [isLoadingDocs, setIsLoadingDocs] = useState<boolean>(false);

  // Validation details & issues
  const [validationDataMap, setValidationDataMap] = useState<Record<string, ValidationResultData>>({});
  const [isLoadingValidation, setIsLoadingValidation] = useState<boolean>(false);

  // Active selected issue for detail inspection panel
  const [selectedIssue, setSelectedIssue] = useState<ValidationIssueItem | null>(null);

  // Source preview modal integration
  const [previewSourceId, setPreviewSourceId] = useState<string | null>(null);

  // Filter states
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Review action prompt modal states
  const [promptType, setPromptType] = useState<PromptType>(null);
  const [promptInput, setPromptInput] = useState<string>("");
  const [isSubmittingAction, setIsSubmittingAction] = useState<boolean>(false);
  const [feedbackMessage, setFeedbackMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Role permissions
  const canReview = user?.role === "admin" || user?.role === "reviewer";

  // Load documents on open
  useEffect(() => {
    if (isOpen) {
      loadDocuments();
    }
  }, [isOpen]);

  // Load validation results whenever documents change or are loaded
  const loadDocuments = async () => {
    setIsLoadingDocs(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/documents`, {
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data: DocumentItem[] = await res.json();
        setDocuments(data);
        // Pre-fetch validation for each document
        data.forEach((doc) => {
          fetchDocValidation(doc.id);
        });
      }
    } catch {
      // Backend error fallback
    } finally {
      setIsLoadingDocs(false);
    }
  };

  const fetchDocValidation = async (docId: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/documents/${docId}/validation`, {
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const valData: ValidationResultData = await res.json();
        setValidationDataMap((prev) => ({
          ...prev,
          [docId]: valData,
        }));
      }
    } catch {
      // Quiet ignore
    }
  };

  // Keyboard shortcut (Escape)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !previewSourceId && !promptType) {
        onClose();
      }
    };
    if (isOpen) {
      window.addEventListener("keydown", handleKeyDown);
      return () => window.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, previewSourceId, promptType, onClose]);

  // Auto-clear feedback after 4 seconds
  useEffect(() => {
    if (feedbackMessage) {
      const timer = setTimeout(() => setFeedbackMessage(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [feedbackMessage]);

  // Filtered documents list
  const activeDocs = useMemo(() => {
    if (selectedDocId === "all") return documents;
    return documents.filter((d) => d.id === selectedDocId);
  }, [documents, selectedDocId]);

  // Summary Metrics calculation
  const summaryMetrics = useMemo(() => {
    let totalRecords = 0;
    let accepted = 0;
    let needsReview = 0;
    let errors = 0;

    activeDocs.forEach((d) => {
      const v = validationDataMap[d.id];
      if (v) {
        totalRecords += v.total_records_examined;
        accepted += v.valid_count;
        needsReview += v.needs_review_count;
        errors += v.errors_count;
      } else {
        totalRecords += d.total_records;
        accepted += d.valid_count;
        needsReview += d.needs_review_count;
        errors += d.errors_count;
      }
    });

    return { totalRecords, accepted, needsReview, errors };
  }, [activeDocs, validationDataMap]);

  // Aggregated issues across selected document(s)
  const allIssues = useMemo(() => {
    const list: Array<ValidationIssueItem & { docId: string; docName: string; docStatus: string }> = [];
    activeDocs.forEach((d) => {
      const v = validationDataMap[d.id];
      if (v && v.issues) {
        v.issues.forEach((iss) => {
          list.push({
            ...iss,
            docId: d.id,
            docName: d.original_filename,
            docStatus: d.status,
          });
        });
      }
    });
    return list;
  }, [activeDocs, validationDataMap]);

  // Filtered issues
  const filteredIssues = useMemo(() => {
    return allIssues.filter((item) => {
      // Status filter
      if (statusFilter !== "all") {
        if (statusFilter === "needs_review" && item.severity !== "warning" && item.severity !== "needs_review") {
          return false;
        }
        if (statusFilter === "error" && item.severity !== "error") {
          return false;
        }
      }

      // Severity / Issue Type filter
      if (severityFilter !== "all") {
        if (severityFilter === "error" && item.severity !== "error") return false;
        if (severityFilter === "warning" && item.severity !== "warning") return false;
        if (severityFilter === "missing" && !item.issue_type.toLowerCase().includes("missing")) return false;
        if (severityFilter === "invalid" && !item.issue_type.toLowerCase().includes("invalid")) return false;
      }

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const msg = item.message.toLowerCase();
        const type = item.issue_type.toLowerCase();
        const doc = item.docName.toLowerCase();
        const sheet = (item.sheet_name || "").toLowerCase();
        const cell = (item.cell_or_range || "").toLowerCase();
        const raw = (item.raw_value || "").toLowerCase();

        if (
          !msg.includes(q) &&
          !type.includes(q) &&
          !doc.includes(q) &&
          !sheet.includes(q) &&
          !cell.includes(q) &&
          !raw.includes(q)
        ) {
          return false;
        }
      }

      return true;
    });
  }, [allIssues, statusFilter, severityFilter, searchQuery]);

  // Set initial selected issue
  useEffect(() => {
    if (!selectedIssue && filteredIssues.length > 0) {
      setSelectedIssue(filteredIssues[0]);
    }
  }, [filteredIssues, selectedIssue]);

  // Target document for review actions
  const targetDocument = useMemo(() => {
    if (selectedIssue) {
      const match = documents.find((d) => d.id === (selectedIssue as any).docId);
      if (match) return match;
    }
    if (selectedDocId !== "all") {
      const match = documents.find((d) => d.id === selectedDocId);
      if (match) return match;
    }
    return documents[0] || null;
  }, [selectedIssue, selectedDocId, documents]);

  // Active validation data for target document
  const targetDocValidation = useMemo(() => {
    if (!targetDocument) return null;
    return validationDataMap[targetDocument.id] || null;
  }, [targetDocument, validationDataMap]);

  // Handle Review Action execution
  const handleExecuteAction = async () => {
    if (!canReview) {
      setFeedbackMessage({
        type: "error",
        text: "Unauthorized: Only Admin and Reviewer roles can perform review actions.",
      });
      return;
    }
    if (!targetDocument) {
      setFeedbackMessage({ type: "error", text: "No document selected for review." });
      return;
    }

    if (promptType === "reject" && !promptInput.trim()) {
      alert("A rejection reason is mandatory.");
      return;
    }
    if (promptType === "correction" && !promptInput.trim()) {
      alert("Correction instructions are mandatory.");
      return;
    }

    setIsSubmittingAction(true);
    let endpoint = "";
    let body: any = {};

    if (promptType === "approve") {
      endpoint = `${API_BASE_URL}/api/v1/documents/${targetDocument.id}/approve`;
      body = { notes: promptInput.trim() || undefined };
    } else if (promptType === "reject") {
      endpoint = `${API_BASE_URL}/api/v1/documents/${targetDocument.id}/reject`;
      body = { reason: promptInput.trim() };
    } else if (promptType === "correction") {
      endpoint = `${API_BASE_URL}/api/v1/documents/${targetDocument.id}/needs-correction`;
      body = { instructions: promptInput.trim() };
    }

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `Review action failed with status ${res.status}`);
      }

      const resData = await res.json();
      setFeedbackMessage({
        type: "success",
        text: `Document successfully marked as ${resData.status || promptType}!`,
      });

      // Close prompt dialog
      setPromptType(null);
      setPromptInput("");

      // Refresh documents and target document validation
      await loadDocuments();
      if (targetDocument) {
        await fetchDocValidation(targetDocument.id);
      }
    } catch (err: any) {
      setFeedbackMessage({
        type: "error",
        text: err.message || "Failed to submit review action.",
      });
    } finally {
      setIsSubmittingAction(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-labelledby="workspace-title">
      <div className={styles.modal}>
        {/* Header */}
        <header className={styles.header}>
          <div className={styles.titleArea}>
            <div className={styles.titleRow}>
              <h2 id="workspace-title" className={styles.title}>
                Document Review &amp; Validation
              </h2>
              {user && (
                <span
                  className={`${styles.roleBadge} ${
                    user.role === "admin"
                      ? styles.roleBadgeAdmin
                      : user.role === "reviewer"
                      ? styles.roleBadgeReviewer
                      : user.role === "viewer"
                      ? styles.roleBadgeViewer
                      : styles.roleBadgeUploader
                  }`}
                >
                  Role: {user.role} {user.role === "viewer" ? "(View-Only)" : ""}
                </span>
              )}
            </div>
            <p className={styles.subtitle}>
              Inspect validation issues, verify extracted records against original source document references, and record review decisions.
            </p>
          </div>

          <div className={styles.headerActions}>
            <button
              type="button"
              className={styles.iconButton}
              onClick={loadDocuments}
              title="Refresh validation records"
              aria-label="Refresh validation records"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M23 4v6h-6" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
            </button>
            <button
              type="button"
              className={styles.closeButton}
              onClick={onClose}
              aria-label="Close review workspace"
            >
              &times;
            </button>
          </div>
        </header>

        {/* Feedback Message */}
        {feedbackMessage && (
          <div
            style={{
              padding: "10px 24px",
              backgroundColor: feedbackMessage.type === "success" ? "#def7ec" : "#fde8e8",
              color: feedbackMessage.type === "success" ? "#03543f" : "#c5221f",
              fontSize: "0.85rem",
              fontWeight: 500,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              borderBottom: "1px solid var(--border-color)",
            }}
          >
            <span>{feedbackMessage.text}</span>
            <button
              type="button"
              onClick={() => setFeedbackMessage(null)}
              style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", fontWeight: 700 }}
            >
              &times;
            </button>
          </div>
        )}

        {/* Summary Cards */}
        <section className={styles.summaryRow} aria-label="Validation summary metrics">
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>Total Records</span>
            <span className={styles.summaryValue}>{summaryMetrics.totalRecords}</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>Accepted</span>
            <span className={`${styles.summaryValue} ${styles.summaryValAccepted}`}>
              {summaryMetrics.accepted}
            </span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>Needs Review</span>
            <span className={`${styles.summaryValue} ${styles.summaryValReview}`}>
              {summaryMetrics.needsReview}
            </span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>Validation Errors</span>
            <span className={`${styles.summaryValue} ${styles.summaryValError}`}>
              {summaryMetrics.errors}
            </span>
          </div>
        </section>

        {/* Filter Controls Bar */}
        <section className={styles.filterBar} aria-label="Review workspace filters">
          <div className={styles.filterGroup}>
            <label htmlFor="doc-select" className={styles.filterLabel}>
              Document:
            </label>
            <select
              id="doc-select"
              className={styles.selectInput}
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
            >
              <option value="all">All Documents ({documents.length})</option>
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.original_filename} ({d.status})
                </option>
              ))}
            </select>
          </div>

          <div className={styles.filterGroup}>
            <label htmlFor="status-select" className={styles.filterLabel}>
              Status:
            </label>
            <select
              id="status-select"
              className={styles.selectInput}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">All Statuses</option>
              <option value="needs_review">Needs Review</option>
              <option value="error">Validation Error</option>
            </select>
          </div>

          <div className={styles.filterGroup}>
            <label htmlFor="severity-select" className={styles.filterLabel}>
              Issue Type:
            </label>
            <select
              id="severity-select"
              className={styles.selectInput}
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
            >
              <option value="all">All Types</option>
              <option value="error">Errors Only</option>
              <option value="warning">Warnings Only</option>
              <option value="missing">Missing Values</option>
              <option value="invalid">Invalid Format</option>
            </select>
          </div>

          <div className={styles.filterGroup} style={{ flex: 1, justifyContent: "flex-end" }}>
            <input
              type="text"
              className={styles.searchInput}
              placeholder="Search issues, values, cells..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </section>

        {/* Workspace Body: Split View (Table + Detail Panel) */}
        <div className={styles.workspaceBody}>
          {/* Main Validation Table Column */}
          <div className={styles.tableColumn}>
            <div className={styles.tableHeader}>
              <span>
                Showing <strong>{filteredIssues.length}</strong> validation issues
              </span>
              {targetDocument && (
                <span>
                  Current Target Document: <strong>{targetDocument.original_filename}</strong> (
                  <span style={{ textTransform: "capitalize" }}>{targetDocument.status}</span>)
                </span>
              )}
            </div>

            {filteredIssues.length === 0 ? (
              <div className={styles.emptyState}>
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.5">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                <strong>No validation issues match your current filters.</strong>
                <span>
                  {documents.length === 0
                    ? "No documents have been uploaded yet."
                    : "All examined records are valid or clean according to the selected criteria."}
                </span>
              </div>
            ) : (
              <table className={styles.mainTable}>
                <thead>
                  <tr>
                    <th>Record</th>
                    <th>Source Reference</th>
                    <th>Issue &amp; Details</th>
                    <th>Status</th>
                    <th style={{ textAlign: "right" }}>Review Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredIssues.map((issue, idx) => {
                    const isSelected =
                      selectedIssue === issue ||
                      (selectedIssue?.source_reference_id === issue.source_reference_id &&
                        selectedIssue?.issue_type === issue.issue_type);

                    return (
                      <tr
                        key={`${issue.source_reference_id || idx}-${issue.issue_type}`}
                        className={`${styles.tableRow} ${isSelected ? styles.tableRowActive : ""}`}
                        onClick={() => setSelectedIssue(issue)}
                      >
                        <td>
                          <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                            {issue.record_type || "Document Record"}
                          </div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            ID: {issue.record_id ? issue.record_id.slice(0, 8) + "..." : "Pending"}
                          </div>
                        </td>
                        <td>
                          <div style={{ fontWeight: 500 }}>{issue.docName}</div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                            {issue.sheet_name ? `Sheet: ${issue.sheet_name}` : `Page ${issue.page_number || 1}`}
                            {issue.cell_or_range ? ` (${issue.cell_or_range})` : ""}
                          </div>
                        </td>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                            <span
                              className={`${styles.badge} ${
                                issue.severity === "error" ? styles.badgeError : styles.badgeWarning
                              }`}
                            >
                              {issue.severity.toUpperCase()}
                            </span>
                            <span style={{ fontWeight: 600, fontSize: "0.8rem" }}>{issue.issue_type}</span>
                          </div>
                          <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                            {issue.message}
                          </div>
                        </td>
                        <td>
                          <span
                            className={`${styles.badge} ${
                              issue.docStatus === "approved"
                                ? styles.badgeSuccess
                                : issue.docStatus === "rejected"
                                ? styles.badgeError
                                : issue.docStatus === "needs_correction"
                                ? styles.badgeWarning
                                : styles.badgeNeutral
                            }`}
                          >
                            {issue.docStatus || "Imported"}
                          </span>
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <button
                            type="button"
                            className={styles.previewSourceBtn}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedIssue(issue);
                            }}
                          >
                            Inspect &amp; Review
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* Detail / Review Panel Column */}
          <div className={styles.detailColumn}>
            <div className={styles.detailHeader}>
              <h3 className={styles.detailTitle}>Record &amp; Issue Details</h3>
              {selectedIssue?.source_reference_id && (
                <button
                  type="button"
                  className={styles.previewSourceBtn}
                  onClick={() => setPreviewSourceId(selectedIssue.source_reference_id || null)}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                  Preview Full Source
                </button>
              )}
            </div>

            <div className={styles.detailBody}>
              {selectedIssue ? (
                <>
                  {/* Record Information */}
                  <div className={styles.detailSection}>
                    <h4 className={styles.sectionHeading}>Record Information</h4>
                    <div className={styles.infoBox}>
                      <div className={styles.infoRow}>
                        <span className={styles.infoKey}>Record Type:</span>
                        <span className={styles.infoVal}>{selectedIssue.record_type || "Structured Office Record"}</span>
                      </div>
                      <div className={styles.infoRow}>
                        <span className={styles.infoKey}>Record ID:</span>
                        <span className={styles.infoVal}>{selectedIssue.record_id || "N/A"}</span>
                      </div>
                      {selectedIssue.record_details?.date && (
                        <div className={styles.infoRow}>
                          <span className={styles.infoKey}>Date:</span>
                          <span className={styles.infoVal}>{selectedIssue.record_details.date}</span>
                        </div>
                      )}
                      {selectedIssue.record_details?.satsang_ghar_id && (
                        <div className={styles.infoRow}>
                          <span className={styles.infoKey}>Satsang Ghar:</span>
                          <span className={styles.infoVal}>{selectedIssue.record_details.satsang_ghar_id}</span>
                        </div>
                      )}
                      {selectedIssue.record_details?.person_name && (
                        <div className={styles.infoRow}>
                          <span className={styles.infoKey}>Person Name:</span>
                          <span className={styles.infoVal}>{selectedIssue.record_details.person_name}</span>
                        </div>
                      )}
                      {selectedIssue.record_details?.count !== undefined && (
                        <div className={styles.infoRow}>
                          <span className={styles.infoKey}>Count:</span>
                          <span className={styles.infoVal}>{selectedIssue.record_details.count}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Source Document Reference */}
                  <div className={styles.detailSection}>
                    <h4 className={styles.sectionHeading}>Source Document &amp; Reference</h4>
                    <div className={styles.infoBox}>
                      <div className={styles.infoRow}>
                        <span className={styles.infoKey}>Document:</span>
                        <span className={styles.infoVal}>
                          {(selectedIssue as any).docName || selectedIssue.document_name || "Source Document"}
                        </span>
                      </div>
                      {selectedIssue.sheet_name && (
                        <div className={styles.infoRow}>
                          <span className={styles.infoKey}>Sheet:</span>
                          <span className={styles.infoVal}>{selectedIssue.sheet_name}</span>
                        </div>
                      )}
                      {selectedIssue.page_number && (
                        <div className={styles.infoRow}>
                          <span className={styles.infoKey}>Page:</span>
                          <span className={styles.infoVal}>{selectedIssue.page_number}</span>
                        </div>
                      )}
                      {selectedIssue.row_number && (
                        <div className={styles.infoRow}>
                          <span className={styles.infoKey}>Row:</span>
                          <span className={styles.infoVal}>{selectedIssue.row_number}</span>
                        </div>
                      )}
                      {selectedIssue.cell_or_range && (
                        <div className={styles.infoRow}>
                          <span className={styles.infoKey}>Cell / Range:</span>
                          <span className={styles.infoVal}>{selectedIssue.cell_or_range}</span>
                        </div>
                      )}
                      {selectedIssue.source_reference_id && (
                        <div className={styles.infoRow}>
                          <span className={styles.infoKey}>Reference ID:</span>
                          <span className={styles.infoVal}>{selectedIssue.source_reference_id.slice(0, 12)}...</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Validation Issue */}
                  <div className={styles.detailSection}>
                    <h4 className={styles.sectionHeading}>Validation Issue</h4>
                    <div className={styles.infoBox}>
                      <div className={styles.infoRow}>
                        <span className={styles.infoKey}>Issue Code:</span>
                        <span className={styles.infoVal}>
                          <span
                            className={`${styles.badge} ${
                              selectedIssue.severity === "error" ? styles.badgeError : styles.badgeWarning
                            }`}
                          >
                            {selectedIssue.issue_type}
                          </span>
                        </span>
                      </div>
                      <div className={styles.infoRow}>
                        <span className={styles.infoKey}>Severity:</span>
                        <span className={styles.infoVal} style={{ textTransform: "uppercase" }}>
                          {selectedIssue.severity}
                        </span>
                      </div>
                      <div style={{ marginTop: 8, fontSize: "0.82rem", color: "var(--text-primary)" }}>
                        {selectedIssue.message}
                      </div>
                    </div>
                  </div>

                  {/* Original / Raw Value */}
                  <div className={styles.detailSection}>
                    <h4 className={styles.sectionHeading}>Original / Raw Value</h4>
                    <div className={styles.codeBox}>
                      {selectedIssue.raw_value || "(No raw string recorded in source cell)"}
                    </div>
                  </div>

                  {/* Relevant Extracted Value */}
                  <div className={styles.detailSection}>
                    <h4 className={styles.sectionHeading}>Relevant Extracted Value</h4>
                    <div className={styles.codeBox}>
                      {selectedIssue.extracted_value
                        ? JSON.stringify(selectedIssue.extracted_value, null, 2)
                        : selectedIssue.record_details
                        ? JSON.stringify(selectedIssue.record_details, null, 2)
                        : "No structured value available"}
                    </div>
                  </div>

                  {/* Review History */}
                  <div className={styles.detailSection}>
                    <h4 className={styles.sectionHeading}>Review &amp; Audit History</h4>
                    {targetDocValidation?.review_history && targetDocValidation.review_history.length > 0 ? (
                      <div className={styles.historyTimeline}>
                        {targetDocValidation.review_history.map((rev, i) => (
                          <div key={rev.id || i} className={styles.historyItem}>
                            <div className={styles.historyHeader}>
                              <span className={styles.historyAction}>
                                <strong>{rev.action}</strong> by {rev.reviewer_name}
                              </span>
                              <span className={styles.historyTime}>
                                {rev.timestamp ? new Date(rev.timestamp).toLocaleString() : ""}
                              </span>
                            </div>
                            {(rev.notes || rev.reason || rev.instructions) && (
                              <div className={styles.historyNote}>
                                &ldquo;{rev.notes || rev.reason || rev.instructions}&rdquo;
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                        No review actions recorded yet for this document.
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className={styles.emptyState}>
                  <span>Select any issue from the table to view affected records and source references.</span>
                </div>
              )}
            </div>

            {/* Action Area */}
            <div className={styles.actionArea}>
              {canReview ? (
                <>
                  <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                    Review Decision for: <strong>{targetDocument?.original_filename || "Document"}</strong>
                  </div>
                  <div className={styles.actionButtonGroup}>
                    <button
                      type="button"
                      className={styles.btnApprove}
                      onClick={() => {
                        setPromptType("approve");
                        setPromptInput("");
                      }}
                      disabled={isSubmittingAction}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      Approve
                    </button>

                    <button
                      type="button"
                      className={styles.btnCorrection}
                      onClick={() => {
                        setPromptType("correction");
                        setPromptInput("");
                      }}
                      disabled={isSubmittingAction}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                      </svg>
                      Correct
                    </button>

                    <button
                      type="button"
                      className={styles.btnReject}
                      onClick={() => {
                        setPromptType("reject");
                        setPromptInput("");
                      }}
                      disabled={isSubmittingAction}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="18" y1="6" x2="6" y2="18" />
                        <line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                      Reject
                    </button>
                  </div>
                </>
              ) : (
                <div className={styles.viewerNotice}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#6b7280" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                  <span>
                    <strong>View-Only Mode:</strong> Review actions (Approve, Reject, Request Correction) are restricted to Reviewer and Admin roles.
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Prompt Modal Dialog for Review Decision (Approve / Reject / Correction) */}
        {promptType && (
          <div className={styles.promptOverlay}>
            <div className={styles.promptCard}>
              <h4 className={styles.promptTitle}>
                {promptType === "approve"
                  ? "Approve Document & Records"
                  : promptType === "reject"
                  ? "Reject Document"
                  : "Request Document Correction"}
              </h4>

              <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", margin: 0 }}>
                {promptType === "approve"
                  ? "Optionally add reviewer notes to document approval:"
                  : promptType === "reject"
                  ? "Please provide the required reason for rejecting this document:"
                  : "Please provide the required correction instructions:"}
              </p>

              <textarea
                className={styles.promptTextarea}
                placeholder={
                  promptType === "approve"
                    ? "Optional notes (e.g. verified with field team)..."
                    : promptType === "reject"
                    ? "Mandatory reason (e.g. incorrect year entered in dates)..."
                    : "Mandatory instructions (e.g. re-upload with corrected attendance totals)..."
                }
                value={promptInput}
                onChange={(e) => setPromptInput(e.target.value)}
                autoFocus
              />

              <div className={styles.promptButtons}>
                <button
                  type="button"
                  className={styles.promptCancelBtn}
                  onClick={() => {
                    setPromptType(null);
                    setPromptInput("");
                  }}
                  disabled={isSubmittingAction}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className={styles.promptSubmitBtn}
                  onClick={handleExecuteAction}
                  disabled={isSubmittingAction}
                >
                  {isSubmittingAction
                    ? "Submitting..."
                    : promptType === "approve"
                    ? "Confirm Approval"
                    : promptType === "reject"
                    ? "Confirm Rejection"
                    : "Submit Instructions"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Full Source Reference Preview Modal */}
        {previewSourceId && (
          <SourcePreviewModal
            sourceId={previewSourceId}
            onClose={() => setPreviewSourceId(null)}
          />
        )}
      </div>
    </div>
  );
}
