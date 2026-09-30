"""
Comprehensive test suite for Phase 2.4 — Optional AI Query Planner.

Verifies:
1. Local planner: Deterministic queries pass with expected intents and entities.
2. AI planner interface: Base QueryPlanner ABC compliance.
3. Valid AI QueryPlan: Mock AI provider returns valid schema, successfully validated.
4. Invalid AI QueryPlan: Malformed output / extra fields / SQL injection safely rejected & falls back.
5. AI disabled: AI_PLANNER_ENABLED=false uses LocalQueryPlanner directly.
6. Missing API key: External provider with no key falls back gracefully.
7. AI provider failure: Provider timeout/exception falls back silently to LocalQueryPlanner.
8. AI fallback: End-to-end SearchService returns correct DB results when AI fails.
9. Unsupported vocabulary: Hallucinated Satsang Ghar returns clarification, no guessing.
10. Ambiguous question: Ambiguous queries return clarification_required.
11. Numerical integrity: DB calculates final answer (e.g. 87.5 from 74, 83, 92, 101), NOT the AI.
12. Data safety: AI provider never receives DB rows, dumps, filesystem paths, or secrets.
"""

from datetime import date
from pathlib import Path
import unittest

from sqlalchemy import text

from app.config import Settings
from app.database import SessionLocal, engine
from app.schemas.search import (
    NumericOperation,
    QueryPlan,
    QueryPlanResult,
    RecordType,
    SearchIntent,
)
from app.services.excel_ingestion import ingest_excel_file
from app.services.query_planner import (
    AIQueryPlannerProvider,
    DeterministicQueryPlanner,
    ExternalAIQueryPlannerProvider,
    LocalQueryPlanner,
    MockAIQueryPlannerProvider,
    OptionalAIQueryPlanner,
    QueryPlanner,
    get_query_planner,
)
from app.services.search_service import SearchContext, SearchService

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SEARCH_FIXTURE = FIXTURES_DIR / "search_test_data.xlsx"


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


