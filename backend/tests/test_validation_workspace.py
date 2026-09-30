"""
Focused Unit & Integration Tests for Phase 2.6 Document Review & Validation Workspace.
Covers:
- Listing documents with validation summaries
- Fetching validation report with review history
- Enriched validation issues (raw_value, extracted_value, record_details)
- Document records retrieval
- Review history audit trail
- Role permissions: Admin & Reviewer can approve/reject/needs_correction; Viewer is 403 Forbidden
"""

import json
from pathlib import Path
import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import create_access_token
from app.database import SessionLocal, engine
from app.main import app
from app.models import Document, User
from app.services.excel_ingestion import ingest_excel_file
from app.services.validation_service import (
    DOC_STATUS_APPROVED,
    DOC_STATUS_NEEDS_CORRECTION,
    DOC_STATUS_REJECTED,
    validate_document,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestValidationWorkspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Create tokens for test roles
        cls.admin_token = create_access_token({"sub": "admin", "role": "admin"})
        cls.reviewer_token = create_access_token({"sub": "reviewer", "role": "reviewer"})
        cls.viewer_token = create_access_token({"sub": "viewer", "role": "viewer"})

    def setUp(self):
        self.session = SessionLocal()
        # Seed test document
        test_file = FIXTURES_DIR / "multi_sheet_office.xlsx"
        if test_file.exists():
            ingest_excel_file(
                db=self.session,
                file_path=test_file,
                original_filename="multi_sheet_office.xlsx",
                source_type="manual_upload",
                data_source_name="Test Workspace",
                storage_path=str(test_file),
            )
        self.doc = self.session.query(Document).filter(
            Document.original_filename == "multi_sheet_office.xlsx"
        ).first()

    def tearDown(self):
        self.session.close()

    def test_list_documents_authenticated(self):
        """Test GET /api/v1/documents returns list with validation stats."""
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        res = self.client.get("/api/v1/documents", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)

        doc_item = next((d for d in data if d["original_filename"] == "multi_sheet_office.xlsx"), None)
        self.assertIsNotNone(doc_item)
        self.assertIn("total_records", doc_item)
        self.assertIn("valid_count", doc_item)
        self.assertIn("validation_status", doc_item)

    def test_fetch_validation_and_history(self):
        """Test GET /api/v1/documents/{id}/validation includes review_history."""
        headers = {"Authorization": f"Bearer {self.viewer_token}"}
        res = self.client.get(f"/api/v1/documents/{self.doc.id}/validation", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["document_id"], str(self.doc.id))
        self.assertIn("issues", data)
        self.assertIn("review_history", data)

    def test_fetch_issues_enriched(self):
        """Test GET /api/v1/documents/{id}/issues returns enriched issue fields."""
        headers = {"Authorization": f"Bearer {self.viewer_token}"}
        res = self.client.get(f"/api/v1/documents/{self.doc.id}/issues", headers=headers)
        self.assertEqual(res.status_code, 200)
        issues = res.json()
        self.assertIsInstance(issues, list)
        if len(issues) > 0:
            first = issues[0]
            self.assertIn("issue_type", first)
            self.assertIn("severity", first)
            self.assertIn("raw_value", first)
            self.assertIn("document_name", first)

    def test_fetch_document_records(self):
        """Test GET /api/v1/documents/{id}/records returns entity records."""
        headers = {"Authorization": f"Bearer {self.viewer_token}"}
        res = self.client.get(f"/api/v1/documents/{self.doc.id}/records", headers=headers)
        self.assertEqual(res.status_code, 200)
        records = res.json()
        self.assertIsInstance(records, list)
        self.assertGreaterEqual(len(records), 1)
        first = records[0]
        self.assertIn("record_type", first)
        self.assertIn("status", first)
        self.assertIn("summary", first)

    def test_reviewer_approval_workflow(self):
        """Test Reviewer can approve and audit entry is created."""
        headers = {"Authorization": f"Bearer {self.reviewer_token}"}
        payload = {"notes": "Approved by verified reviewer."}
        res = self.client.post(
            f"/api/v1/documents/{self.doc.id}/approve",
            json=payload,
            headers=headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], DOC_STATUS_APPROVED)
        self.assertEqual(data["action"], "approved")

        # Verify audit history
        hist_res = self.client.get(f"/api/v1/documents/{self.doc.id}/history", headers=headers)
        self.assertEqual(hist_res.status_code, 200)
        history = hist_res.json()
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["action"], "approved")

    def test_admin_rejection_workflow(self):
        """Test Admin can reject document with reason."""
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        payload = {"reason": "Document has formatting discrepancies."}
        res = self.client.post(
            f"/api/v1/documents/{self.doc.id}/reject",
            json=payload,
            headers=headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], DOC_STATUS_REJECTED)
        self.assertEqual(data["action"], "rejected")

    def test_reviewer_needs_correction_workflow(self):
        """Test Reviewer can mark document as Needs Correction."""
        headers = {"Authorization": f"Bearer {self.reviewer_token}"}
        payload = {"instructions": "Please update row 4 attendance count."}
        res = self.client.post(
            f"/api/v1/documents/{self.doc.id}/needs-correction",
            json=payload,
            headers=headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], DOC_STATUS_NEEDS_CORRECTION)
        self.assertEqual(data["action"], "needs_correction")

    def test_viewer_permission_forbidden(self):
        """Test Viewer role CANNOT approve, reject, or request correction (403 Forbidden)."""
        headers = {"Authorization": f"Bearer {self.viewer_token}"}

        # Attempt approve
        app_res = self.client.post(
            f"/api/v1/documents/{self.doc.id}/approve",
            json={"notes": "Viewer trying to approve"},
            headers=headers,
        )
        self.assertEqual(app_res.status_code, 403)

        # Attempt reject
        rej_res = self.client.post(
            f"/api/v1/documents/{self.doc.id}/reject",
            json={"reason": "Viewer trying to reject"},
            headers=headers,
        )
        self.assertEqual(rej_res.status_code, 403)

        # Attempt needs correction
        corr_res = self.client.post(
            f"/api/v1/documents/{self.doc.id}/needs-correction",
            json={"instructions": "Viewer trying to correct"},
            headers=headers,
        )
        self.assertEqual(corr_res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
