"""
Reports & Data Export API Endpoints.
Phase 3.1 — RSSB Office Data Platform.
"""

import os
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_permission
from app.core.permissions import PERM_ADMIN, PERM_GENERATE_REPORTS, PERM_READ
from app.database import get_db
from app.models import Report, User
from app.schemas.reports import (
    ReportCreateRequest,
    ReportDetailResponse,
    ReportItemResponse,
    ReportListResponse,
)
from app.services.report_service import ReportService

router = APIRouter()


@router.post(
    "/generate",
    response_model=ReportDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate an official office report",
)
def generate_report(
    payload: ReportCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_GENERATE_REPORTS)),
):
    """
    Generates a structured office report (Monthly, Attendance, Duty, or Vehicle),
    persists the metadata record to the PostgreSQL `reports` table, and compiles
    both Excel (.xlsx) and CSV (.csv) exports on disk in `data/exports/`.

    Requires: `generate_reports` permission (roles: `admin`, `reviewer`).
    """
    service = ReportService(db)
    try:
        report, result = service.generate_report(payload, created_by=current_user.username)
        return ReportDetailResponse(
            id=str(report.id),
            name=report.name,
            report_type=report.report_type,
            reporting_period_start=report.reporting_period_start,
            reporting_period_end=report.reporting_period_end,
            status=report.status,
            created_by=report.created_by,
            created_at=report.created_at,
            updated_at=report.updated_at,
            summary_metrics=result["summary_metrics"],
            summary_kpis=result["summary_metrics"],
            data=result["data"],
            export_files=result["export_files"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate report: {str(e)}",
        )


@router.get(
    "",
    response_model=ReportListResponse,
    summary="List registered office reports",
)
def list_reports(
    report_type: Optional[str] = Query(None, description="Filter by report_type"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_READ)),
):
    """
    Lists registered reports ordered by creation date descending.
    Requires: `read` permission (all authenticated users).
    """
    service = ReportService(db)
    reports, total = service.list_reports(
        report_type=report_type, status=status_filter, limit=limit, offset=offset
    )

    items = [
        ReportItemResponse(
            id=str(r.id),
            name=r.name,
            report_type=r.report_type,
            reporting_period_start=r.reporting_period_start,
            reporting_period_end=r.reporting_period_end,
            status=r.status,
            created_by=r.created_by,
            created_at=r.created_at,
            updated_at=r.updated_at,
            export_formats=["xlsx", "csv"],
        )
        for r in reports
    ]

    return ReportListResponse(reports=items, total=total)


@router.get(
    "/{report_id}",
    response_model=ReportDetailResponse,
    summary="Get report details and KPIs",
)
def get_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_READ)),
):
    """
    Retrieves full metrics and dataset details for a specific report.
    Requires: `read` permission (all authenticated users).
    """
    service = ReportService(db)
    report = service.get_report_by_id(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with id '{report_id}' not found.",
        )

    # Re-collect summary KPIs for detailed response
    attendance_data = service._collect_attendance_data(
        report.reporting_period_start, report.reporting_period_end, None
    )
    assignment_data = service._collect_assignment_data(
        report.reporting_period_start, report.reporting_period_end, None
    )
    vehicle_data = service._collect_vehicle_data(
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
        "period_label": service._format_period_label(
            report.reporting_period_start, report.reporting_period_end
        ),
    }

    safe_name = service._sanitize_filename(report.name)
    return ReportDetailResponse(
        id=str(report.id),
        name=report.name,
        report_type=report.report_type,
        reporting_period_start=report.reporting_period_start,
        reporting_period_end=report.reporting_period_end,
        status=report.status,
        created_by=report.created_by,
        created_at=report.created_at,
        updated_at=report.updated_at,
        summary_metrics=summary_metrics,
        summary_kpis=summary_metrics,
        data={
            "attendance": attendance_data,
            "assignments": assignment_data,
            "vehicles": vehicle_data,
        },
        export_files={
            "xlsx": f"{report.id}_{safe_name}.xlsx",
            "csv": f"{report.id}_{safe_name}.csv",
        },
    )


@router.get(
    "/{report_id}/download",
    summary="Download exported report file (Excel or CSV)",
)
def download_report(
    report_id: uuid.UUID,
    format: str = Query("xlsx", regex="^(xlsx|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_READ)),
):
    """
    Downloads the pre-generated Excel (.xlsx) or CSV (.csv) file for a report.
    Requires: `read` permission (all authenticated users).
    """
    service = ReportService(db)
    report = service.get_report_by_id(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with id '{report_id}' not found.",
        )

    file_path = service.get_report_export_path(report, format_type=format)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export file for report '{report_id}' could not be located.",
        )

    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if format.lower() == "xlsx"
        else "text/csv"
    )
    safe_name = service._sanitize_filename(report.name)
    download_filename = f"{safe_name}.{format.lower()}"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=download_filename,
    )


@router.delete(
    "/{report_id}",
    summary="Delete a report",
)
def delete_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_ADMIN)),
):
    """
    Deletes a report and associated export files.
    Requires: `admin` permission.
    """
    service = ReportService(db)
    success = service.delete_report(report_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with id '{report_id}' not found.",
        )
    return {"deleted": True, "id": str(report_id)}
