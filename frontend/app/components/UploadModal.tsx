"use client";

import React, { useRef, useState } from "react";
import { IngestionResponse } from "../types";
import styles from "./UploadModal.module.css";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (result: IngestionResponse) => void;
  acceptedFormat?: "excel" | "pdf" | "all";
}

export default function UploadModal({
  isOpen,
  onClose,
  onSuccess,
  acceptedFormat = "all",
}: UploadModalProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const acceptMime =
    acceptedFormat === "excel"
      ? ".xlsx, .xlsm, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel.sheet.macroEnabled.12"
      : acceptedFormat === "pdf"
      ? ".pdf, application/pdf"
      : ".xlsx, .xlsm, .pdf, application/pdf, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

  const formatTitle =
    acceptedFormat === "excel"
      ? "Upload Excel data"
      : acceptedFormat === "pdf"
      ? "Upload PDF document"
      : "Upload office data";

  const formatSubtitle =
    acceptedFormat === "excel"
      ? "Supported formats: .xlsx, .xlsm"
      : acceptedFormat === "pdf"
      ? "Supported formats: .pdf"
      : "Supported formats: .xlsx, .xlsm, .pdf";

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setErrorMessage(null);
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      validateAndSetFile(file);
    }
  };

  const validateAndSetFile = (file: File) => {
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    const validExcel = [".xlsx", ".xlsm"].includes(ext);
    const validPdf = ext === ".pdf";

    if (acceptedFormat === "excel" && !validExcel) {
      setErrorMessage("Please select a valid Excel file (.xlsx or .xlsm).");
      return;
    }
    if (acceptedFormat === "pdf" && !validPdf) {
      setErrorMessage("Please select a valid PDF file (.pdf).");
      return;
    }
    if (!validExcel && !validPdf) {
      setErrorMessage("Unsupported file format. Please upload an Excel (.xlsx, .xlsm) or PDF (.pdf) file.");
      return;
    }

    setSelectedFile(file);
    setErrorMessage(null);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getFileTypeLabel = (fileName: string): string => {
    const ext = fileName.slice(fileName.lastIndexOf(".")).toLowerCase();
    if (ext === ".xlsx") return "Excel Workbook (.xlsx)";
    if (ext === ".xlsm") return "Excel Macro-Enabled Workbook (.xlsm)";
    if (ext === ".pdf") return "PDF Document (.pdf)";
    return ext.toUpperCase();
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setErrorMessage(null);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("data_source_name", "Web UI Upload");

      // Try relative API endpoint via Next.js rewrite or direct backend
      let response = await fetch("/api/v1/documents/upload", {
        method: "POST",
        body: formData,
      });

      // Fallback directly to localhost:8000 if rewrite proxy fails
      if (!response.ok && response.status === 404) {
        response = await fetch("http://127.0.0.1:8000/api/v1/documents/upload", {
          method: "POST",
          body: formData,
        });
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const detail = errorData?.detail || `Upload failed with status ${response.status}`;
        throw new Error(detail);
      }

      const result: IngestionResponse = await response.json();
      result.file_size = selectedFile.size;
      result.uploaded_at = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

      setSelectedFile(null);
      onSuccess(result);
      onClose();
    } catch (err: any) {
      const friendlyMsg =
        err?.message?.includes("Unsupported file format")
          ? "Unsupported file format. Please upload an Excel (.xlsx, .xlsm) or PDF (.pdf) file."
          : err?.message?.includes("Failed to fetch")
          ? "Cannot connect to the office server. Please verify the backend service is running."
          : err?.message || "An unexpected error occurred during upload. Please try again.";
      setErrorMessage(friendlyMsg);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-title"
      onClick={onClose}
    >
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h2 id="upload-title" className={styles.title}>
            {formatTitle}
          </h2>
          <button
            type="button"
            className={styles.closeButton}
            onClick={onClose}
            aria-label="Close upload dialog"
            disabled={isUploading}
          >
            &times;
          </button>
        </div>

        <p className={styles.subtitle}>{formatSubtitle}</p>

        {errorMessage && (
          <div className={styles.errorAlert} role="alert">
            <span className={styles.errorIcon} aria-hidden="true">
              !
            </span>
            <span>{errorMessage}</span>
          </div>
        )}

        <div
          className={styles.dropZone}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onClick={() => !isUploading && fileInputRef.current?.click()}
          tabIndex={0}
          role="button"
          aria-label="Select file to upload"
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={acceptMime}
            onChange={handleFileChange}
            className={styles.hiddenInput}
            aria-hidden="true"
            tabIndex={-1}
          />
          <div className={styles.dropPrompt}>
            <span className={styles.uploadIcon} aria-hidden="true">
              &#8679;
            </span>
            <p className={styles.dropText}>
              <strong>Click to choose a file</strong> or drag and drop here
            </p>
            <p className={styles.dropNote}>Office documents up to 50MB</p>
          </div>
        </div>

        {selectedFile && (
          <div className={styles.fileDetails} aria-live="polite">
            <div className={styles.fileInfo}>
              <span className={styles.fileName}>{selectedFile.name}</span>
              <span className={styles.fileMeta}>
                {getFileTypeLabel(selectedFile.name)} &bull; {formatFileSize(selectedFile.size)}
              </span>
            </div>
          </div>
        )}

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.cancelButton}
            onClick={onClose}
            disabled={isUploading}
          >
            Cancel
          </button>
          <button
            type="button"
            className={styles.uploadButton}
            onClick={handleUpload}
            disabled={!selectedFile || isUploading}
          >
            {isUploading ? "Uploading & Processing..." : "Upload Document"}
          </button>
        </div>
      </div>
    </div>
  );
}