class TestAIQueryPlanner(unittest.TestCase):
    """Test suite covering Phase 2.4 Optional AI Query Planner architecture & constraints."""

    @classmethod
    def setUpClass(cls):
        _clean_tables()
        cls.db = SessionLocal()
        cls.excel_ingest = ingest_excel_file(
            cls.db,
            SEARCH_FIXTURE,
            original_filename="search_test_data.xlsx",
            auto_commit=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        _clean_tables()

    # -------------------------------------------------------------------------
    # 1. Local Planner
    # -------------------------------------------------------------------------
    def test_1_local_planner(self):
        """LocalQueryPlanner correctly parses deterministic queries."""
        planner = LocalQueryPlanner()
        self.assertIsInstance(planner, QueryPlanner)

        # Average attendance at Sukhliya in September
        res1 = planner.plan("average attendance at Sukhliya in September")
        self.assertFalse(res1.is_ambiguous)
        self.assertIsNotNone(res1.plan)
        self.assertEqual(res1.plan.intent, "average")
        self.assertEqual(res1.plan.record_type, "attendance")
        self.assertEqual(res1.plan.satsang_ghar, "Sukhliya")
        self.assertEqual(res1.plan.month, 9)

        # Show attendance for Sukhliya -> find intent
        res2 = planner.plan("show attendance for Sukhliya")
        self.assertFalse(res2.is_ambiguous)
        self.assertEqual(res2.plan.intent, "find")
        self.assertEqual(res2.plan.satsang_ghar, "Sukhliya")

        # List attendance for Sukhliya -> list intent
        res2_list = planner.plan("list attendance for Sukhliya")
        self.assertFalse(res2_list.is_ambiguous)
        self.assertEqual(res2_list.plan.intent, "list")
        self.assertEqual(res2_list.plan.satsang_ghar, "Sukhliya")

        # Count attendance records
        res3 = planner.plan("count attendance records")
        self.assertFalse(res3.is_ambiguous)
        self.assertEqual(res3.plan.intent, "count")

        # Find assignment for Sukhliya
        res4 = planner.plan("find assignment for Sukhliya")
        self.assertFalse(res4.is_ambiguous)
        self.assertEqual(res4.plan.intent, "find")
        self.assertEqual(res4.plan.record_type, "assignment")
        self.assertEqual(res4.plan.satsang_ghar, "Sukhliya")

        # Show SK assignments
        res5 = planner.plan("show SK assignments")
        self.assertFalse(res5.is_ambiguous)
        self.assertEqual(res5.plan.role, "SK")

    # -------------------------------------------------------------------------
    # 2. AI Planner Interface
    # -------------------------------------------------------------------------
    def test_2_ai_planner_interface(self):
        """QueryPlanner ABC is adhered to by both Local and Optional AI planners."""
        local = LocalQueryPlanner()
        ai = OptionalAIQueryPlanner(local_planner=local, enabled=False)

        self.assertTrue(issubclass(LocalQueryPlanner, QueryPlanner))
        self.assertTrue(issubclass(OptionalAIQueryPlanner, QueryPlanner))
        self.assertTrue(issubclass(DeterministicQueryPlanner, QueryPlanner))

        self.assertIsInstance(local, QueryPlanner)
        self.assertIsInstance(ai, QueryPlanner)

        # Base operation plan(question) -> QueryPlanResult
        r_local = local.plan("count attendance")
        r_ai = ai.plan("count attendance")
        self.assertIsInstance(r_local, QueryPlanResult)
        self.assertIsInstance(r_ai, QueryPlanResult)

    # -------------------------------------------------------------------------
    # 3. Valid AI QueryPlan
    # -------------------------------------------------------------------------
    def test_3_valid_ai_query_plan(self):
        """Valid structured output from AI provider passes Pydantic validation."""
        mock_provider = MockAIQueryPlannerProvider(
            canned_response={
                "raw_question": "average attendance at Sukhliya in September",
                "intent": "average",
                "record_type": "attendance",
                "numeric_operation": "average",
                "calculation": "average",
                "satsang_ghar": "Sukhliya",
                "month": 9,
                "source_required": True,
            }
        )
        ai_planner = OptionalAIQueryPlanner(
            provider=mock_provider,
            enabled=True,
        )

        res = ai_planner.plan("average attendance at Sukhliya in September")
        self.assertFalse(res.is_ambiguous)
        self.assertIsNotNone(res.plan)
        self.assertEqual(res.plan.intent, "average")
        self.assertEqual(res.plan.satsang_ghar, "Sukhliya")
        self.assertEqual(res.plan.month, 9)
        self.assertTrue(res.plan.source_required)
        self.assertEqual(len(res.warnings), 0)

    # -------------------------------------------------------------------------
    # 4. Invalid AI QueryPlan
    # -------------------------------------------------------------------------
    def test_4_invalid_ai_query_plan_triggers_fallback(self):
        """AI returning invalid schema, extra fields, or SQL keywords safely triggers fallback."""
        # Case A: Extra forbidden field (ConfigDict(extra='forbid'))
        bad_provider_extra_field = MockAIQueryPlannerProvider(
            canned_response={
                "intent": "average",
                "record_type": "attendance",
                "satsang_ghar": "Sukhliya",
                "arbitrary_code": "import os; os.system('echo hacked')",
            }
        )
        ai_planner_a = OptionalAIQueryPlanner(
            provider=bad_provider_extra_field,
            enabled=True,
        )
        res_a = ai_planner_a.plan("average attendance at Sukhliya in September")
        # Should gracefully fall back to local planner and not crash
        self.assertFalse(res_a.is_ambiguous)
        self.assertIsNotNone(res_a.plan)
        self.assertEqual(res_a.plan.satsang_ghar, "Sukhliya")
        self.assertTrue(any("AI planning bypassed" in w for w in res_a.warnings))

        # Case B: AI attempts SQL injection in satsang_ghar field
        bad_provider_sql = MockAIQueryPlannerProvider(
            canned_response={
                "intent": "find",
                "record_type": "attendance",
                "satsang_ghar": "Sukhliya'; DROP TABLE attendances; --",
            }
        )
        ai_planner_b = OptionalAIQueryPlanner(
            provider=bad_provider_sql,
            enabled=True,
        )
        res_b = ai_planner_b.plan("show attendance for Sukhliya")
        self.assertFalse(res_b.is_ambiguous)
        self.assertIsNotNone(res_b.plan)
        # Fallback to local planner extracts safe 'Sukhliya' without the injection
        self.assertEqual(res_b.plan.satsang_ghar, "Sukhliya")
        self.assertTrue(any("AI planning bypassed" in w for w in res_b.warnings))

    # -------------------------------------------------------------------------
    # 5. AI Disabled Mode
    # -------------------------------------------------------------------------
    def test_5_ai_disabled_mode(self):
        """AI_PLANNER_ENABLED=false does not invoke AI provider."""
        mock_provider = MockAIQueryPlannerProvider(should_fail=True)
        # Even if mock_provider is configured to fail, disabled mode never calls it
        ai_planner = OptionalAIQueryPlanner(
            provider=mock_provider,
            enabled=False,
        )

        res = ai_planner.plan("show attendance for Sukhliya")
        self.assertFalse(res.is_ambiguous)
        self.assertIsNotNone(res.plan)
        self.assertEqual(res.plan.satsang_ghar, "Sukhliya")
        # Provider was never touched
        self.assertIsNone(mock_provider.last_received_payload)

        # Factory test
        default_planner = get_query_planner(enabled=False)
        self.assertIsInstance(default_planner, LocalQueryPlanner)

    # -------------------------------------------------------------------------
    # 6. Missing API Key
    # -------------------------------------------------------------------------
    def test_6_missing_api_key_falls_back(self):
        """External provider without an API key safely falls back to local planner."""
        ext_provider = ExternalAIQueryPlannerProvider(api_key=None)
        ai_planner = OptionalAIQueryPlanner(
            provider=ext_provider,
            enabled=True,
            api_key=None,
        )

        res = ai_planner.plan("average attendance at Sukhliya in September")
        self.assertFalse(res.is_ambiguous)
        self.assertIsNotNone(res.plan)
        self.assertEqual(res.plan.satsang_ghar, "Sukhliya")
        self.assertEqual(res.plan.month, 9)

    # -------------------------------------------------------------------------
    # 7. AI Provider Failure
    # -------------------------------------------------------------------------
    def test_7_ai_provider_failure_falls_back(self):
        """Timeout or exception in AI provider gracefully falls back without user-visible error."""
        failing_provider = MockAIQueryPlannerProvider(
            should_fail=True,
            failure_exception=TimeoutError("Connection to AI service timed out after 5.0s"),
        )
        ai_planner = OptionalAIQueryPlanner(
            provider=failing_provider,
            enabled=True,
        )

        res = ai_planner.plan("count attendance records")
        self.assertFalse(res.is_ambiguous)
        self.assertIsNotNone(res.plan)
        self.assertEqual(res.plan.intent, "count")
        self.assertTrue(any("AI planning bypassed (TimeoutError)" in w for w in res.warnings))

    # -------------------------------------------------------------------------
    # 8. AI Fallback (End-to-End Search Service)
    # -------------------------------------------------------------------------
    def test_8_ai_fallback_in_search_service(self):
        """SearchService succeeds seamlessly even if AI provider throws an error."""
        failing_provider = MockAIQueryPlannerProvider(should_fail=True)
        failing_planner = OptionalAIQueryPlanner(provider=failing_provider, enabled=True)

        service = SearchService(self.db, planner=failing_planner)
        result = service.search("show attendance for Sukhliya")

        self.assertFalse(result.clarification_required)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.total_records, 4)
        self.assertIn("Sukhliya", result.answer)
        self.assertTrue(len(result.records) > 0)

    # -------------------------------------------------------------------------
    # 9. Unsupported Vocabulary
    # -------------------------------------------------------------------------
    def test_9_unsupported_vocabulary_not_executed(self):
        """AI returning an unverified Satsang Ghar does not guess; returns clarification."""
        hallucinated_provider = MockAIQueryPlannerProvider(
            canned_response={
                "intent": "find",
                "record_type": "attendance",
                "satsang_ghar": "Atlantis Main Hall",
            }
        )
        ai_planner = OptionalAIQueryPlanner(provider=hallucinated_provider, enabled=True)

        res = ai_planner.plan("show attendance for Atlantis Main Hall")
        self.assertTrue(res.is_ambiguous)
        self.assertIn("unrecognized Satsang Ghar", res.warnings[0])
        self.assertIn("Atlantis Main Hall", res.clarification_question)

    # -------------------------------------------------------------------------
    # 10. Ambiguous Question
    # -------------------------------------------------------------------------
    def test_10_ambiguous_question_returns_clarification(self):
        """Ambiguous query returns clarification_required without guessing."""
        planner = OptionalAIQueryPlanner(
            provider=MockAIQueryPlannerProvider(),
            enabled=True,
        )

        res = planner.plan("What was the highest attendance?")
        self.assertTrue(res.is_ambiguous)
        self.assertIsNotNone(res.clarification_question)
        self.assertIn("Which period do you mean?", res.clarification_question)

    # -------------------------------------------------------------------------
    # 11. Numerical Integrity (DB Calculates Final Answer)
    # -------------------------------------------------------------------------
    def test_11_numerical_answer_still_calculated_by_database(self):
        """
        Verifies that AI generates ONLY the structured QueryPlan.
        The final calculation (87.5 from records 74, 83, 92, 101) is strictly
        executed by the backend search calculation engine and PostgreSQL.
        """
        # AI returns structured intent and filters, but NO numerical answer
        ai_mock = MockAIQueryPlannerProvider(
            canned_response={
                "raw_question": "What was the average attendance at Sukhliya in September?",
                "intent": "average",
                "record_type": "attendance",
                "numeric_operation": "average",
                "calculation": "average",
                "satsang_ghar": "Sukhliya",
                "month": 9,
                "source_required": True,
            }
        )
        ai_planner = OptionalAIQueryPlanner(provider=ai_mock, enabled=True)

        # Execute search through SearchService
        service = SearchService(self.db, planner=ai_planner)
        result = service.search("What was the average attendance at Sukhliya in September?")

        # 1. Answer MUST be exact calculated average from DB
        self.assertEqual(result.status, "success")
        self.assertIn("87.5", result.answer)
        # 2. Supporting records count MUST be 4
        self.assertEqual(result.total_records, 4)
        # 3. Calculation object shows exact DB arithmetic: 87.5 from (74 + 83 + 92 + 101) / 4
        self.assertIsNotNone(result.calculation)
        self.assertEqual(result.calculation.operation, "average")
        self.assertEqual(result.calculation.value, 87.5)
        self.assertIn("74", result.calculation.breakdown)
        self.assertIn("83", result.calculation.breakdown)
        self.assertIn("92", result.calculation.breakdown)
        self.assertIn("101", result.calculation.breakdown)
        self.assertIn("87.5", result.calculation.breakdown)
        self.assertIn("Sum of 350", result.calculation.formula_description)
        # 4. Each record has source provenance
        for rec in result.records:
            self.assertIn("source_reference", rec)
            self.assertIn("attendance_count", rec)

    # -------------------------------------------------------------------------
    # 12. Data Safety (No Leakage to AI)
    # -------------------------------------------------------------------------
    def test_12_data_safety_no_leakage(self):
        """Verifies AI provider only receives query string and metadata schema, never DB rows."""
        spy_provider = MockAIQueryPlannerProvider()
        ai_planner = OptionalAIQueryPlanner(provider=spy_provider, enabled=True)

        ai_planner.plan("average attendance at Sukhliya in September")

        payload = spy_provider.last_received_payload
        self.assertIsNotNone(payload)
        self.assertIn("question", payload)
        self.assertIn("vocabulary_keys", payload)
        self.assertIn("allowed_intents", payload)

        # Ensure no database dumps, rows, or passwords exist in payload
        payload_str = str(payload).lower()
        self.assertNotIn("select ", payload_str)
        self.assertNotIn("password", payload_str)
        self.assertNotIn("secret", payload_str)
        self.assertNotIn("table attendances", payload_str)


if __name__ == "__main__":
    unittest.main()
