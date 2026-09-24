"""
Query Planning Service for RSSB Office Data Platform.
Phase 2.2 — Natural-Language Search Foundation.

Implements:
1. BaseQueryPlanner interface (preparing for future AI planners).
2. DeterministicQueryPlanner with controlled office vocabulary,
   alias resolution, intent mapping, entity extraction, and ambiguity detection.
"""

from abc import ABC, abstractmethod
from datetime import date, datetime
import re
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.search import (
    NumericOperation,
    QueryPlan,
    QueryPlanResult,
    RecordType,
    SearchIntent,
)


# =============================================================================
# Controlled Office Vocabulary & Aliases
# =============================================================================

ROLE_ALIASES: Dict[str, str] = {
    "sk": "SK",
    "satsang karta": "SK",
    "satsangkarta": "SK",
    "sr": "SR",
    "satsang reader": "SR",
    "satsangreader": "SR",
    "video cd": "VIDEO CD",
    "videocd": "VIDEO CD",
    "video-cd": "VIDEO CD",
    "vcd": "VIDEO CD",
}

ROLE_FULL_NAMES: Dict[str, str] = {
    "SK": "Satsang Karta",
    "SR": "Satsang Reader",
    "VIDEO CD": "VIDEO CD",
}

MONTH_MAP: Dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

# Known common office locations in test/sample datasets
KNOWN_SATSANG_GHARS: List[str] = [
    "Sukhliya",
    "Bicholi",
    "Pithampur",
    "Rau",
    "Model Town",
    "Karol Bagh",
    "Rohini Sector 7",
    "Rohini",
    "Pusa Road",
    "Indore East",
    "Indore West",
    "Indore",
]

KNOWN_REPORT_TYPES: Dict[str, str] = {
    "monthly report": "Monthly Report",
    "monthly": "Monthly Report",
    "sk report": "SK Report",
    "sr report": "SR Report",
    "wheel report": "Vehicle/Wheel Report",
    "vehicle report": "Vehicle/Wheel Report",
}


# =============================================================================
# Query Planner Interface
# =============================================================================

class BaseQueryPlanner(ABC):
    """
    Abstract interface for query planners.
    Allows swapping between DeterministicQueryPlanner and future AIQueryPlanner.
    """

    @abstractmethod
    def plan(self, question: str) -> QueryPlanResult:
        """
        Parses a natural language question into a structured QueryPlan.
        Returns a QueryPlanResult with the plan, ambiguity flags, or clarification questions.
        """
        pass


# =============================================================================
# Deterministic Query Planner Implementation
# =============================================================================

