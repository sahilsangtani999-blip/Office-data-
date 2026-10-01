"""
Core service for Visual Analytics, Trend Trajectories & Executive Dashboard.
Phase 3.2 — RSSB Office Data Platform.
"""

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import func, or_
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
from app.schemas.trends import (
    CenterRanking,
    DashboardKPIs,
    ExecutiveDashboardResponse,
    OperationalAnomaly,
    TrendAnalysisResponse,
    TrendDataPoint,
)


class TrendService:
    """Service providing longitudinal trend computations, dashboard aggregation, and anomaly detection."""

    def __init__(self, db: Session):
        self.db = db

    def _apply_document_lifecycle_filter(self, query, entity_cls):
        """Filters out records belonging to unapproved, pending, or rejected documents."""
        return (
            query.join(entity_cls.source_reference, isouter=True)
            .join(SourceReference.document, isouter=True)
            .filter(
                or_(
                    Document.id == None,
                    Document.status.notin_(["needs_correction", "rejected", "superseded", "pending_review"]),
                )
            )
        )

    # -------------------------------------------------------------------------
    # 1. Trend Trajectory Analytics
    # -------------------------------------------------------------------------

    def get_trends(
        self,
        center: Optional[str] = None,
        metric: str = "attendance",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        interval: str = "month",
    ) -> TrendAnalysisResponse:
        """
        Computes time-series trend trajectory for attendance, vehicles, or assignments.
        """
        ghar_obj = None
        if center and center.strip() and center.lower() not in ["all", "all satsang ghars"]:
            ghar_obj = (
                self.db.query(SatsangGhar)
                .filter(func.lower(SatsangGhar.name) == center.strip().lower())
                .first()
            )

        target_label = ghar_obj.name if ghar_obj else "All Satsang Ghars"

        # Raw observations: list of (date, value, record_count)
        raw_items: List[Tuple[date, float]] = []

        if metric == "attendance":
            q = self.db.query(Attendance.date, Attendance.count_value).filter(
                Attendance.count_value != None, Attendance.date != None
            )
            q = self._apply_document_lifecycle_filter(q, Attendance)
            if ghar_obj:
                q = q.filter(Attendance.satsang_ghar_id == ghar_obj.id)
            if start_date:
                q = q.filter(Attendance.date >= start_date)
            if end_date:
                q = q.filter(Attendance.date <= end_date)
            q = q.order_by(Attendance.date)
            for d, val in q.all():
                raw_items.append((d, float(val)))

        elif metric == "vehicle_wheel":
            q = self.db.query(VehicleWheelData.date, VehicleWheelData.count_value).filter(
                VehicleWheelData.count_value != None, VehicleWheelData.date != None
            )
            q = self._apply_document_lifecycle_filter(q, VehicleWheelData)
            if ghar_obj:
                q = q.filter(VehicleWheelData.satsang_ghar_id == ghar_obj.id)
            if start_date:
                q = q.filter(VehicleWheelData.date >= start_date)
            if end_date:
                q = q.filter(VehicleWheelData.date <= end_date)
            q = q.order_by(VehicleWheelData.date)
            for d, val in q.all():
                raw_items.append((d, float(val)))

        elif metric == "assignment":
            q = self.db.query(Assignment.date, func.count(Assignment.id)).filter(
                Assignment.date != None
            )
            q = self._apply_document_lifecycle_filter(q, Assignment)
            if ghar_obj:
                q = q.filter(Assignment.satsang_ghar_id == ghar_obj.id)
            if start_date:
                q = q.filter(Assignment.date >= start_date)
            if end_date:
                q = q.filter(Assignment.date <= end_date)
            q = q.group_by(Assignment.date).order_by(Assignment.date)
            for d, count_val in q.all():
                raw_items.append((d, float(count_val)))

        if not raw_items:
            return TrendAnalysisResponse(
                metric=metric,
                target_entity=target_label,
                interval=interval,
                data_points=[],
                overall_direction="neutral",
                summary_text=f"No verified operational records found for {target_label} within the specified period.",
            )

        # Bucket by interval (month or day)
        buckets: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"total": 0.0, "count": 0, "date_key": None})

        for d, val in raw_items:
            if interval == "day":
                key = d.strftime("%Y-%m-%d")
                label = d.strftime("%b %d, %Y")
            else:
                key = d.strftime("%Y-%m")
                label = d.strftime("%B %Y")

            buckets[key]["total"] += val
            buckets[key]["count"] += 1
            buckets[key]["label"] = label
            buckets[key]["date_key"] = key

        sorted_keys = sorted(buckets.keys())
        points: List[TrendDataPoint] = []
        values_history: List[float] = []

        for idx, k in enumerate(sorted_keys):
            b = buckets[k]
            # For attendance, represent as average per session in bucket; for assignments/vehicles, total count
            if metric == "attendance":
                point_val = round(b["total"] / b["count"], 1)
            else:
                point_val = round(b["total"], 1)

            values_history.append(point_val)

            # Rolling 3-period simple moving average
            window = values_history[max(0, idx - 2) : idx + 1]
            sma = round(sum(window) / len(window), 1)

            # Period-over-period percentage variance
            pct_change = None
            if idx > 0 and values_history[idx - 1] > 0:
                pct_change = round(((point_val - values_history[idx - 1]) / values_history[idx - 1]) * 100.0, 1)

            points.append(
                TrendDataPoint(
                    period_label=b["label"],
                    date_key=b["date_key"],
                    value=point_val,
                    moving_average=sma,
                    percentage_change=pct_change,
                    record_count=b["count"],
                )
            )

        # Overall trajectory metrics
        peak_pt = max(points, key=lambda p: p.value)
        lowest_pt = min(points, key=lambda p: p.value)

        growth_overall = None
        if len(points) >= 2 and points[0].value > 0:
            growth_overall = round(((points[-1].value - points[0].value) / points[0].value) * 100.0, 1)

        direction = "neutral"
        if growth_overall is not None:
            if growth_overall > 3.0:
                direction = "growth"
            elif growth_overall < -3.0:
                direction = "decline"
            else:
                direction = "stable"

        # Generate summary text
        unit_str = "attendees per meeting" if metric == "attendance" else ("vehicles" if metric == "vehicle_wheel" else "assignments")
        if len(points) == 1:
            summary = f"{target_label} recorded an average of {points[0].value} {unit_str} in {points[0].period_label} across {points[0].record_count} verified records."
        elif growth_overall is not None:
            growth_sign = "+" if growth_overall > 0 else ""
            summary = (
                f"{target_label} {metric} trajectory showed a net {direction} of {growth_sign}{growth_overall}% "
                f"from {points[0].period_label} ({points[0].value} {unit_str}) to {points[-1].period_label} ({points[-1].value} {unit_str}). "
                f"Peak recorded in {peak_pt.period_label} at {peak_pt.value} {unit_str}."
            )
        else:
            summary = f"Recorded {len(points)} periods of {metric} observations for {target_label}."

        return TrendAnalysisResponse(
            metric=metric,
            target_entity=target_label,
            interval=interval,
            data_points=points,
            overall_direction=direction,
            growth_rate_overall=growth_overall,
            peak_period=peak_pt.period_label,
            peak_value=peak_pt.value,
            lowest_period=lowest_pt.period_label,
            lowest_value=lowest_pt.value,
            summary_text=summary,
        )

    # -------------------------------------------------------------------------
    # 2. Executive Dashboard Aggregation
    # -------------------------------------------------------------------------

    def get_executive_dashboard(self) -> ExecutiveDashboardResponse:
        """
        Aggregates system-wide key performance indicators, center rankings, and monthly trend trajectory.
        """
        # Attendance KPIs
        att_q = self.db.query(Attendance).filter(Attendance.count_value != None)
        att_q = self._apply_document_lifecycle_filter(att_q, Attendance)
        att_records = att_q.all()

        total_attendance = sum(a.count_value for a in att_records)
        total_meetings = len(att_records)
        avg_session = round(total_attendance / total_meetings, 1) if total_meetings else 0.0

        # Active Centers count & rankings
        ghar_map: Dict[uuid.UUID, Dict[str, Any]] = defaultdict(lambda: {"total": 0, "count": 0, "name": ""})
        for a in att_records:
            if a.satsang_ghar_id:
                ghar_map[a.satsang_ghar_id]["total"] += a.count_value
                ghar_map[a.satsang_ghar_id]["count"] += 1

        ghars = self.db.query(SatsangGhar).all()
        ghar_names = {g.id: g.name for g in ghars}

        rankings: List[CenterRanking] = []
        for g_id, data in ghar_map.items():
            name = ghar_names.get(g_id, "Unknown Center")
            rankings.append(
                CenterRanking(
                    satsang_ghar=name,
                    total_attendance=data["total"],
                    average_attendance=round(data["total"] / data["count"], 1) if data["count"] else 0.0,
                    sessions=data["count"],
                )
            )
        rankings.sort(key=lambda r: r.total_attendance, reverse=True)

        # Duty Assignments
        asg_q = self.db.query(Assignment)
        asg_q = self._apply_document_lifecycle_filter(asg_q, Assignment)
        assignments = asg_q.options(joinedload(Assignment.role)).all()
        total_assignments = len(assignments)

        unique_sevadars = len({a.person_id for a in assignments if a.person_id})

        role_breakdown: Dict[str, int] = defaultdict(int)
        for a in assignments:
            code = a.role.code if a.role else "General"
            role_breakdown[code] += 1

        # Vehicles
        veh_q = self.db.query(VehicleWheelData).filter(VehicleWheelData.count_value != None)
        veh_q = self._apply_document_lifecycle_filter(veh_q, VehicleWheelData)
        vehicles = veh_q.all()

        total_vehicles = sum(v.count_value for v in vehicles)
        vehicle_breakdown: Dict[str, int] = defaultdict(int)
        for v in vehicles:
            v_type = v.vehicle_type or "Unknown"
            vehicle_breakdown[v_type] += v.count_value

        # Global Monthly Trend
        monthly_trend_resp = self.get_trends(center=None, metric="attendance", interval="month")

        return ExecutiveDashboardResponse(
            summary_kpis=DashboardKPIs(
                total_attendance=total_attendance,
                average_session_attendance=avg_session,
                total_meetings=total_meetings,
                active_centers_count=len(rankings),
                total_duty_assignments=total_assignments,
                unique_sevadars=unique_sevadars,
                total_vehicles_recorded=total_vehicles,
            ),
            center_rankings=rankings,
            vehicle_breakdown=dict(vehicle_breakdown),
            role_breakdown=dict(role_breakdown),
            monthly_trend=monthly_trend_resp.data_points,
        )

    # -------------------------------------------------------------------------
    # 3. Operational Anomaly & Conflict Detection
    # -------------------------------------------------------------------------

    def get_operational_anomalies(self, threshold_pct: float = 35.0) -> List[OperationalAnomaly]:
        """
        Detects statistical anomalies (attendance swings) and operational scheduling overlaps.
        """
        anomalies: List[OperationalAnomaly] = []

        # A. Attendance statistical anomalies
        att_q = self.db.query(Attendance).filter(Attendance.count_value != None, Attendance.date != None)
        att_q = self._apply_document_lifecycle_filter(att_q, Attendance)
        att_records = att_q.options(
            joinedload(Attendance.satsang_ghar),
            joinedload(Attendance.source_reference).joinedload(SourceReference.document),
        ).all()

        # Group by ghar
        by_ghar: Dict[str, List[Attendance]] = defaultdict(list)
        for a in att_records:
            g_name = a.satsang_ghar.name if a.satsang_ghar else "General"
            by_ghar[g_name].append(a)

        for g_name, records in by_ghar.items():
            if len(records) < 2:
                continue
            vals = [r.count_value for r in records]
            mean_val = sum(vals) / len(vals)
            if mean_val <= 0:
                continue

            for r in records:
                diff = r.count_value - mean_val
                pct_diff = (abs(diff) / mean_val) * 100.0

                if pct_diff >= threshold_pct:
                    is_spike = diff > 0
                    severity = "HIGH" if pct_diff >= 60.0 else "MEDIUM"
                    atype = "attendance_spike" if is_spike else "attendance_drop"
                    title = f"Attendance {'Spike' if is_spike else 'Drop'} at {g_name}"
                    desc = (
                        f"Recorded {r.count_value} attendees on {r.date.isoformat()}, which is "
                        f"{'+' if is_spike else '-'}{round(pct_diff, 1)}% from center average ({round(mean_val, 1)})."
                    )

                    sr_dict = None
                    if r.source_reference:
                        sr = r.source_reference
                        sr_dict = {
                            "document_id": str(sr.document_id) if sr.document_id else None,
                            "filename": sr.document.original_filename if sr.document else None,
                            "sheet_name": sr.sheet_name,
                            "row_number": sr.row_number,
                            "cell_or_range": sr.cell_or_range,
                        }

                    anomalies.append(
                        OperationalAnomaly(
                            anomaly_type=atype,
                            severity=severity,
                            title=title,
                            description=desc,
                            date=r.date.isoformat(),
                            entity=g_name,
                            metric_value=float(r.count_value),
                            baseline_value=round(mean_val, 1),
                            source_reference=sr_dict,
                        )
                    )

        # B. Cross-document duty scheduling overlaps
        asg_q = self.db.query(Assignment).filter(Assignment.date != None, Assignment.person_id != None)
        asg_q = self._apply_document_lifecycle_filter(asg_q, Assignment)
        assignments = asg_q.options(
            joinedload(Assignment.person),
            joinedload(Assignment.satsang_ghar),
            joinedload(Assignment.source_reference).joinedload(SourceReference.document),
        ).all()

        # Group by (person_id, date)
        person_dates: Dict[Tuple[uuid.UUID, date], List[Assignment]] = defaultdict(list)
        for asg in assignments:
            person_dates[(asg.person_id, asg.date)].append(asg)

        for (p_id, d), asg_list in person_dates.items():
            ghars_assigned = {a.satsang_ghar.name for a in asg_list if a.satsang_ghar}
            if len(ghars_assigned) > 1:
                p_name = asg_list[0].person.name if asg_list[0].person else "Unknown Sevadar"
                ghar_names_str = " and ".join(sorted(ghars_assigned))
                anomalies.append(
                    OperationalAnomaly(
                        anomaly_type="schedule_conflict",
                        severity="HIGH",
                        title=f"Dual Duty Assignment Conflict: {p_name}",
                        description=f"Sevadar '{p_name}' has scheduled sewa assignments across multiple locations ({ghar_names_str}) on {d.isoformat()}.",
                        date=d.isoformat(),
                        entity=p_name,
                    )
                )

        return anomalies
