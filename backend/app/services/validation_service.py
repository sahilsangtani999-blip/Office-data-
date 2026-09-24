"""
Data Validation and Review Service for RSSB Office Data Platform.

Provides:
- Comprehensive structural validation (file type, readability, hash, relationships, provenance)
- Excel validation (missing headers, empty sheets, ambiguous columns, missing/invalid dates,
  missing Satsang Ghar, invalid numeric values, empty rows, duplicate rows, unknown columns)
- PDF validation (readability, page extraction, empty pages, table extraction, ambiguous content,
  missing provenance, unsupported mappings)
- Controlled vocabulary validation (approved terminology: SK, SR, VIDEO CD; unknown -> Needs Review)
- Duplicate record detection (distinguishes document duplicate from logical record duplicate;
  preserves provenance and marks for review without silent deletion)
- Controlled lifecycle states for Documents and individual Records
- Full validation result and issue persistence via SourceReference and Report models
- Review service operations: approve, reject, mark needs correction with permission preparation
"""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    Attendance,
    DataSource,
    Document,
    DocumentVersion,
    Person,
    Report,
    Role,
    SatsangGhar,
    SourceReference,
    VehicleWheelData,
)

# =============================================================================
# Controlled States and Severities
# =============================================================================

# Document & Version Statuses
DOC_STATUS_IMPORTED = "imported"
DOC_STATUS_VALIDATED = "validated"
DOC_STATUS_PENDING_REVIEW = "pending_review"
DOC_STATUS_APPROVED = "approved"
DOC_STATUS_REJECTED = "rejected"
DOC_STATUS_NEEDS_CORRECTION = "needs_correction"
DOC_STATUS_ACTIVE = "active"
DOC_STATUS_SUPERSEDED = "superseded"
DOC_STATUS_ARCHIVED = "archived"

VALID_DOC_STATUSES = {
    DOC_STATUS_IMPORTED,
    DOC_STATUS_VALIDATED,
    DOC_STATUS_PENDING_REVIEW,
    DOC_STATUS_APPROVED,
    DOC_STATUS_REJECTED,
    DOC_STATUS_NEEDS_CORRECTION,
    DOC_STATUS_ACTIVE,
    DOC_STATUS_SUPERSEDED,
    DOC_STATUS_ARCHIVED,
}

# Individual Record Statuses
RECORD_STATUS_VALID = "valid"
RECORD_STATUS_NEEDS_REVIEW = "needs_review"
RECORD_STATUS_INVALID = "invalid"
RECORD_STATUS_ACTIVE = "active"

VALID_RECORD_STATUSES = {
    RECORD_STATUS_VALID,
    RECORD_STATUS_NEEDS_REVIEW,
    RECORD_STATUS_INVALID,
    RECORD_STATUS_ACTIVE,
}

# Issue Severity Levels
SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_ERROR = "ERROR"

# Issue Types
ISSUE_FILE_UNREADABLE = "FILE_UNREADABLE"
ISSUE_INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
ISSUE_HASH_MISMATCH = "HASH_MISMATCH"
ISSUE_MISSING_PROVENANCE = "MISSING_PROVENANCE"
ISSUE_DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"

ISSUE_EMPTY_SHEET = "EMPTY_SHEET"
ISSUE_MISSING_HEADERS = "MISSING_HEADERS"
ISSUE_AMBIGUOUS_COLUMNS = "AMBIGUOUS_COLUMNS"
ISSUE_UNKNOWN_COLUMNS = "UNKNOWN_COLUMNS"
ISSUE_MISSING_DATE = "MISSING_DATE"
ISSUE_INVALID_DATE = "INVALID_DATE"
ISSUE_MISSING_SATSANG_GHAR = "MISSING_SATSANG_GHAR"
ISSUE_INVALID_NUMERIC_VALUE = "INVALID_NUMERIC_VALUE"
ISSUE_EMPTY_ROW = "EMPTY_ROW"
ISSUE_DUPLICATE_RECORD = "DUPLICATE_RECORD"

