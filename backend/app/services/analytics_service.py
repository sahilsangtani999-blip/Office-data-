"""
Core service for Multi-Document Analytics & Comparison.
Phase 3.0 — RSSB Office Data Platform.
"""

from datetime import date
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from sqlalchemy import and_, distinct, func
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Assignment,
    Attendance,
    Document,
    Person,
    Role,
    SatsangGhar,
    SourceReference,
    VehicleWheelData,
)
from app.schemas.analytics import (
    AnalyticsDimensionsResponse,
    ComparisonRequest,
    ComparisonResultResponse,
    EntityMetricSummary,
    MultiDocSummaryRequest,
    MultiDocSummaryResponse,
)
from app.schemas.search import SourceReferenceInfo


class AnalyticsService:
    """Service providing multi-document aggregation and comparative analytics."""

    def __init__(self, db: Session):
        self.db = db

    # -------------------------------------------------------------------------
    # Public Entrypoints
    # -------------------------------------------------------------------------

    def compare(self, req: ComparisonRequest) -> ComparisonResultResponse:
        """Executes a comparative analytics query based on requested dimension and metric."""
        if req.dimension == "location":
            return self._compare_locations(req)
        elif req.dimension == "period":
            return self._compare_periods(req)
        else:
            raise ValueError(f"Unsupported comparison dimension '{req.dimension}'. Must be 'location' or 'period'.")

    def get_multi_document_summary(self, req: MultiDocSummaryRequest) -> MultiDocSummaryResponse:
        """Aggregates high-level metrics across multiple documents in a given date span."""
        att_query = self.db.query(Attendance).join(Attendance.source_reference, isouter=True)
        asg_query = self.db.query(Assignment).join(Assignment.source_reference, isouter=True)
        veh_query = self.db.query(VehicleWheelData).join(VehicleWheelData.source_reference, isouter=True)

        if req.date_start:
            att_query = att_query.filter(Attendance.date >= req.date_start)
            asg_query = asg_query.filter(Assignment.date >= req.date_start)
            veh_query = veh_query.filter(VehicleWheelData.date >= req.date_start)

        if req.date_end:
            att_query = att_query.filter(Attendance.date <= req.date_end)
            asg_query = asg_query.filter(Assignment.date <= req.date_end)
            veh_query = veh_query.filter(VehicleWheelData.date <= req.date_end)

        if req.document_ids:
            doc_uuids = []
            for d_id in req.document_ids:
                try:
                    doc_uuids.append(uuid.UUID(d_id))
                except ValueError:
                    pass
            if doc_uuids:
                att_query = att_query.filter(SourceReference.document_id.in_(doc_uuids))
                asg_query = asg_query.filter(SourceReference.document_id.in_(doc_uuids))
                veh_query = veh_query.filter(SourceReference.document_id.in_(doc_uuids))

        attendances = att_query.options(joinedload(Attendance.source_reference).joinedload(SourceReference.document)).all()
        assignments = asg_query.options(joinedload(Assignment.source_reference).joinedload(SourceReference.document)).all()
        vehicles = veh_query.options(joinedload(VehicleWheelData.source_reference).joinedload(SourceReference.document)).all()

        # Compute attendance KPIs
        att_vals = [a.count_value for a in attendances if a.count_value is not None]
        total_att = sum(att_vals)
        avg_att = round(total_att / len(att_vals), 2) if att_vals else 0.0

        total_asg = len(assignments)
        veh_vals = [v.count_value for v in vehicles if v.count_value is not None]
        total_veh = sum(veh_vals)

        # Distinct contributing documents
        doc_map: Dict[str, Dict[str, Any]] = {}

        def record_doc_contrib(sr: Optional[SourceReference], domain: str, count: int):
            if not sr or not sr.document:
                return
            d_id = str(sr.document.id)
            if d_id not in doc_map:
                doc_map[d_id] = {
                    "document_id": d_id,
                    "filename": sr.document.original_filename,
                    "document_type": sr.document.document_type,
                    "status": sr.document.status,
                    "attendance_count": 0,
                    "assignment_count": 0,
                    "vehicle_count": 0,
                }
            if domain == "attendance":
                doc_map[d_id]["attendance_count"] += count
            elif domain == "assignment":
                doc_map[d_id]["assignment_count"] += count
            elif domain == "vehicle":
                doc_map[d_id]["vehicle_count"] += count

        for a in attendances:
            record_doc_contrib(a.source_reference, "attendance", 1)
        for asg in assignments:
            record_doc_contrib(asg.source_reference, "assignment", 1)
        for v in vehicles:
            record_doc_contrib(v.source_reference, "vehicle", 1)

        return MultiDocSummaryResponse(
            total_documents=len(doc_map),
            total_attendance=total_att,
            average_attendance=avg_att,
            total_assignments=total_asg,
            total_vehicles=total_veh,
            period_start=req.date_start.isoformat() if req.date_start else None,
            period_end=req.date_end.isoformat() if req.date_end else None,
            per_document_breakdown=list(doc_map.values()),
        )

    def get_dimensions(self) -> AnalyticsDimensionsResponse:
        """Returns available dimensions, metrics, known ghars, and months for UI selectors."""
        ghars = [g.name for g in self.db.query(SatsangGhar).order_by(SatsangGhar.name).all()]
        months = [
            {"value": 1, "label": "January"},
            {"value": 2, "label": "February"},
            {"value": 3, "label": "March"},
            {"value": 4, "label": "April"},
            {"value": 5, "label": "May"},
            {"value": 6, "label": "June"},
            {"value": 7, "label": "July"},
            {"value": 8, "label": "August"},
            {"value": 9, "label": "September"},
            {"value": 10, "label": "October"},
            {"value": 11, "label": "November"},
            {"value": 12, "label": "December"},
        ]
        return AnalyticsDimensionsResponse(
            dimensions=[
                {"value": "location", "label": "Centre vs. Centre (Same Period)"},
                {"value": "period", "label": "Period vs. Period (Month-over-Month)"},
            ],
            metrics=[
                {"value": "attendance", "label": "Attendance (Average & Total)"},
                {"value": "vehicle_wheel", "label": "Vehicle Logs (2-Wheeler / 4-Wheeler)"},
                {"value": "assignment", "label": "Duty Rosters (Sewadar Assignments)"},
            ],
            known_satsang_ghars=ghars,
            available_months=months,
        )

    # -------------------------------------------------------------------------
    # Location Comparison Execution
    # -------------------------------------------------------------------------

    def _compare_locations(self, req: ComparisonRequest) -> ComparisonResultResponse:
        name_a = (req.entity_a or "").strip()
        name_b = (req.entity_b or "").strip()

        if not name_a or not name_b:
            raise ValueError("Location comparison requires both entity_a and entity_b (Satsang Ghar names).")
        if name_a.lower() == name_b.lower():
            raise ValueError("Location comparison requires two distinct Satsang Ghars.")

        ghar_a = self._resolve_ghar(name_a)
        ghar_b = self._resolve_ghar(name_b)

        if not ghar_a:
            raise ValueError(f"Satsang Ghar '{name_a}' not found in database.")
        if not ghar_b:
            raise ValueError(f"Satsang Ghar '{name_b}' not found in database.")

        period_start = req.shared_period_start
        period_end = req.shared_period_end

        warnings: List[str] = []
        all_srs: List[SourceReference] = []

        if req.metric == "attendance":
            summary_a, srs_a = self._get_attendance_summary(ghar_a, period_start, period_end, req.sub_metric, ghar_a.name)
            summary_b, srs_b = self._get_attendance_summary(ghar_b, period_start, period_end, req.sub_metric, ghar_b.name)
            unit = "attendees/session" if req.sub_metric != "total" else "attendees"
        elif req.metric == "vehicle_wheel":
            summary_a, srs_a = self._get_vehicle_summary(ghar_a, period_start, period_end, req.sub_metric, ghar_a.name)
            summary_b, srs_b = self._get_vehicle_summary(ghar_b, period_start, period_end, req.sub_metric, ghar_b.name)
            unit = "vehicles"
        elif req.metric == "assignment":
            summary_a, srs_a = self._get_assignment_summary(ghar_a, period_start, period_end, req.sub_metric, ghar_a.name)
            summary_b, srs_b = self._get_assignment_summary(ghar_b, period_start, period_end, req.sub_metric, ghar_b.name)
            unit = "assignments"
        else:
            raise ValueError(f"Unsupported metric '{req.metric}'.")

        all_srs.extend(srs_a)
        all_srs.extend(srs_b)

        # Delta and percentage
        val_a = summary_a.primary_value
        val_b = summary_b.primary_value
        delta = round(val_b - val_a, 2)
        pct_change = round(((val_b - val_a) / val_a) * 100, 2) if val_a > 0 else None

        # Build sentence & breakdown text
        date_str = f" for period {period_start} to {period_end}" if period_start and period_end else ""
        pct_str = f" ({pct_change:+0.2f}%)" if pct_change is not None else ""
        diff_str = f"{delta:+0.2f}" if delta != 0 else "0.00"

        metric_title = "Average Attendance" if req.metric == "attendance" and req.sub_metric != "total" else req.metric.replace("_", " ").title()
        if req.metric == "attendance" and req.sub_metric != "total":
            summary_sentence = (
                f"Comparison of Average Attendance{date_str}: {summary_a.label} averaged {val_a} ({summary_a.record_count} records), "
                f"while {summary_b.label} averaged {val_b} ({summary_b.record_count} records). "
                f"Difference is {diff_str}."
            )
        else:
            summary_sentence = (
                f"Comparison of {metric_title}{date_str}: {summary_a.label} recorded {val_a} {unit} ({summary_a.record_count} records across {summary_a.document_count} doc), "
                f"while {summary_b.label} recorded {val_b} {unit} ({summary_b.record_count} records across {summary_b.document_count} doc). "
                f"Difference is {diff_str} {unit}{pct_str}."
            )

        breakdown_text = (
            f"{summary_a.label}: {val_a} | {summary_b.label}: {val_b} | "
            f"Delta: {diff_str} | % Change: {pct_str.strip() or 'N/A'}"
        )

        # Check for unreviewed documents
        self._check_unreviewed_documents(all_srs, warnings)

        source_info_list = self._format_source_references(all_srs)

        return ComparisonResultResponse(
            metric=req.metric,
            dimension="location",
            unit=unit,
            entity_a=summary_a,
            entity_b=summary_b,
            delta=delta,
            percentage_change=pct_change,
            summary_sentence=summary_sentence,
            breakdown_text=breakdown_text,
            source_references=source_info_list,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    # Period Comparison Execution
    # -------------------------------------------------------------------------

    def _compare_periods(self, req: ComparisonRequest) -> ComparisonResultResponse:
        p_a_start = req.period_a_start
        p_a_end = req.period_a_end
        p_b_start = req.period_b_start
        p_b_end = req.period_b_end

        if not p_a_start or not p_a_end or not p_b_start or not p_b_end:
            raise ValueError("Period comparison requires period_a_start, period_a_end, period_b_start, and period_b_end.")

        if p_a_start > p_a_end:
            raise ValueError(f"Period A start date ({p_a_start}) cannot be after end date ({p_a_end}).")
        if p_b_start > p_b_end:
            raise ValueError(f"Period B start date ({p_b_start}) cannot be after end date ({p_b_end}).")

        ghar = self._resolve_ghar(req.satsang_ghar) if req.satsang_ghar else None
        ghar_label = ghar.name if ghar else "All Centres"

        label_a = f"{ghar_label} ({p_a_start.strftime('%b %Y') if p_a_start.month == p_a_end.month and p_a_start.year == p_a_end.year else f'{p_a_start} to {p_a_end}'})"
        label_b = f"{ghar_label} ({p_b_start.strftime('%b %Y') if p_b_start.month == p_b_end.month and p_b_start.year == p_b_end.year else f'{p_b_start} to {p_b_end}'})"

        warnings: List[str] = []
        all_srs: List[SourceReference] = []

        if req.metric == "attendance":
            summary_a, srs_a = self._get_attendance_summary(ghar, p_a_start, p_a_end, req.sub_metric, label_a)
            summary_b, srs_b = self._get_attendance_summary(ghar, p_b_start, p_b_end, req.sub_metric, label_b)
            unit = "attendees/session" if req.sub_metric != "total" else "attendees"
        elif req.metric == "vehicle_wheel":
            summary_a, srs_a = self._get_vehicle_summary(ghar, p_a_start, p_a_end, req.sub_metric, label_a)
            summary_b, srs_b = self._get_vehicle_summary(ghar, p_b_start, p_b_end, req.sub_metric, label_b)
            unit = "vehicles"
        elif req.metric == "assignment":
            summary_a, srs_a = self._get_assignment_summary(ghar, p_a_start, p_a_end, req.sub_metric, label_a)
            summary_b, srs_b = self._get_assignment_summary(ghar, p_b_start, p_b_end, req.sub_metric, label_b)
            unit = "assignments"
        else:
            raise ValueError(f"Unsupported metric '{req.metric}'.")

        all_srs.extend(srs_a)
        all_srs.extend(srs_b)

        val_a = summary_a.primary_value
        val_b = summary_b.primary_value
        delta = round(val_b - val_a, 2)
        pct_change = round(((val_b - val_a) / val_a) * 100, 2) if val_a > 0 else None

        pct_str = f" ({pct_change:+0.2f}%)" if pct_change is not None else ""
        diff_str = f"{delta:+0.2f}" if delta != 0 else "0.00"

        summary_sentence = (
            f"Period Comparison for {ghar_label}: Period A ({p_a_start} to {p_a_end}) recorded {val_a} {unit} ({summary_a.record_count} records across {summary_a.document_count} doc), "
            f"while Period B ({p_b_start} to {p_b_end}) recorded {val_b} {unit} ({summary_b.record_count} records across {summary_b.document_count} doc). "
            f"Net change is {diff_str} {unit}{pct_str}."
        )

        breakdown_text = (
            f"Period A: {val_a} | Period B: {val_b} | Delta: {diff_str} | Growth: {pct_str.strip() or 'N/A'}"
        )

        self._check_unreviewed_documents(all_srs, warnings)
        source_info_list = self._format_source_references(all_srs)

        return ComparisonResultResponse(
            metric=req.metric,
            dimension="period",
            unit=unit,
            entity_a=summary_a,
            entity_b=summary_b,
            delta=delta,
            percentage_change=pct_change,
            summary_sentence=summary_sentence,
            breakdown_text=breakdown_text,
            source_references=source_info_list,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    # Aggregation Helpers
    # -------------------------------------------------------------------------

    def _get_attendance_summary(
        self,
        ghar: Optional[SatsangGhar],
        start_date: Optional[date],
        end_date: Optional[date],
        sub_metric: Optional[str],
        label: str,
    ) -> Tuple[EntityMetricSummary, List[SourceReference]]:
        query = self.db.query(Attendance).options(
            joinedload(Attendance.satsang_ghar),
            joinedload(Attendance.source_reference).joinedload(SourceReference.document),
        )
        if ghar:
            query = query.filter(Attendance.satsang_ghar_id == ghar.id)
        if start_date:
            query = query.filter(Attendance.date >= start_date)
        if end_date:
            query = query.filter(Attendance.date <= end_date)

        records = query.order_by(Attendance.date.asc()).all()
        vals = [r.count_value for r in records if r.count_value is not None]
        total_val = sum(vals)
        avg_val = round(total_val / len(vals), 2) if vals else 0.0

        is_total = (sub_metric == "total")
        primary_val = float(total_val) if is_total else avg_val
        secondary_val = avg_val if is_total else float(total_val)

        doc_names = set()
        srs: List[SourceReference] = []
        breakdown_items = []

        for r in records:
            doc_name = None
            if r.source_reference:
                srs.append(r.source_reference)
                if r.source_reference.document:
                    doc_name = r.source_reference.document.original_filename
                    doc_names.add(doc_name)

            breakdown_items.append({
                "date": r.date.isoformat() if r.date else None,
                "satsang_ghar": r.satsang_ghar.name if r.satsang_ghar else None,
                "count": r.count_value,
                "raw_value": r.raw_value,
                "document_name": doc_name,
                "source_reference_id": str(r.source_reference_id) if r.source_reference_id else None,
            })

        summary = EntityMetricSummary(
            label=label,
            primary_value=primary_val,
            secondary_value=secondary_val,
            record_count=len(records),
            document_count=len(doc_names),
            document_names=sorted(list(doc_names)),
            breakdown_items=breakdown_items,
        )
        return summary, srs

    def _get_vehicle_summary(
        self,
        ghar: Optional[SatsangGhar],
        start_date: Optional[date],
        end_date: Optional[date],
        sub_metric: Optional[str],
        label: str,
    ) -> Tuple[EntityMetricSummary, List[SourceReference]]:
        query = self.db.query(VehicleWheelData).options(
            joinedload(VehicleWheelData.satsang_ghar),
            joinedload(VehicleWheelData.source_reference).joinedload(SourceReference.document),
        )
        if ghar:
            query = query.filter(VehicleWheelData.satsang_ghar_id == ghar.id)
        if start_date:
            query = query.filter(VehicleWheelData.date >= start_date)
        if end_date:
            query = query.filter(VehicleWheelData.date <= end_date)
        if sub_metric:
            query = query.filter(VehicleWheelData.vehicle_type.ilike(f"%{sub_metric}%"))

        records = query.order_by(VehicleWheelData.date.asc()).all()
        vals = [r.count_value for r in records if r.count_value is not None]
        total_val = sum(vals)

        doc_names = set()
        srs: List[SourceReference] = []
        breakdown_items = []

        for r in records:
            doc_name = None
            if r.source_reference:
                srs.append(r.source_reference)
                if r.source_reference.document:
                    doc_name = r.source_reference.document.original_filename
                    doc_names.add(doc_name)

            breakdown_items.append({
                "date": r.date.isoformat() if r.date else None,
                "satsang_ghar": r.satsang_ghar.name if r.satsang_ghar else None,
                "vehicle_type": r.vehicle_type,
                "count": r.count_value,
                "description": r.description,
                "document_name": doc_name,
                "source_reference_id": str(r.source_reference_id) if r.source_reference_id else None,
            })

        summary = EntityMetricSummary(
            label=label,
            primary_value=float(total_val),
            secondary_value=None,
            record_count=len(records),
            document_count=len(doc_names),
            document_names=sorted(list(doc_names)),
            breakdown_items=breakdown_items,
        )
        return summary, srs

    def _get_assignment_summary(
        self,
        ghar: Optional[SatsangGhar],
        start_date: Optional[date],
        end_date: Optional[date],
        sub_metric: Optional[str],
        label: str,
    ) -> Tuple[EntityMetricSummary, List[SourceReference]]:
        query = self.db.query(Assignment).options(
            joinedload(Assignment.satsang_ghar),
            joinedload(Assignment.person),
            joinedload(Assignment.role),
            joinedload(Assignment.source_reference).joinedload(SourceReference.document),
        )
        if ghar:
            query = query.filter(Assignment.satsang_ghar_id == ghar.id)
        if start_date:
            query = query.filter(Assignment.date >= start_date)
        if end_date:
            query = query.filter(Assignment.date <= end_date)
        if sub_metric:
            query = query.join(Assignment.role).filter(Role.code.ilike(sub_metric))

        records = query.order_by(Assignment.date.asc()).all()
        doc_names = set()
        person_ids = set()
        srs: List[SourceReference] = []
        breakdown_items = []

        for r in records:
            doc_name = None
            if r.source_reference:
                srs.append(r.source_reference)
                if r.source_reference.document:
                    doc_name = r.source_reference.document.original_filename
                    doc_names.add(doc_name)
            if r.person_id:
                person_ids.add(r.person_id)

            breakdown_items.append({
                "date": r.date.isoformat() if r.date else None,
                "satsang_ghar": r.satsang_ghar.name if r.satsang_ghar else None,
                "person": r.person.name if r.person else None,
                "role_code": r.role.code if r.role else None,
                "role_name": r.role.name if r.role else None,
                "description": r.description,
                "document_name": doc_name,
                "source_reference_id": str(r.source_reference_id) if r.source_reference_id else None,
            })

        summary = EntityMetricSummary(
            label=label,
            primary_value=float(len(records)),
            secondary_value=float(len(person_ids)),
            record_count=len(records),
            document_count=len(doc_names),
            document_names=sorted(list(doc_names)),
            breakdown_items=breakdown_items,
        )
        return summary, srs

    # -------------------------------------------------------------------------
    # Shared Utilities
    # -------------------------------------------------------------------------

    def _resolve_ghar(self, name: Optional[str]) -> Optional[SatsangGhar]:
        if not name:
            return None
        norm = name.strip().lower()
        ghars = self.db.query(SatsangGhar).all()
        for g in ghars:
            if g.name.lower() == norm or norm in g.name.lower():
                return g
        return None

    def _check_unreviewed_documents(self, srs: List[SourceReference], warnings: List[str]):
        """Inspects contributing documents for any review flags or unverified states."""
        unreviewed_docs: Set[str] = set()
        for sr in srs:
            if sr and sr.document:
                doc_status = (sr.document.status or "").lower()
                if doc_status in ["needs_review", "pending_validation", "rejected"]:
                    unreviewed_docs.add(sr.document.original_filename)

        if unreviewed_docs:
            doc_list_str = ", ".join(sorted(list(unreviewed_docs)))
            warnings.append(
                f"Comparison includes data from documents with pending validation/review: {doc_list_str}"
            )

    def _format_source_references(self, srs: List[SourceReference]) -> List[SourceReferenceInfo]:
        """Converts ORM SourceReference objects to clean API models, removing duplicates."""
        seen_ids: Set[str] = set()
        res: List[SourceReferenceInfo] = []

        for sr in srs:
            if not sr:
                continue
            sr_id = str(sr.id)
            if sr_id in seen_ids:
                continue
            seen_ids.add(sr_id)

            doc_name = sr.document.original_filename if sr.document else None
            doc_id = str(sr.document_id) if sr.document_id else None
            doc_type = sr.document.document_type if sr.document else None
            v_num = sr.document_version.version_number if sr.document_version else 1

            res.append(
                SourceReferenceInfo(
                    id=sr_id,
                    document_id=doc_id,
                    document_name=doc_name,
                    document_version=v_num,
                    document_type=doc_type,
                    page_number=sr.page_number,
                    sheet_name=sr.sheet_name,
                    row_number=sr.row_number,
                    cell_or_range=sr.cell_or_range,
                    source_text=sr.source_text,
                )
            )
        return res
