"use client";

import React, { useEffect, useState } from "react";
import { SourcePreviewData } from "../types";
import styles from "./SourcePreviewModal.module.css";

interface SourcePreviewModalProps {
  sourceId: string | null;
  onClose: () => void;
}

export default function SourcePreviewModal({ sourceId, onClose }: SourcePreviewModalProps) {
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SourcePreviewData | null>(null);

  useEffect(() => {
    if (!sourceId) return;

    let isMounted = true;
    setLoading(true);
    setError(null);

    fetch(`/api/v1/sources/${sourceId}/preview`)
      .then(async (res) => {
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || `Failed to fetch source details (status ${res.status}).`);
        }
        return res.json();
      })
      .then((previewData: SourcePreviewData) => {
        if (isMounted) {
          setData(previewData);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || "Unable to load source preview.");
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [sourceId]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!sourceId) return null;

  return (
    <div className={styles.overlay} onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <button type="button" className={styles.backButton} onClick={onClose} aria-label="Back to Results">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="19" y1="12" x2="5" y2="12" />
                <polyline points="12 19 5 12 12 5" />
              </svg>
              Back to Results
            </button>
            <div className={styles.titleArea}>
              <h3 id="modal-title" className={styles.modalTitle}>
                Source Verification Preview
              </h3>
              {data && (
                <span className={styles.modalSubtitle}>
                  {data.document_name}
                </span>
              )}
            </div>
          </div>
          <button type="button" className={styles.closeButton} onClick={onClose} aria-label="Close Preview">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Content Body */}
        <div className={styles.content}>
          {loading && (
            <div className={styles.stateCard}>
              <div className={styles.spinner} />
              <p>Loading verified source context...</p>
            </div>
          )}

          {error && (
            <div className={styles.stateCard}>
              <p style={{ color: "#dc2626", fontWeight: 600 }}>{error}</p>
              <button type="button" className={styles.backButton} onClick={onClose}>
                Return to Search Results
              </button>
            </div>
          )}

          {!loading && !error && data && (
            <>
              {/* Relevance Explanation */}
              <div className={styles.relevanceCard}>
                <div className={styles.relevanceHeader}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="16" x2="12" y2="12" />
                    <line x1="12" y1="8" x2="12.01" y2="8" />
                  </svg>
                  Why this source is relevant
                </div>
                <p className={styles.relevanceText}>{data.relevance_explanation}</p>
              </div>

              {/* Provenance Metadata Grid */}
              <div className={styles.metaGrid}>
                <div className={styles.metaField}>
                  <span className={styles.metaLabel}>Source Document</span>
                  <span className={styles.metaValue}>{data.document_name}</span>
                </div>
                <div className={styles.metaField}>
                  <span className={styles.metaLabel}>Document Type</span>
                  <div>
                    {data.document_type === "excel" ? (
                      <span className={styles.badgeExcel}>Excel Workbook</span>
                    ) : data.document_type === "pdf" ? (
                      <span className={styles.badgePdf}>PDF Document</span>
                    ) : (
                      <span className={styles.metaValue}>{data.document_type}</span>
                    )}
                  </div>
                </div>

                {data.sheet_name && (
                  <div className={styles.metaField}>
                    <span className={styles.metaLabel}>Sheet Name</span>
                    <span className={styles.metaValue}>{data.sheet_name}</span>
                  </div>
                )}

                {data.row_number !== null && data.row_number !== undefined && (
                  <div className={styles.metaField}>
                    <span className={styles.metaLabel}>Row Number</span>
                    <span className={styles.metaValue}>Row {data.row_number}</span>
                  </div>
                )}

                {data.page_number !== null && data.page_number !== undefined && (
                  <div className={styles.metaField}>
                    <span className={styles.metaLabel}>Page Number</span>
                    <span className={styles.metaValue}>Page {data.page_number}</span>
                  </div>
                )}

                {data.cell_or_range && (
                  <div className={styles.metaField}>
                    <span className={styles.metaLabel}>Cell / Range</span>
                    <span className={styles.metaValue}>{data.cell_or_range}</span>
                  </div>
                )}
              </div>

              {/* PDF Bounding Box Highlight Coordinates */}
              {data.bbox && data.bbox.length === 4 && (
                <div className={styles.bboxCard}>
                  <div className={styles.bboxLabel}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="3" width="18" height="18" rx="2" />
                      <line x1="9" y1="3" x2="9" y2="21" />
                    </svg>
                    Region Coordinates (Page {data.page_number || 1})
                  </div>
                  <div className={styles.bboxValue}>
                    x0: {data.bbox[0]}, y0: {data.bbox[1]}, x1: {data.bbox[2]}, y1: {data.bbox[3]}
                  </div>
                </div>
              )}

              {/* Excel: Surrounding Rows Table */}
              {data.surrounding_rows && data.surrounding_rows.length > 0 && (
                <div>
                  <h4 className={styles.sectionTitle}>
                    <span>Surrounding Rows in Workbook</span>
                    <span style={{ fontSize: "0.8125rem", color: "#64748b", fontWeight: 400 }}>
                      Sheet: {data.sheet_name}
                    </span>
                  </h4>
                  <div className={styles.tableWrapper}>
                    <table className={styles.previewTable}>
                      <thead>
                        <tr>
                          <th>Row #</th>
                          {Object.keys(data.surrounding_rows[0].data || {}).map((col) => (
                            <th key={col}>{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {data.surrounding_rows.map((row) => (
                          <tr key={row.row_number} className={row.is_target ? styles.targetRow : undefined}>
                            <td>
                              <strong>{row.row_number}</strong>
                              {row.is_target && <span className={styles.targetRowBadge}>Target</span>}
                            </td>
                            {Object.keys(data.surrounding_rows![0].data || {}).map((col) => (
                              <td key={col}>{row.data[col] !== undefined ? String(row.data[col]) : "—"}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Parsed Record Key-Values (if surrounding rows not available or for single record) */}
              {(!data.surrounding_rows || data.surrounding_rows.length === 0) && data.parsed_content && (
                <div>
                  <h4 className={styles.sectionTitle}>Extracted Row Data</h4>
                  <div className={styles.tableWrapper}>
                    <table className={styles.previewTable}>
                      <thead>
                        <tr>
                          <th>Column / Field</th>
                          <th>Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(data.parsed_content).map(([k, v]) => (
                          <tr key={k}>
                            <td><strong>{k}</strong></td>
                            <td>{v !== null && v !== undefined ? String(v) : "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* PDF: Page Text Excerpt / Extracted Content */}
              {data.document_type === "pdf" && (data.page_text_excerpt || data.raw_content) && (
                <div>
                  <h4 className={styles.sectionTitle}>
                    <span>Extracted Page Content</span>
                    {data.page_number && (
                      <span style={{ fontSize: "0.8125rem", color: "#64748b", fontWeight: 400 }}>
                        Page {data.page_number}
                      </span>
                    )}
                  </h4>
                  <div className={styles.textSnippet}>
                    {data.page_text_excerpt || data.raw_content}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Modal Footer */}
        <div className={styles.footer}>
          <button type="button" className={styles.backButton} onClick={onClose}>
            Back to Results
          </button>
        </div>
      </div>
    </div>
  );
}
