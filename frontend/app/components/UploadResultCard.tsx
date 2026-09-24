"use client";

import React from "react";
import { DisplayStatus, IngestionResponse } from "../types";
import styles from "./UploadResultCard.module.css";

interface UploadResultCardProps {
  result: IngestionResponse;
  onUploadAnother: () => void;
}

export default function UploadResultCard({
  result,
  onUploadAnother,
}: UploadResultCardProps) {
  // Determine display status
  let displayStatus: DisplayStatus = "Imported";

  if (result.duplicate_status === "duplicate") {
    displayStatus = "Duplicate";
  } else if (
    (result.records_requiring_review && result.records_requiring_review > 0) ||
    (result.records_needing_review && result.records_needing_review > 0) ||
    (result.review_items && result.review_items.length > 0)
  ) {
    displayStatus = "Needs Review";
  } else if (result.errors && result.errors.length > 0) {
    displayStatus = "Needs Review";
  }

  // Compute metrics
  const processed =
    result.records_processed !== undefined
      ? result.records_processed
      : result.structured_records_created !== undefined
      ? result.structured_records_created + (result.records_needing_review || 0)
      : 0;

  const accepted =
    result.records_accepted !== undefined
      ? result.records_accepted
      : result.structured_records_created !== undefined
      ? result.structured_records_created
      : 0;

  const reviewCount =
    result.records_requiring_review !== undefined
      ? result.records_requiring_review
      : result.records_needing_review !== undefined
      ? result.records_needing_review
      : (result.review_items && result.review_items.length) || 0;

  const pagesOrSheets =
    result.sheets_discovered && result.sheets_discovered.length > 0
      ? `${result.sheets_discovered.length} sheet${result.sheets_discovered.length > 1 ? "s" : ""} (${result.sheets_discovered.join(", ")})`
      : result.page_count !== undefined && result.page_count > 0
      ? `${result.page_count} page${result.page_count > 1 ? "s" : ""}`
      : "1 document";

  const statusClass =
    displayStatus === "Imported"
      ? styles.statusValid
      : displayStatus === "Needs Review"
      ? styles.statusReview
      : displayStatus === "Duplicate"
      ? styles.statusDuplicate
      : styles.statusError;

  return (
    <article className={styles.card} aria-label={`Ingestion result for ${result.filename}`}>
      <div className={styles.header}>
        <div className={styles.fileHeader}>
          <h3 className={styles.fileName}>{result.filename}</h3>
          <span className={`${styles.statusBadge} ${statusClass}`}>{displayStatus}</span>
        </div>
        <button
          type="button"
          className={styles.anotherButton}
          onClick={onUploadAnother}
        >
          Upload another file
        </button>
      </div>

      {displayStatus === "Duplicate" && (
        <p className={styles.duplicateNote}>
          This exact file has already been ingested. The existing document version and records were preserved.
        </p>
      )}

      {displayStatus === "Needs Review" && (
        <p className={styles.reviewNote}>
          This file was imported, but certain columns, approximate values, or records have been flagged for office review.
        </p>
      )}

      <dl className={styles.metricsGrid}>
        <div className={styles.metricItem}>
          <dt className={styles.metricLabel}>Records processed</dt>
          <dd className={styles.metricValue}>{processed}</dd>
        </div>
        <div className={styles.metricItem}>
          <dt className={styles.metricLabel}>Records accepted</dt>
          <dd className={styles.metricValue}>{accepted}</dd>
        </div>
        <div className={styles.metricItem}>
          <dt className={styles.metricLabel}>Records needing review</dt>
          <dd className={styles.metricValue}>{reviewCount}</dd>
        </div>
        <div className={styles.metricItem}>
          <dt className={styles.metricLabel}>Sheets / pages</dt>
          <dd className={styles.metricValue}>{pagesOrSheets}</dd>
        </div>
        <div className={styles.metricItem}>
          <dt className={styles.metricLabel}>Source provenance</dt>
          <dd className={styles.metricValue}>Verified in PostgreSQL</dd>
        </div>
        <div className={styles.metricItem}>
          <dt className={styles.metricLabel}>Content hash (SHA-256)</dt>
          <dd className={styles.metricHash} title={result.content_hash}>
            {result.content_hash.slice(0, 16)}...
          </dd>
        </div>
      </dl>

      {result.review_items && result.review_items.length > 0 && (
        <div className={styles.reviewSection}>
          <h4 className={styles.reviewHeader}>Items Flagged for Review</h4>
          <ul className={styles.reviewList}>
            {result.review_items.map((item, idx) => (
              <li key={idx} className={styles.reviewItem}>
                <span className={styles.reviewReason}>
                  {item.reason || `Review required on row ${item.row || "?"}`}
                </span>
                {(item.page || item.row) && (
                  <span className={styles.reviewLocation}>
                    {item.page ? `Page ${item.page}` : ""}
                    {item.page && item.row ? ", " : ""}
                    {item.row ? `Row ${item.row}` : ""}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
