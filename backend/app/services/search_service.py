"""
Search Service for RSSB Office Data Platform.
Phase 2.2 — Natural-Language Search Foundation.

Executes structured QueryPlans against PostgreSQL via SQLAlchemy ORM.
Applies:
- Permission boundary checks
- Database-backed ambiguity resolution (e.g. multiple matching ghars or people)
- Clean relational retrieval
- Numerical calculations strictly from retrieved database values
- Granular SourceReference provenance extraction
- Machine-readable structured SearchResult models
"""

from datetime import date
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session, joinedload

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
from app.schemas.search import (
    QueryPlan,
    QueryPlanResult,
    SearchCalculation,
    SearchResult,
    SourceReferenceInfo,
)


class SearchContext:
    """
    Service boundary context for authorization and permission filtering.
    Prepares for multi-tenant or role-based access control.
    """

    def __init__(
        self,
        user_id: str = "default-user",
        roles: Optional[List[str]] = None,
        is_authorized: bool = True,
    ):
        self.user_id = user_id
        self.roles = roles or ["user"]
        self.is_authorized = is_authorized

    def verify_permission(self, action: str = "read") -> None:
        """Verifies if the current context has permission to execute searches."""
        if not self.is_authorized:
            raise PermissionError(f"User '{self.user_id}' is not authorized to search office data.")


