export interface IngestionResponse {
  document_id: string | null;
  version_id: string | null;
  filename: string;
  content_hash: string;
  // Excel fields
  sheets_discovered?: string[];
  records_processed?: number;
  records_accepted?: number;
  records_requiring_review?: number;
  // PDF fields
  page_count?: number;
  pages_processed?: number;
  tables_detected?: number;
  structured_records_created?: number;
  records_needing_review?: number;
  // Common
  review_items?: Array<{
    page?: number;
    row?: number;
    status?: string;
    reason?: string;
  }>;
  errors?: string[];
  duplicate_status: "new" | "duplicate";
  file_size?: number;
  uploaded_at?: string;
}

export type DisplayStatus = "Imported" | "Needs Review" | "Approved" | "Duplicate" | "Failed";

export interface SearchCalculation {
  operation: string;
  value?: number | null;
  unit?: string | null;
  records_counted: number;
  formula_description?: string | null;
  breakdown?: string | null;
}

export interface SourceReferenceInfo {
  id?: string | null;
  document_id?: string | null;
  document_name?: string | null;
  document_version?: number | null;
  document_type?: string | null;
  page_number?: number | null;
  sheet_name?: string | null;
  row_number?: number | null;
  cell_or_range?: string | null;
  bbox?: number[] | null;
  source_text?: string | null;
}

export interface SearchResult {
  original_question: string;
  interpreted_query: Record<string, any>;
  status: "success" | "no_results" | "clarification_required" | "needs_review" | "error";
  answer: string;
  records: Array<Record<string, any>>;
  total_records: number;
  calculation?: SearchCalculation | null;
  source_references: SourceReferenceInfo[];
  clarification_required: boolean;
  clarification_question?: string | null;
  warnings: string[];
}

export interface SourcePreviewData {
  id?: string | null;
  source_id: string;
  document_id?: string | null;
  document_name: string;
  document_version?: number | null;
  document_type: string;
  page_number?: number | null;
  sheet_name?: string | null;
  row_number?: number | null;
  cell_or_range?: string | null;
  bbox?: number[] | null;
  parsed_content?: Record<string, any> | null;
  raw_content?: string | null;
  surrounding_rows?: Array<{
    row_number: number;
    is_target: boolean;
    data: Record<string, any>;
  }> | null;
  page_text_excerpt?: string | null;
  relevance_explanation: string;
  associated_records?: Array<Record<string, any>>;
}

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  full_name?: string | null;
  role: "admin" | "reviewer" | "uploader" | "viewer";
  permissions: string[];
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

export type ReportType = "monthly" | "attendance_summary" | "duty_summary" | "vehicle_report";

export interface ReportItem {
  id: string;
  name: string;
  report_type: ReportType;
  reporting_period_start?: string | null;
  reporting_period_end?: string | null;
  status: string;
  created_by: string;
  created_at?: string | null;
  updated_at?: string | null;
  export_xlsx_url?: string | null;
  export_csv_url?: string | null;
}

export interface ReportDetail extends ReportItem {
  summary_kpis?: Record<string, any> | null;
  generated_files?: Record<string, any> | null;
}

export interface ReportCreateRequest {
  report_type: ReportType;
  name?: string | null;
  reporting_period_start?: string | null;
  reporting_period_end?: string | null;
  satsang_ghar_id?: string | null;
  formats?: string[];
}

export interface DocumentItem {
  id: string;
  original_filename: string;
  document_type?: string | null;
  status: string;
  data_source_name?: string | null;
  created_at: string;
  updated_at: string;
  version_count: number;
  total_records: number;
  valid_count: number;
  needs_review_count: number;
  invalid_count: number;
  warnings_count: number;
  errors_count: number;
  validation_status: string;
}

export interface ValidationIssueItem {
  issue_type: string;
  severity: "error" | "warning" | "info" | string;
  message: string;
  record_type?: string | null;
  record_id?: string | null;
  source_reference_id?: string | null;
  page_number?: number | null;
  sheet_name?: string | null;
  row_number?: number | null;
  cell_or_range?: string | null;
  raw_value?: string | null;
  extracted_value?: Record<string, any> | null;
  record_details?: Record<string, any> | null;
  document_name?: string | null;
}

export interface ReviewHistoryItem {
  id: string;
  action: string;
  reviewer_name: string;
  notes?: string | null;
  reason?: string | null;
  instructions?: string | null;
  timestamp: string;
}

export interface DocumentRecordItem {
  record_type: string;
  record_id: string;
  date?: string | null;
  satsang_ghar_id?: string | null;
  source_reference_id?: string | null;
  sheet_name?: string | null;
  row_number?: number | null;
  page_number?: number | null;
  details?: Record<string, any>;
}

export interface ValidationResultData {
  document_id: string;
  document_name?: string | null;
  version_id?: string | null;
  validation_status: string;
  total_records_examined: number;
  valid_count: number;
  needs_review_count: number;
  invalid_count: number;
  warnings_count: number;
  errors_count: number;
  validation_timestamp: string;
  issues: ValidationIssueItem[];
  review_history?: ReviewHistoryItem[] | null;
}

// ============================================================================
// Phase 3.0 — Multi-Document Analytics & Comparison Types
// ============================================================================

export type ComparisonDimension = "location" | "period";
export type ComparisonMetric = "attendance" | "vehicle_wheel" | "assignment";

export interface ComparisonRequest {
  dimension: ComparisonDimension;
  metric: ComparisonMetric;
  sub_metric?: string | null;
  // Location comparison
  entity_a?: string | null;
  entity_b?: string | null;
  shared_period_start?: string | null;
  shared_period_end?: string | null;
  // Period comparison
  satsang_ghar?: string | null;
  period_a_start?: string | null;
  period_a_end?: string | null;
  period_b_start?: string | null;
  period_b_end?: string | null;
}

export interface EntityMetricSummary {
  label: string;
  primary_value: number;
  secondary_value?: number | null;
  record_count: number;
  document_count: number;
  document_names: string[];
  breakdown_items: Array<Record<string, any>>;
}

export interface ComparisonResponse {
  metric: string;
  dimension: string;
  unit: string;
  entity_a: EntityMetricSummary;
  entity_b: EntityMetricSummary;
  delta: number;
  percentage_change?: number | null;
  summary_sentence: string;
  breakdown_text: string;
  source_references: SourceReferenceInfo[];
  warnings: string[];
}

export interface MultiDocSummaryRequest {
  date_start?: string | null;
  date_end?: string | null;
  document_ids?: string[] | null;
}

export interface MultiDocSummaryResponse {
  total_documents: number;
  total_attendance: number;
  average_attendance: number;
  total_assignments: number;
  total_vehicles: number;
  period_start?: string | null;
  period_end?: string | null;
  per_document_breakdown: Array<{
    document_id: string;
    filename: string;
    document_type?: string | null;
    status: string;
    attendance_count: number;
    assignment_count: number;
    vehicle_count: number;
  }>;
}

export interface AnalyticsDimensionsResponse {
  dimensions: Array<{ value: string; label: string }>;
  metrics: Array<{ value: string; label: string }>;
  known_satsang_ghars: string[];
  available_months: Array<{ value: number; label: string }>;
}