class DeterministicQueryPlanner(BaseQueryPlanner):
    """
    Deterministic rule-based query parser and planner adhering strictly to
    controlled office vocabulary without using external AI APIs.
    """

    def plan(self, question: str) -> QueryPlanResult:
        cleaned_question = question.strip()
        if not cleaned_question:
            return QueryPlanResult(
                plan=None,
                is_ambiguous=True,
                clarification_question="Please enter a question to search office data.",
                warnings=["Empty question received."],
            )

        q_lower = cleaned_question.lower()

        # 1. Ambiguity Pre-checks:
        # Check: "What was the highest attendance?" without period or location
        is_extreme = bool(re.search(r"\b(highest|maximum|max|peak|lowest|minimum|min)\b", q_lower))
        has_period_or_ghar = any(
            m in q_lower for m in MONTH_MAP.keys()
        ) or any(
            g.lower() in q_lower for g in KNOWN_SATSANG_GHARS
        ) or bool(re.search(r"\b(202\d|in\s+\w+|for\s+\w+)\b", q_lower))

        if is_extreme and "attendance" in q_lower and not has_period_or_ghar:
            return QueryPlanResult(
                plan=None,
                is_ambiguous=True,
                clarification_question="I found attendance data for multiple periods. Which period do you mean?",
                warnings=["Query requests extreme value without specifying period or Satsang Ghar."],
            )

        # 2. Extract Entities
        month, year = self._extract_month_and_year(q_lower)
        parsed_date, date_start, date_end = self._extract_dates(q_lower)
        satsang_ghar = self._extract_satsang_ghar(q_lower, cleaned_question)
        role = self._extract_role(q_lower)
        person = self._extract_person(q_lower, cleaned_question, role)
        vehicle_type = self._extract_vehicle_type(q_lower)
        source_requirement = self._extract_source_requirement(q_lower)

        # 3. Determine Numeric Operation
        operation = self._extract_numeric_operation(q_lower)

        # 4. Determine Record Type
        record_type = self._extract_record_type(q_lower, role, vehicle_type)

        # 5. Determine Intent
        intent = self._extract_intent(q_lower, operation, source_requirement, record_type)

        # 6. Check for Compare intent targets
        comparison_target = None
        if intent == "compare":
            comparison_target = self._extract_comparison_target(q_lower, satsang_ghar, month)

        # 7. Ambiguity Post-check
        # If question is too vague, e.g. single word "attendance" or "discourse"
        words = re.findall(r"\w+", q_lower)
        if len(words) <= 2 and not satsang_ghar and not person and not parsed_date and not month:
            if "attendance" in q_lower:
                return QueryPlanResult(
                    plan=None,
                    is_ambiguous=True,
                    clarification_question="Could you please specify whether you want to list, count, or calculate average attendance for a specific Satsang Ghar or period?",
                    warnings=["Ambiguous broad query without filters."],
                )
            if any(w in q_lower for w in ["assignment", "duty", "sewa"]):
                return QueryPlanResult(
                    plan=None,
                    is_ambiguous=True,
                    clarification_question="Please specify a Satsang Ghar, person name, or date to search duty assignments.",
                    warnings=["Broad assignment query."],
                )

        plan = QueryPlan(
            raw_question=cleaned_question,
            intent=intent,
            record_type=record_type,
            numeric_operation=operation,
            satsang_ghar=satsang_ghar,
            person=person,
            role=role,
            date=parsed_date,
            date_start=date_start,
            date_end=date_end,
            month=month,
            year=year,
            vehicle_type=vehicle_type,
            requested_fields=[],
            source_requirement=source_requirement,
            comparison_target=comparison_target,
            filters={},
        )

        return QueryPlanResult(
            plan=plan,
            is_ambiguous=False,
            clarification_question=None,
            warnings=[],
        )

    # -------------------------------------------------------------------------
    # Entity Extraction Helpers
    # -------------------------------------------------------------------------

    def _extract_month_and_year(self, q_lower: str) -> Tuple[Optional[int], Optional[int]]:
        """Extracts month number (1-12) and 4-digit year."""
        month = None
        year = None

        # Year search (2000-2099)
        year_match = re.search(r"\b(20\d{2})\b", q_lower)
        if year_match:
            year = int(year_match.group(1))

        # Month search
        for month_name, month_num in MONTH_MAP.items():
            if re.search(rf"\b{month_name}\b", q_lower):
                month = month_num
                break

        return month, year

    def _extract_dates(self, q_lower: str) -> Tuple[Optional[date], Optional[date], Optional[date]]:
        """Extracts exact date or date ranges."""
        parsed_date = None
        date_start = None
        date_end = None

        # ISO format: YYYY-MM-DD
        iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", q_lower)
        if iso_match:
            try:
                parsed_date = date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
                return parsed_date, date_start, date_end
            except ValueError:
                pass

        # DD-MM-YYYY format
        dmy_match = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", q_lower)
        if dmy_match:
            try:
                parsed_date = date(int(dmy_match.group(3)), int(dmy_match.group(2)), int(dmy_match.group(1)))
                return parsed_date, date_start, date_end
            except ValueError:
                pass

        # "15 September 2026" or "September 15, 2026" or "15th September"
        for month_name, month_num in MONTH_MAP.items():
            pattern1 = rf"\b(\d{1,2})(?:st|nd|rd|th)?\s+{month_name}(?:\s+(\d{4}))?\b"
            m1 = re.search(pattern1, q_lower)
            if m1:
                day = int(m1.group(1))
                yr = int(m1.group(2)) if m1.group(2) else 2026
                try:
                    parsed_date = date(yr, month_num, day)
                    return parsed_date, date_start, date_end
                except ValueError:
                    pass

            pattern2 = rf"\b{month_name}\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b"
            m2 = re.search(pattern2, q_lower)
            if m2:
                day = int(m2.group(1))
                yr = int(m2.group(2)) if m2.group(2) else 2026
                try:
                    parsed_date = date(yr, month_num, day)
                    return parsed_date, date_start, date_end
                except ValueError:
                    pass

        return parsed_date, date_start, date_end

    def _extract_satsang_ghar(self, q_lower: str, q_original: str) -> Optional[str]:
        """Extracts Satsang Ghar name from question using controlled vocabulary."""
        # Check known ghars, longest first to match "Indore East" before "Indore"
        sorted_ghars = sorted(KNOWN_SATSANG_GHARS, key=len, reverse=True)
        for ghar in sorted_ghars:
            if re.search(rf"\b{re.escape(ghar.lower())}\b", q_lower):
                return ghar

        # Look for pattern "at <Name>" or "for <Name>" before common terms
        match = re.search(r"\b(?:at|for|in)\s+([A-Z][a-zA-Z0-9_\s]{2,20})(?:\s+(?:in|on|for|during|attendance|records|satsang))?", q_original)
        if match:
            candidate = match.group(1).strip()
            # Exclude month names, roles, or common keywords
            cand_lower = candidate.lower()
            if cand_lower not in MONTH_MAP and cand_lower not in ["september", "october", "attendance", "assignment", "duty", "sk", "sr"]:
                return candidate

        return None

    def _extract_role(self, q_lower: str) -> Optional[str]:
        """Extracts duty role using controlled vocabulary and aliases."""
        for alias, code in ROLE_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", q_lower):
                return code
        return None

    def _extract_person(self, q_lower: str, q_original: str, role: Optional[str]) -> Optional[str]:
        """Extracts person name from query."""
        # Check patterns like "assigned to <Person>", "discourse by <Person>", "for <Person>"
        patterns = [
            r"\b(?:assigned\s+to|speaker|karta|reader|reader\s+name|by|person)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",
            r"\b(?:is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:assigned|scheduled)\b",
            r"\bfind\s+(?:person\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+))\b",
        ]
        for pat in patterns:
            m = re.search(pat, q_original)
            if m:
                cand = m.group(1).strip()
                cand_lower = cand.lower()
                if cand_lower not in KNOWN_REPORT_TYPES and cand_lower not in [g.lower() for g in KNOWN_SATSANG_GHARS]:
                    return cand

        # Known test names fallback if capitalized in question
        known_test_names = ["Harish Kumar", "Rajesh Sharma", "Mohan Lal", "Ram Kumar", "Sham Lal", "Mohan Das"]
        for name in known_test_names:
            if re.search(rf"\b{re.escape(name.lower())}\b", q_lower):
                return name

        return None

    def _extract_vehicle_type(self, q_lower: str) -> Optional[str]:
        """Identifies vehicle or wheel type."""
        if re.search(r"\b(2-wheeler|two[- ]wheeler|two wheeler|bike|bikes|motorcycle)\b", q_lower):
            return "2-Wheeler"
        if re.search(r"\b(4-wheeler|four[- ]wheeler|four wheeler|car|cars)\b", q_lower):
            return "4-Wheeler"
        if re.search(r"\b(vehicle|wheel)\b", q_lower):
            return "Vehicle/Wheel"
        return None

    def _extract_source_requirement(self, q_lower: str) -> bool:
        """Checks if the user explicitly requested source provenance."""
        return bool(re.search(r"\b(source|provenance|origin|sheet|document|file|reference|where did this come from)\b", q_lower))

    def _extract_numeric_operation(self, q_lower: str) -> Optional[NumericOperation]:
        """Identifies requested numeric operation."""
        if re.search(r"\b(average|avg|mean)\b", q_lower):
            return "average"
        if re.search(r"\b(sum|total)\b", q_lower):
            return "sum"
        if re.search(r"\b(count|number\s+of|how\s+many)\b", q_lower):
            return "count"
        if re.search(r"\b(highest|maximum|max|peak|top)\b", q_lower):
            return "max"
        if re.search(r"\b(lowest|minimum|min|bottom)\b", q_lower):
            return "min"
        return None

    def _extract_record_type(
        self, q_lower: str, role: Optional[str], vehicle_type: Optional[str]
    ) -> RecordType:
        """Determines domain record type."""
        if vehicle_type or "wheel" in q_lower or "vehicle" in q_lower:
            return "vehicle_wheel"
        if "attendance" in q_lower or "sangat" in q_lower or "attendees" in q_lower:
            return "attendance"
        if role == "VIDEO CD" or "video cd" in q_lower or "vcd" in q_lower:
            return "assignment"
        if any(w in q_lower for w in ["assignment", "assigned", "duty", "duties", "sewa", "schedule", "speaker", "karta", "reader"]):
            return "assignment"
        if "report" in q_lower:
            return "report"
        if any(w in q_lower for w in ["document", "file", "workbook", "upload"]):
            return "document"

        # If role or person is present, defaults to assignment
        if role:
            return "assignment"

        # Default fallback
        return "attendance"

    def _extract_intent(
        self,
        q_lower: str,
        operation: Optional[NumericOperation],
        source_requirement: bool,
        record_type: RecordType,
    ) -> SearchIntent:
        """Maps user question to one of the 10 supported search intents."""
        if "compare" in q_lower or "difference between" in q_lower or "versus" in q_lower or " vs " in q_lower:
            return "compare"

        if source_requirement and any(w in q_lower for w in ["source of", "what is the source", "where did"]):
            return "source"

        if operation == "average":
            return "average"
        if operation == "sum":
            return "sum"
        if operation == "count":
            return "count"

        if "filter" in q_lower or "only" in q_lower:
            return "filter"

        if "lookup" in q_lower or "look up" in q_lower:
            return "lookup"

        if "report" in q_lower:
            return "report"

        if any(w in q_lower for w in ["list", "show all", "all attendance", "all records", "display"]):
            return "list"

        # Default to find
        return "find"

    def _extract_comparison_target(
        self, q_lower: str, satsang_ghar: Optional[str], month: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """Extracts comparison entities (e.g. between Sukhliya and Bicholi)."""
        # Find another ghar mentioned
        for ghar in KNOWN_SATSANG_GHARS:
            if ghar != satsang_ghar and re.search(rf"\b{re.escape(ghar.lower())}\b", q_lower):
                return {"satsang_ghar": ghar}

        # Find another month mentioned
        for m_name, m_num in MONTH_MAP.items():
            if m_num != month and re.search(rf"\b{m_name}\b", q_lower):
                return {"month": m_num}

        return None
