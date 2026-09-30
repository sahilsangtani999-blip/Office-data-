"""
API routes for document upload and ingestion (Excel and PDF).
"""

import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import AuthenticatedUserContext, require_permission
from app.database import get_db
from app.models import Document
from app.services.excel_ingestion import (
    SUPPORTED_EXTENSIONS as EXCEL_EXTENSIONS,
    UnsupportedFileFormatError as ExcelFormatError,
    ingest_excel_file,
)
from app.services.pdf_ingestion import (
    SUPPORTED_PDF_EXTENSIONS,
    UnsupportedFileFormatError as PDFFormatError,
    ingest_pdf_file,
)
from app.services.validation_service import get_validation_result

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# Define default upload storage directory
UPLOAD_DIR = Path("d:/office-data-platform/data/uploads")
ALL_SUPPORTED_EXTENSIONS = EXCEL_EXTENSIONS | SUPPORTED_PDF_EXTENSIONS


class DocumentItemResponse(BaseModel):
    id: str
    original_filename: str
    document_type: Optional[str] = None
    status: str
    data_source_name: Optional[str] = None
    created_at: str
    updated_at: str
    version_count: int = 1
    total_records: int = 0
    valid_count: int = 0
    needs_review_count: int = 0
    invalid_count: int = 0
    warnings_count: int = 0
    errors_count: int = 0
    validation_status: str = "pending_validation"


@router.post("/upload", status_code=status.HTTP_200_OK)
async def upload_document(
    file: UploadFile = File(...),
    data_source_name: Optional[str] = Form("Manual Upload"),
    db: Session = Depends(get_db),
    user: AuthenticatedUserContext = Depends(require_permission("upload")),
):
    """
    Upload and ingest an Excel (.xlsx, .xlsm) or PDF (.pdf) document.

    Routes:
    - .xlsx, .xlsm -> Excel ingestion engine
    - .pdf -> PDF ingestion engine (pdfplumber / PyMuPDF)
    """
    filename = file.filename or "unknown_file"
    ext = Path(filename).suffix.lower()

    if ext not in ALL_SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file format '{ext}'. "
                "Supported formats: .xlsx, .xlsm, .pdf."
            ),
        )

    # Ensure upload directory exists
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Store with unique filename to prevent overwrite
    stored_filename = f"{uuid.uuid4()}_{filename}"
    file_path = UPLOAD_DIR / stored_filename

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {exc}",
        )

    try:
        if ext in EXCEL_EXTENSIONS:
            result = ingest_excel_file(
                db=db,
                file_path=file_path,
                original_filename=filename,
                source_type="manual_upload",
                data_source_name=data_source_name or "Manual Upload",
                storage_path=str(file_path),
            )
        elif ext in SUPPORTED_PDF_EXTENSIONS:
            result = ingest_pdf_file(
                db=db,
                file_path=file_path,
                original_filename=filename,
                source_type="manual_upload",
                data_source_name=data_source_name or "Manual Upload",
                storage_path=str(file_path),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format '{ext}'.",
            )
        return result.to_dict()
    except (ExcelFormatError, PDFFormatError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        )


@router.get("", response_model=List[DocumentItemResponse], summary="List uploaded documents")
def list_documents(
    status: Optional[str] = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: AuthenticatedUserContext = Depends(require_permission("read")),
):
    """List uploaded documents with validation summary information."""
    query = db.query(Document)
    if status:
        query = query.filter(Document.status == status)
    docs = query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()

    items = []
    for d in docs:
        val_res = None
        try:
            val_res = get_validation_result(db, d.id)
        except Exception:
            pass

        items.append(
            DocumentItemResponse(
                id=str(d.id),
                original_filename=d.original_filename,
                document_type=d.document_type,
                status=d.status,
                data_source_name=d.data_source.name if d.data_source else None,
                created_at=d.created_at.isoformat() if d.created_at else "",
                updated_at=d.updated_at.isoformat() if d.updated_at else "",
                version_count=len(d.versions) if d.versions else 1,
                total_records=val_res.total_records_examined if val_res else 0,
                valid_count=val_res.valid_count if val_res else 0,
                needs_review_count=val_res.needs_review_count if val_res else 0,
                invalid_count=val_res.invalid_count if val_res else 0,
                warnings_count=val_res.warnings_count if val_res else 0,
                errors_count=val_res.errors_count if val_res else 0,
                validation_status=val_res.validation_status if val_res else (d.status or "pending_validation"),
            )
        )
    return items


@router.get("/{document_id}", response_model=DocumentItemResponse, summary="Get document details")
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUserContext = Depends(require_permission("read")),
):
    """Retrieve details for a single uploaded document."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format for document_id.",
        )

    doc = db.query(Document).filter(Document.id == doc_uuid).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    val_res = None
    try:
        val_res = get_validation_result(db, doc.id)
    except Exception:
        pass

    return DocumentItemResponse(
        id=str(doc.id),
        original_filename=doc.original_filename,
        document_type=doc.document_type,
        status=doc.status,
        data_source_name=doc.data_source.name if doc.data_source else None,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
        updated_at=doc.updated_at.isoformat() if doc.updated_at else "",
        version_count=len(doc.versions) if doc.versions else 1,
        total_records=val_res.total_records_examined if val_res else 0,
        valid_count=val_res.valid_count if val_res else 0,
        needs_review_count=val_res.needs_review_count if val_res else 0,
        invalid_count=val_res.invalid_count if val_res else 0,
        warnings_count=val_res.warnings_count if val_res else 0,
        errors_count=val_res.errors_count if val_res else 0,
        validation_status=val_res.validation_status if val_res else (doc.status or "pending_validation"),
    )
