"""
Report generation, aggregation, and export engine.
Phase 3.1 — RSSB Office Data Platform.
"""

import calendar
import csv
from datetime import date, datetime
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    Attendance,
    Document,
    Person,
    Report,
    Role,
    SatsangGhar,
    SourceReference,
    VehicleWheelData,
)
from app.schemas.reports import ReportCreateRequest

EXPORTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "exports")
)


class ReportService:
    """Service handling report calculation, PostgreSQL persistence, and Excel/CSV exporting."""

    def __init__(self, db: Session):
        self.db = db
        os.makedirs(EXPORTS_DIR, exist_ok=True)

    # -------------------------------------------------------------------------
    # Public API Methods
    # -------------------------------------------------------------------------

    def generate_report(
        self, request: ReportCreateRequest, created_by: str = "system"
    ) -> Tuple[Report, Dict[str, Any]]:
        """
        Calculates report data from verified records, saves Report entry to database,
        and produces exported .xlsx and .csv files in data/exports/.
        """
        start_date, end_date = self._resolve_period(request)
        ghar = self._resolve_ghar(request.satsang_ghar)

        # 1. Collect aggregated datasets
        attendance_data = self._collect_attendance_data(start_date, end_date, ghar)
        assignment_data = self._collect_assignment_data(start_date, end_date, ghar)
        vehicle_data = self._collect_vehicle_data(start_date, end_date, ghar)

        # 2. Determine report name
        report_name = request.name or self._build_default_report_name(
            request.report_type, start_date, end_date, ghar
        )

        # 3. Create Report model in database
        report = Report(
            id=uuid.uuid4(),
            name=report_name,
            report_type=request.report_type,
            reporting_period_start=start_date,
            reporting_period_end=end_date,
            status="final",
            created_by=created_by,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)

        # 4. Assemble summary KPIs and full payload
        summary_metrics = {
            "total_attendance": attendance_data["total_attendance"],
            "attendance_meetings": attendance_data["total_records"],
            "average_attendance": attendance_data["average_attendance"],
            "avg_attendance": attendance_data["average_attendance"],
            "total_duties_assigned": assignment_data["total_records"],
            "total_duty_assignments": assignment_data["total_records"],
            "unique_duty_holders": len(assignment_data["by_person"]),
            "total_vehicles_recorded": vehicle_data["total_count"],
            "total_vehicles": vehicle_data["total_count"],
            "location_scope": ghar.name if ghar else "All Satsang Ghars",
            "period_label": self._format_period_label(start_date, end_date),
        }

        full_data = {
            "attendance": attendance_data,
            "assignments": assignment_data,
            "vehicles": vehicle_data,
        }

        # 5. Generate physical export files (.xlsx and .csv)
        xlsx_path, csv_path = self._generate_export_files(
            report=report,
            summary_metrics=summary_metrics,
            data=full_data,
        )

        export_files = {
            "xlsx": os.path.basename(xlsx_path),
            "csv": os.path.basename(csv_path),
        }

        return report, {
            "summary_metrics": summary_metrics,
            "data": full_data,
            "export_files": export_files,
        }

    def list_reports(
        self,
        report_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Report], int]:
        """Lists registered reports ordered by created_at descending."""
        query = self.db.query(Report)
        if report_type:
            query = query.filter(Report.report_type == report_type)
        if status:
            query = query.filter(Report.status == status)

        total = query.count()
        reports = query.order_by(desc(Report.created_at)).offset(offset).limit(limit).all()
        return reports, total

    def get_report_by_id(self, report_id: uuid.UUID) -> Optional[Report]:
        """Fetches single report by UUID."""
        return self.db.query(Report).filter(Report.id == report_id).first()

    def get_report_export_path(
        self, report: Report, format_type: str = "xlsx"
    ) -> Optional[str]:
        """
        Locates the physical exported file for a report, or regenerates it
        if missing from disk.
        """
        safe_name = self._sanitize_filename(report.name)
        ext = "xlsx" if format_type.lower() == "xlsx" else "csv"
        expected_filename = f"{report.id}_{safe_name}.{ext}"
        expected_path = os.path.join(EXPORTS_DIR, expected_filename)

        if os.path.exists(expected_path):
            return expected_path

        # If file was removed or missing, regenerate on demand
        self._regenerate_export_file(report)
        return expected_path if os.path.exists(expected_path) else None

    def delete_report(self, report_id: uuid.UUID) -> bool:
        """Deletes a report from PostgreSQL and purges associated disk export files."""
        report = self.get_report_by_id(report_id)
        if not report:
            return False

        # Remove disk files
        safe_name = self._sanitize_filename(report.name)
        for ext in ["xlsx", "csv"]:
            p = os.path.join(EXPORTS_DIR, f"{report.id}_{safe_name}.{ext}")
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

        self.db.delete(report)
        self.db.commit()
        return True

    # -------------------------------------------------------------------------
    # Data Collection & Aggregation Helpers
    # -------------------------------------------------------------------------

    def _collect_attendance_data(
        self, start_date: Optional[date], end_date: Optional[date], ghar: Optional[SatsangGhar]
    ) -> Dict[str, Any]:
        """Queries and summarizes attendance records."""
        query = (
            self.db.query(Attendance)
            .join(Attendance.source_reference, isouter=True)
            .join(SourceReference.document, isouter=True)
            .filter(
                or_(
                    Document.id == None,
                    Document.status.notin_(["needs_correction", "rejected", "superseded", "pending_review"]),
                )
            )
        )
        if start_date:
            query = query.filter(Attendance.date >= start_date)
        if end_date:
            query = query.filter(Attendance.date <= end_date)
        if ghar:
            query = query.filter(Attendance.satsang_ghar_id == ghar.id)

        records = query.order_by(Attendance.date.asc()).all()
        counts = [r.count_value for r in records if r.count_value is not None]
        total_att = sum(counts)
        avg_att = round(total_att / len(counts), 2) if counts else 0.0
        min_att = min(counts) if counts else 0
        max_att = max(counts) if counts else 0

        by_ghar: Dict[str, Dict[str, Any]] = {}
        rows = []
        for r in records:
            g_name = r.satsang_ghar.name if r.satsang_ghar else "Unknown"
            if g_name not in by_ghar:
                by_ghar[g_name] = {"total": 0, "count": 0, "average": 0.0}
            val = r.count_value or 0
            by_ghar[g_name]["total"] += val
            by_ghar[g_name]["count"] += 1

            rows.append({
                "date": r.date.isoformat() if r.date else "",
                "satsang_ghar": g_name,
                "count_value": r.count_value,
                "raw_value": r.raw_value or "",
            })

        for g in by_ghar:
            cnt = by_ghar[g]["count"]
            tot = by_ghar[g]["total"]
            by_ghar[g]["average"] = round(tot / cnt, 2) if cnt > 0 else 0.0

        return {
            "total_records": len(records),
            "total_attendance": total_att,
            "average_attendance": avg_att,
            "min_attendance": min_att,
            "max_attendance": max_att,
            "by_ghar": by_ghar,
            "records": rows,
        }

    def _collect_assignment_data(
        self, start_date: Optional[date], end_date: Optional[date], ghar: Optional[SatsangGhar]
    ) -> Dict[str, Any]:
        """Queries and summarizes duty assignment records."""
        query = (
            self.db.query(Assignment)
            .join(Assignment.source_reference, isouter=True)
            .join(SourceReference.document, isouter=True)
            .filter(
                or_(
                    Document.id == None,
                    Document.status.notin_(["needs_correction", "rejected", "superseded", "pending_review"]),
                )
            )
        )
        if start_date:
            query = query.filter(Assignment.date >= start_date)
        if end_date:
            query = query.filter(Assignment.date <= end_date)
        if ghar:
            query = query.filter(Assignment.satsang_ghar_id == ghar.id)

        records = query.order_by(Assignment.date.asc()).all()

        by_role: Dict[str, int] = {}
        by_person: Dict[str, int] = {}
        rows = []

        for r in records:
            g_name = r.satsang_ghar.name if r.satsang_ghar else "Unknown"
            p_name = r.person.name if r.person else "Unknown"
            r_name = r.role.name if r.role else "Unknown"

            by_role[r_name] = by_role.get(r_name, 0) + 1
            by_person[p_name] = by_person.get(p_name, 0) + 1

            rows.append({
                "date": r.date.isoformat() if r.date else "",
                "satsang_ghar": g_name,
                "person": p_name,
                "role": r_name,
                "notes": r.description or "",
            })

        return {
            "total_records": len(records),
            "by_role": by_role,
            "by_person": by_person,
            "records": rows,
        }

    def _collect_vehicle_data(
        self, start_date: Optional[date], end_date: Optional[date], ghar: Optional[SatsangGhar]
    ) -> Dict[str, Any]:
        """Queries and summarizes vehicle/wheel data records."""
        query = (
            self.db.query(VehicleWheelData)
            .join(VehicleWheelData.source_reference, isouter=True)
            .join(SourceReference.document, isouter=True)
            .filter(
                or_(
                    Document.id == None,
                    Document.status.notin_(["needs_correction", "rejected", "superseded", "pending_review"]),
                )
            )
        )
        if start_date:
            query = query.filter(VehicleWheelData.date >= start_date)
        if end_date:
            query = query.filter(VehicleWheelData.date <= end_date)
        if ghar:
            query = query.filter(VehicleWheelData.satsang_ghar_id == ghar.id)

        records = query.order_by(VehicleWheelData.date.asc()).all()

        by_type: Dict[str, int] = {}
        total_count = 0
        rows = []

        for r in records:
            g_name = r.satsang_ghar.name if r.satsang_ghar else "Unknown"
            v_type = r.vehicle_type or "General"
            cnt = r.count_value or 0
            total_count += cnt
            by_type[v_type] = by_type.get(v_type, 0) + cnt

            rows.append({
                "date": r.date.isoformat() if r.date else "",
                "satsang_ghar": g_name,
                "vehicle_type": v_type,
                "count_value": r.count_value,
                "raw_value": r.raw_value or "",
            })

        return {
            "total_records": len(records),
            "total_count": total_count,
            "by_type": by_type,
            "records": rows,
        }

    # -------------------------------------------------------------------------
    # File Export Engine (Excel & CSV)
    # -------------------------------------------------------------------------

    def _generate_export_files(
        self,
        report: Report,
        summary_metrics: Dict[str, Any],
        data: Dict[str, Any],
    ) -> Tuple[str, str]:
        """Builds formatted Excel (.xlsx) and CSV (.csv) report files on disk."""
        safe_name = self._sanitize_filename(report.name)
        xlsx_filename = f"{report.id}_{safe_name}.xlsx"
        csv_filename = f"{report.id}_{safe_name}.csv"

        xlsx_path = os.path.join(EXPORTS_DIR, xlsx_filename)
        csv_path = os.path.join(EXPORTS_DIR, csv_filename)

        # 1. Build Excel Workbook
        wb = openpyxl.Workbook()
        # Remove default sheet
        wb.remove(wb.active)

        maroon_header_fill = PatternFill(start_color="941B1B", end_color="941B1B", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        title_font = Font(name="Calibri", size=16, bold=True, color="941B1B")
        sub_font = Font(name="Calibri", size=11, bold=True, color="444444")
        bold_font = Font(name="Calibri", size=11, bold=True)
        regular_font = Font(name="Calibri", size=11)
        border_thin = Border(
            left=Side(style="thin", color="E5E2DE"),
            right=Side(style="thin", color="E5E2DE"),
            top=Side(style="thin", color="E5E2DE"),
            bottom=Side(style="thin", color="E5E2DE"),
        )
        zebra_fill = PatternFill(start_color="FAF9F6", end_color="FAF9F6", fill_type="solid")

        # --- Sheet 1: Summary ---
        ws_sum = wb.create_sheet(title="Summary")
        ws_sum.views.sheetView[0].showGridLines = True

        ws_sum.cell(row=2, column=2, value="RSSB Office Data Platform").font = title_font
        ws_sum.cell(row=3, column=2, value=report.name).font = sub_font
        ws_sum.cell(
            row=4,
            column=2,
            value=f"Reporting Period: {summary_metrics['period_label']}  |  Location: {summary_metrics['location_scope']}  |  Status: {report.status.upper()}",
        ).font = regular_font
        ws_sum.cell(
            row=5,
            column=2,
            value=f"Generated By: {report.created_by or 'System'}  |  Generated On: {report.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
        ).font = regular_font

        # Key Metrics Table
        ws_sum.cell(row=7, column=2, value="Executive KPI Summary").font = sub_font
        ws_sum.cell(row=8, column=2, value="Metric").font = header_font
        ws_sum.cell(row=8, column=2).fill = maroon_header_fill
        ws_sum.cell(row=8, column=3, value="Value").font = header_font
        ws_sum.cell(row=8, column=3).fill = maroon_header_fill

        kpis = [
            ("Total Attendance Recorded", summary_metrics["total_attendance"]),
            ("Total Meetings / Sessions", summary_metrics["attendance_meetings"]),
            ("Average Attendance per Meeting", summary_metrics["average_attendance"]),
            ("Total Duty Assignments", summary_metrics["total_duties_assigned"]),
            ("Unique Sevadars Assigned", summary_metrics["unique_duty_holders"]),
            ("Total Vehicles Recorded", summary_metrics["total_vehicles_recorded"]),
        ]

        curr_row = 9
        for label, val in kpis:
            c1 = ws_sum.cell(row=curr_row, column=2, value=label)
            c2 = ws_sum.cell(row=curr_row, column=3, value=val)
            c1.font = regular_font
            c2.font = bold_font
            c1.border = border_thin
            c2.border = border_thin
            if curr_row % 2 == 1:
                c1.fill = zebra_fill
                c2.fill = zebra_fill
            curr_row += 1

        # Attendance by Ghar Table (if multiple ghars)
        ghar_breakdown = data.get("attendance", {}).get("by_ghar", {})
        if ghar_breakdown:
            curr_row += 2
            ws_sum.cell(row=curr_row, column=2, value="Attendance Breakdown by Satsang Ghar").font = sub_font
            curr_row += 1
            headers = ["Satsang Ghar", "Total Attendance", "Meetings", "Average"]
            for col_idx, h in enumerate(headers, start=2):
                c = ws_sum.cell(row=curr_row, column=col_idx, value=h)
                c.font = header_font
                c.fill = maroon_header_fill
                c.border = border_thin
            curr_row += 1

            for g_name, g_stats in sorted(ghar_breakdown.items()):
                vals = [g_name, g_stats["total"], g_stats["count"], g_stats["average"]]
                for col_idx, val in enumerate(vals, start=2):
                    c = ws_sum.cell(row=curr_row, column=col_idx, value=val)
                    c.font = regular_font
                    c.border = border_thin
                    if curr_row % 2 == 1:
                        c.fill = zebra_fill
                curr_row += 1

        # Duty Breakdown Table
        role_breakdown = data.get("assignments", {}).get("by_role", {})
        if role_breakdown:
            curr_row += 2
            ws_sum.cell(row=curr_row, column=2, value="Duty Assignments by Role").font = sub_font
            curr_row += 1
            headers = ["Role / Duty", "Count Assigned"]
            for col_idx, h in enumerate(headers, start=2):
                c = ws_sum.cell(row=curr_row, column=col_idx, value=h)
                c.font = header_font
                c.fill = maroon_header_fill
                c.border = border_thin
            curr_row += 1

            for r_name, r_cnt in sorted(role_breakdown.items()):
                vals = [r_name, r_cnt]
                for col_idx, val in enumerate(vals, start=2):
                    c = ws_sum.cell(row=curr_row, column=col_idx, value=val)
                    c.font = regular_font
                    c.border = border_thin
                    if curr_row % 2 == 1:
                        c.fill = zebra_fill
                curr_row += 1

        self._auto_size_columns(ws_sum)

        # --- Sheet 2: Attendance Records ---
        att_rows = data.get("attendance", {}).get("records", [])
        ws_att = wb.create_sheet(title="Attendance")
        ws_att.views.sheetView[0].showGridLines = True
        att_headers = ["Date", "Satsang Ghar", "Attendance Count", "Raw Notes"]
        for idx, h in enumerate(att_headers, start=1):
            c = ws_att.cell(row=1, column=idx, value=h)
            c.font = header_font
            c.fill = maroon_header_fill
            c.border = border_thin

        for r_idx, row in enumerate(att_rows, start=2):
            for c_idx, val in enumerate([row["date"], row["satsang_ghar"], row["count_value"], row["raw_value"]], start=1):
                c = ws_att.cell(row=r_idx, column=c_idx, value=val)
                c.font = regular_font
                c.border = border_thin
                if r_idx % 2 == 1:
                    c.fill = zebra_fill
        self._auto_size_columns(ws_att)

        # --- Sheet 3: Duty Assignments ---
        assign_rows = data.get("assignments", {}).get("records", [])
        ws_asgn = wb.create_sheet(title="Duty Assignments")
        ws_asgn.views.sheetView[0].showGridLines = True
        asgn_headers = ["Date", "Satsang Ghar", "Person / Sevadar", "Role / Duty", "Notes"]
        for idx, h in enumerate(asgn_headers, start=1):
            c = ws_asgn.cell(row=1, column=idx, value=h)
            c.font = header_font
            c.fill = maroon_header_fill
            c.border = border_thin

        for r_idx, row in enumerate(assign_rows, start=2):
            for c_idx, val in enumerate([row["date"], row["satsang_ghar"], row["person"], row["role"], row["notes"]], start=1):
                c = ws_asgn.cell(row=r_idx, column=c_idx, value=val)
                c.font = regular_font
                c.border = border_thin
                if r_idx % 2 == 1:
                    c.fill = zebra_fill
        self._auto_size_columns(ws_asgn)

        # --- Sheet 4: Vehicles ---
        veh_rows = data.get("vehicles", {}).get("records", [])
        ws_veh = wb.create_sheet(title="Vehicles")
        ws_veh.views.sheetView[0].showGridLines = True
        veh_headers = ["Date", "Satsang Ghar", "Vehicle Type", "Count", "Raw Notes"]
        for idx, h in enumerate(veh_headers, start=1):
            c = ws_veh.cell(row=1, column=idx, value=h)
            c.font = header_font
            c.fill = maroon_header_fill
            c.border = border_thin

        for r_idx, row in enumerate(veh_rows, start=2):
            for c_idx, val in enumerate([row["date"], row["satsang_ghar"], row["vehicle_type"], row["count_value"], row["raw_value"]], start=1):
                c = ws_veh.cell(row=r_idx, column=c_idx, value=val)
                c.font = regular_font
                c.border = border_thin
                if r_idx % 2 == 1:
                    c.fill = zebra_fill
        self._auto_size_columns(ws_veh)

        wb.save(xlsx_path)

        # 2. Build CSV File
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["# RSSB Office Data Platform - Official Report"])
            writer.writerow(["Report Name", report.name])
            writer.writerow(["Report Type", report.report_type])
            writer.writerow(["Reporting Period", summary_metrics["period_label"]])
            writer.writerow(["Location", summary_metrics["location_scope"]])
            writer.writerow(["Generated At", report.created_at.strftime("%Y-%m-%d %H:%M:%S")])
            writer.writerow(["Generated By", report.created_by or "System"])
            writer.writerow([])
            writer.writerow(["--- KPI SUMMARY ---"])
            for label, val in kpis:
                writer.writerow([label, val])
            writer.writerow([])
            writer.writerow(["--- ATTENDANCE RECORDS ---"])
            writer.writerow(["Date", "Satsang Ghar", "Attendance Count", "Raw Notes"])
            for r in att_rows:
                writer.writerow([r["date"], r["satsang_ghar"], r["count_value"], r["raw_value"]])
            writer.writerow([])
            writer.writerow(["--- DUTY ASSIGNMENTS ---"])
            writer.writerow(["Date", "Satsang Ghar", "Person", "Role", "Notes"])
            for r in assign_rows:
                writer.writerow([r["date"], r["satsang_ghar"], r["person"], r["role"], r["notes"]])
            writer.writerow([])
            writer.writerow(["--- VEHICLE COUNTS ---"])
            writer.writerow(["Date", "Satsang Ghar", "Vehicle Type", "Count", "Raw Notes"])
            for r in veh_rows:
                writer.writerow([r["date"], r["satsang_ghar"], r["vehicle_type"], r["count_value"], r["raw_value"]])

        return xlsx_path, csv_path

    def _regenerate_export_file(self, report: Report) -> None:
        """Regenerates the export files for an existing Report record."""
        req = ReportCreateRequest(
            name=report.name,
            report_type=report.report_type,
            start_date=report.reporting_period_start,
            end_date=report.reporting_period_end,
        )
        attendance_data = self._collect_attendance_data(
            report.reporting_period_start, report.reporting_period_end, None
        )
        assignment_data = self._collect_assignment_data(
            report.reporting_period_start, report.reporting_period_end, None
        )
        vehicle_data = self._collect_vehicle_data(
            report.reporting_period_start, report.reporting_period_end, None
        )
        summary_metrics = {
            "total_attendance": attendance_data["total_attendance"],
            "attendance_meetings": attendance_data["total_records"],
            "average_attendance": attendance_data["average_attendance"],
            "total_duties_assigned": assignment_data["total_records"],
            "unique_duty_holders": len(assignment_data["by_person"]),
            "total_vehicles_recorded": vehicle_data["total_count"],
            "location_scope": "All Satsang Ghars",
            "period_label": self._format_period_label(
                report.reporting_period_start, report.reporting_period_end
            ),
        }
        self._generate_export_files(
            report=report,
            summary_metrics=summary_metrics,
            data={
                "attendance": attendance_data,
                "assignments": assignment_data,
                "vehicles": vehicle_data,
            },
        )

    # -------------------------------------------------------------------------
    # Utility Helpers
    # -------------------------------------------------------------------------

    def _resolve_period(self, req: ReportCreateRequest) -> Tuple[Optional[date], Optional[date]]:
        """Determines start and end dates from user request."""
        start = req.reporting_period_start or req.start_date
        end = req.reporting_period_end or req.end_date
        if start and end:
            return start, end

        if req.month and req.year:
            last_day = calendar.monthrange(req.year, req.month)[1]
            return date(req.year, req.month, 1), date(req.year, req.month, last_day)

        if req.year and not req.month:
            return date(req.year, 1, 1), date(req.year, 12, 31)

        # Fallback: check database records for min and max dates
        min_date = self.db.query(func.min(Attendance.date)).scalar()
        max_date = self.db.query(func.max(Attendance.date)).scalar()
        if min_date and max_date:
            return min_date, max_date

        # Default fallback to current month
        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        return date(today.year, today.month, 1), date(today.year, today.month, last_day)

    def _resolve_ghar(self, ghar_name: Optional[str]) -> Optional[SatsangGhar]:
        """Resolves Satsang Ghar entity if specified."""
        if not ghar_name:
            return None
        clean = ghar_name.strip()
        return (
            self.db.query(SatsangGhar)
            .filter(func.lower(SatsangGhar.name) == clean.lower())
            .first()
        )

    def _build_default_report_name(
        self,
        report_type: str,
        start_date: Optional[date],
        end_date: Optional[date],
        ghar: Optional[SatsangGhar],
    ) -> str:
        """Constructs clear institutional title."""
        type_labels = {
            "monthly": "Monthly Report",
            "attendance_summary": "Attendance Summary Report",
            "duty_summary": "Duty Assignments Report",
            "vehicle_report": "Vehicle & Wheel Report",
        }
        type_str = type_labels.get(report_type, "Office Data Report")
        period_str = self._format_period_label(start_date, end_date)
        loc_str = f" - {ghar.name}" if ghar else ""
        return f"{type_str}{loc_str} ({period_str})"

    def _format_period_label(
        self, start_date: Optional[date], end_date: Optional[date]
    ) -> str:
        """Returns human-readable period label."""
        if not start_date and not end_date:
            return "All Available Dates"
        if start_date and end_date:
            if start_date.year == end_date.year and start_date.month == end_date.month:
                return start_date.strftime("%B %Y")
            return f"{start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}"
        if start_date:
            return f"From {start_date.strftime('%d %b %Y')}"
        return f"Until {end_date.strftime('%d %b %Y')}"

    def _sanitize_filename(self, name: str) -> str:
        """Sanitizes report name for cross-platform safe file paths."""
        cleaned = re.sub(r"[^\w\s-]", "", name).strip()
        cleaned = re.sub(r"[-\s]+", "_", cleaned)
        return cleaned[:60] or "report"

    def _auto_size_columns(self, ws) -> None:
        """Adjusts column widths based on content."""
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = cell.value
                if val:
                    max_len = max(max_len, len(str(val)))
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
