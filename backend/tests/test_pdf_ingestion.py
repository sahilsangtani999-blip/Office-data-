"""
Comprehensive unit and integration tests for Phase 1.3 PDF Data Ingestion.

Covers:
1. Valid text PDF ingestion and page count.
2. Multi-page PDF extraction and per-page SourceReference creation.
3. Table detection with bounding box (bbox) coordinates.
4. Structured record extraction (Attendance) into PostgreSQL with raw preservation.
5. Granular SourceReference provenance (page_number, row_number, cell_or_range/bbox).
6. Ambiguous table structure detection ("Needs Review" without guessing).
7. Empty/minimal PDF handling ("Needs Review").
8. Corrupt/unsupported file format rejection.
9. Duplicate PDF detection via SHA-256 (no duplicate DocumentVersion created).
10. Unified API upload endpoint (POST /api/v1/documents/upload) with PDF.
11. Backward compatibility: Excel upload still works alongside PDF upload.
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
    SatsangGhar,
    SourceReference,
)
from app.services.pdf_ingestion import (
    UnsupportedFileFormatError,
    calculate_sha256,
    ingest_pdf_file,
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


class TestPDFIngestion(unittest.TestCase):
    """Integration test suite for PDF ingestion with PostgreSQL table isolation."""

    def setUp(self):
        _clean_tables()
        self.session = SessionLocal()

    def tearDown(self):
        self.session.close()
        _clean_tables()

    def test_calculate_sha256(self):
        """Test SHA-256 computation on PDF file."""
        file_path = FIXTURES_DIR / "simple_text.pdf"
        hash_val = calculate_sha256(file_path)
        self.assertIsInstance(hash_val, str)
        self.assertEqual(len(hash_val), 64)

    def test_unsupported_file_format_rejection(self):
        """Verify non-PDF file raises UnsupportedFileFormatError."""
        file_path = FIXTURES_DIR / "unsupported_sample.txt"
        with self.assertRaises(UnsupportedFileFormatError):
            ingest_pdf_file(
                db=self.session,
                file_path=file_path,
                original_filename="unsupported_sample.txt",
            )

    def test_simple_text_pdf_ingestion(self):
        """Test ingesting single-page text PDF and page-level SourceReference."""
        file_path = FIXTURES_DIR / "simple_text.pdf"
        result = ingest_pdf_file(
            db=self.session,
            file_path=file_path,
            original_filename="simple_text.pdf",
            data_source_name="Test PDF Source",
        )

        self.assertEqual(result.duplicate_status, "new")
        self.assertEqual(result.page_count, 1)
        self.assertEqual(result.pages_processed, 1)
        self.assertEqual(result.tables_detected, 0)
        self.assertEqual(result.structured_records_created, 0)

        # Verify Document and Version in PostgreSQL
        doc = self.session.get(Document, result.document_id)
        self.assertIsNotNone(doc)
        self.assertEqual(doc.document_type, "pdf")

        # Verify page-level SourceReference
        source_refs = self.session.scalars(
            select(SourceReference).where(SourceReference.document_id == doc.id)
        ).all()
        self.assertEqual(len(source_refs), 1)
        self.assertEqual(source_refs[0].page_number, 1)
        self.assertIn("RSSB Office Data Platform - General Notice", source_refs[0].source_text)

    def test_multi_page_pdf_extraction(self):
        """Test ingesting a 3-page PDF and verifying page-level provenance."""
        file_path = FIXTURES_DIR / "multi_page_text.pdf"
        result = ingest_pdf_file(
            db=self.session,
            file_path=file_path,
            original_filename="multi_page_text.pdf",
            data_source_name="Multi Page Source",
        )

        self.assertEqual(result.page_count, 3)
        self.assertEqual(result.pages_processed, 3)

        source_refs = self.session.scalars(
            select(SourceReference)
            .where(SourceReference.document_id == result.document_id)
            .order_by(SourceReference.page_number)
        ).all()
        self.assertEqual(len(source_refs), 3)
        pages_found = [sr.page_number for sr in source_refs]
        self.assertEqual(pages_found, [1, 2, 3])
        self.assertIn("Section 1: Overview", source_refs[0].source_text)
        self.assertIn("Section 2: Coordination Guidelines", source_refs[1].source_text)
        self.assertIn("Section 3: Action Items", source_refs[2].source_text)

    def test_table_attendance_detection_and_coordinates(self):
        """Test table detection, bounding box preservation, and Attendance record creation."""
        file_path = FIXTURES_DIR / "table_attendance.pdf"
        result = ingest_pdf_file(
            db=self.session,
            file_path=file_path,
            original_filename="table_attendance.pdf",
            data_source_name="Attendance PDF Source",
        )

        self.assertEqual(result.duplicate_status, "new")
        self.assertEqual(result.tables_detected, 1)
        self.assertEqual(result.structured_records_created, 3)
        self.assertEqual(result.records_needing_review, 0)

        # Verify Attendance records created in DB
        attendances = self.session.scalars(
            select(Attendance).join(SourceReference).where(SourceReference.document_id == result.document_id)
        ).all()
        self.assertEqual(len(attendances), 3)

        # Check raw values and counts
        counts = [a.count_value for a in attendances]
        self.assertIn(520, counts)
        self.assertIn(410, counts)
        self.assertIn(630, counts)

        # Check coordinates and provenance
        for att in attendances:
            sr = self.session.get(SourceReference, att.source_reference_id)
            self.assertIsNotNone(sr)
            self.assertEqual(sr.page_number, 1)
            self.assertIsNotNone(sr.row_number)
            self.assertIn("bbox:[", sr.cell_or_range)
            # Verify real coordinates format: bbox:[x0,top,x1,bottom]
            self.assertTrue(sr.cell_or_range.startswith("bbox:["))

    def test_ambiguous_table_needs_review(self):
        """Verify unrecognized table structure is flagged as 'Needs Review' without guessing."""
        file_path = FIXTURES_DIR / "ambiguous_table.pdf"
        result = ingest_pdf_file(
            db=self.session,
            file_path=file_path,
            original_filename="ambiguous_table.pdf",
            data_source_name="Ambiguous PDF Source",
        )

        self.assertEqual(result.tables_detected, 1)
        self.assertEqual(result.structured_records_created, 0)
        self.assertEqual(result.records_needing_review, 1)
        self.assertTrue(len(result.review_items) > 0)
        self.assertEqual(result.review_items[0]["status"], "Needs Review")
        self.assertIn("Unknown table column structure", result.review_items[0]["reason"])

    def test_empty_minimal_pdf_handling(self):
        """Verify empty/blank PDF is processed and flagged as 'Needs Review'."""
        file_path = FIXTURES_DIR / "empty_minimal.pdf"
        result = ingest_pdf_file(
            db=self.session,
            file_path=file_path,
            original_filename="empty_minimal.pdf",
            data_source_name="Empty PDF Source",
        )

        self.assertEqual(result.page_count, 1)
        self.assertEqual(result.tables_detected, 0)
        self.assertEqual(result.structured_records_created, 0)
        self.assertEqual(result.records_needing_review, 1)
        self.assertEqual(result.review_items[0]["status"], "Needs Review")

    def test_duplicate_pdf_detection(self):
        """Verify identical PDF returns duplicate status without duplicate DocumentVersion."""
        file_path = FIXTURES_DIR / "table_attendance.pdf"

        # 1. First ingestion
        first_result = ingest_pdf_file(
            db=self.session,
            file_path=file_path,
            original_filename="table_attendance.pdf",
            data_source_name="Duplicate PDF Source",
        )
        self.assertEqual(first_result.duplicate_status, "new")

        # 2. Second ingestion of identical file
        second_result = ingest_pdf_file(
            db=self.session,
            file_path=file_path,
            original_filename="table_attendance_copy.pdf",
            data_source_name="Duplicate PDF Source",
        )
        self.assertEqual(second_result.duplicate_status, "duplicate")
        self.assertEqual(second_result.version_id, first_result.version_id)
        self.assertEqual(second_result.document_id, first_result.document_id)
        self.assertEqual(second_result.structured_records_created, 0)

        # Confirm only 1 DocumentVersion exists
        versions = self.session.scalars(
            select(DocumentVersion).where(DocumentVersion.content_hash == first_result.content_hash)
        ).all()
        self.assertEqual(len(versions), 1)


class TestUnifiedDocumentUploadAPI(unittest.TestCase):
    """Test the POST /api/v1/documents/upload HTTP endpoint for both PDF and Excel."""

    def setUp(self):
        _clean_tables()
        self.client = TestClient(app)

    def tearDown(self):
        _clean_tables()

    def test_upload_valid_pdf_and_duplicate(self):
        """Test uploading PDF via HTTP endpoint, then verifying duplicate detection on second upload."""
        file_path = FIXTURES_DIR / "table_attendance.pdf"

        # 1. Initial upload
        with open(file_path, "rb") as f:
            response1 = self.client.post(
                "/api/v1/documents/upload",
                files={"file": ("api_test_table.pdf", f, "application/pdf")},
                data={"data_source_name": "API PDF Source"},
            )

        self.assertEqual(response1.status_code, 200)
        data1 = response1.json()
        self.assertEqual(data1["duplicate_status"], "new")
        self.assertEqual(data1["structured_records_created"], 3)
        self.assertIn("document_id", data1)
        self.assertIn("version_id", data1)

        # 2. Duplicate upload
        with open(file_path, "rb") as f:
            response2 = self.client.post(
                "/api/v1/documents/upload",
                files={"file": ("api_test_table_copy.pdf", f, "application/pdf")},
                data={"data_source_name": "API PDF Source"},
            )

        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertEqual(data2["duplicate_status"], "duplicate")
        self.assertEqual(data2["version_id"], data1["version_id"])

    def test_excel_upload_still_works(self):
        """Verify that Excel upload continues to function without regression."""
        file_path = FIXTURES_DIR / "valid_attendance.xlsx"
        with open(file_path, "rb") as f:
            response = self.client.post(
                "/api/v1/documents/upload",
                files={"file": ("regression_test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"data_source_name": "Regression Test Source"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["duplicate_status"], "new")
        self.assertEqual(data["records_accepted"], 3)


if __name__ == "__main__":
    unittest.main()
