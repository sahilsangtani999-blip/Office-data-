"""
Comprehensive test suite for Phase 2.2 — Natural-Language Search Foundation.

Verifies:
1. Count attendance records.
2. List attendance for a Satsang Ghar.
3. Calculate average attendance (e.g., Sukhliya in September: 87.5 from 74, 83, 92, 101).
4. Calculate total attendance (sum).
5. Find an assignment for a date and Satsang Ghar.
6. Look up a VIDEO CD.
7. Find a person assignment.
8. Filter by role (SK / SR / VIDEO CD).
9. Return no results for non-existent entities or dates.
10. Request clarification for ambiguous questions (e.g., 'What was the highest attendance?').
11. Ambiguity handling for partial Satsang Ghar matches (e.g., Indore matching Indore East / West).
12. Ambiguity handling for partial Person matches (e.g., Ram matching Ram Kumar / Ram Singh).
13. Traceability to source provenance (document, version, sheet, row, cell).
14. Full API endpoint test (POST /api/v1/query) via FastAPI TestClient.
15. Authorization and permission checks on the search service boundary.
16. Comparative queries (Compare attendance between Sukhliya and Bicholi).
"""

from datetime import date
import json
from pathlib import Path
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.database import SessionLocal, engine
from app.main import app
from app.models import (
    Assignment,
    Attendance,
    Document,
    DocumentVersion,
    Person,
    Report,
    Role,
    SatsangGhar,
    SourceReference,
    VehicleWheelData,
)
from app.schemas.search import QueryPlan, QueryPlanResult, SearchResult
from app.services.excel_ingestion import ingest_excel_file
from app.services.pdf_ingestion import ingest_pdf_file
from app.services.query_planner import DeterministicQueryPlanner
from app.services.search_service import SearchContext, SearchService

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SEARCH_FIXTURE = FIXTURES_DIR / "search_test_data.xlsx"
PDF_FIXTURE = FIXTURES_DIR / "table_attendance.pdf"


