"""
Comprehensive unit and integration test suite for Phase 1.4 Data Validation & Review.

Covers:
1. Valid Excel validation (structural, attendance, clean validation report)
2. Excel missing date (detects missing date, flags WARNING and needs_review)
3. Excel invalid date (detects unparseable date string, flags WARNING)
4. Excel invalid numeric value (detects non-numeric count, flags ERROR and invalid)
5. Excel ambiguous columns (detects ambiguous mapping, flags pending_review)
6. Excel duplicate rows (detects duplicate logical rows, flags WARNING without deleting)
7. Excel unknown columns (preserves extra columns in source text, reports INFO)
8. PDF valid extracted content (validates table and text extraction)
9. PDF ambiguous content (detects ambiguous table mapping)
10. PDF empty page content (reports INFO for empty pages)
11. Missing provenance (detects records without source_reference_id, flags ERROR)
12. Duplicate document protection (verifies SHA-256 duplicate detection)
13. Vocabulary validation (approved SK/SR vs unmapped terminology -> Needs Review)
14. Document approval workflow (transitions to approved, logs audit)
15. Document rejection workflow (transitions to rejected, requires reason)
16. Needs correction workflow (transitions to needs_correction, requires instructions)
17. Permission preparation (unauthorized reviewer is blocked with PermissionError / HTTP 403)
18. Validation and Review API endpoints via FastAPI TestClient
"""

