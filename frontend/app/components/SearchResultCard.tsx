"use client";

import React, { useState } from "react";
import { SearchResult, SourceReferenceInfo } from "../types";
import styles from "./SearchResultCard.module.css";

interface SearchResultCardProps {
  result: SearchResult;
  onSelectSuggestion?: (question: string) => void;
  onViewSource?: (sourceId: string) => void;
}

export default function SearchResultCard({ result, onSelectSuggestion, onViewSource }: SearchResultCardProps) {
  const [showSource, setShowSource] = useState(false);
  const [showRecords, setShowRecords] = useState(false);

  const {
    original_question,
    status,
    answer,
    records,
    total_records,
    calculation,
    source_references,
    clarification_required,
    clarification_question,
    warnings,
  } = result;

  // Format main source label
  const primarySource: SourceReferenceInfo | undefined = source_references[0];
  const sourceLabel = primarySource?.document_name
    ? `${primarySource.document_name}${primarySource.sheet_name ? ` (${primarySource.sheet_name})` : ""}${primarySource.page_number ? ` (p.${primarySource.page_number})` : ""}`
    : "Verified Database Records";

  // Clarification Required State
  if (clarification_required || status === "clarification_required") {
    return (
      <div className={styles.card} role="region" aria-label="Clarification needed">
        <div className={styles.header}>
          <p className={styles.queryText}>
            Question: <strong>&ldquo;{original_question}&rdquo;</strong>
          </p>
          <span className={`${styles.badge} ${styles.badgeClarification}`}>Clarification Needed</span>
        </div>

        <div className={styles.clarificationCard}>
          <h4 className={styles.clarificationTitle}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            Please clarify your request
          </h4>
          <p className={styles.clarificationPrompt}>
            {clarification_question || answer}
          </p>
        </div>
      </div>
    );
  }

  // No Results State
  if (status === "no_results") {
    return (
      <div className={styles.card} role="region" aria-label="Search results">
        <div className={styles.header}>
          <p className={styles.queryText}>
            Question: <strong>&ldquo;{original_question}&rdquo;</strong>
          </p>
          <span className={`${styles.badge} ${styles.badgeNoResults}`}>No Results</span>
        </div>

        <div className={styles.noResultsCard}>
          <p className={styles.noResultsTitle}>{answer}</p>
          <p className={styles.noResultsSub}>
            Try checking the spelling of the Satsang Ghar or specifying a valid date / month period.
          </p>
        </div>
      </div>
    );
  }

  // Error State
  if (status === "error") {
    return (
      <div className={styles.card} role="region" aria-label="Search error">
        <div className={styles.header}>
          <p className={styles.queryText}>
            Question: <strong>&ldquo;{original_question}&rdquo;</strong>
          </p>
          <span className={`${styles.badge} ${styles.badgeError}`}>Error</span>
        </div>
        <p className={styles.answerText}>{answer}</p>
      </div>
    );
  }

  // Success or Needs Review State
  const isNeedsReview = status === "needs_review";

  return (
    <div className={styles.card} role="region" aria-label="Search results">
      <div className={styles.header}>
        <p className={styles.queryText}>
          Question: <strong>&ldquo;{original_question}&rdquo;</strong>
        </p>
        {isNeedsReview ? (
          <span className={`${styles.badge} ${styles.badgeNeedsReview}`}>Needs Review</span>
        ) : (
          <span className={`${styles.badge} ${styles.badgeSuccess}`}>Verified Result</span>
        )}
      </div>

      {/* Needs Review Warning Banner */}
      {isNeedsReview && warnings && warnings.length > 0 && (
        <div className={styles.warningBanner}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <div>{warnings[0]}</div>
        </div>
      )}

      {/* Numerical Stat Display if calculation exists */}
      {calculation && calculation.value !== null && calculation.value !== undefined && (
        <div className={styles.statHero}>
          <div className={styles.statLabel}>
            {calculation.operation === "average"
              ? "Average Attendance"
              : calculation.operation === "sum"
              ? "Total Attendance"
              : calculation.operation === "count"
              ? "Total Records"
              : `${calculation.operation.toUpperCase()} Value`}
          </div>
          <div className={styles.statValue}>
            {calculation.value}
            {calculation.unit && <span className={styles.statUnit}>{calculation.unit}</span>}
          </div>
          {calculation.formula_description && (
            <p className={styles.statFormula}>{calculation.formula_description}</p>
          )}
          {calculation.breakdown && (
            <div className={styles.statCalculation}>
              <span className={styles.calcLabel}>Calculation:</span>
              <span className={styles.calcBreakdown}>{calculation.breakdown}</span>
            </div>
          )}
        </div>
      )}

      {/* Answer Sentence */}
      <div className={styles.answerSection}>
        <p className={styles.answerText}>{answer}</p>
      </div>

      {/* Metadata Grid */}
      <div className={styles.metaGrid}>
        <div className={styles.metaItem}>
          <span className={styles.metaTitle}>Supporting Records</span>
          <span className={styles.metaValue}>{total_records} record{total_records === 1 ? "" : "s"}</span>
        </div>
        <div className={styles.metaItem}>
          <span className={styles.metaTitle}>Primary Source</span>
          <span className={styles.metaValue}>{sourceLabel}</span>
        </div>
      </div>

      {/* Actions */}
      <div className={styles.actionRow}>
        {source_references.length > 0 && (
          <button
            type="button"
            className={`${styles.actionButton} ${showSource ? styles.actionButtonActive : ""}`}
            onClick={() => setShowSource(!showSource)}
            aria-expanded={showSource}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
            {showSource ? "Hide Sources" : `View Sources (${source_references.length})`}
          </button>
        )}

        {records.length > 0 && (
          <button
            type="button"
            className={`${styles.actionButton} ${showRecords ? styles.actionButtonActive : ""}`}
            onClick={() => setShowRecords(!showRecords)}
            aria-expanded={showRecords}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <line x1="3" y1="9" x2="21" y2="9" />
              <line x1="9" y1="21" x2="9" y2="9" />
            </svg>
            {showRecords ? "Hide Supporting Records" : `View Supporting Records (${records.length})`}
          </button>
        )}

        {primarySource?.id && onViewSource && (
          <button
            type="button"
            className={styles.actionButton}
            onClick={() => onViewSource(primarySource.id!)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polygon points="12 8 8 12 12 16 12 8" />
            </svg>
            Inspect Primary Source
          </button>
        )}
      </div>

      {/* Source Provenance Drawer */}
      {showSource && (
        <div className={styles.drawer}>
          <h4 className={styles.drawerHeading}>Document Provenance</h4>
          <div className={styles.sourceList}>
            {source_references.map((sr, idx) => (
              <div key={idx} className={styles.sourceItem}>
                <div className={styles.sourceItemHeader}>
                  <div className={styles.sourceDocTitle}>
                    {sr.document_name || "Unknown Document"}
                    {sr.document_version !== null && sr.document_version !== undefined && ` (v${sr.document_version})`}
                  </div>
                  {sr.id && onViewSource && (
                    <button
                      type="button"
                      className={styles.viewSourceBtnSmall}
                      onClick={() => onViewSource(sr.id!)}
                    >
                      View Source
                    </button>
                  )}
                </div>
                <div className={styles.sourceDetails}>
                  {sr.document_type && <span>{sr.document_type.toUpperCase()} • </span>}
                  {sr.sheet_name && <span>Sheet: {sr.sheet_name} • </span>}
                  {sr.row_number !== null && sr.row_number !== undefined && <span>Row: {sr.row_number} • </span>}
                  {sr.page_number !== null && sr.page_number !== undefined && <span>Page: {sr.page_number} • </span>}
                  {sr.cell_or_range && <span>Range: {sr.cell_or_range} • </span>}
                  {sr.bbox && <span>Region: [{sr.bbox.join(", ")}]</span>}
                </div>
                {sr.source_text && (
                  <div className={styles.sourceSnippet}>
                    {sr.source_text}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Supporting Records Table */}
      {showRecords && (
        <div className={styles.drawer}>
          <h4 className={styles.drawerHeading}>Supporting Records</h4>
          <div className={styles.recordsTableWrapper}>
            <table className={styles.recordsTable}>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Satsang Ghar</th>
                  {records.some((r) => r.attendance_count !== undefined) && <th>Value / Count</th>}
                  {records.some((r) => r.person) && <th>Person</th>}
                  {records.some((r) => r.role_code || r.role_name) && <th>Role</th>}
                  {records.some((r) => r.vehicle_type) && <th>Vehicle Type</th>}
                  <th>Status</th>
                  <th>Source Action</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r, i) => (
                  <tr key={r.id || i}>
                    <td>{r.date || "—"}</td>
                    <td>{r.satsang_ghar || "—"}</td>
                    {records.some((rec) => rec.attendance_count !== undefined) && (
                      <td><strong>{r.attendance_count ?? "—"}</strong></td>
                    )}
                    {records.some((rec) => rec.person) && <td>{r.person || "—"}</td>}
                    {records.some((rec) => rec.role_code || rec.role_name) && (
                      <td>{r.role_code ? `${r.role_name} (${r.role_code})` : r.role_name || "—"}</td>
                    )}
                    {records.some((rec) => rec.vehicle_type) && <td>{r.vehicle_type || "—"}</td>}
                    <td>
                      {r.status === "needs_review" ? (
                        <span className={styles.badgePillReview}>Needs Review</span>
                      ) : (
                        <span style={{ color: "#16a34a", fontSize: "0.75rem", fontWeight: 600 }}>Verified</span>
                      )}
                    </td>
                    <td>
                      {r.source_reference_id && onViewSource ? (
                        <button
                          type="button"
                          className={styles.viewSourceBtnSmall}
                          onClick={() => onViewSource(r.source_reference_id)}
                        >
                          View Source
                        </button>
                      ) : r.source_reference ? (
                        <span>
                          {r.source_reference.sheet_name || "Sheet"}
                          {r.source_reference.row_number ? ` : Row ${r.source_reference.row_number}` : ""}
                        </span>
                      ) : (
                        "—"
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
  );
}
