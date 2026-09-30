"""
Phase 2.5 — Authentication & Office Permissions Regression Test Suite.

Comprehensive test coverage verifying:
1. Unauthenticated access blocked with HTTP 401 Unauthorized.
2. Successful authentication via login with valid tokens and assigned roles.
3. Invalid authentication blocked (wrong password, unknown user, inactive user, expired token, malformed token).
4. Authorized role access succeeds according to the RBAC matrix.
5. Unauthorized role access blocked with HTTP 403 Forbidden.
6. Protection of existing office-data endpoints (documents, validation, query, sources).
7. Existing Excel/PDF upload, duplicate detection, review, provenance, and natural language search continue working under authenticated sessions.
"""

from datetime import timedelta
from pathlib import Path
import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.core.security import create_access_token
from app.database import SessionLocal
from app.main import app
from app.models import User
from app.services.auth_service import create_user, seed_default_users

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _clean_database():
    """Clean all tables while preserving schema."""
    with SessionLocal() as db:
        db.execute(text("TRUNCATE TABLE assignments CASCADE;"))
        db.execute(text("TRUNCATE TABLE attendances CASCADE;"))
        db.execute(text("TRUNCATE TABLE vehicle_wheel_data CASCADE;"))
        db.execute(text("TRUNCATE TABLE source_references CASCADE;"))
        db.execute(text("TRUNCATE TABLE document_versions CASCADE;"))
        db.execute(text("TRUNCATE TABLE documents CASCADE;"))
        db.execute(text("TRUNCATE TABLE data_sources CASCADE;"))
        db.execute(text("TRUNCATE TABLE reports CASCADE;"))
        db.execute(text("TRUNCATE TABLE users CASCADE;"))
        db.commit()