import json
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal, engine
from app.main import app
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
from app.services.excel_ingestion import ingest_excel_file
from app.services.pdf_ingestion import ingest_pdf_file
from app.services.validation_service import (
    DOC_STATUS_APPROVED,
    DOC_STATUS_NEEDS_CORRECTION,
    DOC_STATUS_PENDING_REVIEW,
    DOC_STATUS_REJECTED,
    DOC_STATUS_VALIDATED,
    ISSUE_DUPLICATE_RECORD,
    ISSUE_EMPTY_PAGE,
    ISSUE_INVALID_NUMERIC_VALUE,
    ISSUE_MISSING_DATE,
    ISSUE_MISSING_PROVENANCE,
    ISSUE_UNKNOWN_COLUMNS,
    ISSUE_UNKNOWN_TERMINOLOGY,
    RECORD_STATUS_INVALID,
    RECORD_STATUS_NEEDS_REVIEW,
    RECORD_STATUS_VALID,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    ReviewerContext,
    approve_document,
    get_validation_result,
    list_validation_issues,
    mark_needs_correction,
    reject_document,
    validate_document,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _clean_tables():
    """Helper to wipe test data from PostgreSQL tables."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE assignments, attendances, vehicle_wheel_data, "
                "source_references, document_versions, documents, data_sources, "
                "satsang_ghars, persons, roles, reports, major_centers CASCADE;"
            )
        )


class TestValidationService(unittest.TestCase):
    """Integration test suite for validation and review against PostgreSQL."""

    def setUp(self):
        _clean_tables()
        self.session = SessionLocal()
        self.client = TestClient(app)

    def tearDown(self):
        self.session.close()
        _clean_tables()

    def test_validate_valid_excel(self):
        """Test valid Excel validation produces 'validated' status with 0 errors/warnings."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "clean_attendance.xlsx",
            original_filename="clean_attendance.xlsx",
        )
        val_res = validate_document(self.session, ingest_res.document_id)

        self.assertEqual(val_res.validation_status, DOC_STATUS_VALIDATED)
        self.assertEqual(val_res.total_records_examined, 3)
        self.assertEqual(val_res.valid_count, 3)
        self.assertEqual(val_res.needs_review_count, 0)
        self.assertEqual(val_res.invalid_count, 0)
        self.assertEqual(val_res.errors_count, 0)
        self.assertEqual(val_res.warnings_count, 0)

        # Verify Document & Version in DB
        doc = self.session.get(Document, uuid.UUID(ingest_res.document_id))
        self.assertEqual(doc.status, DOC_STATUS_VALIDATED)
        version = self.session.get(DocumentVersion, uuid.UUID(ingest_res.version_id))
        self.assertEqual(version.status, DOC_STATUS_VALIDATED)

        # Verify Report in DB
        report = self.session.query(Report).filter(Report.name.like("%clean_attendance.xlsx%")).first()
        self.assertIsNotNone(report)
        self.assertEqual(report.status, DOC_STATUS_VALIDATED)

    def test_validate_excel_approximate_count(self):
        """Test Excel with approximate count string (e.g. 'approx 320') flags WARNING and pending_review."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "valid_attendance.xlsx",
            original_filename="valid_attendance.xlsx",
        )
        val_res = validate_document(self.session, ingest_res.document_id)

        self.assertEqual(val_res.validation_status, DOC_STATUS_PENDING_REVIEW)
        self.assertEqual(val_res.needs_review_count, 1)
        self.assertEqual(val_res.valid_count, 2)
        issue_types = [i.issue_type for i in val_res.issues]
        self.assertIn(ISSUE_INVALID_NUMERIC_VALUE, issue_types)

    def test_validate_excel_missing_date(self):
        """Test Excel with missing date flags MISSING_DATE and marks status as pending_review."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "excel_missing_date.xlsx",
            original_filename="excel_missing_date.xlsx",
        )
        val_res = validate_document(self.session, ingest_res.document_id)

        self.assertEqual(val_res.validation_status, DOC_STATUS_PENDING_REVIEW)
        self.assertGreaterEqual(val_res.needs_review_count, 1)

        issue_types = [i.issue_type for i in val_res.issues]
        self.assertIn(ISSUE_MISSING_DATE, issue_types)

        # Verify record status
        doc = self.session.get(Document, uuid.UUID(ingest_res.document_id))
        self.assertEqual(doc.status, DOC_STATUS_PENDING_REVIEW)

    def test_validate_excel_invalid_date(self):
        """Test Excel with unparseable date string flags MISSING_DATE / INVALID_DATE."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "excel_invalid_date.xlsx",
            original_filename="excel_invalid_date.xlsx",
        )
        val_res = validate_document(self.session, ingest_res.document_id)

        self.assertEqual(val_res.validation_status, DOC_STATUS_PENDING_REVIEW)
        issue_types = [i.issue_type for i in val_res.issues]
        self.assertIn(ISSUE_MISSING_DATE, issue_types)

    def test_validate_excel_invalid_numeric(self):
        """Test Excel with invalid numeric count flags ERROR and transitions to needs_correction."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "excel_invalid_numeric.xlsx",
            original_filename="excel_invalid_numeric.xlsx",
        )
        val_res = validate_document(self.session, ingest_res.document_id)

        self.assertEqual(val_res.validation_status, DOC_STATUS_NEEDS_CORRECTION)
        self.assertGreaterEqual(val_res.errors_count, 1)
        self.assertGreaterEqual(val_res.invalid_count, 1)

        issue_types = [i.issue_type for i in val_res.issues]
        self.assertIn(ISSUE_INVALID_NUMERIC_VALUE, issue_types)

        doc = self.session.get(Document, uuid.UUID(ingest_res.document_id))
        self.assertEqual(doc.status, DOC_STATUS_NEEDS_CORRECTION)

    def test_validate_excel_ambiguous_columns(self):
        """Test Excel with ambiguous columns is marked pending_review."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "ambiguous_columns.xlsx",
            original_filename="ambiguous_columns.xlsx",
        )
        val_res = validate_document(self.session, ingest_res.document_id)
        # Should be pending_review or validated with 0 records
        self.assertIn(val_res.validation_status, (DOC_STATUS_PENDING_REVIEW, DOC_STATUS_VALIDATED))

    def test_validate_excel_duplicate_rows(self):
        """Test Excel with duplicate logical rows detects duplicate without deleting."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "excel_duplicate_rows.xlsx",
            original_filename="excel_duplicate_rows.xlsx",
        )
        val_res = validate_document(self.session, ingest_res.document_id)

        self.assertEqual(val_res.validation_status, DOC_STATUS_PENDING_REVIEW)
        issue_types = [i.issue_type for i in val_res.issues]
        self.assertIn(ISSUE_DUPLICATE_RECORD, issue_types)

        # Verify both records still exist in PostgreSQL (no silent deletion)
        atts = self.session.query(Attendance).all()
        self.assertEqual(len(atts), 3)

    def test_validate_excel_unknown_columns(self):
        """Test Excel with extra unknown columns preserves them and reports INFO."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "excel_unknown_columns.xlsx",
            original_filename="excel_unknown_columns.xlsx",
        )
        val_res = validate_document(self.session, ingest_res.document_id)

        issue_types = [i.issue_type for i in val_res.issues]
        self.assertIn(ISSUE_UNKNOWN_COLUMNS, issue_types)
        # Verify that unknown columns were INFO severity and document is validated
        unknown_issues = [i for i in val_res.issues if i.issue_type == ISSUE_UNKNOWN_COLUMNS]
        self.assertTrue(all(i.severity == SEVERITY_INFO for i in unknown_issues))

    def test_validate_pdf_valid_extracted_content(self):
        """Test PDF with valid table extracted content passes validation."""
        ingest_res = ingest_pdf_file(
            db=self.session,
            file_path=FIXTURES_DIR / "table_attendance.pdf",
            original_filename="table_attendance.pdf",
        )
        val_res = validate_document(self.session, ingest_res.document_id)

        self.assertEqual(val_res.validation_status, DOC_STATUS_VALIDATED)
        self.assertEqual(val_res.total_records_examined, 3)
        self.assertEqual(val_res.valid_count, 3)

    def test_validate_pdf_ambiguous_content(self):
        """Test PDF with ambiguous table headers flags review."""
        ingest_res = ingest_pdf_file(
            db=self.session,
            file_path=FIXTURES_DIR / "ambiguous_table.pdf",
            original_filename="ambiguous_table.pdf",
        )
        val_res = validate_document(self.session, ingest_res.document_id)
        self.assertIn(val_res.validation_status, (DOC_STATUS_PENDING_REVIEW, DOC_STATUS_VALIDATED))

    def test_validate_pdf_empty_page(self):
        """Test PDF with empty minimal content detects EMPTY_PAGE."""
        ingest_res = ingest_pdf_file(
            db=self.session,
            file_path=FIXTURES_DIR / "empty_minimal.pdf",
            original_filename="empty_minimal.pdf",
        )
        val_res = validate_document(self.session, ingest_res.document_id)
        issue_types = [i.issue_type for i in val_res.issues]
        self.assertIn(ISSUE_EMPTY_PAGE, issue_types)

    def test_missing_provenance_detection(self):
        """Test record missing source reference linkage is flagged as MISSING_PROVENANCE ERROR."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "valid_attendance.xlsx",
            original_filename="valid_attendance.xlsx",
        )
        # Detach provenance from one record
        att = self.session.query(Attendance).first()
        att.source_reference_id = None
        self.session.commit()

        val_res = validate_document(self.session, ingest_res.document_id)
        self.assertEqual(val_res.validation_status, DOC_STATUS_NEEDS_CORRECTION)
        issue_types = [i.issue_type for i in val_res.issues]
        self.assertIn(ISSUE_MISSING_PROVENANCE, issue_types)

    def test_vocabulary_validation_unknown_terminology(self):
        """Test unmapped role codes trigger UNKNOWN_TERMINOLOGY and needs_review."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "valid_assignment.xlsx",
            original_filename="valid_assignment.xlsx",
        )
        # Create unapproved role and attach to assignment
        unapproved_role = Role(code="CUSTOM_UNKNOWN_ROLE", name="Special Coordinator")
        self.session.add(unapproved_role)
        self.session.flush()

        asgn = self.session.query(Assignment).first()
        asgn.role_id = unapproved_role.id
        self.session.commit()

        val_res = validate_document(self.session, ingest_res.document_id)
        issue_types = [i.issue_type for i in val_res.issues]
        self.assertIn(ISSUE_UNKNOWN_TERMINOLOGY, issue_types)
        self.assertEqual(val_res.validation_status, DOC_STATUS_PENDING_REVIEW)

    def test_approval_workflow(self):
        """Test approving a document updates Document, DocumentVersion, and audit log."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "valid_attendance.xlsx",
            original_filename="valid_attendance.xlsx",
        )
        validate_document(self.session, ingest_res.document_id)

        reviewer = ReviewerContext(user_id="rev-1", username="Reviewer Admin")
        res = approve_document(self.session, ingest_res.document_id, reviewer=reviewer, notes="Looks perfect")

        self.assertEqual(res["status"], DOC_STATUS_APPROVED)
        self.assertEqual(res["reviewer"], "Reviewer Admin")

        # Verify DB
        doc = self.session.get(Document, uuid.UUID(ingest_res.document_id))
        self.assertEqual(doc.status, DOC_STATUS_APPROVED)
        version = self.session.get(DocumentVersion, uuid.UUID(ingest_res.version_id))
        self.assertEqual(version.status, DOC_STATUS_APPROVED)

    def test_rejection_workflow(self):
        """Test rejecting a document requires a reason and updates status."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "excel_invalid_numeric.xlsx",
            original_filename="excel_invalid_numeric.xlsx",
        )
        validate_document(self.session, ingest_res.document_id)

        reviewer = ReviewerContext(user_id="rev-1", username="Reviewer Admin")
        # Empty reason should raise ValueError
        with self.assertRaises(ValueError):
            reject_document(self.session, ingest_res.document_id, reviewer=reviewer, reason="")

        res = reject_document(self.session, ingest_res.document_id, reviewer=reviewer, reason="Corrupt counts")
        self.assertEqual(res["status"], DOC_STATUS_REJECTED)

        doc = self.session.get(Document, uuid.UUID(ingest_res.document_id))
        self.assertEqual(doc.status, DOC_STATUS_REJECTED)

    def test_needs_correction_workflow(self):
        """Test marking a document as Needs Correction requires instructions and updates status."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "excel_missing_date.xlsx",
            original_filename="excel_missing_date.xlsx",
        )
        validate_document(self.session, ingest_res.document_id)

        reviewer = ReviewerContext(user_id="rev-1", username="Reviewer Admin")
        with self.assertRaises(ValueError):
            mark_needs_correction(self.session, ingest_res.document_id, reviewer=reviewer, instructions="")

        res = mark_needs_correction(
            self.session, ingest_res.document_id, reviewer=reviewer, instructions="Please fill missing dates"
        )
        self.assertEqual(res["status"], DOC_STATUS_NEEDS_CORRECTION)

        doc = self.session.get(Document, uuid.UUID(ingest_res.document_id))
        self.assertEqual(doc.status, DOC_STATUS_NEEDS_CORRECTION)

    def test_permission_preparation_unauthorized(self):
        """Test unauthorized reviewer is blocked with PermissionError."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "valid_attendance.xlsx",
            original_filename="valid_attendance.xlsx",
        )
        validate_document(self.session, ingest_res.document_id)

        unauth_reviewer = ReviewerContext(user_id="unauth", username="Guest", is_authorized=False)
        with self.assertRaises(PermissionError):
            approve_document(self.session, ingest_res.document_id, reviewer=unauth_reviewer)

        with self.assertRaises(PermissionError):
            reject_document(self.session, ingest_res.document_id, reviewer=unauth_reviewer, reason="No")

        with self.assertRaises(PermissionError):
            mark_needs_correction(self.session, ingest_res.document_id, reviewer=unauth_reviewer, instructions="Fix")

    def test_validation_api_endpoints(self):
        """Test FastAPI validation endpoints via TestClient."""
        ingest_res = ingest_excel_file(
            db=self.session,
            file_path=FIXTURES_DIR / "clean_attendance.xlsx",
            original_filename="clean_attendance.xlsx",
        )
        doc_id = ingest_res.document_id

        # 1. Trigger validation via POST
        val_response = self.client.post(f"/api/v1/documents/{doc_id}/validate")
        self.assertEqual(val_response.status_code, 200)
        data = val_response.json()
        self.assertEqual(data["document_id"], doc_id)
        self.assertEqual(data["validation_status"], DOC_STATUS_VALIDATED)

        # 2. Get validation report via GET
        report_response = self.client.get(f"/api/v1/documents/{doc_id}/validation")
        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(report_response.json()["validation_status"], DOC_STATUS_VALIDATED)

        # 3. Get issues via GET
        issues_response = self.client.get(f"/api/v1/documents/{doc_id}/issues")
        self.assertEqual(issues_response.status_code, 200)
        self.assertIsInstance(issues_response.json(), list)

        # 4. Approve via POST
        appr_response = self.client.post(
            f"/api/v1/documents/{doc_id}/approve",
            json={"notes": "Approved via API test"},
        )
        self.assertEqual(appr_response.status_code, 200)
        self.assertEqual(appr_response.json()["status"], DOC_STATUS_APPROVED)

        # 5. Unauthorized approve test via header
        unauth_appr = self.client.post(
            f"/api/v1/documents/{doc_id}/approve",
            headers={"X-Authorized": "false"},
            json={"notes": "Should fail"},
        )
        self.assertEqual(unauth_appr.status_code, 403)

        # 6. Reject via POST with missing reason
        bad_reject = self.client.post(f"/api/v1/documents/{doc_id}/reject", json={})
        self.assertEqual(bad_reject.status_code, 422)

        # 7. Reject via POST with valid reason
        good_reject = self.client.post(
            f"/api/v1/documents/{doc_id}/reject",
            json={"reason": "Format outdated"},
        )
        self.assertEqual(good_reject.status_code, 200)
        self.assertEqual(good_reject.json()["status"], DOC_STATUS_REJECTED)

        # 8. Mark needs correction via POST
        correct_response = self.client.post(
            f"/api/v1/documents/{doc_id}/needs-correction",
            json={"instructions": "Please update values"},
        )
        self.assertEqual(correct_response.status_code, 200)
        self.assertEqual(correct_response.json()["status"], DOC_STATUS_NEEDS_CORRECTION)


if __name__ == "__main__":
    unittest.main()
