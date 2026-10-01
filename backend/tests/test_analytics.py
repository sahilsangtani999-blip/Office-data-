"""
Comprehensive automated unit & integration test suite for
Phase 3.0 — Multi-Document Analytics & Comparison.
"""

from datetime import date
import os
from pathlib import Path
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_password_hash
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import (
    Assignment,
    Attendance,
    Document,
    DocumentVersion,
    Person,
    Role,
    SatsangGhar,
    SourceReference,
    User,
    VehicleWheelData,
)
from app.schemas.analytics import ComparisonRequest, MultiDocSummaryRequest
from app.services.analytics_service import AnalyticsService
from app.services.excel_ingestion import ingest_excel_file

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _clean_tables():
    with engine.begin() as conn:
        conn.execute(VehicleWheelData.__table__.delete())
        conn.execute(Assignment.__table__.delete())
        conn.execute(Attendance.__table__.delete())
        conn.execute(SourceReference.__table__.delete())
        conn.execute(DocumentVersion.__table__.delete())
        conn.execute(Document.__table__.delete())
        conn.execute(Role.__table__.delete())
        conn.execute(Person.__table__.delete())
        conn.execute(SatsangGhar.__table__.delete())
        conn.execute(User.__table__.delete())


class TestMultiDocumentAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        _clean_tables()

        cls.db: Session = SessionLocal()
        cls.client = TestClient(app)

        # 1. Seed Roles
        cls.role_sk = Role(code="SK", name="Satsang Karta")
        cls.role_sr = Role(code="SR", name="Satsang Reader")
        cls.db.add_all([cls.role_sk, cls.role_sr])

        # 2. Seed Satsang Ghars
        cls.ghar_sukhliya = SatsangGhar(name="Sukhliya")
        cls.ghar_bicholi = SatsangGhar(name="Bicholi")
        cls.ghar_pithampur = SatsangGhar(name="Pithampur")
        cls.db.add_all([cls.ghar_sukhliya, cls.ghar_bicholi, cls.ghar_pithampur])

        # 3. Seed Users with various roles for RBAC verification
        cls.admin_user = User(
            username="admin_user",
            email="admin@rssb.org",
            role="admin",
            hashed_password=get_password_hash("pass123"),
            is_active=True,
        )
        cls.viewer_user = User(
            username="viewer_user",
            email="viewer@rssb.org",
            role="viewer",
            hashed_password=get_password_hash("pass123"),
            is_active=True,
        )
        cls.db.add_all([cls.admin_user, cls.viewer_user])
        cls.db.commit()

        # Generate JWT Bearer tokens
        cls.admin_token = create_access_token(data={"sub": cls.admin_user.username, "role": cls.admin_user.role})
        cls.viewer_token = create_access_token(data={"sub": cls.viewer_user.username, "role": cls.viewer_user.role})
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}
        cls.viewer_headers = {"Authorization": f"Bearer {cls.viewer_token}"}

        # 4. Ingest multi-month fixtures
        # Ingest September data (search_test_data.xlsx)
        sept_path = FIXTURES_DIR / "search_test_data.xlsx"
        if sept_path.exists():
            cls.sept_doc_res = ingest_excel_file(
                cls.db,
                file_path=str(sept_path),
                original_filename="search_test_data.xlsx",
                data_source_name="Test Suite",
            )

        # Ingest October data (RSSB_Dummy_Attendance_October_2026.xlsx)
        oct_att_path = FIXTURES_DIR / "RSSB_Dummy_Attendance_October_2026.xlsx"
        if oct_att_path.exists():
            cls.oct_doc_res = ingest_excel_file(
                cls.db,
                file_path=str(oct_att_path),
                original_filename="RSSB_Dummy_Attendance_October_2026.xlsx",
                data_source_name="Test Suite",
            )

        # Ingest September vehicles (RSSB_Dummy_Vehicle_September_2026.xlsx)
        sept_veh_path = FIXTURES_DIR / "RSSB_Dummy_Vehicle_September_2026.xlsx"
        if sept_veh_path.exists():
            cls.sept_veh_res = ingest_excel_file(
                cls.db,
                file_path=str(sept_veh_path),
                original_filename="RSSB_Dummy_Vehicle_September_2026.xlsx",
                data_source_name="Test Suite",
            )

        # Ingest October assignments and vehicles (RSSB_Dummy_Assignment_Vehicle_October_2026.xlsx)
        oct_asg_path = FIXTURES_DIR / "RSSB_Dummy_Assignment_Vehicle_October_2026.xlsx"
        if oct_asg_path.exists():
            cls.oct_asg_res = ingest_excel_file(
                cls.db,
                file_path=str(oct_asg_path),
                original_filename="RSSB_Dummy_Assignment_Vehicle_October_2026.xlsx",
                data_source_name="Test Suite",
            )

        cls.db.commit()
        cls.service = AnalyticsService(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    # -------------------------------------------------------------------------
    # 1. Location Comparison (Sukhliya vs Bicholi)
    # -------------------------------------------------------------------------
    def test_1_location_comparison_attendance(self):
        """Verifies center-to-center attendance comparison, delta, and provenance."""
        req = ComparisonRequest(
            dimension="location",
            metric="attendance",
            entity_a="Sukhliya",
            entity_b="Bicholi",
            shared_period_start=date(2026, 9, 1),
            shared_period_end=date(2026, 9, 30),
        )
        res = self.service.compare(req)

        self.assertEqual(res.dimension, "location")
        self.assertEqual(res.metric, "attendance")
        self.assertEqual(res.entity_a.label, "Sukhliya")
        self.assertEqual(res.entity_b.label, "Bicholi")
        self.assertGreater(res.entity_a.record_count, 0)
        self.assertGreater(res.entity_b.record_count, 0)

        # Delta must be B - A
        expected_delta = round(res.entity_b.primary_value - res.entity_a.primary_value, 2)
        self.assertEqual(res.delta, expected_delta)
        self.assertIsNotNone(res.percentage_change)
        self.assertIn("Comparison of Average Attendance", res.summary_sentence)
        self.assertGreater(len(res.source_references), 0)

    # -------------------------------------------------------------------------
    # 2. Period-over-Period Comparison (September vs October)
    # -------------------------------------------------------------------------
    def test_2_period_comparison_attendance(self):
        """Verifies month-over-month attendance comparison across multiple documents."""
        req = ComparisonRequest(
            dimension="period",
            metric="attendance",
            satsang_ghar="Sukhliya",
            period_a_start=date(2026, 9, 1),
            period_a_end=date(2026, 9, 30),
            period_b_start=date(2026, 10, 1),
            period_b_end=date(2026, 10, 31),
        )
        res = self.service.compare(req)

        self.assertEqual(res.dimension, "period")
        self.assertEqual(res.metric, "attendance")
        self.assertIn("Sukhliya", res.entity_a.label)
        self.assertIn("Sukhliya", res.entity_b.label)
        self.assertGreater(res.entity_a.record_count, 0)
        self.assertGreater(res.entity_b.record_count, 0)

        # Contributing documents must span multiple files
        all_docs = res.entity_a.document_names + res.entity_b.document_names
        self.assertTrue(len(set(all_docs)) >= 2)
        self.assertIn("search_test_data.xlsx", all_docs)
        self.assertIn("RSSB_Dummy_Attendance_October_2026.xlsx", all_docs)

    # -------------------------------------------------------------------------
    # 3. Vehicle Log Comparison
    # -------------------------------------------------------------------------
    def test_3_vehicle_comparison_across_months(self):
        """Verifies transportation vehicle comparison between September and October."""
        req = ComparisonRequest(
            dimension="period",
            metric="vehicle_wheel",
            period_a_start=date(2026, 9, 1),
            period_a_end=date(2026, 9, 30),
            period_b_start=date(2026, 10, 1),
            period_b_end=date(2026, 10, 31),
        )
        res = self.service.compare(req)

        self.assertEqual(res.dimension, "period")
        self.assertEqual(res.metric, "vehicle_wheel")
        self.assertEqual(res.unit, "vehicles")
        self.assertGreater(res.entity_a.primary_value, 0)
        self.assertGreater(res.entity_b.primary_value, 0)
        self.assertIsNotNone(res.delta)

    # -------------------------------------------------------------------------
    # 4. Duty Assignment Comparison
    # -------------------------------------------------------------------------
    def test_4_duty_assignment_comparison(self):
        """Verifies sewadar assignment comparison between locations."""
        req = ComparisonRequest(
            dimension="location",
            metric="assignment",
            entity_a="Sukhliya",
            entity_b="Bicholi",
            shared_period_start=date(2026, 9, 1),
            shared_period_end=date(2026, 10, 31),
        )
        res = self.service.compare(req)

        self.assertEqual(res.dimension, "location")
        self.assertEqual(res.metric, "assignment")
        self.assertEqual(res.unit, "assignments")
        self.assertIsNotNone(res.delta)

    # -------------------------------------------------------------------------
    # 5. Division by Zero Handling
    # -------------------------------------------------------------------------
    def test_5_division_by_zero_handling(self):
        """When baseline entity has 0 records, percentage_change should be None without crashing."""
        req = ComparisonRequest(
            dimension="location",
            metric="attendance",
            entity_a="Pithampur",  # Has 0 attendance records in test data
            entity_b="Sukhliya",
            shared_period_start=date(2026, 9, 1),
            shared_period_end=date(2026, 9, 30),
        )
        res = self.service.compare(req)
        self.assertEqual(res.entity_a.primary_value, 0.0)
        self.assertIsNone(res.percentage_change)
        self.assertEqual(res.delta, res.entity_b.primary_value)

    # -------------------------------------------------------------------------
    # 6. Parameter Validation & Error Handling
    # -------------------------------------------------------------------------
    def test_6_invalid_comparison_parameters(self):
        """API rejects missing entities or identical entities with 400 Bad Request."""
        # Missing entity_b
        res1 = self.client.post(
            "/api/v1/analytics/compare",
            headers=self.admin_headers,
            json={"dimension": "location", "entity_a": "Sukhliya"},
        )
        self.assertEqual(res1.status_code, 400)

        # Identical entities
        res2 = self.client.post(
            "/api/v1/analytics/compare",
            headers=self.admin_headers,
            json={"dimension": "location", "entity_a": "Sukhliya", "entity_b": "Sukhliya"},
        )
        self.assertEqual(res2.status_code, 400)

        # Non-existent center
        res3 = self.client.post(
            "/api/v1/analytics/compare",
            headers=self.admin_headers,
            json={"dimension": "location", "entity_a": "Sukhliya", "entity_b": "NonExistentCenter"},
        )
        self.assertEqual(res3.status_code, 400)

    # -------------------------------------------------------------------------
    # 7. Multi-Document Summary Aggregation
    # -------------------------------------------------------------------------
    def test_7_multi_document_summary(self):
        """Verifies POST /api/v1/analytics/multi-document-summary."""
        res = self.client.post(
            "/api/v1/analytics/multi-document-summary",
            headers=self.viewer_headers,
            json={"date_start": "2026-09-01", "date_end": "2026-10-31"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["total_documents"], 2)
        self.assertGreater(data["total_attendance"], 0)
        self.assertGreater(data["total_vehicles"], 0)
        self.assertTrue(len(data["per_document_breakdown"]) >= 2)

    # -------------------------------------------------------------------------
    # 8. Dimensions & Options Metadata
    # -------------------------------------------------------------------------
    def test_8_dimensions_metadata(self):
        """Verifies GET /api/v1/analytics/dimensions metadata."""
        res = self.client.get("/api/v1/analytics/dimensions", headers=self.viewer_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("dimensions", data)
        self.assertIn("metrics", data)
        self.assertIn("known_satsang_ghars", data)
        self.assertIn("Sukhliya", data["known_satsang_ghars"])
        self.assertIn("Bicholi", data["known_satsang_ghars"])

    # -------------------------------------------------------------------------
    # 9. RBAC Enforcement
    # -------------------------------------------------------------------------
    def test_9_rbac_enforcement(self):
        """Verifies unauthenticated access is rejected, while authenticated roles succeed."""
        from app.config import settings

        payload = {
            "dimension": "location",
            "metric": "attendance",
            "entity_a": "Sukhliya",
            "entity_b": "Bicholi",
            "shared_period_start": "2026-09-01",
            "shared_period_end": "2026-09-30",
        }
        # 1. Unauthenticated with explicit X-Authorized=false -> 401
        res_unauth = self.client.post("/api/v1/analytics/compare", headers={"X-Authorized": "false"}, json=payload)
        self.assertEqual(res_unauth.status_code, 401)

        # 2. Unauthenticated with AUTH_ENFORCED=True -> 401
        settings.AUTH_ENFORCED = True
        try:
            res_enforced = self.client.post("/api/v1/analytics/compare", json=payload)
            self.assertEqual(res_enforced.status_code, 401)
        finally:
            settings.AUTH_ENFORCED = False

        # 3. Viewer role (has read permission) -> 200 OK
        res_viewer = self.client.post("/api/v1/analytics/compare", headers=self.viewer_headers, json=payload)
        self.assertEqual(res_viewer.status_code, 200)

        # 4. Admin role -> 200 OK
        res_admin = self.client.post("/api/v1/analytics/compare", headers=self.admin_headers, json=payload)
        self.assertEqual(res_admin.status_code, 200)

    # -------------------------------------------------------------------------
    # 10. Natural-Language Search Integration (Centre vs Centre)
    # -------------------------------------------------------------------------
    def test_10_nl_search_compare_locations(self):
        """Tests natural-language query 'Compare attendance between Sukhliya and Bicholi'."""
        q = "Compare attendance between Sukhliya and Bicholi"
        res = self.client.post("/api/v1/query", headers=self.viewer_headers, json={"question": q})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("Comparison of Average Attendance", data["answer"])
        self.assertIn("Sukhliya", data["answer"])
        self.assertIn("Bicholi", data["answer"])
        self.assertEqual(data["calculation"]["operation"], "compare")
        self.assertTrue(len(data["records"]) >= 2)
        self.assertTrue(len(data["source_references"]) >= 1)

    # -------------------------------------------------------------------------
    # 11. Natural-Language Search Integration (Period vs Period)
    # -------------------------------------------------------------------------
    def test_11_nl_search_compare_periods(self):
        """Tests natural-language query 'Compare September vs October attendance at Sukhliya'."""
        q = "Compare September vs October attendance at Sukhliya"
        res = self.client.post("/api/v1/query", headers=self.viewer_headers, json={"question": q})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("Period Comparison", data["answer"])
        self.assertIn("Sukhliya", data["answer"])
        self.assertEqual(data["calculation"]["operation"], "compare")
        self.assertTrue(len(data["records"]) >= 2)

    # -------------------------------------------------------------------------
    # 12. Cross-Document Source Reference Traceability
    # -------------------------------------------------------------------------
    def test_12_cross_document_source_provenance(self):
        """Confirms that source_references contain valid document names, sheets, and coordinates."""
        req = ComparisonRequest(
            dimension="location",
            metric="attendance",
            entity_a="Sukhliya",
            entity_b="Bicholi",
            shared_period_start=date(2026, 9, 1),
            shared_period_end=date(2026, 9, 30),
        )
        res = self.service.compare(req)
        self.assertGreater(len(res.source_references), 0)
        first_ref = res.source_references[0]
        self.assertIsNotNone(first_ref.document_name)
        self.assertIsNotNone(first_ref.sheet_name)
        self.assertIsNotNone(first_ref.row_number)


if __name__ == "__main__":
    unittest.main()