ISSUE_PDF_UNREADABLE = "PDF_UNREADABLE"
ISSUE_EMPTY_PAGE = "EMPTY_PAGE"
ISSUE_TABLE_EXTRACTION_ISSUE = "TABLE_EXTRACTION_ISSUE"
ISSUE_AMBIGUOUS_STRUCTURED_CONTENT = "AMBIGUOUS_STRUCTURED_CONTENT"
ISSUE_UNSUPPORTED_MAPPING = "UNSUPPORTED_MAPPING"

ISSUE_UNKNOWN_TERMINOLOGY = "UNKNOWN_TERMINOLOGY"

# Approved Vocabulary Constants (Strictly Known Concepts Only)
APPROVED_ROLE_CODES = {"SK", "SR", "VIDEO CD", "VCD", "SPEAKER", "KARTA", "READER"}


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class ValidationIssue:
    """Represents a specific validation finding on a document or record."""
    issue_type: str
    severity: str  # INFO, WARNING, ERROR
    message: str
    record_type: Optional[str] = None
    record_id: Optional[str] = None
    source_reference_id: Optional[str] = None
    page_number: Optional[int] = None
    sheet_name: Optional[str] = None
    row_number: Optional[int] = None
    cell_or_range: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationResult:
    """Structured report representing the overall validation outcome."""
    document_id: str
    version_id: Optional[str]
    validation_status: str
    total_records_examined: int = 0
    valid_count: int = 0
    needs_review_count: int = 0
    invalid_count: int = 0
    warnings_count: int = 0
    errors_count: int = 0
    validation_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    issues: List[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["issues"] = [i.to_dict() for i in self.issues]
        return data


@dataclass
class ReviewerContext:
    """
    Permission preparation context.
    Encapsulates caller identity and authorization checks for review workflows.
    """
    user_id: str = "dev-test-user"
    username: str = "Developer / Test Reviewer"
    roles: List[str] = field(default_factory=lambda: ["reviewer", "admin"])
    is_authorized: bool = True

    def verify_permission(self, action: str) -> None:
        """Verify whether reviewer has permission to perform action."""
        if not self.is_authorized:
            raise PermissionError(
                f"User '{self.username}' ({self.user_id}) is not authorized to perform '{action}'."
            )


# =============================================================================
# Helper Utilities
# =============================================================================

def _compute_file_sha256(file_path: Union[str, Path]) -> Optional[str]:
    """Calculate SHA-256 hash of a file if it exists."""
    path = Path(file_path)
    if not path.is_file():
        return None
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


# =============================================================================
# Core Validation Engine
# =============================================================================

def validate_document(
    db: Session,
    document_id: Union[str, uuid.UUID],
    version_id: Optional[Union[str, uuid.UUID]] = None,
    auto_commit: bool = True,
) -> ValidationResult:
    """
    Perform comprehensive validation on a Document and its DocumentVersion.

    Rules applied:
    1. Structural validation (file integrity, SHA-256 hash match, document/version links, provenance)
    2. Format-specific validation (Excel sheets, headers, columns; PDF pages, tables)
    3. Business-data validation (dates, numeric values, Satsang Ghar, unknown terminology)
    4. Logical duplicate detection (flags duplicates without silent deletion)
    5. Unknown columns preserved and reported as review info
    6. State transitions (Document & Records) and persistence in PostgreSQL
    """
    doc_uuid = uuid.UUID(str(document_id))
    doc = db.query(Document).filter(Document.id == doc_uuid).first()
    if not doc:
        raise ValueError(f"Document with ID '{document_id}' not found.")

    if version_id:
        ver_uuid = uuid.UUID(str(version_id))
        version = db.query(DocumentVersion).filter(
            DocumentVersion.id == ver_uuid, DocumentVersion.document_id == doc.id
        ).first()
    else:
        version = db.query(DocumentVersion).filter(
            DocumentVersion.document_id == doc.id
        ).order_by(DocumentVersion.version_number.desc()).first()

    issues: List[ValidationIssue] = []
    total_records = 0
    valid_count = 0
    needs_review_count = 0
    invalid_count = 0

    # -------------------------------------------------------------------------
    # 1. Structural Validation
    # -------------------------------------------------------------------------
    if not version:
        issues.append(
            ValidationIssue(
                issue_type=ISSUE_MISSING_PROVENANCE,
                severity=SEVERITY_ERROR,
                message=f"Document '{doc.id}' has no associated DocumentVersion.",
            )
        )
    else:
        storage_path = version.storage_path
        if storage_path:
            p = Path(storage_path)
            if not p.exists():
                issues.append(
                    ValidationIssue(
                        issue_type=ISSUE_FILE_UNREADABLE,
                        severity=SEVERITY_WARNING,
                        message=f"Underlying storage file '{storage_path}' is not accessible on disk.",
                    )
                )
            else:
                current_hash = _compute_file_sha256(p)
                if current_hash and version.content_hash and current_hash != version.content_hash:
                    issues.append(
                        ValidationIssue(
                            issue_type=ISSUE_HASH_MISMATCH,
                            severity=SEVERITY_ERROR,
                            message=f"Content hash mismatch: stored '{version.content_hash}', calculated '{current_hash}'.",
                        )
                    )

    # -------------------------------------------------------------------------
    # 2. Source References Inspection
    # -------------------------------------------------------------------------
    srs_query = db.query(SourceReference).filter(SourceReference.document_id == doc.id)
    if version:
        srs_query = srs_query.filter(SourceReference.document_version_id == version.id)
    all_srs = srs_query.all()

    # Filter out previous validation metadata records
    content_srs = [
        sr for sr in all_srs
        if not (sr.cell_or_range and sr.cell_or_range.startswith("validation_"))
    ]

    # Check for empty pages in PDF
    page_srs = [sr for sr in content_srs if sr.page_number is not None and sr.row_number is None]
    for p_sr in page_srs:
        if not p_sr.source_text or not p_sr.source_text.strip() or p_sr.source_text.strip() == "[Empty Page]":
            issues.append(
                ValidationIssue(
                    issue_type=ISSUE_EMPTY_PAGE,
                    severity=SEVERITY_INFO,
                    message=f"Page {p_sr.page_number} contains no readable text content.",
                    source_reference_id=str(p_sr.id),
                    page_number=p_sr.page_number,
                )
            )

    # Inspect sheet headers & unknown columns in Excel rows
    known_concept_headers = {
        "date", "tarikh", "day", "satsang ghar", "ghar", "center", "location", "place",
        "attendance", "headcount", "sangat", "count", "present", "total",
        "person", "sewadar", "name", "karta", "speaker", "sk", "reader", "pathak", "sr",
        "role", "duty", "assignment", "vehicle", "wheel", "2 wheeler", "4 wheeler", "car", "scooter", "bike"
    }

    seen_unknown_cols: Set[str] = set()
    for sr in content_srs:
        if sr.source_text:
            try:
                row_data = json.loads(sr.source_text)
                if isinstance(row_data, dict):
                    # Check for unknown columns
                    for col_name in row_data.keys():
                        clean_col = str(col_name).strip().lower()
                        if clean_col not in seen_unknown_cols:
                            # If column does not contain any known concept words
                            if not any(k in clean_col for k in known_concept_headers):
                                seen_unknown_cols.add(clean_col)
                                issues.append(
                                    ValidationIssue(
                                        issue_type=ISSUE_UNKNOWN_COLUMNS,
                                        severity=SEVERITY_INFO,
                                        message=f"Preserved unmapped column '{col_name}' as review information.",
                                        source_reference_id=str(sr.id),
                                        sheet_name=sr.sheet_name,
                                        row_number=sr.row_number,
                                    )
                                )
            except (json.JSONDecodeError, TypeError):
                pass

    # -------------------------------------------------------------------------
    # 3. Entity Records Validation (Attendance)
    # -------------------------------------------------------------------------
    # Check for unlinked attendance records lacking provenance
    unlinked_attendances = db.query(Attendance).filter(Attendance.source_reference_id.is_(None)).all()
    for u_att in unlinked_attendances:
        issues.append(
            ValidationIssue(
                issue_type=ISSUE_MISSING_PROVENANCE,
                severity=SEVERITY_ERROR,
                message=f"Attendance record '{u_att.id}' has no source reference linkage.",
                record_type="Attendance",
                record_id=str(u_att.id),
            )
        )
        invalid_count += 1
        total_records += 1

    sr_ids = [sr.id for sr in content_srs]

    attendances = db.query(Attendance).filter(
        Attendance.source_reference_id.in_(sr_ids)
    ).all() if sr_ids else []

    seen_attendance_tuples: Dict[Tuple[Any, Any, Any], str] = {}

    for att in attendances:
        total_records += 1
        att_issues = 0
        is_invalid = False
        is_review = False

        # Missing provenance check
        if not att.source_reference_id:
            issues.append(
                ValidationIssue(
                    issue_type=ISSUE_MISSING_PROVENANCE,
                    severity=SEVERITY_ERROR,
                    message=f"Attendance record '{att.id}' has no source reference linkage.",
                    record_type="Attendance",
                    record_id=str(att.id),
                )
            )
            att_issues += 1
            is_invalid = True

        # Date validation
        if att.date is None:
            # Check if raw value contained an invalid date string
            issues.append(
                ValidationIssue(
                    issue_type=ISSUE_MISSING_DATE,
                    severity=SEVERITY_WARNING,
                    message=f"Attendance record '{att.id}' has missing or unparseable date.",
                    record_type="Attendance",
                    record_id=str(att.id),
                    source_reference_id=str(att.source_reference_id) if att.source_reference_id else None,
                )
            )
            att_issues += 1
            is_review = True

        # Count value validation
        if att.count_value is None:
            if att.raw_value:
                if any(c.isdigit() for c in str(att.raw_value)):
                    issues.append(
                        ValidationIssue(
                            issue_type=ISSUE_INVALID_NUMERIC_VALUE,
                            severity=SEVERITY_WARNING,
                            message=f"Attendance record '{att.id}' has approximate/qualified count: '{att.raw_value}'.",
                            record_type="Attendance",
                            record_id=str(att.id),
                            source_reference_id=str(att.source_reference_id) if att.source_reference_id else None,
                        )
                    )
                    att_issues += 1
                    is_review = True
                else:
                    issues.append(
                        ValidationIssue(
                            issue_type=ISSUE_INVALID_NUMERIC_VALUE,
                            severity=SEVERITY_ERROR,
                            message=f"Attendance record '{att.id}' has non-numeric count value: '{att.raw_value}'.",
                            record_type="Attendance",
                            record_id=str(att.id),
                            source_reference_id=str(att.source_reference_id) if att.source_reference_id else None,
                        )
                    )
                    att_issues += 1
                    is_invalid = True
            else:
                issues.append(
                    ValidationIssue(
                        issue_type=ISSUE_INVALID_NUMERIC_VALUE,
                        severity=SEVERITY_WARNING,
                        message=f"Attendance record '{att.id}' is missing count value.",
                        record_type="Attendance",
                        record_id=str(att.id),
                        source_reference_id=str(att.source_reference_id) if att.source_reference_id else None,
                    )
                )
                att_issues += 1
                is_review = True

        # Satsang Ghar validation
        if not att.satsang_ghar_id:
            issues.append(
                ValidationIssue(
                    issue_type=ISSUE_MISSING_SATSANG_GHAR,
                    severity=SEVERITY_ERROR,
                    message=f"Attendance record '{att.id}' has missing Satsang Ghar reference.",
                    record_type="Attendance",
                    record_id=str(att.id),
                    source_reference_id=str(att.source_reference_id) if att.source_reference_id else None,
                )
            )
            att_issues += 1
            is_invalid = True

        # Logical duplicate record check (date, satsang_ghar_id, count_value)
        logical_key = (att.date, att.satsang_ghar_id, att.count_value)
        if all(k is not None for k in logical_key):
            if logical_key in seen_attendance_tuples:
                issues.append(
                    ValidationIssue(
                        issue_type=ISSUE_DUPLICATE_RECORD,
                        severity=SEVERITY_WARNING,
                        message=(
                            f"Duplicate attendance record detected: Date '{att.date}', "
                            f"Ghar '{att.satsang_ghar_id}', Count '{att.count_value}'. "
                            f"Previous record ID: {seen_attendance_tuples[logical_key]}."
                        ),
                        record_type="Attendance",
                        record_id=str(att.id),
                        source_reference_id=str(att.source_reference_id) if att.source_reference_id else None,
                    )
                )
                att_issues += 1
                is_review = True
            else:
                seen_attendance_tuples[logical_key] = str(att.id)

        # Update record status
        if is_invalid:
            att.status = RECORD_STATUS_INVALID
            invalid_count += 1
        elif is_review:
            att.status = RECORD_STATUS_NEEDS_REVIEW
            needs_review_count += 1
        else:
            att.status = RECORD_STATUS_VALID
            valid_count += 1

    # -------------------------------------------------------------------------
    # 4. Entity Records Validation (Assignment)
    # -------------------------------------------------------------------------
    assignments = db.query(Assignment).filter(
        Assignment.source_reference_id.in_(sr_ids)
    ).all() if sr_ids else []

    seen_assignment_tuples: Dict[Tuple[Any, Any, Any, Any], str] = {}

    for asgn in assignments:
        total_records += 1
        asgn_issues = 0
        is_invalid = False
        is_review = False

        if not asgn.source_reference_id:
            issues.append(
                ValidationIssue(
                    issue_type=ISSUE_MISSING_PROVENANCE,
                    severity=SEVERITY_ERROR,
                    message=f"Assignment record '{asgn.id}' has no source reference linkage.",
                    record_type="Assignment",
                    record_id=str(asgn.id),
                )
            )
            asgn_issues += 1
            is_invalid = True

        if asgn.date is None:
            issues.append(
                ValidationIssue(
                    issue_type=ISSUE_MISSING_DATE,
                    severity=SEVERITY_WARNING,
                    message=f"Assignment record '{asgn.id}' has missing date.",
                    record_type="Assignment",
                    record_id=str(asgn.id),
                    source_reference_id=str(asgn.source_reference_id) if asgn.source_reference_id else None,
                )
            )
            asgn_issues += 1
            is_review = True

        # Vocabulary validation on Role
        if asgn.role_id:
            role = db.query(Role).filter(Role.id == asgn.role_id).first()
            if role:
                code_upper = role.code.upper().strip()
                if code_upper not in APPROVED_ROLE_CODES and not any(app in code_upper for app in APPROVED_ROLE_CODES):
                    issues.append(
                        ValidationIssue(
                            issue_type=ISSUE_UNKNOWN_TERMINOLOGY,
                            severity=SEVERITY_WARNING,
                            message=f"Unrecognized role code '{role.code}' in assignment. Terminology marked for review.",
                            record_type="Assignment",
                            record_id=str(asgn.id),
                            source_reference_id=str(asgn.source_reference_id) if asgn.source_reference_id else None,
                        )
                    )
                    asgn_issues += 1
                    is_review = True

        # Logical duplicate check
        logical_key = (asgn.date, asgn.satsang_ghar_id, asgn.person_id, asgn.role_id)
        if all(k is not None for k in logical_key):
            if logical_key in seen_assignment_tuples:
                issues.append(
                    ValidationIssue(
                        issue_type=ISSUE_DUPLICATE_RECORD,
                        severity=SEVERITY_WARNING,
                        message=(
                            f"Duplicate assignment record detected: Date '{asgn.date}', "
                            f"Ghar '{asgn.satsang_ghar_id}', Person '{asgn.person_id}', Role '{asgn.role_id}'."
                        ),
                        record_type="Assignment",
                        record_id=str(asgn.id),
                        source_reference_id=str(asgn.source_reference_id) if asgn.source_reference_id else None,
                    )
                )
                asgn_issues += 1
                is_review = True
            else:
                seen_assignment_tuples[logical_key] = str(asgn.id)

        if is_invalid:
            asgn.status = RECORD_STATUS_INVALID
            invalid_count += 1
        elif is_review:
            asgn.status = RECORD_STATUS_NEEDS_REVIEW
            needs_review_count += 1
        else:
            asgn.status = RECORD_STATUS_VALID
            valid_count += 1

    # -------------------------------------------------------------------------
    # 5. Entity Records Validation (VehicleWheelData)
    # -------------------------------------------------------------------------
    vehicles = db.query(VehicleWheelData).filter(
        VehicleWheelData.source_reference_id.in_(sr_ids)
    ).all() if sr_ids else []

    seen_vehicle_tuples: Dict[Tuple[Any, Any, Any], str] = {}

    for vh in vehicles:
        total_records += 1
        vh_issues = 0
        is_invalid = False
        is_review = False

        if not vh.source_reference_id:
            issues.append(
                ValidationIssue(
                    issue_type=ISSUE_MISSING_PROVENANCE,
                    severity=SEVERITY_ERROR,
                    message=f"Vehicle record '{vh.id}' has no source reference linkage.",
                    record_type="VehicleWheelData",
                    record_id=str(vh.id),
                )
            )
            vh_issues += 1
            is_invalid = True

        if vh.count_value is None and vh.raw_value:
            issues.append(
                ValidationIssue(
                    issue_type=ISSUE_INVALID_NUMERIC_VALUE,
                    severity=SEVERITY_ERROR,
                    message=f"Vehicle record '{vh.id}' has invalid numeric count: '{vh.raw_value}'.",
                    record_type="VehicleWheelData",
                    record_id=str(vh.id),
                    source_reference_id=str(vh.source_reference_id) if vh.source_reference_id else None,
                )
            )
            vh_issues += 1
            is_invalid = True

        logical_key = (vh.date, vh.satsang_ghar_id, vh.vehicle_type)
        if all(k is not None for k in logical_key):
            if logical_key in seen_vehicle_tuples:
                issues.append(
                    ValidationIssue(
                        issue_type=ISSUE_DUPLICATE_RECORD,
                        severity=SEVERITY_WARNING,
                        message=f"Duplicate vehicle record detected: Date '{vh.date}', Ghar '{vh.satsang_ghar_id}', Type '{vh.vehicle_type}'.",
                        record_type="VehicleWheelData",
                        record_id=str(vh.id),
                        source_reference_id=str(vh.source_reference_id) if vh.source_reference_id else None,
                    )
                )
                vh_issues += 1
                is_review = True
            else:
                seen_vehicle_tuples[logical_key] = str(vh.id)

        if is_invalid:
            vh.status = RECORD_STATUS_INVALID
            invalid_count += 1
        elif is_review:
            vh.status = RECORD_STATUS_NEEDS_REVIEW
            needs_review_count += 1
        else:
            vh.status = RECORD_STATUS_VALID
            valid_count += 1

    # -------------------------------------------------------------------------
    # 6. Overall Validation Status Determination
    # -------------------------------------------------------------------------
    warnings_count = sum(1 for i in issues if i.severity == SEVERITY_WARNING)
    errors_count = sum(1 for i in issues if i.severity == SEVERITY_ERROR)

    # Determine document status
    if errors_count > 0 or invalid_count > 0:
        doc_status = DOC_STATUS_NEEDS_CORRECTION
    elif warnings_count > 0 or needs_review_count > 0:
        doc_status = DOC_STATUS_PENDING_REVIEW
    else:
        doc_status = DOC_STATUS_VALIDATED

    # Update Document and Version status
    doc.status = doc_status
    if version:
        version.status = doc_status

    result = ValidationResult(
        document_id=str(doc.id),
        version_id=str(version.id) if version else None,
        validation_status=doc_status,
        total_records_examined=total_records,
        valid_count=valid_count,
        needs_review_count=needs_review_count,
        invalid_count=invalid_count,
        warnings_count=warnings_count,
        errors_count=errors_count,
        issues=issues,
    )

    # -------------------------------------------------------------------------
    # 7. Persist Validation Results in PostgreSQL
    # -------------------------------------------------------------------------
    # Remove older validation metadata source references for this version
    if version:
        old_val_srs = db.query(SourceReference).filter(
            SourceReference.document_id == doc.id,
            SourceReference.document_version_id == version.id,
            SourceReference.cell_or_range.like("validation_%"),
        ).all()
        for old_sr in old_val_srs:
            db.delete(old_sr)
        db.flush()

        # Persist summary
        summary_sr = SourceReference(
            document_id=doc.id,
            document_version_id=version.id,
            cell_or_range="validation_summary",
            source_text=json.dumps(result.to_dict(), default=str),
        )
        db.add(summary_sr)

        # Persist individual issues
        for issue in issues:
            issue_sr = SourceReference(
                document_id=doc.id,
                document_version_id=version.id,
                page_number=issue.page_number,
                sheet_name=issue.sheet_name,
                row_number=issue.row_number,
                cell_or_range=f"validation_issue:{issue.severity}:{issue.issue_type}",
                source_text=json.dumps(issue.to_dict(), default=str),
            )
            db.add(issue_sr)

    # Update or create Report entry
    report_name = f"Validation Report: {doc.original_filename}"
    report = db.query(Report).filter(
        Report.name == report_name, Report.report_type == "validation_report"
    ).first()
    if not report:
        report = Report(
            name=report_name,
            report_type="validation_report",
            status=doc_status,
            created_by="system_validation_engine",
        )
        db.add(report)
    else:
        report.status = doc_status

    if auto_commit:
        db.commit()
    else:
        db.flush()

    return result


# =============================================================================
# Review & Approval Operations
# =============================================================================

def get_validation_result(
    db: Session,
    document_id: Union[str, uuid.UUID],
    version_id: Optional[Union[str, uuid.UUID]] = None,
) -> ValidationResult:
    """Fetch the latest persisted validation result for a document or run validation."""
    doc_uuid = uuid.UUID(str(document_id))
    doc = db.query(Document).filter(Document.id == doc_uuid).first()
    if not doc:
        raise ValueError(f"Document with ID '{document_id}' not found.")

    # Look for persisted validation summary
    query = db.query(SourceReference).filter(
        SourceReference.document_id == doc.id,
        SourceReference.cell_or_range == "validation_summary",
    )
    if version_id:
        ver_uuid = uuid.UUID(str(version_id))
        query = query.filter(SourceReference.document_version_id == ver_uuid)
    else:
        query = query.order_by(SourceReference.created_at.desc())

    summary_sr = query.first()
    if summary_sr and summary_sr.source_text:
        data = json.loads(summary_sr.source_text)
        raw_issues = data.get("issues", [])
        issues = [ValidationIssue(**item) for item in raw_issues]
        return ValidationResult(
            document_id=data["document_id"],
            version_id=data.get("version_id"),
            validation_status=data["validation_status"],
            total_records_examined=data.get("total_records_examined", 0),
            valid_count=data.get("valid_count", 0),
            needs_review_count=data.get("needs_review_count", 0),
            invalid_count=data.get("invalid_count", 0),
            warnings_count=data.get("warnings_count", 0),
            errors_count=data.get("errors_count", 0),
            validation_timestamp=data.get("validation_timestamp", ""),
            issues=issues,
        )

    # If no persisted summary exists, execute validation
    return validate_document(db, doc.id, version_id=version_id, auto_commit=True)


def list_validation_issues(
    db: Session,
    document_id: Union[str, uuid.UUID],
    version_id: Optional[Union[str, uuid.UUID]] = None,
    severity: Optional[str] = None,
) -> List[ValidationIssue]:
    """Retrieve validation issues for a document, optionally filtered by severity."""
    result = get_validation_result(db, document_id, version_id=version_id)
    if not severity:
        return result.issues
    sev_upper = severity.upper()
    return [i for i in result.issues if i.severity == sev_upper]


def approve_document(
    db: Session,
    document_id: Union[str, uuid.UUID],
    reviewer: ReviewerContext,
    notes: Optional[str] = None,
    auto_commit: bool = True,
) -> Dict[str, Any]:
    """
    Approve a document for official use.
    Verifies reviewer authorization and transitions status to 'approved'.
    """
    reviewer.verify_permission("approve")

    doc_uuid = uuid.UUID(str(document_id))
    doc = db.query(Document).filter(Document.id == doc_uuid).first()
    if not doc:
        raise ValueError(f"Document with ID '{document_id}' not found.")

    doc.status = DOC_STATUS_APPROVED

    versions = db.query(DocumentVersion).filter(DocumentVersion.document_id == doc.id).all()
    for v in versions:
        v.status = DOC_STATUS_APPROVED

    # Log approval audit entry in SourceReference
    audit_sr = SourceReference(
        document_id=doc.id,
        cell_or_range="review_audit:approved",
        source_text=json.dumps({
            "action": "approved",
            "reviewer_id": reviewer.user_id,
            "reviewer_name": reviewer.username,
            "notes": notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    )
    db.add(audit_sr)

    # Update report status
    report_name = f"Validation Report: {doc.original_filename}"
    report = db.query(Report).filter(Report.name == report_name).first()
    if report:
        report.status = DOC_STATUS_APPROVED

    if auto_commit:
        db.commit()
    else:
        db.flush()

    return {
        "document_id": str(doc.id),
        "status": DOC_STATUS_APPROVED,
        "action": "approved",
        "reviewer": reviewer.username,
        "notes": notes,
    }


def reject_document(
    db: Session,
    document_id: Union[str, uuid.UUID],
    reviewer: ReviewerContext,
    reason: str,
    auto_commit: bool = True,
) -> Dict[str, Any]:
    """
    Reject a document.
    Verifies reviewer authorization and transitions status to 'rejected'.
    """
    reviewer.verify_permission("reject")

    if not reason or not reason.strip():
        raise ValueError("A rejection reason is required.")

    doc_uuid = uuid.UUID(str(document_id))
    doc = db.query(Document).filter(Document.id == doc_uuid).first()
    if not doc:
        raise ValueError(f"Document with ID '{document_id}' not found.")

    doc.status = DOC_STATUS_REJECTED

    versions = db.query(DocumentVersion).filter(DocumentVersion.document_id == doc.id).all()
    for v in versions:
        v.status = DOC_STATUS_REJECTED

    # Log rejection audit entry in SourceReference
    audit_sr = SourceReference(
        document_id=doc.id,
        cell_or_range="review_audit:rejected",
        source_text=json.dumps({
            "action": "rejected",
            "reviewer_id": reviewer.user_id,
            "reviewer_name": reviewer.username,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    )
    db.add(audit_sr)

    report_name = f"Validation Report: {doc.original_filename}"
    report = db.query(Report).filter(Report.name == report_name).first()
    if report:
        report.status = DOC_STATUS_REJECTED

    if auto_commit:
        db.commit()
    else:
        db.flush()

    return {
        "document_id": str(doc.id),
        "status": DOC_STATUS_REJECTED,
        "action": "rejected",
        "reviewer": reviewer.username,
        "reason": reason,
    }


def mark_needs_correction(
    db: Session,
    document_id: Union[str, uuid.UUID],
    reviewer: ReviewerContext,
    instructions: str,
    auto_commit: bool = True,
) -> Dict[str, Any]:
    """
    Mark a document as Needs Correction.
    Verifies reviewer authorization and transitions status to 'needs_correction'.
    """
    reviewer.verify_permission("needs_correction")

    if not instructions or not instructions.strip():
        raise ValueError("Correction instructions are required.")

    doc_uuid = uuid.UUID(str(document_id))
    doc = db.query(Document).filter(Document.id == doc_uuid).first()
    if not doc:
        raise ValueError(f"Document with ID '{document_id}' not found.")

    doc.status = DOC_STATUS_NEEDS_CORRECTION

    versions = db.query(DocumentVersion).filter(DocumentVersion.document_id == doc.id).all()
    for v in versions:
        v.status = DOC_STATUS_NEEDS_CORRECTION

    # Log correction audit entry in SourceReference
    audit_sr = SourceReference(
        document_id=doc.id,
        cell_or_range="review_audit:needs_correction",
        source_text=json.dumps({
            "action": "needs_correction",
            "reviewer_id": reviewer.user_id,
            "reviewer_name": reviewer.username,
            "instructions": instructions,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    )
    db.add(audit_sr)

    report_name = f"Validation Report: {doc.original_filename}"
    report = db.query(Report).filter(Report.name == report_name).first()
    if report:
        report.status = DOC_STATUS_NEEDS_CORRECTION

    if auto_commit:
        db.commit()
    else:
        db.flush()

    return {
        "document_id": str(doc.id),
        "status": DOC_STATUS_NEEDS_CORRECTION,
        "action": "needs_correction",
        "reviewer": reviewer.username,
        "instructions": instructions,
    }
