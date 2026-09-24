"""
Comprehensive unit and integration tests for Phase 1.2 Excel Data Ingestion.

Covers:
1. Valid XLSX parsing and entity extraction.
2. Multiple sheets handling.
3. Header detection and column normalization.
4. Row parsing into domain records.
5. Granular SourceReference provenance creation.
6. Duplicate file detection via SHA-256 (no duplicate DocumentVersion created).
7. Unsupported file format rejection (.txt, etc.).
8. Empty sheet handling ("Needs Review").
9. Ambiguous / unknown columns ("Needs Review" without guessing).
10. Raw value preservation (raw_value string preserved alongside parsed count).
11. Full API upload endpoint (POST /api/v1/documents/upload) via TestClient.
"""

import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import (
    Assignment,
    Attendance,
    DataSource,
    Document,
    DocumentVersion,
    Person,
    Role,
    SatsangGhar,
    SourceReference,
    VehicleWheelData,
)
from app.services.excel_ingestion import (
    UnsupportedFileFormatError,
    calculate_sha256,
    ingest_excel_file,
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


class TestExcelIngestion(unittest.TestCase):
    """Integration test suite using local PostgreSQL database with clean fixture isolation."""

    def setUp(self):
        _clean_tables()
        self.session = SessionLocal()

    def tearDown(self):
        self.session.close()
        _clean_tables()

    def test_calculate_sha256(self):
        """Test SHA-256 hash calculation on valid file."""
        file_path = FIXTURES_DIR / "valid_attendance.xlsx"
        hash_val = calculate_sha256(file_path)
        self.assertIsInstance(hash_val, str)
        self.assertEqual(len(hash_val), 64)

    def test_unsupported_file_format_rejection(self):
        """Verify non-Excel file raises UnsupportedFileFormatError."""
        file_path = FIXTURES_DIR / "unsupported_sample.txt"
        with self.assertRaises(UnsupportedFileFormatError):
            ingest_excel_file(
                db=self.session,
                file_path=file_path,
                original_filename="unsupported_sample.txt",
            )

    def test_valid_attendance_ingestion_and_provenance(self):
        """Test ingesting valid attendance XLSX file with raw value preservation and SourceReference."""
        file_path = FIXTURES_DIR / "valid_attendance.xlsx"
        result = ingest_excel_file(
            db=self.session,
            file_path=file_path,
            original_filename="valid_attendance.xlsx",
            data_source_name="Test Attendance Source",
        )

        self.assertEqual(result.duplicate_status, "new")
        self.assertEqual(result.records_accepted, 3)
        self.assertEqual(result.records_processed, 3)
        self.assertEqual(result.records_requiring_review, 0)
        self.assertEqual(len(result.errors), 0)
        self.assertIn("Weekly Attendance", result.sheets_discovered)

        # Verify Document & Version in DB
        doc = self.session.get(Document, result.document_id)
        self.assertIsNotNone(doc)
        self.assertEqual(doc.original_filename, "valid_attendance.xlsx")

        version = self.session.get(DocumentVersion, result.version_id)
        self.assertIsNotNone(version)
        self.assertEqual(version.content_hash, result.content_hash)

        # Verify Attendance records and raw value preservation
        attendances = self.session.scalars(
            select(Attendance).join(SourceReference).where(SourceReference.document_id == doc.id)
        ).all()
        self.assertEqual(len(attendances), 3)

        # Check raw values
        raw_vals = [a.raw_value for a in attendances]
        self.assertIn("450", raw_vals)
        self.assertIn("approx 320", raw_vals)
        self.assertIn("580", raw_vals)

        # Verify SourceReferences
        for att in attendances:
            self.assertIsNotNone(att.source_reference_id)
            sr = self.session.get(SourceReference, att.source_reference_id)
            self.assertIsNotNone(sr)
            self.assertEqual(sr.sheet_name, "Weekly Attendance")
            self.assertGreater(sr.row_number, 1)

    def test_valid_assignment_ingestion(self):
        """Test ingesting valid assignments schedule with Person, Role, and Ghar resolution."""
        file_path = FIXTURES_DIR / "valid_assignment.xlsx"
        result = ingest_excel_file(
            db=self.session,
            file_path=file_path,
            original_filename="valid_assignment.xlsx",
            data_source_name="Test Assignment Source",
        )

        self.assertEqual(result.duplicate_status, "new")
        self.assertEqual(result.records_accepted, 3)
        self.assertEqual(result.records_processed, 3)
        self.assertEqual(result.records_requiring_review, 0)

        # Check that Persons and Roles were created
        assignments = self.session.scalars(
            select(Assignment).join(SourceReference).where(SourceReference.document_id == result.document_id)
        ).all()
        self.assertEqual(len(assignments), 3)

        roles_assigned = [a.role.code for a in assignments if a.role]
        self.assertIn("SK", roles_assigned)
        self.assertIn("SR", roles_assigned)

    def test_multi_sheet_workbook(self):
        """Test ingesting a workbook with multiple sheets (Attendance + Vehicles)."""
        file_path = FIXTURES_DIR / "multi_sheet_office.xlsx"
        result = ingest_excel_file(
            db=self.session,
            file_path=file_path,
            original_filename="multi_sheet_office.xlsx",
            data_source_name="Multi Sheet Source",
        )

        self.assertEqual(result.duplicate_status, "new")
        self.assertEqual(len(result.sheets_discovered), 2)
        self.assertIn("Attendance Summary", result.sheets_discovered)
        self.assertIn("Vehicle Statistics", result.sheets_discovered)
        self.assertEqual(result.records_accepted, 4)  # 2 attendance + 2 vehicle

        # Verify VehicleWheelData records created
        vehicles = self.session.scalars(
            select(VehicleWheelData).join(SourceReference).where(SourceReference.document_id == result.document_id)
        ).all()
        self.assertEqual(len(vehicles), 2)
        for v in vehicles:
            self.assertIn("2-Wheeler Count", v.vehicle_type)

    def test_duplicate_file_detection(self):
        """Verify identical file is detected as duplicate and does not create redundant versions."""
        file_path = FIXTURES_DIR / "valid_attendance.xlsx"

        # First ingestion
        first_result = ingest_excel_file(
            db=self.session,
            file_path=file_path,
            original_filename="valid_attendance.xlsx",
            data_source_name="Duplicate Test Source",
        )
        self.assertEqual(first_result.duplicate_status, "new")

        # Second ingestion with same file
        second_result = ingest_excel_file(
            db=self.session,
            file_path=file_path,
            original_filename="valid_attendance_copy.xlsx",
            data_source_name="Duplicate Test Source",
        )
        self.assertEqual(second_result.duplicate_status, "duplicate")
        self.assertEqual(second_result.version_id, first_result.version_id)
        self.assertEqual(second_result.document_id, first_result.document_id)
        self.assertEqual(second_result.records_accepted, 0)

        # Count total versions for this hash
        versions_count = len(
            self.session.scalars(
                select(DocumentVersion).where(DocumentVersion.content_hash == first_result.content_hash)
            ).all()
        )
        self.assertEqual(versions_count, 1)

    def test_ambiguous_columns_needs_review(self):
        """Verify unmapped or ambiguous columns are flagged as 'Needs Review' without guessing."""
        file_path = FIXTURES_DIR / "ambiguous_columns.xlsx"
        result = ingest_excel_file(
            db=self.session,
            file_path=file_path,
            original_filename="ambiguous_columns.xlsx",
            data_source_name="Ambiguous Source",
        )

        self.assertEqual(result.records_accepted, 0)
        self.assertEqual(result.records_requiring_review, 1)
        self.assertTrue(len(result.review_items) > 0)
        self.assertEqual(result.review_items[0]["status"], "Needs Review")
        self.assertIn("Unknown column structure", result.review_items[0]["reason"])

    def test_empty_sheet_handling(self):
        """Verify empty sheets are flagged as 'Needs Review' without errors."""
        file_path = FIXTURES_DIR / "empty_sheet.xlsx"
        result = ingest_excel_file(
            db=self.session,
            file_path=file_path,
            original_filename="empty_sheet.xlsx",
            data_source_name="Empty Source",
        )

        self.assertEqual(result.records_accepted, 0)
        self.assertEqual(result.records_requiring_review, 1)
        self.assertEqual(result.review_items[0]["status"], "Needs Review")


class TestDocumentUploadAPI(unittest.TestCase):
    """Test the POST /api/v1/documents/upload HTTP endpoint."""

    def setUp(self):
        _clean_tables()
        self.client = TestClient(app)

    def tearDown(self):
        _clean_tables()

    def test_upload_lifecycle_valid_and_duplicate(self):
        """Test full upload lifecycle: initial upload succeeds, second upload detects duplicate."""
        file_path = FIXTURES_DIR / "valid_attendance.xlsx"

        # 1. First upload -> "new"
        with open(file_path, "rb") as f:
            response1 = self.client.post(
                "/api/v1/documents/upload",
                files={"file": ("api_test_attendance.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"data_source_name": "API Test Source"},
            )

        self.assertEqual(response1.status_code, 200)
        data1 = response1.json()
        self.assertIn("document_id", data1)
        self.assertIn("version_id", data1)
        self.assertEqual(data1["duplicate_status"], "new")
        self.assertEqual(data1["records_accepted"], 3)

        # 2. Second upload -> "duplicate"
        with open(file_path, "rb") as f:
            response2 = self.client.post(
                "/api/v1/documents/upload",
                files={"file": ("api_test_attendance_copy.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"data_source_name": "API Test Source"},
            )

        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertEqual(data2["duplicate_status"], "duplicate")
        self.assertEqual(data2["version_id"], data1["version_id"])
        self.assertEqual(data2["records_accepted"], 0)

    def test_upload_unsupported_file(self):
        """Test uploading a .txt file returns 400 Bad Request."""
        file_path = FIXTURES_DIR / "unsupported_sample.txt"
        with open(file_path, "rb") as f:
            response = self.client.post(
                "/api/v1/documents/upload",
                files={"file": ("unsupported_sample.txt", f, "text/plain")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file format", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
