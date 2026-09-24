"""
API routes for document upload and ingestion (Excel and PDF).
"""

import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
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

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# Define default upload storage directory
UPLOAD_DIR = Path("d:/office-data-platform/data/uploads")
ALL_SUPPORTED_EXTENSIONS = EXCEL_EXTENSIONS | SUPPORTED_PDF_EXTENSIONS


@router.post("/upload", status_code=status.HTTP_200_OK)
async def upload_document(
    file: UploadFile = File(...),
    data_source_name: Optional[str] = Form("Manual Upload"),
    db: Session = Depends(get_db),
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