class SearchService:
    """
    Core search engine that transforms a QueryPlan into safe ORM queries,
    performs calculations on retrieved records, and compiles provenance.
    """

    def __init__(self, db: Session, context: Optional[SearchContext] = None):
        self.db = db
        self.context = context or SearchContext()

    def execute_search(
        self, plan_result: QueryPlanResult, original_question: str
    ) -> SearchResult:
        """
        Main entry point for executing search.
        Handles planning ambiguity or executes the structured QueryPlan.
        """
        # 1. Check authorization
        self.context.verify_permission("read")

        # 2. Check if the planner identified ambiguity upfront
        if plan_result.is_ambiguous or not plan_result.plan:
            return SearchResult(
                original_question=original_question,
                interpreted_query={},
                status="clarification_required",
                answer=plan_result.clarification_question or "Could you please clarify your question?",
                records=[],
                total_records=0,
                calculation=None,
                source_references=[],
                clarification_required=True,
                clarification_question=plan_result.clarification_question,
                warnings=plan_result.warnings,
            )

        plan = plan_result.plan
        interpreted_dict = plan.model_dump(mode="json")

        # 3. Resolve Ambiguity in Database Entities (Satsang Ghar, Person)
        ghar_match, ghar_clarification = self._resolve_satsang_ghar(plan.satsang_ghar)
        if ghar_clarification:
            return SearchResult(
                original_question=original_question,
                interpreted_query=interpreted_dict,
                status="clarification_required",
                answer=ghar_clarification,
                records=[],
                total_records=0,
                calculation=None,
                source_references=[],
                clarification_required=True,
                clarification_question=ghar_clarification,
                warnings=["Multiple matching Satsang Ghars found in database."],
            )

        person_match, person_clarification = self._resolve_person(plan.person)
        if person_clarification:
            return SearchResult(
                original_question=original_question,
                interpreted_query=interpreted_dict,
                status="clarification_required",
                answer=person_clarification,
                records=[],
                total_records=0,
                calculation=None,
                source_references=[],
                clarification_required=True,
                clarification_question=person_clarification,
                warnings=["Multiple matching persons found in database."],
            )

        # 4. Route Execution based on record_type and intent
        try:
            if plan.intent == "compare":
                return self._execute_compare(plan, ghar_match, original_question, interpreted_dict)

            if plan.record_type == "attendance":
                return self._execute_attendance_search(plan, ghar_match, original_question, interpreted_dict)
            elif plan.record_type == "assignment":
                return self._execute_assignment_search(plan, ghar_match, person_match, original_question, interpreted_dict)
            elif plan.record_type == "vehicle_wheel":
                return self._execute_vehicle_search(plan, ghar_match, original_question, interpreted_dict)
            elif plan.record_type == "report":
                return self._execute_report_search(plan, original_question, interpreted_dict)
            elif plan.record_type == "document":
                return self._execute_document_search(plan, original_question, interpreted_dict)
            else:
                # Default fallback to attendance
                return self._execute_attendance_search(plan, ghar_match, original_question, interpreted_dict)
        except Exception as e:
            return SearchResult(
                original_question=original_question,
                interpreted_query=interpreted_dict,
                status="error",
                answer="An error occurred while retrieving search results.",
                records=[],
                total_records=0,
                calculation=None,
                source_references=[],
                clarification_required=False,
                clarification_question=None,
                warnings=[str(e)],
            )

    # -------------------------------------------------------------------------
    # Ambiguity Resolution Helpers
    # -------------------------------------------------------------------------

    def _resolve_satsang_ghar(self, ghar_name: Optional[str]) -> Tuple[Optional[SatsangGhar], Optional[str]]:
        """
        Finds SatsangGhar in database. If multiple distinct entities match,
        returns a clarification question instead of guessing.
        """
        if not ghar_name:
            return None, None

        # Try exact match first (case-insensitive)
        exact = self.db.query(SatsangGhar).filter(func.lower(SatsangGhar.name) == ghar_name.lower()).all()
        if len(exact) == 1:
            return exact[0], None

        # Try substring match
        matches = self.db.query(SatsangGhar).filter(SatsangGhar.name.ilike(f"%{ghar_name}%")).all()
        if len(matches) > 1:
            names = ", ".join([f"'{m.name}'" for m in matches])
            clarification = f"I found multiple Satsang Ghars matching '{ghar_name}': {names}. Which one do you mean?"
            return None, clarification
        elif len(matches) == 1:
            return matches[0], None

        return None, None

    def _resolve_person(self, person_name: Optional[str]) -> Tuple[Optional[Person], Optional[str]]:
        """
        Finds Person in database. If multiple people match, asks for clarification.
        """
        if not person_name:
            return None, None

        exact = self.db.query(Person).filter(func.lower(Person.name) == person_name.lower()).all()
        if len(exact) == 1:
            return exact[0], None

        matches = self.db.query(Person).filter(Person.name.ilike(f"%{person_name}%")).all()
        if len(matches) > 1:
            names = ", ".join([f"'{p.name}'" for p in matches])
            clarification = f"I found multiple people matching '{person_name}': {names}. Which person do you mean?"
            return None, clarification
        elif len(matches) == 1:
            return matches[0], None

        return None, None

    # -------------------------------------------------------------------------
    # Attendance Search & Calculation Execution
    # -------------------------------------------------------------------------

    def _execute_attendance_search(
        self,
        plan: QueryPlan,
        ghar: Optional[SatsangGhar],
        original_question: str,
        interpreted_dict: Dict[str, Any],
    ) -> SearchResult:
        query = (
            self.db.query(Attendance)
            .options(
                joinedload(Attendance.satsang_ghar),
                joinedload(Attendance.source_reference).joinedload(SourceReference.document),
                joinedload(Attendance.source_reference).joinedload(SourceReference.document_version),
            )
            .filter(Attendance.status != "invalid")  # Exclude invalid records
        )

        if ghar:
            query = query.filter(Attendance.satsang_ghar_id == ghar.id)
        elif plan.satsang_ghar:
            # Name specified but not found in DB
            return SearchResult(
                original_question=original_question,
                interpreted_query=interpreted_dict,
                status="no_results",
                answer=f"No Satsang Ghar named '{plan.satsang_ghar}' was found.",
                records=[],
                total_records=0,
                calculation=None,
                source_references=[],
                warnings=[f"Satsang Ghar '{plan.satsang_ghar}' does not exist in the database."],
            )

        # Date filtering
        if plan.date:
            query = query.filter(Attendance.date == plan.date)
        else:
            if plan.month:
                query = query.filter(extract("month", Attendance.date) == plan.month)
            if plan.year:
                query = query.filter(extract("year", Attendance.date) == plan.year)

        query = query.order_by(Attendance.date.asc())
        records = query.all()

        if not records:
            ghar_text = f" at {ghar.name}" if ghar else ""
            period_text = f" in {self._format_period(plan)}" if (plan.month or plan.year or plan.date) else ""
            return SearchResult(
                original_question=original_question,
                interpreted_query=interpreted_dict,
                status="no_results",
                answer=f"No attendance records found{ghar_text}{period_text}.",
                records=[],
                total_records=0,
                calculation=None,
                source_references=[],
            )

        # Numerical Calculations
        calculation = None
        values = [r.count_value for r in records if r.count_value is not None]

        operation = plan.numeric_operation or (plan.intent if plan.intent in ["average", "sum", "count"] else None)

        if operation == "average":
            avg_val = round(sum(values) / len(values), 2) if values else 0.0
            breakdown_str = f"({' + '.join(map(str, values))}) / {len(values)} = {avg_val}" if values else "0"
            calculation = SearchCalculation(
                operation="average",
                value=avg_val,
                unit="attendees",
                records_counted=len(values),
                formula_description=f"Sum of {sum(values)} across {len(values)} sessions = {avg_val}",
                breakdown=breakdown_str,
            )
        elif operation == "sum":
            total_val = sum(values) if values else 0
            breakdown_str = f"{' + '.join(map(str, values))} = {total_val}" if values else "0"
            calculation = SearchCalculation(
                operation="sum",
                value=total_val,
                unit="attendees",
                records_counted=len(values),
                formula_description=f"Total sum across {len(values)} sessions = {total_val}",
                breakdown=breakdown_str,
            )
        elif operation == "count":
            calculation = SearchCalculation(
                operation="count",
                value=len(records),
                unit="records",
                records_counted=len(records),
                formula_description=f"Counted {len(records)} attendance records",
                breakdown=f"Count of {len(records)} records = {len(records)}",
            )
        elif operation == "max":
            max_val = max(values) if values else 0
            calculation = SearchCalculation(
                operation="max",
                value=max_val,
                unit="attendees",
                records_counted=len(values),
                formula_description=f"Maximum attendance count = {max_val}",
                breakdown=f"max({', '.join(map(str, values))}) = {max_val}" if values else "0",
            )
        elif operation == "min":
            min_val = min(values) if values else 0
            calculation = SearchCalculation(
                operation="min",
                value=min_val,
                unit="attendees",
                records_counted=len(values),
                formula_description=f"Minimum attendance count = {min_val}",
                breakdown=f"min({', '.join(map(str, values))}) = {min_val}" if values else "0",
            )

        # Serialize Records & Collect Provenance
        serialized_records = []
        source_refs: List[SourceReferenceInfo] = []
        seen_sr_ids = set()

        for att in records:
            sr_info = self._extract_source_ref_info(att.source_reference)
            if att.source_reference_id and att.source_reference_id not in seen_sr_ids and sr_info:
                seen_sr_ids.add(att.source_reference_id)
                source_refs.append(sr_info)

            serialized_records.append({
                "id": str(att.id),
                "date": att.date.isoformat() if att.date else None,
                "satsang_ghar": att.satsang_ghar.name if att.satsang_ghar else None,
                "attendance_count": att.count_value,
                "raw_value": att.raw_value,
                "status": att.status,
                "source_reference_id": str(att.source_reference_id) if att.source_reference_id else None,
                "source_reference": sr_info.model_dump() if sr_info else None,
            })

        # Check for Needs Review state
        has_needs_review = any(r.status == "needs_review" for r in records)
        search_status = "needs_review" if has_needs_review else "success"
        warnings = []
        if has_needs_review:
            warnings.append("Some or all matching records are flagged as Needs Review by office verification.")

        # Generate Human-Friendly Answer
        answer = self._generate_attendance_answer(plan, ghar, len(records), calculation)
        if search_status == "needs_review":
            answer += " (Note: Supporting records are flagged as Needs Review.)"

        return SearchResult(
            original_question=original_question,
            interpreted_query=interpreted_dict,
            status=search_status,
            answer=answer,
            records=serialized_records,
            total_records=len(records),
            calculation=calculation,
            source_references=source_refs,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    # Assignment Search Execution
    # -------------------------------------------------------------------------

    def _execute_assignment_search(
        self,
        plan: QueryPlan,
        ghar: Optional[SatsangGhar],
        person: Optional[Person],
        original_question: str,
        interpreted_dict: Dict[str, Any],
    ) -> SearchResult:
        query = (
            self.db.query(Assignment)
            .options(
                joinedload(Assignment.satsang_ghar),
                joinedload(Assignment.person),
                joinedload(Assignment.role),
                joinedload(Assignment.source_reference).joinedload(SourceReference.document),
                joinedload(Assignment.source_reference).joinedload(SourceReference.document_version),
            )
            .filter(Assignment.status != "invalid")
        )

        if ghar:
            query = query.filter(Assignment.satsang_ghar_id == ghar.id)
        elif plan.satsang_ghar:
            return SearchResult(
                original_question=original_question,
                interpreted_query=interpreted_dict,
                status="no_results",
                answer=f"No Satsang Ghar named '{plan.satsang_ghar}' was found.",
                records=[],
                total_records=0,
                calculation=None,
                source_references=[],
            )

        if person:
            query = query.filter(Assignment.person_id == person.id)
        elif plan.person:
            # Check if person was searched for but not in DB
            person_exists = self.db.query(Person).filter(Person.name.ilike(f"%{plan.person}%")).first()
            if not person_exists:
                return SearchResult(
                    original_question=original_question,
                    interpreted_query=interpreted_dict,
                    status="no_results",
                    answer=f"No person named '{plan.person}' was found in assignment records.",
                    records=[],
                    total_records=0,
                    calculation=None,
                    source_references=[],
                )

        if plan.role:
            role_obj = self.db.query(Role).filter(Role.code == plan.role).first()
            if role_obj:
                query = query.filter(Assignment.role_id == role_obj.id)
            else:
                # Also check description for role keywords like "VIDEO CD"
                query = query.filter(Assignment.description.ilike(f"%{plan.role}%"))

        if plan.date:
            query = query.filter(Assignment.date == plan.date)
        else:
            if plan.month:
                query = query.filter(extract("month", Assignment.date) == plan.month)
            if plan.year:
                query = query.filter(extract("year", Assignment.date) == plan.year)

        query = query.order_by(Assignment.date.asc())
        records = query.all()

        if not records:
            ghar_text = f" at {ghar.name}" if ghar else ""
            role_text = f" for role '{plan.role}'" if plan.role else ""
            date_text = f" on {plan.date.isoformat()}" if plan.date else ""
            return SearchResult(
                original_question=original_question,
                interpreted_query=interpreted_dict,
                status="no_results",
                answer=f"No duty assignments found{role_text}{ghar_text}{date_text}.",
                records=[],
                total_records=0,
                calculation=None,
                source_references=[],
            )

        # Serialization & Provenance
        serialized_records = []
        source_refs: List[SourceReferenceInfo] = []
        seen_sr_ids = set()

        for asn in records:
            sr_info = self._extract_source_ref_info(asn.source_reference)
            if asn.source_reference_id and asn.source_reference_id not in seen_sr_ids and sr_info:
                seen_sr_ids.add(asn.source_reference_id)
                source_refs.append(sr_info)

            role_code = asn.role.code if asn.role else None
            role_name = asn.role.name if asn.role else (asn.description or "General Duty")
            person_name = asn.person.name if asn.person else "Unassigned"

            serialized_records.append({
                "id": str(asn.id),
                "date": asn.date.isoformat() if asn.date else None,
                "satsang_ghar": asn.satsang_ghar.name if asn.satsang_ghar else None,
                "person": person_name,
                "role_code": role_code,
                "role_name": role_name,
                "description": asn.description,
                "status": asn.status,
                "source_reference_id": str(asn.source_reference_id) if asn.source_reference_id else None,
                "source_reference": sr_info.model_dump() if sr_info else None,
            })

        calculation = None
        if plan.numeric_operation == "count" or plan.intent == "count":
            calculation = SearchCalculation(
                operation="count",
                value=len(records),
                unit="assignments",
                records_counted=len(records),
                formula_description=f"Counted {len(records)} matching duty assignments",
                breakdown=f"Count of {len(records)} assignments = {len(records)}",
            )

        # Check for Needs Review state
        has_needs_review = any(r.status == "needs_review" for r in records)
        search_status = "needs_review" if has_needs_review else "success"
        warnings = []
        if has_needs_review:
            warnings.append("Some or all matching assignment records are flagged as Needs Review.")

        # Generate Human Answer
        if len(records) == 1:
            rec = serialized_records[0]
            role_code_str = f" ({rec['role_code']})" if rec.get("role_code") else ""
            ghar_loc_str = f" at {rec['satsang_ghar']}" if rec.get("satsang_ghar") else ""
            date_str = f" on {rec['date']}" if rec.get("date") else ""
            answer = f"{rec['person']} is assigned as {rec['role_name']}{role_code_str}{ghar_loc_str}{date_str}."
        else:
            ghar_str = f" at {ghar.name}" if ghar else ""
            answer = f"Found {len(records)} duty assignments{ghar_str}."

        if search_status == "needs_review":
            answer += " (Note: Supporting records are flagged as Needs Review.)"

        return SearchResult(
            original_question=original_question,
            interpreted_query=interpreted_dict,
            status=search_status,
            answer=answer,
            records=serialized_records,
            total_records=len(records),
            calculation=calculation,
            source_references=source_refs,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    # Vehicle / Wheel Search Execution
    # -------------------------------------------------------------------------

    def _execute_vehicle_search(
        self,
        plan: QueryPlan,
        ghar: Optional[SatsangGhar],
        original_question: str,
        interpreted_dict: Dict[str, Any],
    ) -> SearchResult:
        query = (
            self.db.query(VehicleWheelData)
            .options(
                joinedload(VehicleWheelData.satsang_ghar),
                joinedload(VehicleWheelData.source_reference).joinedload(SourceReference.document),
            )
            .filter(VehicleWheelData.status != "invalid")
        )

        if ghar:
            query = query.filter(VehicleWheelData.satsang_ghar_id == ghar.id)
        if plan.vehicle_type and plan.vehicle_type != "Vehicle/Wheel":
            query = query.filter(VehicleWheelData.vehicle_type.ilike(f"%{plan.vehicle_type}%"))
        if plan.date:
            query = query.filter(VehicleWheelData.date == plan.date)
        elif plan.month:
            query = query.filter(extract("month", VehicleWheelData.date) == plan.month)

        records = query.all()
        if not records:
            return SearchResult(
                original_question=original_question,
                interpreted_query=interpreted_dict,
                status="no_results",
                answer="No vehicle or wheel records found matching your query.",
                records=[],
                total_records=0,
                calculation=None,
                source_references=[],
            )

        values = [r.count_value for r in records if r.count_value is not None]
        calculation = None
        if plan.numeric_operation == "sum" or plan.intent == "sum":
            calculation = SearchCalculation(
                operation="sum",
                value=sum(values),
                unit="vehicles",
                records_counted=len(values),
            )
        elif plan.numeric_operation == "average" or plan.intent == "average":
            avg = round(sum(values) / len(values), 2) if values else 0.0
            calculation = SearchCalculation(
                operation="average",
                value=avg,
                unit="vehicles",
                records_counted=len(values),
            )

        serialized = [
            {
                "id": str(v.id),
                "date": v.date.isoformat() if v.date else None,
                "satsang_ghar": v.satsang_ghar.name if v.satsang_ghar else None,
                "count_value": v.count_value,
                "vehicle_type": v.vehicle_type,
                "raw_value": v.raw_value,
            }
            for v in records
        ]

        source_refs = [
            self._extract_source_ref_info(v.source_reference)
            for v in records
            if v.source_reference
        ]

        ans = f"Found {len(records)} vehicle/wheel statistics records."
        if calculation:
            ans += f" Calculated {calculation.operation}: {calculation.value} {calculation.unit}."

        return SearchResult(
            original_question=original_question,
            interpreted_query=interpreted_dict,
            status="success",
            answer=ans,
            records=serialized,
            total_records=len(records),
            calculation=calculation,
            source_references=source_refs,
        )

    # -------------------------------------------------------------------------
    # Report & Document Search
    # -------------------------------------------------------------------------

    def _execute_report_search(
        self, plan: QueryPlan, original_question: str, interpreted_dict: Dict[str, Any]
    ) -> SearchResult:
        query = self.db.query(Report)
        records = query.all()
        if not records:
            return SearchResult(
                original_question=original_question,
                interpreted_query=interpreted_dict,
                status="no_results",
                answer="No registered reports found.",
                records=[],
                total_records=0,
                calculation=None,
                source_references=[],
            )

        serialized = [
            {
                "id": str(r.id),
                "name": r.name,
                "report_type": r.report_type,
                "status": r.status,
            }
            for r in records
        ]

        return SearchResult(
            original_question=original_question,
            interpreted_query=interpreted_dict,
            status="success",
            answer=f"Found {len(records)} reports.",
            records=serialized,
            total_records=len(records),
            calculation=None,
            source_references=[],
        )

    def _execute_document_search(
        self, plan: QueryPlan, original_question: str, interpreted_dict: Dict[str, Any]
    ) -> SearchResult:
        query = self.db.query(Document).options(joinedload(Document.versions))
        records = query.all()
        serialized = [
            {
                "id": str(d.id),
                "filename": d.original_filename,
                "document_type": d.document_type,
                "status": d.status,
                "versions_count": len(d.versions),
            }
            for d in records
        ]
        return SearchResult(
            original_question=original_question,
            interpreted_query=interpreted_dict,
            status="success",
            answer=f"Found {len(records)} documents in the platform.",
            records=serialized,
            total_records=len(records),
            calculation=None,
            source_references=[],
        )

    # -------------------------------------------------------------------------
    # Compare Intent Execution
    # -------------------------------------------------------------------------

    def _execute_compare(
        self,
        plan: QueryPlan,
        ghar: Optional[SatsangGhar],
        original_question: str,
        interpreted_dict: Dict[str, Any],
    ) -> SearchResult:
        """Compares attendance between two entities (e.g. two Satsang Ghars or periods)."""
        target = plan.comparison_target or {}
        other_ghar_name = target.get("satsang_ghar")

        if not ghar or not other_ghar_name:
            return SearchResult(
                original_question=original_question,
                interpreted_query=interpreted_dict,
                status="clarification_required",
                answer="Please specify two Satsang Ghars or two time periods to compare.",
                records=[],
                total_records=0,
                calculation=None,
                source_references=[],
                clarification_required=True,
                clarification_question="Which two Satsang Ghars or time periods would you like to compare?",
            )

        other_ghar, _ = self._resolve_satsang_ghar(other_ghar_name)
        if not other_ghar:
            return SearchResult(
                original_question=original_question,
                interpreted_query=interpreted_dict,
                status="no_results",
                answer=f"Comparison Satsang Ghar '{other_ghar_name}' not found.",
                records=[],
                total_records=0,
                calculation=None,
                source_references=[],
            )

        records_1 = self.db.query(Attendance).filter(Attendance.satsang_ghar_id == ghar.id).all()
        records_2 = self.db.query(Attendance).filter(Attendance.satsang_ghar_id == other_ghar.id).all()

        v1 = [r.count_value for r in records_1 if r.count_value is not None]
        v2 = [r.count_value for r in records_2 if r.count_value is not None]

        avg1 = round(sum(v1) / len(v1), 2) if v1 else 0.0
        avg2 = round(sum(v2) / len(v2), 2) if v2 else 0.0
        diff = round(avg1 - avg2, 2)

        ans = (
            f"Comparison of Average Attendance: {ghar.name} averaged {avg1} ({len(v1)} records), "
            f"while {other_ghar.name} averaged {avg2} ({len(v2)} records). "
            f"Difference is {diff:+0.2f}."
        )

        return SearchResult(
            original_question=original_question,
            interpreted_query=interpreted_dict,
            status="success",
            answer=ans,
            records=[
                {"satsang_ghar": ghar.name, "average_attendance": avg1, "count": len(v1)},
                {"satsang_ghar": other_ghar.name, "average_attendance": avg2, "count": len(v2)},
            ],
            total_records=len(records_1) + len(records_2),
            calculation=SearchCalculation(
                operation="compare",
                value=diff,
                unit="difference",
                records_counted=len(v1) + len(v2),
            ),
            source_references=[],
        )

    # -------------------------------------------------------------------------
    # Provenance & Answer Formatting Helpers
    # -------------------------------------------------------------------------

    def _extract_source_ref_info(self, sr: Optional[SourceReference]) -> Optional[SourceReferenceInfo]:
        """Extracts source provenance fields from a SourceReference model."""
        if not sr:
            return None
        doc_name = sr.document.original_filename if sr.document else None
        v_num = sr.document_version.version_number if sr.document_version else None
        raw_doc_type = sr.document.document_type if sr.document else None
        doc_type = "excel" if raw_doc_type in ["xlsx", "xls"] else (raw_doc_type or "unknown")

        bbox = None
        if sr.cell_or_range and sr.cell_or_range.startswith("bbox:["):
            try:
                coords_str = sr.cell_or_range[6:-1]
                bbox = [float(x.strip()) for x in coords_str.split(",")]
            except Exception:
                bbox = None

        return SourceReferenceInfo(
            id=str(sr.id),
            document_id=str(sr.document_id) if sr.document_id else None,
            document_name=doc_name,
            document_version=v_num,
            document_type=doc_type,
            page_number=sr.page_number,
            sheet_name=sr.sheet_name,
            row_number=sr.row_number,
            cell_or_range=sr.cell_or_range,
            bbox=bbox,
            source_text=sr.source_text,
        )

    def _format_period(self, plan: QueryPlan) -> str:
        """Formats human-readable date/period description."""
        month_names = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        if plan.date:
            return plan.date.isoformat()
        if plan.month and plan.year:
            return f"{month_names[plan.month]} {plan.year}"
        if plan.month:
            return f"{month_names[plan.month]}"
        if plan.year:
            return f"{plan.year}"
        return ""

    def _generate_attendance_answer(
        self,
        plan: QueryPlan,
        ghar: Optional[SatsangGhar],
        count: int,
        calc: Optional[SearchCalculation],
    ) -> str:
        """Constructs human-friendly, accurate natural language response."""
        ghar_str = f" at {ghar.name}" if ghar else ""
        period_str = f" in {self._format_period(plan)}" if (plan.month or plan.year or plan.date) else ""

        if calc:
            if calc.operation == "average":
                return f"The average attendance{ghar_str}{period_str} was {calc.value} across {calc.records_counted} recorded sessions."
            elif calc.operation == "sum":
                return f"The total attendance{ghar_str}{period_str} was {calc.value} across {calc.records_counted} recorded sessions."
            elif calc.operation == "count":
                return f"Found {calc.value} attendance records{ghar_str}{period_str}."
            elif calc.operation == "max":
                return f"The highest attendance{ghar_str}{period_str} was {calc.value}."
            elif calc.operation == "min":
                return f"The lowest attendance{ghar_str}{period_str} was {calc.value}."

        return f"Found {count} attendance records{ghar_str}{period_str}."
