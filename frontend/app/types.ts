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
