"use client";

import React, { useEffect, useState } from "react";
import Header from "./components/Header";
import LoginScreen from "./components/LoginScreen";
import ReportsModal from "./components/ReportsModal";
import ReviewWorkspaceModal from "./components/ReviewWorkspaceModal";
import AnalyticsModal from "./components/AnalyticsModal";
import DashboardModal from "./components/DashboardModal";
import SearchResultCard from "./components/SearchResultCard";
import SourcePreviewModal from "./components/SourcePreviewModal";
import UploadModal from "./components/UploadModal";
import UploadResultCard from "./components/UploadResultCard";
import { fetchCurrentUser, getAuthHeaders, getStoredUser } from "./auth";
import { AuthUser, IngestionResponse, SearchResult } from "./types";
import styles from "./page.module.css";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function Home() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [authChecking, setAuthChecking] = useState<boolean>(true);

  const [modalOpen, setModalOpen] = useState(false);
  const [modalFormat, setModalFormat] = useState<"excel" | "pdf" | "all">("all");
  const [reportsModalOpen, setReportsModalOpen] = useState(false);
  const [reviewWorkspaceOpen, setReviewWorkspaceOpen] = useState(false);
  const [analyticsModalOpen, setAnalyticsModalOpen] = useState(false);
  const [dashboardModalOpen, setDashboardModalOpen] = useState(false);
  const [uploadHistory, setUploadHistory] = useState<IngestionResponse[]>([]);

  useEffect(() => {
    // Check initial cached session
    const cached = getStoredUser();
    if (cached) {
      setCurrentUser(cached);
    }
    // Verify session validity with backend
    fetchCurrentUser()
      .then((user) => {
        setCurrentUser(user);
      })
      .catch(() => {
        setCurrentUser(null);
      })
      .finally(() => {
        setAuthChecking(false);
      });
  }, []);

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
          ...getAuthHeaders(),
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

  const handleClearSearch = () => {
    setSearchQuery("");
    setSearchResult(null);
    setSearchError(null);
  };

  if (authChecking) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "var(--bg-primary)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: "var(--brand-maroon)", display: "inline-block" }} />
          <span style={{ color: "var(--brand-maroon)", fontWeight: 600 }}>Loading RSSB Office Platform...</span>
        </div>
      </div>
    );
  }

  if (!currentUser) {
    return <LoginScreen onLoginSuccess={(u) => setCurrentUser(u)} />;
  }

  return (
    <div className={styles.page}>
      <Header
        user={currentUser}
        onLogout={() => setCurrentUser(null)}
        onUserChange={(u) => setCurrentUser(u)}
      />

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
                onSelectSuggestion={(q) => {
                  setSearchQuery(q);
                  executeSearch(q);
                }}
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
              <button
                type="button"
                className={styles.reportButton}
                onClick={() => setReportsModalOpen(true)}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
                Office Reports & Exports
              </button>
              <button
                type="button"
                className={styles.reviewWorkspaceBtn}
                onClick={() => setReviewWorkspaceOpen(true)}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 11l3 3L22 4" />
                  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                </svg>
                Document Review & Validation
              </button>
              <button
                type="button"
                className={styles.analyticsBtn}
                onClick={() => setAnalyticsModalOpen(true)}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 20V10" />
                  <path d="M12 20V4" />
                  <path d="M6 20v-6" />
                </svg>
                Multi-Doc Analytics & Comparison
              </button>
              <button
                type="button"
                className={styles.dashboardBtn}
                onClick={() => setDashboardModalOpen(true)}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
                  <polyline points="17 6 23 6 23 12" />
                </svg>
                Executive Dashboard & Trends
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

      {/* Office Reports & Data Export Modal */}
      <ReportsModal
        isOpen={reportsModalOpen}
        onClose={() => setReportsModalOpen(false)}
        user={currentUser}
      />

      {/* Document Review & Validation Workspace Modal */}
      <ReviewWorkspaceModal
        isOpen={reviewWorkspaceOpen}
        onClose={() => setReviewWorkspaceOpen(false)}
        user={currentUser}
      />

      {/* Multi-Document Analytics & Comparison Modal */}
      <AnalyticsModal
        isOpen={analyticsModalOpen}
        onClose={() => setAnalyticsModalOpen(false)}
        user={currentUser}
      />

      {/* Visual Analytics & Executive Dashboard Modal */}
      <DashboardModal
        isOpen={dashboardModalOpen}
        onClose={() => setDashboardModalOpen(false)}
        user={currentUser}
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

