"""
Test suite for Phase 3.2 — Visual Analytics, Trend Trajectories & Operational Insights.
"""

from datetime import date
import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal, engine
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
from app.services.auth_service import seed_default_users
from app.services.trend_service import TrendService


def _clean_tables():
    """Wipes test data to ensure isolation."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE assignments, attendances, vehicle_wheel_data, "
                "source_references, document_versions, documents, data_sources, "
                "satsang_ghars, persons, roles, reports, users CASCADE;"
            )
        )


class TestTrendsAndDashboard(unittest.TestCase):
    """Test suite covering Phase 3.2 Trend Trajectories, Executive Dashboard, and Anomalies."""

    @classmethod
    def setUpClass(cls):
        _clean_tables()
        cls.db = SessionLocal()
        cls.client = TestClient(app)

        # 1. Seed users
        seed_default_users(cls.db)

        # 2. Obtain valid tokens for each role
        cls.tokens = {}
        for role in ["admin", "reviewer", "uploader", "viewer"]:
            res = cls.client.post(
                "/api/v1/auth/login",
                json={"username": role, "password": f"{role}123"},
            )
            assert res.status_code == 200, f"Login failed for {role}: {res.text}"
            cls.tokens[role] = res.json()["access_token"]

        # 3. Seed domain records
        cls._seed_trend_records()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        _clean_tables()
        with SessionLocal() as db:
            seed_default_users(db)

    @classmethod
    def _seed_trend_records(cls):
        # Centers
        cls.ghar_sukhliya = SatsangGhar(name="Sukhliya", status="active")
        cls.ghar_khandwa = SatsangGhar(name="Khandwa", status="active")
        cls.db.add_all([cls.ghar_sukhliya, cls.ghar_khandwa])
        cls.db.commit()

        # Approved Document
        cls.doc_approved = Document(
            original_filename="approved_schedule.xlsx",
            document_type="excel",
            status="approved",
        )
        cls.db.add(cls.doc_approved)
        cls.db.commit()

        cls.ver_approved = DocumentVersion(
            document_id=cls.doc_approved.id,
            version_number=1,
            storage_path="/tmp/trend_1.xlsx",
            content_hash="trend_hash_1",
            status="active",
        )
        cls.db.add(cls.ver_approved)
        cls.db.commit()

        # Rejected Document (should be excluded)
        cls.doc_rejected = Document(
            original_filename="rejected_schedule.xlsx",
            document_type="excel",
            status="rejected",
        )
        cls.db.add(cls.doc_rejected)
        cls.db.commit()

        cls.ver_rejected = DocumentVersion(
            document_id=cls.doc_rejected.id,
            version_number=1,
            storage_path="/tmp/trend_rej.xlsx",
            content_hash="trend_hash_rej",
            status="active",
        )
        cls.db.add(cls.ver_rejected)
        cls.db.commit()

        cls.ref_approved = SourceReference(
            document_id=cls.doc_approved.id,
            document_version_id=cls.ver_approved.id,
            sheet_name="Attendance",
        )
        cls.ref_rejected = SourceReference(
            document_id=cls.doc_rejected.id,
            document_version_id=cls.ver_rejected.id,
            sheet_name="Attendance",
        )
        cls.db.add_all([cls.ref_approved, cls.ref_rejected])
        cls.db.commit()

        # Attendance data points over 4 consecutive months for Sukhliya (100 -> 120 -> 150 -> 250)
        # Month 1: Jul 2026
        cls.db.add(
            Attendance(
                date=date(2026, 7, 5),
                satsang_ghar_id=cls.ghar_sukhliya.id,
                count_value=100,
                raw_value="100",
                status="active",
                source_reference_id=cls.ref_approved.id,
            )
        )
        # Month 2: Aug 2026
        cls.db.add(
            Attendance(
                date=date(2026, 8, 2),
                satsang_ghar_id=cls.ghar_sukhliya.id,
                count_value=120,
                raw_value="120",
                status="active",
                source_reference_id=cls.ref_approved.id,
            )
        )
        # Month 3: Sep 2026
        cls.db.add(
            Attendance(
                date=date(2026, 9, 6),
                satsang_ghar_id=cls.ghar_sukhliya.id,
                count_value=150,
                raw_value="150",
                status="active",
                source_reference_id=cls.ref_approved.id,
            )
        )
        # Month 4: Oct 2026 (anomalous surge from 150 to 250 = +66.7%)
        cls.db.add(
            Attendance(
                date=date(2026, 10, 4),
                satsang_ghar_id=cls.ghar_sukhliya.id,
                count_value=250,
                raw_value="250",
                status="active",
                source_reference_id=cls.ref_approved.id,
            )
        )

        # Rejected attendance record (should NOT count)
        cls.db.add(
            Attendance(
                date=date(2026, 10, 11),
                satsang_ghar_id=cls.ghar_sukhliya.id,
                count_value=9999,
                raw_value="9999",
                status="active",
                source_reference_id=cls.ref_rejected.id,
            )
        )

        # Attendance data points for Khandwa (50 -> 60 -> 70 -> 75)
        cls.db.add(
            Attendance(
                date=date(2026, 7, 12),
                satsang_ghar_id=cls.ghar_khandwa.id,
                count_value=50,
                raw_value="50",
                status="active",
                source_reference_id=cls.ref_approved.id,
            )
        )
        cls.db.add(
            Attendance(
                date=date(2026, 8, 9),
                satsang_ghar_id=cls.ghar_khandwa.id,
                count_value=60,
                raw_value="60",
                status="active",
                source_reference_id=cls.ref_approved.id,
            )
        )
        cls.db.add(
            Attendance(
                date=date(2026, 9, 13),
                satsang_ghar_id=cls.ghar_khandwa.id,
                count_value=70,
                raw_value="70",
                status="active",
                source_reference_id=cls.ref_approved.id,
            )
        )
        cls.db.add(
            Attendance(
                date=date(2026, 10, 11),
                satsang_ghar_id=cls.ghar_khandwa.id,
                count_value=75,
                raw_value="75",
                status="active",
                source_reference_id=cls.ref_approved.id,
            )
        )

        # Sewadar Assignments
        role_sk = Role(name="SK", code="SK")
        cls.db.add(role_sk)
        cls.db.commit()

        p1 = Person(name="Bhai Amrit", status="active")
        cls.db.add(p1)
        cls.db.commit()

        cls.db.add(
            Assignment(
                date=date(2026, 10, 4),
                satsang_ghar_id=cls.ghar_sukhliya.id,
                role_id=role_sk.id,
                person_id=p1.id,
                status="active",
                source_reference_id=cls.ref_approved.id,
            )
        )

        cls.db.commit()

    def test_trends_endpoint_default(self):
        """Test GET /api/v1/analytics/trends with default parameters."""
        headers = {"Authorization": f"Bearer {self.tokens['admin']}"}
        res = self.client.get("/api/v1/analytics/trends", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["metric"], "attendance")
        self.assertEqual(data["interval"], "month")
        self.assertGreaterEqual(len(data["data_points"]), 4)

        # Check moving averages are calculated
        has_moving_avg = any(pt["moving_average"] is not None for pt in data["data_points"])
        self.assertTrue(has_moving_avg)

        # Check overall direction is calculated
        self.assertIn(data["overall_direction"], ["growth", "decline", "stable", "neutral"])
        self.assertIsNotNone(data["growth_rate_overall"])

    def test_trends_center_filter(self):
        """Test GET /api/v1/analytics/trends filtering by Sukhliya."""
        headers = {"Authorization": f"Bearer {self.tokens['viewer']}"}
        res = self.client.get(
            "/api/v1/analytics/trends?center=Sukhliya&metric=attendance&interval=month",
            headers=headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["target_entity"], "Sukhliya")
        # Ensure values exclude rejected document (which had count 9999)
        oct_points = [p for p in data["data_points"] if "2026-10" in (p["date_key"] or p["period_label"])]
        self.assertEqual(len(oct_points), 1)
        self.assertEqual(oct_points[0]["value"], 250)

    def test_trends_metrics_assignments_and_vehicles(self):
        """Test trends with assignment and vehicle_wheel metrics."""
        headers = {"Authorization": f"Bearer {self.tokens['reviewer']}"}
        res_asg = self.client.get("/api/v1/analytics/trends?metric=assignment", headers=headers)
        self.assertEqual(res_asg.status_code, 200)
        self.assertEqual(res_asg.json()["metric"], "assignment")

        res_veh = self.client.get("/api/v1/analytics/trends?metric=vehicle_wheel", headers=headers)
        self.assertEqual(res_veh.status_code, 200)
        self.assertEqual(res_veh.json()["metric"], "vehicle_wheel")

    def test_trends_intervals_month_and_day(self):
        """Test trends with month and day bucketing."""
        headers = {"Authorization": f"Bearer {self.tokens['admin']}"}
        res_m = self.client.get("/api/v1/analytics/trends?interval=month", headers=headers)
        self.assertEqual(res_m.status_code, 200)
        self.assertEqual(res_m.json()["interval"], "month")

        res_d = self.client.get("/api/v1/analytics/trends?interval=day", headers=headers)
        self.assertEqual(res_d.status_code, 200)
        self.assertEqual(res_d.json()["interval"], "day")

    def test_dashboard_endpoint(self):
        """Test GET /api/v1/analytics/dashboard returns executive KPIs and center rankings."""
        headers = {"Authorization": f"Bearer {self.tokens['viewer']}"}
        res = self.client.get("/api/v1/analytics/dashboard", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Check KPIs
        kpis = data["summary_kpis"]
        self.assertGreater(kpis["total_attendance"], 0)
        self.assertGreaterEqual(kpis["total_duty_assignments"], 1)
        self.assertGreaterEqual(kpis["total_meetings"], 1)
        self.assertEqual(kpis["active_centers_count"], 2)

        # Check rankings
        rankings = data["center_rankings"]
        self.assertGreaterEqual(len(rankings), 2)
        # Sukhliya should be ranked higher due to higher attendance
        self.assertEqual(rankings[0]["satsang_ghar"], "Sukhliya")

    def test_anomalies_endpoint(self):
        """Test GET /api/v1/analytics/anomalies identifies rapid attendance surge in Sukhliya."""
        headers = {"Authorization": f"Bearer {self.tokens['admin']}"}
        res = self.client.get("/api/v1/analytics/anomalies?threshold_pct=25.0", headers=headers)
        self.assertEqual(res.status_code, 200)
        anomalies = res.json()
        self.assertIsInstance(anomalies, list)
        self.assertGreaterEqual(len(anomalies), 1)

        # Should find Sukhliya anomalies between mean (155) and observations (100 and 250)
        sukhliya_anom = [a for a in anomalies if a["entity"] == "Sukhliya"]
        self.assertTrue(len(sukhliya_anom) > 0)
        severities = [a["severity"] for a in sukhliya_anom]
        self.assertIn("HIGH", severities)

    def test_rbac_authentication(self):
        """Test RBAC controls on Phase 3.2 endpoints."""
        from unittest.mock import patch
        from app.config import settings

        # 1. Explicit unauthorized header -> 401
        res_unauth = self.client.get("/api/v1/analytics/trends", headers={"X-Authorized": "false"})
        self.assertEqual(res_unauth.status_code, 401)

        # 2. When AUTH_ENFORCED is True, missing credentials -> 401
        with patch.object(settings, "AUTH_ENFORCED", True):
            res_enforced = self.client.get("/api/v1/analytics/dashboard")
            self.assertEqual(res_enforced.status_code, 401)

        # 3. Viewer role has 'read' permission -> 200
        headers = {"Authorization": f"Bearer {self.tokens['viewer']}"}
        res = self.client.get("/api/v1/analytics/dashboard", headers=headers)
        self.assertEqual(res.status_code, 200)

    def test_query_planner_and_search_integration(self):
        """Test that natural language queries map to trend and dashboard operations."""
        headers = {"Authorization": f"Bearer {self.tokens['admin']}"}

        # Trend Query
        res_trend = self.client.post(
            "/api/v1/query",
            headers=headers,
            json={"question": "Show attendance trend for Sukhliya"},
        )
        self.assertEqual(res_trend.status_code, 200)
        data_trend = res_trend.json()
        self.assertEqual(data_trend["interpreted_query"]["intent"], "trend")
        self.assertEqual(data_trend["calculation"]["operation"], "trend")
        self.assertGreater(len(data_trend["records"]), 0)

        # Dashboard Query
        res_dash = self.client.post(
            "/api/v1/query",
            headers=headers,
            json={"question": "Executive dashboard summary"},
        )
        self.assertEqual(res_dash.status_code, 200)
        data_dash = res_dash.json()
        self.assertEqual(data_dash["interpreted_query"]["intent"], "dashboard")
        self.assertEqual(data_dash["calculation"]["operation"], "dashboard")
        self.assertGreater(len(data_dash["records"]), 0)


if __name__ == "__main__":
    unittest.main()
