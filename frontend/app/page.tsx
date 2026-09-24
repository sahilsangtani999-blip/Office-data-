"use client";

import React, { useState } from "react";
import Header from "./components/Header";
import SearchResultCard from "./components/SearchResultCard";
import SourcePreviewModal from "./components/SourcePreviewModal";
import UploadModal from "./components/UploadModal";
import UploadResultCard from "./components/UploadResultCard";
import { IngestionResponse, SearchResult } from "./types";
import styles from "./page.module.css";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const SAMPLE_QUERIES = [
  "What was the average attendance at Sukhliya in September?",
  "Show attendance for Sukhliya in September",
  "Show attendance for Model Town",
  "What was the total attendance for Sukhliya in September?",
  "Find assignment at Sukhliya on 2026-09-06",
  "Lookup VIDEO CD",
  "What was the highest attendance?",
];

export default function Home() {
  const [modalOpen, setModalOpen] = useState(false);
  const [modalFormat, setModalFormat] = useState<"excel" | "pdf" | "all">("all");
  const [uploadHistory, setUploadHistory] = useState<IngestionResponse[]>([]);

  // Search states
  const [searchQuery, setSearchQuery] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResult, setSearchResult] = useState<SearchResult | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);

  const handleOpenUpload = (format: "excel" | "pdf" | "all") => {
    setModalFormat(format);
    setModalOpen(true);
  };

  const handleUploadSuccess = (result: IngestionResponse) => {
    setUploadHistory((prev) => [result, ...prev]);
  };

  const executeSearch = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed) return;

    setSearchLoading(true);
    setSearchError(null);
    setSearchResult(null);

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/query`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: trimmed }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        throw new Error(errorData?.detail || `Search failed with status ${res.status}`);
      }

      const data: SearchResult = await res.json();
      setSearchResult(data);
    } catch (err: any) {
      setSearchError(err.message || "Failed to execute search. Is the backend server running?");
    } finally {
      setSearchLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    executeSearch(searchQuery);
  };

  const handleSelectSample = (sample: string) => {
    setSearchQuery(sample);
    executeSearch(sample);
  };

  const handleClearSearch = () => {
    setSearchQuery("");
    setSearchResult(null);
    setSearchError(null);
  };

  return (
    <div className={styles.page}>
      <Header />

      <main className={styles.main}>
        <div className={styles.contentContainer}>
          {/* Main Heading & Search Bar */}
          <section className={styles.heroSection} aria-labelledby="main-heading">
            <h2 id="main-heading" className={styles.mainHeading}>
              Search your office data
            </h2>

            <div className={styles.searchWrapper}>
              <form onSubmit={handleSubmit} className={styles.searchForm}>
                <div className={styles.searchInputContainer}>
                  <label htmlFor="office-search" className="sr-only">
                    Ask anything about your office data
                  </label>
                  <input
                    id="office-search"
                    type="text"
                    className={styles.searchInput}
                    placeholder="Ask anything about your office data (e.g. average attendance, duty assignments)..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    disabled={searchLoading}
                  />

                  <div className={styles.searchInputButtons}>
                    {searchQuery && !searchLoading && (
                      <button
                        type="button"
                        className={styles.searchClearBtn}
                        onClick={handleClearSearch}
                        aria-label="Clear search input"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      </button>
                    )}

                    <button
                      type="submit"
                      className={styles.searchSubmitBtn}
                      disabled={searchLoading || !searchQuery.trim()}
                      aria-label="Search"
                    >
                      {searchLoading ? (
                        <div className={styles.spinner} />
                      ) : (
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="11" cy="11" r="8" />
                          <line x1="21" y1="21" x2="16.65" y2="16.65" />
                        </svg>
                      )}
                      <span>Search</span>
                    </button>
                  </div>
                </div>

                {/* Example Query Chips */}
                <div className={styles.chipsContainer}>
                  <span className={styles.chipsLabel}>Examples:</span>
                  {SAMPLE_QUERIES.map((sample, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className={styles.chip}
                      onClick={() => handleSelectSample(sample)}
                      disabled={searchLoading}
                    >
                      {sample}
                    </button>
                  ))}
                </div>
              </form>
            </div>

            {/* Loading Indicator */}
            {searchLoading && (
              <div className={styles.searchLoading} role="status" aria-live="polite">
                <div className={styles.spinner} />
                <span>Searching verified office records...</span>
              </div>
            )}

            {/* Error Message */}
            {searchError && (
              <div className={styles.card} role="alert" style={{ marginTop: "20px" }}>
                <p style={{ color: "#c5221f", margin: 0, fontWeight: 500 }}>
                  {searchError}
                </p>
              </div>
            )}

            {/* Search Result Card */}
            {searchResult && (
              <SearchResultCard
                result={searchResult}
                onSelectSuggestion={(q) => handleSelectSample(q)}
                onViewSource={(sourceId) => setSelectedSourceId(sourceId)}
              />
            )}
          </section>

          {/* Upload Action Section */}
          <section className={styles.uploadSection} aria-labelledby="upload-heading">
            <h3 id="upload-heading" className={styles.uploadHeading}>
              Upload office data
            </h3>
            <p className={styles.uploadDescription}>
              Select and import verified Excel schedules, attendance sheets, or PDF records into the platform.
            </p>

            <div className={styles.buttonGroup}>
              <button
                type="button"
                className={styles.primaryButton}
                onClick={() => handleOpenUpload("excel")}
              >
                Upload Excel
              </button>
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={() => handleOpenUpload("pdf")}
              >
                Upload PDF
              </button>
            </div>
          </section>

          {/* Recent Activity / Status Area */}
          <section className={styles.activitySection} aria-labelledby="activity-heading">
            <h3 id="activity-heading" className={styles.activityHeading}>
              Recent uploads
            </h3>

            {uploadHistory.length === 0 ? (
              <div className={styles.emptyState}>
                <p className={styles.emptyText}>No office data uploaded yet.</p>
                <p className={styles.emptySubtext}>
                  Uploaded Excel files and PDF documents will appear here with verification details.
                </p>
              </div>
            ) : (
              <div className={styles.resultsList}>
                {uploadHistory.map((item, index) => (
                  <UploadResultCard
                    key={`${item.content_hash}-${index}`}
                    result={item}
                    onUploadAnother={() => handleOpenUpload("all")}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      </main>

      {/* Upload Modal */}
      <UploadModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onSuccess={handleUploadSuccess}
        acceptedFormat={modalFormat}
      />

      {/* Source Verification Preview Modal */}
      {selectedSourceId && (
        <SourcePreviewModal
          sourceId={selectedSourceId}
          onClose={() => setSelectedSourceId(null)}
        />
      )}
    </div>
  );
}