class TestAuthAndPermissions(unittest.TestCase):
    """Regression test suite for Authentication & Office Permissions."""

    @classmethod
    def setUpClass(cls):
        _clean_database()
        cls.db = SessionLocal()
        cls.client = TestClient(app)

        # Seed standard users
        seed_default_users(cls.db)

        # Obtain valid tokens for each role
        cls.admin_token = cls._login_and_get_token("admin", "admin123")
        cls.reviewer_token = cls._login_and_get_token("reviewer", "reviewer123")
        cls.uploader_token = cls._login_and_get_token("uploader", "uploader123")
        cls.viewer_token = cls._login_and_get_token("viewer", "viewer123")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        # Restore default setting
        settings.AUTH_ENFORCED = False
        _clean_database()
        with SessionLocal() as db:
            seed_default_users(db)

    @classmethod
    def _login_and_get_token(cls, username: str, password: str) -> str:
        """Helper to login and extract JWT Bearer token."""
        res = cls.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        assert res.status_code == 200, f"Login failed for {username}: {res.text}"
        data = res.json()
        return data["access_token"]

    def _auth_header(self, token: str) -> dict:
        """Helper to create authorization header."""
        return {"Authorization": f"Bearer {token}"}

    # =========================================================================
    # 1. Unauthenticated Access Tests
    # =========================================================================

    def test_unauthenticated_access_blocked_when_enforced(self):
        """When auth is enforced, requests without credentials receive HTTP 401."""
        settings.AUTH_ENFORCED = True
        try:
            # 1. Upload endpoint
            res_upload = self.client.post("/api/v1/documents/upload")
            self.assertEqual(res_upload.status_code, 401)
            self.assertIn("Authentication required", res_upload.json()["detail"])

            # 2. Query endpoint
            res_query = self.client.post(
                "/api/v1/query",
                json={"question": "average attendance"},
            )
            self.assertEqual(res_query.status_code, 401)

            # 3. Source preview endpoint
            dummy_id = str(uuid.uuid4())
            res_source = self.client.get(f"/api/v1/sources/{dummy_id}")
            self.assertEqual(res_source.status_code, 401)

            # 4. Document approval endpoint
            res_appr = self.client.post(f"/api/v1/documents/{dummy_id}/approve", json={})
            self.assertEqual(res_appr.status_code, 401)

            # 5. Auth /me endpoint
            res_me = self.client.get("/api/v1/auth/me")
            self.assertEqual(res_me.status_code, 401)
        finally:
            settings.AUTH_ENFORCED = False

    def test_malformed_authorization_header(self):
        """Malformed authorization headers return HTTP 401."""
        res = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("Invalid authorization header format", res.json()["detail"])

    def test_empty_bearer_token(self):
        """Bearer header with empty token returns HTTP 401."""
        res = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer "},
        )
        self.assertEqual(res.status_code, 401)

    # =========================================================================
    # 2. Successful Authentication Tests
    # =========================================================================

    def test_successful_login_all_roles(self):
        """Verify successful login and correct token claims/permissions for all office roles."""
        role_credentials = [
            ("admin", "admin123", "admin", {"upload", "review", "read", "read_sources", "admin"}),
            ("reviewer", "reviewer123", "reviewer", {"review", "read", "read_sources"}),
            ("uploader", "uploader123", "uploader", {"upload", "read", "read_sources"}),
            ("viewer", "viewer123", "viewer", {"read", "read_sources"}),
        ]

        for username, password, expected_role, expected_perms in role_credentials:
            res = self.client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password},
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("access_token", data)
            self.assertEqual(data["token_type"], "bearer")
            self.assertGreater(data["expires_in"], 0)

            user = data["user"]
            self.assertEqual(user["username"], username)
            self.assertEqual(user["role"], expected_role)
            self.assertTrue(user["is_active"])
            for perm in expected_perms:
                self.assertIn(perm, user["permissions"])

    def test_get_current_user_profile(self):
        """GET /api/v1/auth/me returns the authenticated user's profile and permissions."""
        res = self.client.get(
            "/api/v1/auth/me",
            headers=self._auth_header(self.admin_token),
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["username"], "admin")
        self.assertEqual(data["role"], "admin")
        self.assertIn("upload", data["permissions"])
        self.assertIn("review", data["permissions"])

    def test_seed_endpoint_idempotent(self):
        """POST /api/v1/auth/seed is idempotent and returns all default accounts."""
        res = self.client.post("/api/v1/auth/seed")
        self.assertEqual(res.status_code, 200)
        users = res.json()
        usernames = [u["username"] for u in users]
        self.assertIn("admin", usernames)
        self.assertIn("reviewer", usernames)
        self.assertIn("uploader", usernames)
        self.assertIn("viewer", usernames)

    # =========================================================================
    # 3. Invalid Authentication Tests
    # =========================================================================

    def test_login_invalid_password(self):
        """Login with wrong password returns HTTP 401."""
        res = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong_password_123"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("Incorrect username or password", res.json()["detail"])

    def test_login_non_existent_user(self):
        """Login with unknown username returns HTTP 401."""
        res = self.client.post(
            "/api/v1/auth/login",
            json={"username": "ghost_operator", "password": "password"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("Incorrect username or password", res.json()["detail"])

    def test_login_deactivated_user(self):
        """Deactivated user account cannot login or use existing tokens."""
        # Create an inactive user
        user = create_user(
            db=self.db,
            username="inactive_clerk",
            email="inactive@rssb.local",
            password="secretpassword",
            role="viewer",
            is_active=False,
            auto_commit=True,
        )

        res = self.client.post(
            "/api/v1/auth/login",
            json={"username": "inactive_clerk", "password": "secretpassword"},
        )
        self.assertEqual(res.status_code, 401)

        # Generating token manually for inactive user must fail at dependency check
        token = create_access_token({"sub": "inactive_clerk", "role": "viewer"})
        res_me = self.client.get(
            "/api/v1/auth/me",
            headers=self._auth_header(token),
        )
        self.assertEqual(res_me.status_code, 401)
        self.assertIn("inactive", res_me.json()["detail"].lower())

    def test_expired_access_token(self):
        """Expired JWT access token returns HTTP 401."""
        expired_token = create_access_token(
            {"sub": "admin", "role": "admin"},
            expires_delta=timedelta(minutes=-10),  # expired 10 minutes ago
        )
        res = self.client.get(
            "/api/v1/auth/me",
            headers=self._auth_header(expired_token),
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("expired", res.json()["detail"].lower())

    def test_corrupted_token_signature(self):
        """Token with invalid/tampered signature returns HTTP 401."""
        corrupted_token = self.admin_token[:-6] + "tamper"
        res = self.client.get(
            "/api/v1/auth/me",
            headers=self._auth_header(corrupted_token),
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("invalid token", res.json()["detail"].lower())

    # =========================================================================
    # 4. Authorized Role Access Tests
    # =========================================================================

    def test_uploader_can_upload_excel(self):
        """User with role 'uploader' is permitted to upload office data."""
        file_path = FIXTURES_DIR / "valid_attendance.xlsx"
        with open(file_path, "rb") as f:
            res = self.client.post(
                "/api/v1/documents/upload",
                headers=self._auth_header(self.uploader_token),
                files={"file": ("uploader_test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"data_source_name": "Uploader Role Test"},
            )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("document_id", data)
        self.assertEqual(data["records_accepted"], 3)

    def test_admin_can_perform_all_operations(self):
        """User with role 'admin' can upload, validate, approve, query, and view sources."""
        # 1. Admin upload
        file_path = FIXTURES_DIR / "clean_attendance.xlsx"
        with open(file_path, "rb") as f:
            res_upload = self.client.post(
                "/api/v1/documents/upload",
                headers=self._auth_header(self.admin_token),
                files={"file": ("admin_test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        self.assertEqual(res_upload.status_code, 200)
        doc_id = res_upload.json()["document_id"]

        # 2. Admin validate
        res_val = self.client.post(
            f"/api/v1/documents/{doc_id}/validate",
            headers=self._auth_header(self.admin_token),
        )
        self.assertEqual(res_val.status_code, 200)

        # 3. Admin approve
        res_appr = self.client.post(
            f"/api/v1/documents/{doc_id}/approve",
            headers=self._auth_header(self.admin_token),
            json={"notes": "Approved by Administrator"},
        )
        self.assertEqual(res_appr.status_code, 200)
        self.assertEqual(res_appr.json()["status"], "approved")

        # 4. Admin query
        res_query = self.client.post(
            "/api/v1/query",
            headers=self._auth_header(self.admin_token),
            json={"question": "find attendance"},
        )
        self.assertEqual(res_query.status_code, 200)

    def test_uploader_can_upload_pdf(self):
        """User with role 'uploader' is permitted to upload PDF office documents."""
        file_path = FIXTURES_DIR / "RSSB_Dummy_Attendance_October_2026.pdf"
        with open(file_path, "rb") as f:
            res = self.client.post(
                "/api/v1/documents/upload",
                headers=self._auth_header(self.uploader_token),
                files={"file": ("uploader_pdf_test.pdf", f, "application/pdf")},
                data={"data_source_name": "Uploader PDF Role Test"},
            )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("document_id", data)
        self.assertGreater(data.get("structured_records_created", data.get("records_accepted", 0)), 0)

    # =========================================================================
    # 5. Unauthorized Role Access Tests
    # =========================================================================

    def test_viewer_blocked_from_upload(self):
        """User with role 'viewer' is forbidden from uploading office data."""
        file_path = FIXTURES_DIR / "valid_attendance.xlsx"
        with open(file_path, "rb") as f:
            res = self.client.post(
                "/api/v1/documents/upload",
                headers=self._auth_header(self.viewer_token),
                files={"file": ("viewer_forbidden.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        self.assertEqual(res.status_code, 403)
        self.assertIn("does not have 'upload' permission", res.json()["detail"])

    def test_viewer_blocked_from_upload_pdf(self):
        """User with role 'viewer' is forbidden from uploading PDF documents."""
        file_path = FIXTURES_DIR / "RSSB_Dummy_Attendance_October_2026.pdf"
        with open(file_path, "rb") as f:
            res = self.client.post(
                "/api/v1/documents/upload",
                headers=self._auth_header(self.viewer_token),
                files={"file": ("viewer_pdf_forbidden.pdf", f, "application/pdf")},
            )
        self.assertEqual(res.status_code, 403)
        self.assertIn("does not have 'upload' permission", res.json()["detail"])

    def test_viewer_blocked_from_review_actions(self):
        """User with role 'viewer' is forbidden from review actions (approve, reject, correct)."""
        dummy_id = str(uuid.uuid4())

        # Approve
        res_appr = self.client.post(
            f"/api/v1/documents/{dummy_id}/approve",
            headers=self._auth_header(self.viewer_token),
            json={"notes": "Should fail"},
        )
        self.assertEqual(res_appr.status_code, 403)

        # Reject
        res_rej = self.client.post(
            f"/api/v1/documents/{dummy_id}/reject",
            headers=self._auth_header(self.viewer_token),
            json={"reason": "Should fail"},
        )
        self.assertEqual(res_rej.status_code, 403)

        # Needs Correction
        res_nc = self.client.post(
            f"/api/v1/documents/{dummy_id}/needs-correction",
            headers=self._auth_header(self.viewer_token),
            json={"instructions": "Should fail"},
        )
        self.assertEqual(res_nc.status_code, 403)

    def test_uploader_blocked_from_review_actions(self):
        """User with role 'uploader' is forbidden from approving or rejecting documents."""
        dummy_id = str(uuid.uuid4())
        res = self.client.post(
            f"/api/v1/documents/{dummy_id}/approve",
            headers=self._auth_header(self.uploader_token),
            json={"notes": "Uploader trying to approve"},
        )
        self.assertEqual(res.status_code, 403)

    def test_reviewer_blocked_from_uploading(self):
        """User with role 'reviewer' is forbidden from uploading new documents."""
        file_path = FIXTURES_DIR / "valid_attendance.xlsx"
        with open(file_path, "rb") as f:
            res = self.client.post(
                "/api/v1/documents/upload",
                headers=self._auth_header(self.reviewer_token),
                files={"file": ("reviewer_forbidden.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        self.assertEqual(res.status_code, 403)
        self.assertIn("does not have 'upload' permission", res.json()["detail"])

    # =========================================================================
    # 6. Existing Excel/PDF Workflow Integrity with Authentication
    # =========================================================================

    def test_full_workflow_with_authentication(self):
        """
        Verify end-to-end office workflow under authenticated sessions:
        1. Uploader uploads Excel attendance file.
        2. Duplicate detection works on second upload.
        3. Reviewer validates and approves the document.
        4. Viewer queries average attendance and receives verified calculations.
        5. Viewer inspects source provenance preview.
        """
        file_path = FIXTURES_DIR / "RSSB_Dummy_Attendance_October_2026.xlsx"

        # 1. Uploader uploads Excel
        with open(file_path, "rb") as f:
            res1 = self.client.post(
                "/api/v1/documents/upload",
                headers=self._auth_header(self.uploader_token),
                files={"file": ("october_attendance.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"data_source_name": "Authenticated Workflow Test"},
            )
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        doc_id = data1["document_id"]
        self.assertEqual(data1["duplicate_status"], "new")
        self.assertGreater(data1["records_accepted"], 0)

        # 2. Uploader uploads duplicate
        with open(file_path, "rb") as f:
            res2 = self.client.post(
                "/api/v1/documents/upload",
                headers=self._auth_header(self.uploader_token),
                files={"file": ("october_attendance_dup.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"data_source_name": "Authenticated Workflow Test"},
            )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["duplicate_status"], "duplicate")

        # 3. Reviewer validates and approves
        val_res = self.client.post(
            f"/api/v1/documents/{doc_id}/validate",
            headers=self._auth_header(self.reviewer_token),
        )
        self.assertEqual(val_res.status_code, 200)

        appr_res = self.client.post(
            f"/api/v1/documents/{doc_id}/approve",
            headers=self._auth_header(self.reviewer_token),
            json={"notes": "Approved in end-to-end regression test"},
        )
        self.assertEqual(appr_res.status_code, 200)
        self.assertEqual(appr_res.json()["status"], "approved")

        # 4. Viewer queries office data
        query_res = self.client.post(
            "/api/v1/query",
            headers=self._auth_header(self.viewer_token),
            json={"question": "find the average attendance of kila road"},
        )
        self.assertEqual(query_res.status_code, 200)
        query_data = query_res.json()
        self.assertEqual(query_data["status"], "success")
        self.assertIsNotNone(query_data["calculation"])
        self.assertEqual(query_data["calculation"]["value"], 130.25)
        self.assertEqual(query_data["calculation"]["records_counted"], 4)

        # 5. Viewer inspects source reference preview
        self.assertGreater(len(query_data["source_references"]), 0)
        first_source = query_data["source_references"][0]
        source_id = first_source["id"]

        source_res = self.client.get(
            f"/api/v1/sources/{source_id}/preview",
            headers=self._auth_header(self.viewer_token),
        )
        self.assertEqual(source_res.status_code, 200)
        preview_data = source_res.json()
        self.assertEqual(preview_data["source_id"], source_id)
        self.assertIn("document_name", preview_data)
        self.assertIn("relevance_explanation", preview_data)


if __name__ == "__main__":
    unittest.main()