def _clean_tables():
    """Wipes test data to ensure isolation."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE assignments, attendances, vehicle_wheel_data, "
                "source_references, document_versions, documents, data_sources, "
                "satsang_ghars, persons, roles, reports, major_centers CASCADE;"
            )
        )


class TestSearchFoundation(unittest.TestCase):
    """Integration test suite for Search Foundation with isolated PostgreSQL transactions."""

    @classmethod
    def setUpClass(cls):
        """Ensure search fixture is ingested once for integration tests."""
        _clean_tables()
        cls.db = SessionLocal()
        cls.client = TestClient(app)

        # Ingest the search fixture workbook (Excel)
        cls.excel_ingest = ingest_excel_file(
            cls.db,
            SEARCH_FIXTURE,
            original_filename="search_test_data.xlsx",
            auto_commit=True,
        )

        # Ingest the table attendance PDF fixture
        if PDF_FIXTURE.is_file():
            cls.pdf_ingest = ingest_pdf_file(
                cls.db,
                PDF_FIXTURE,
                original_filename="table_attendance.pdf",
                data_source_name="PDF Attendance Source",
                auto_commit=True,
            )

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        _clean_tables()

    def setUp(self):
        self.planner = DeterministicQueryPlanner()
        self.search_service = SearchService(self.db)

    # -------------------------------------------------------------------------
    # 1. Deterministic Query Parser Tests
    # -------------------------------------------------------------------------

    def test_parser_sukhliya_attendance_plan(self):
        """Test: 'Show attendance for Sukhliya in September' produces expected structured plan."""
        q = "Show attendance for Sukhliya in September"
        result = self.planner.plan(q)

        self.assertFalse(result.is_ambiguous)
        self.assertIsNotNone(result.plan)
        plan = result.plan
        self.assertEqual(plan.record_type, "attendance")
        self.assertEqual(plan.satsang_ghar, "Sukhliya")
        self.assertEqual(plan.month, 9)
        self.assertIn(plan.intent, ["list", "find"])

    def test_parser_average_attendance_plan(self):
        """Test: 'What was the average attendance at Sukhliya in September?' plan."""
        q = "What was the average attendance at Sukhliya in September?"
        result = self.planner.plan(q)

        self.assertFalse(result.is_ambiguous)
        plan = result.plan
        self.assertEqual(plan.intent, "average")
        self.assertEqual(plan.numeric_operation, "average")
        self.assertEqual(plan.record_type, "attendance")
        self.assertEqual(plan.satsang_ghar, "Sukhliya")
        self.assertEqual(plan.month, 9)

    def test_parser_controlled_vocabulary_aliases(self):
        """Test: Controlled vocabulary aliases map correctly (SK -> SK, SR -> SR, VIDEO CD -> VIDEO CD)."""
        res_sk = self.planner.plan("Show assignments for Satsang Karta at Sukhliya")
        self.assertEqual(res_sk.plan.role, "SK")

        res_sr = self.planner.plan("Show assignments for Satsang Reader at Sukhliya")
        self.assertEqual(res_sr.plan.role, "SR")

        res_vcd = self.planner.plan("Lookup VIDEO CD duty schedule")
        self.assertEqual(res_vcd.plan.role, "VIDEO CD")
        self.assertEqual(res_vcd.plan.record_type, "assignment")

    # -------------------------------------------------------------------------
    # 2. Ambiguity Handling Tests
    # -------------------------------------------------------------------------

    def test_ambiguity_highest_attendance_without_period(self):
        """Test Requirement 4: 'What was the highest attendance?' returns clarification request."""
        q = "What was the highest attendance?"
        result = self.planner.plan(q)

        self.assertTrue(result.is_ambiguous)
        self.assertIsNone(result.plan)
        self.assertIn("Which period do you mean?", result.clarification_question)

        # Also test via search service
        search_res = self.search_service.execute_search(result, q)
        self.assertTrue(search_res.clarification_required)
        self.assertEqual(search_res.status, "clarification_required")
        self.assertIn("Which period do you mean?", search_res.clarification_question)

    def test_ambiguity_multiple_satsang_ghars(self):
        """Test Requirement 4: When a name matches multiple entities, ask for clarification."""
        # Insert two ghars: 'Indore East' and 'Indore West'
        ghar1 = SatsangGhar(name="Indore East")
        ghar2 = SatsangGhar(name="Indore West")
        self.db.add_all([ghar1, ghar2])
        self.db.commit()

        q = "Show attendance for Indore in September"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertTrue(res.clarification_required)
        self.assertEqual(res.status, "clarification_required")
        self.assertIn("multiple Satsang Ghars", res.clarification_question)
        self.assertIn("Indore East", res.clarification_question)
        self.assertIn("Indore West", res.clarification_question)

    def test_ambiguity_multiple_persons(self):
        """Test Requirement 4: When person name matches multiple people, ask for clarification."""
        p1 = Person(name="Ram Kumar Verma")
        p2 = Person(name="Ram Kumar Sharma")
        self.db.add_all([p1, p2])
        self.db.commit()

        plan = QueryPlan(
            raw_question="Find assignments for person Ram",
            intent="find",
            record_type="assignment",
            person="Ram",
        )
        plan_res = QueryPlanResult(plan=plan)
        res = self.search_service.execute_search(plan_res, plan.raw_question)

        self.assertTrue(res.clarification_required)
        self.assertIn("multiple people", res.clarification_question)

    # -------------------------------------------------------------------------
    # 3. Numerical Calculations & Ingested Data Verification
    # -------------------------------------------------------------------------

    def test_1_count_attendance_records(self):
        """Requirement 11.1: Count attendance records."""
        q = "Count attendance records for Sukhliya"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertEqual(res.total_records, 4)
        self.assertIsNotNone(res.calculation)
        self.assertEqual(res.calculation.operation, "count")
        self.assertEqual(res.calculation.value, 4)

    def test_2_list_attendance_for_satsang_ghar(self):
        """Requirement 11.2: List attendance for a Satsang Ghar."""
        q = "Show attendance for Sukhliya in September"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertEqual(len(res.records), 4)
        counts = [r["attendance_count"] for r in res.records]
        self.assertEqual(counts, [74, 83, 92, 101])

    def test_3_calculate_average_attendance(self):
        """
        Requirement 11.3 & Section 6: Calculate average attendance.
        If attendance records are 74, 83, 92, 101, average must be 87.5 calculated from records.
        """
        q = "What was the average attendance at Sukhliya in September?"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertEqual(res.total_records, 4)
        self.assertIsNotNone(res.calculation)
        self.assertEqual(res.calculation.operation, "average")
        self.assertEqual(res.calculation.value, 87.5)
        self.assertIn("87.5", res.answer)

    def test_4_calculate_total_attendance(self):
        """Requirement 11.4: Calculate total attendance (sum)."""
        q = "What was the total attendance for Sukhliya in September?"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertEqual(res.total_records, 4)
        self.assertIsNotNone(res.calculation)
        self.assertEqual(res.calculation.operation, "sum")
        # 74 + 83 + 92 + 101 = 350
        self.assertEqual(res.calculation.value, 350)
        self.assertIn("350", res.answer)

    def test_5_find_assignment_for_date_and_ghar(self):
        """Requirement 11.5: Find an assignment for a date and Satsang Ghar."""
        q = "Find assignment at Sukhliya on 2026-09-06"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertGreaterEqual(res.total_records, 1)
        # Check that both Ram Kumar (SK) and Sham Lal (SR) are returned
        roles = [r["role_code"] for r in res.records]
        self.assertIn("SK", roles)
        self.assertIn("SR", roles)

    def test_6_lookup_video_cd(self):
        """Requirement 11.6: Look up a VIDEO CD."""
        q = "Lookup VIDEO CD"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertGreaterEqual(res.total_records, 1)
        found = any("VIDEO CD" in (r.get("role_code") or r.get("description") or "") for r in res.records)
        self.assertTrue(found)
        self.assertTrue(any(r.get("person") == "Mohan Das" for r in res.records))

    def test_7_find_person_assignment(self):
        """Requirement 11.7: Find a person assignment."""
        q = "Find assignments for person Ram Kumar"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertGreaterEqual(res.total_records, 1)
        for rec in res.records:
            self.assertEqual(rec["person"], "Ram Kumar")

    def test_8_filter_by_role(self):
        """Requirement 11.8: Filter by role."""
        q = "Filter assignments where role is SR"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertGreaterEqual(res.total_records, 1)
        for rec in res.records:
            self.assertEqual(rec["role_code"], "SR")

    def test_9_return_no_results(self):
        """Requirement 11.9: Return no results cleanly."""
        q = "Show attendance for Sukhliya in January"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "no_results")
        self.assertEqual(res.total_records, 0)
        self.assertEqual(len(res.records), 0)
        self.assertIn("No attendance records found", res.answer)

    def test_10_request_clarification_for_ambiguous_question(self):
        """Requirement 11.10: Request clarification for an ambiguous question."""
        q = "attendance"
        plan_res = self.planner.plan(q)
        self.assertTrue(plan_res.is_ambiguous)

        res = self.search_service.execute_search(plan_res, q)
        self.assertTrue(res.clarification_required)
        self.assertIsNotNone(res.clarification_question)

    # -------------------------------------------------------------------------
    # 4. Source Provenance Verification
    # -------------------------------------------------------------------------

    def test_source_provenance_retention(self):
        """Requirement 8: Every imported result retains document, version, sheet, row, cell."""
        q = "What was the average attendance at Sukhliya in September?"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertGreater(len(res.source_references), 0)
        sr = res.source_references[0]

        # Verify provenance fields
        self.assertEqual(sr.document_name, "search_test_data.xlsx")
        self.assertEqual(sr.document_version, 1)
        self.assertEqual(sr.sheet_name, "Sukhliya Attendance")
        self.assertIsNotNone(sr.row_number)

        # Verify each individual record has attached provenance
        for rec in res.records:
            self.assertIn("source_reference", rec)
            self.assertIsNotNone(rec["source_reference"])
            self.assertEqual(rec["source_reference"]["sheet_name"], "Sukhliya Attendance")
            self.assertIsNotNone(rec["source_reference"]["row_number"])

    # -------------------------------------------------------------------------
    # 5. Comparative Query Test
    # -------------------------------------------------------------------------

    def test_compare_attendance_between_two_ghars(self):
        """Test Requirement 1: Compare intent between Sukhliya and Bicholi."""
        q = "Compare attendance between Sukhliya and Bicholi"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertIn("Comparison of Average Attendance", res.answer)
        self.assertIn("Sukhliya", res.answer)
        self.assertIn("Bicholi", res.answer)
        self.assertIsNotNone(res.calculation)
        self.assertEqual(res.calculation.operation, "compare")

    # -------------------------------------------------------------------------
    # 6. Full API Endpoint Tests (POST /api/v1/query)
    # -------------------------------------------------------------------------

    def test_api_query_average_attendance(self):
        """Requirement 9: POST /api/v1/query endpoint returns structured SearchResult."""
        payload = {"question": "What was the average attendance at Sukhliya in September?"}
        response = self.client.post("/api/v1/query", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["original_question"], payload["question"])
        self.assertEqual(data["status"], "success")
        self.assertFalse(data["clarification_required"])
        self.assertEqual(data["total_records"], 4)
        self.assertEqual(data["calculation"]["value"], 87.5)
        self.assertIn("87.5", data["answer"])
        self.assertGreaterEqual(len(data["source_references"]), 1)
        self.assertEqual(data["source_references"][0]["document_name"], "search_test_data.xlsx")

    def test_api_query_ambiguous_question(self):
        """Test API returns clarification_required for ambiguous question."""
        payload = {"question": "What was the highest attendance?"}
        response = self.client.post("/api/v1/query", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "clarification_required")
        self.assertTrue(data["clarification_required"])
        self.assertIsNotNone(data["clarification_question"])

    def test_api_empty_question_rejected(self):
        """Test API rejects empty questions with 400 or 422."""
        response = self.client.post("/api/v1/query", json={"question": "   "})
        self.assertIn(response.status_code, [400, 422])

    def test_api_preserves_document_upload(self):
        """Requirement 9: Ensure POST /api/v1/documents/upload is preserved and functional."""
        txt_file = FIXTURES_DIR / "unsupported_sample.txt"
        with open(txt_file, "rb") as f:
            response = self.client.post(
                "/api/v1/documents/upload",
                files={"file": ("unsupported_sample.txt", f, "text/plain")},
            )
        # Should return 400 for unsupported format as tested in Phase 1.2
        self.assertEqual(response.status_code, 400)

    # -------------------------------------------------------------------------
    # 7. Security & Permission Boundary Tests
    # -------------------------------------------------------------------------

    def test_unauthorized_search_context_blocked(self):
        """Requirement 13: Service boundary blocks unauthorized search context."""
        unauth_context = SearchContext(user_id="unauth_user", is_authorized=False)
        unauth_service = SearchService(self.db, context=unauth_context)

        plan = QueryPlan(raw_question="test", intent="list")
        with self.assertRaises(PermissionError):
            unauth_service.execute_search(QueryPlanResult(plan=plan), "test")

    def test_api_unauthorized_header_blocked(self):
        """Requirement 13: API with x-authorized: false returns 403."""
        response = self.client.post(
            "/api/v1/query",
            json={"question": "Show attendance for Sukhliya"},
            headers={"x-authorized": "false"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("not authorized", response.json()["detail"])

    # -------------------------------------------------------------------------
    # 8. Phase 2.3 — Search Results & Source Verification Tests
    # -------------------------------------------------------------------------

    def test_phase23_1_successful_numeric_answer_and_breakdown(self):
        """Phase 2.3 Requirement 1: Successful numeric query returns breakdown formula."""
        q = "What was the average attendance at Sukhliya in September?"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertEqual(res.total_records, 4)
        self.assertIsNotNone(res.calculation)
        self.assertEqual(res.calculation.operation, "average")
        self.assertEqual(res.calculation.value, 87.5)
        # Verify calculation breakdown format (74 + 83 + 92 + 101) / 4 = 87.5
        self.assertEqual(res.calculation.breakdown, "(74 + 83 + 92 + 101) / 4 = 87.5")
        self.assertIn("87.5", res.answer)

    def test_phase23_2_supporting_records_fields(self):
        """Phase 2.3 Requirement 3: Supporting records display only relevant human-readable fields."""
        q = "Show attendance for Sukhliya in September"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertEqual(len(res.records), 4)

        for rec in res.records:
            # Check fields exist and no raw SQLAlchemy model objects are leaked
            self.assertIn("id", rec)
            self.assertIn("date", rec)
            self.assertIn("satsang_ghar", rec)
            self.assertIn("attendance_count", rec)
            self.assertIn("status", rec)
            self.assertIn("source_reference_id", rec)
            self.assertIsNotNone(rec["source_reference_id"])
            self.assertIsInstance(rec["source_reference_id"], str)
            # Ensure it's a valid serialized dict, not a DB object
            self.assertIsInstance(rec, dict)

    def test_phase23_3_excel_source_reference(self):
        """Phase 2.3 Requirement 4: Excel source reference includes sheet, row, and cell/range."""
        q = "Show attendance for Sukhliya in September"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertGreaterEqual(len(res.source_references), 1)
        ref = res.source_references[0]
        self.assertEqual(ref.document_name, "search_test_data.xlsx")
        self.assertEqual(ref.document_type, "excel")
        self.assertEqual(ref.sheet_name, "Sukhliya Attendance")
        self.assertIsNotNone(ref.row_number)
        self.assertGreaterEqual(ref.row_number, 2)

    def test_phase23_4_pdf_source_reference_and_bbox(self):
        """Phase 2.3 Requirement 4 & 5: PDF source reference includes page and bounding box."""
        q = "Show attendance for Model Town"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "success")
        self.assertEqual(len(res.records), 1)
        rec = res.records[0]
        self.assertEqual(rec["attendance_count"], 520)

        self.assertIsNotNone(rec["source_reference"])
        pdf_ref = rec["source_reference"]
        self.assertEqual(pdf_ref["document_name"], "table_attendance.pdf")
        self.assertEqual(pdf_ref["document_type"], "pdf")
        self.assertEqual(pdf_ref["page_number"], 1)
        self.assertIsNotNone(pdf_ref["bbox"])
        self.assertEqual(len(pdf_ref["bbox"]), 4)
        self.assertEqual(pdf_ref["bbox"], [50.0, 80.0, 550.0, 180.0])

    def test_phase23_5_no_results_state(self):
        """Phase 2.3 Requirement 2: No results state has clear, nontechnical message."""
        q = "Show attendance for London in 2020"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "no_results")
        self.assertEqual(len(res.records), 0)
        self.assertIn("No Satsang Ghar named", res.answer)

    def test_phase23_6_clarification_state(self):
        """Phase 2.3 Requirement 2: Ambiguous question returns clarification state with friendly question."""
        q = "What was the highest attendance?"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)

        self.assertEqual(res.status, "clarification_required")
        self.assertTrue(res.clarification_required)
        self.assertIsNotNone(res.clarification_question)
        self.assertIn("Which period do you mean?", res.clarification_question)

    def test_phase23_7_needs_review_state(self):
        """Phase 2.3 Requirement 2: Query matching unverified records transitions to needs_review status."""
        # Find one attendance record for Karol Bagh and update status to needs_review
        att = self.db.scalars(
            select(Attendance).join(SatsangGhar).where(SatsangGhar.name == "Karol Bagh")
        ).first()
        self.assertIsNotNone(att)
        original_status = att.status
        att.status = "needs_review"
        self.db.commit()

        try:
            q = "Show attendance for Karol Bagh"
            plan_res = self.planner.plan(q)
            res = self.search_service.execute_search(plan_res, q)

            self.assertEqual(res.status, "needs_review")
            self.assertGreaterEqual(len(res.warnings), 1)
            self.assertIn("flagged as Needs Review", res.warnings[0])
            self.assertEqual(res.records[0]["status"], "needs_review")
        finally:
            # Revert to avoid affecting any subsequent tests
            att.status = original_status
            self.db.commit()

    def test_phase23_8_source_detail_api(self):
        """Phase 2.3 Requirement 6: GET /api/v1/sources/{source_id} returns accurate metadata."""
        # Query attendance to obtain a valid source_reference_id
        q = "Show attendance for Sukhliya in September"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)
        source_id = res.records[0]["source_reference_id"]

        response = self.client.get(f"/api/v1/sources/{source_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["id"], source_id)
        self.assertEqual(data["document_name"], "search_test_data.xlsx")
        self.assertEqual(data["document_type"], "excel")
        self.assertEqual(data["sheet_name"], "Sukhliya Attendance")
        self.assertIsNotNone(data["row_number"])

    def test_phase23_9_source_preview_api_excel(self):
        """Phase 2.3 Requirement 6 & 8: GET /api/v1/sources/{source_id}/preview for Excel."""
        q = "Show attendance for Sukhliya in September"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)
        source_id = res.records[0]["source_reference_id"]

        response = self.client.get(f"/api/v1/sources/{source_id}/preview")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["id"], source_id)
        self.assertEqual(data["document_name"], "search_test_data.xlsx")
        self.assertEqual(data["document_type"], "excel")
        self.assertEqual(data["sheet_name"], "Sukhliya Attendance")
        self.assertIsNotNone(data["row_number"])
        self.assertIsNotNone(data["parsed_content"])
        self.assertIsNotNone(data["surrounding_rows"])
        self.assertIn("Sukhliya", data["relevance_explanation"])

    def test_phase23_10_source_preview_api_pdf(self):
        """Phase 2.3 Requirement 6 & 8: GET /api/v1/sources/{source_id}/preview for PDF."""
        q = "Show attendance for Model Town"
        plan_res = self.planner.plan(q)
        res = self.search_service.execute_search(plan_res, q)
        source_id = res.records[0]["source_reference_id"]

        response = self.client.get(f"/api/v1/sources/{source_id}/preview")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["id"], source_id)
        self.assertEqual(data["document_name"], "table_attendance.pdf")
        self.assertEqual(data["document_type"], "pdf")
        self.assertEqual(data["page_number"], 1)
        self.assertIsNotNone(data["bbox"])
        self.assertEqual(data["bbox"], [50.0, 80.0, 550.0, 180.0])
        self.assertIn("Model Town", data["relevance_explanation"])

    def test_phase23_11_invalid_source_id_handling(self):
        """Phase 2.3 Requirement 7: Source security rejects invalid or non-existent IDs."""
        # Non-existent UUID
        response = self.client.get("/api/v1/sources/00000000-0000-0000-0000-000000000000")
        self.assertEqual(response.status_code, 404)

        response_prev = self.client.get("/api/v1/sources/00000000-0000-0000-0000-000000000000/preview")
        self.assertEqual(response_prev.status_code, 404)

        # Malformed ID / path traversal attempt
        response_malformed = self.client.get("/api/v1/sources/invalid-uuid-format")
        self.assertEqual(response_malformed.status_code, 404)
        self.assertIn("Must be a valid UUID", response_malformed.json()["detail"])

