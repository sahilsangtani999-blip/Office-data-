"""
PDF Data Ingestion Service for RSSB Office Data Platform.

Provides:
- Secure reading of text-based, multi-page, and tabular PDFs using pdfplumber and PyMuPDF
- SHA-256 content hashing and duplicate prevention
- Page-level text extraction with SourceReference preservation for future preview
- Table detection and extraction with real bounding box coordinates (bbox)
- Controlled mapping to Attendance, Assignment, Vehicle entities
- Strict "Needs Review" flagging for ambiguous tables or unknown headers
- Raw value preservation without guessing field meanings
"""

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pdfplumber
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    Attendance,
    DataSource,
    Document,
    DocumentVersion,
    Person,
    Role,
    SatsangGhar,
    SourceReference,
    VehicleWheelData,
)

SUPPORTED_PDF_EXTENSIONS = {".pdf"}


class UnsupportedFileFormatError(ValueError):
    """Raised when an uploaded file is not a supported PDF."""
    pass


@dataclass
class PDFIngestionResult:
    """Structured report returned after processing a PDF file."""
    document_id: Optional[str]
    version_id: Optional[str]
    filename: str
    content_hash: str
    page_count: int = 0
    pages_processed: int = 0
    tables_detected: int = 0
    structured_records_created: int = 0
    records_needing_review: int = 0
    review_items: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duplicate_status: str = "new"  # "new" or "duplicate"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculate_sha256(file_path: Union[str, Path]) -> str:
    """Compute the SHA-256 hex digest of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _normalize_header(header: Any) -> str:
    """Normalize a column header string for controlled concept matching."""
    if header is None:
        return ""
    text = str(header).strip().lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(val: Any) -> Optional[date]:
    """Parse a date value from text/table cell."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val

    val_str = str(val).strip()
    if not val_str:
        return None

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            pass
    return None


def _parse_int(val: Any) -> Optional[int]:
    """Parse an integer count from a table cell."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return int(val)
        except (ValueError, OverflowError):
            return None

    val_str = str(val).strip().replace(",", "")
    try:
        return int(float(val_str))
    except (ValueError, TypeError):
        return None


def _classify_table_headers(headers: List[str]) -> Tuple[Optional[str], Dict[str, int]]:
    """
    Controlled classifier for PDF table headers.
    Distinguishes Attendance, Assignment, Vehicle concepts.
    Returns (concept_type, column_map).
    """
    col_map: Dict[str, int] = {}
    for idx, h in enumerate(headers):
        if any(w in h for w in ("date", "tarikh", "day")):
            col_map.setdefault("date", idx)
        if any(w in h for w in ("satsang ghar", "ghar", "center", "location", "place")):
            col_map.setdefault("ghar", idx)

        is_vehicle = any(w in h for w in ("vehicle", "wheel", "2 wheeler", "4 wheeler", "car", "scooter", "bike"))
        if is_vehicle:
            col_map.setdefault("vehicle", idx)

        is_attendance = any(w in h for w in ("attendance", "headcount", "sangat", "present", "total attendance")) or ("count" in h and not is_vehicle)
        if is_attendance:
            col_map.setdefault("attendance", idx)

        if any(w in h for w in ("karta", "speaker", "sk", "reader", "sr", "person", "naam", "name", "duty", "sewadar")):
            col_map.setdefault("person", idx)
        if any(w in h for w in ("role", "duty type", "sewa")):
            col_map.setdefault("role", idx)

    # 1. Vehicle
    if "date" in col_map and "vehicle" in col_map:
        return "vehicle", col_map

    # 2. Attendance
    if "date" in col_map and "ghar" in col_map and "attendance" in col_map:
        return "attendance", col_map

    # 3. Assignment
    if "date" in col_map and "ghar" in col_map and ("person" in col_map or "role" in col_map):
        return "assignment", col_map

    return None, {}


def _get_or_create_ghar(db: Session, name: str) -> SatsangGhar:
    clean_name = name.strip()
    stmt = select(SatsangGhar).where(SatsangGhar.name == clean_name)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing:
        return existing
    new_ghar = SatsangGhar(name=clean_name, status="active")
    db.add(new_ghar)
    db.flush()
    return new_ghar


def _get_or_create_person(db: Session, name: str) -> Person:
    clean_name = name.strip()
    stmt = select(Person).where(Person.name == clean_name)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing:
        return existing
    new_person = Person(name=clean_name, status="active")
    db.add(new_person)
    db.flush()
    return new_person


def _get_or_create_role(db: Session, code_or_name: str) -> Role:
    raw = code_or_name.strip()
    clean_code = raw.upper()
    if "KARTA" in clean_code or clean_code == "SK":
        clean_code = "SK"
        role_name = "Satsang Karta"
    elif "READER" in clean_code or clean_code == "SR":
        clean_code = "SR"
        role_name = "Satsang Reader"
    else:
        role_name = raw

    stmt = select(Role).where(Role.code == clean_code)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing:
        return existing
    new_role = Role(code=clean_code, name=role_name)
    db.add(new_role)
    db.flush()
    return new_role


def ingest_pdf_file(
    db: Session,
    file_path: Union[str, Path],
    original_filename: str,
    source_type: str = "manual_upload",
    data_source_name: str = "Manual Upload",
    storage_path: Optional[str] = None,
    auto_commit: bool = True,
) -> PDFIngestionResult:
    """
    Ingest a PDF file into the database.

    Workflow:
    1. Validate .pdf extension.
    2. Compute SHA-256 content hash.
    3. Check DocumentVersion for duplicates.
    4. Register DataSource, Document, and DocumentVersion.
    5. Iterate pages with pdfplumber:
       - Extract full page text and save a page-level SourceReference.
       - Detect tables using page.find_tables() with real bounding box coordinates.
       - Classify tables and create structured records where mapping is clear.
       - If tables are ambiguous, mark as "Needs Review" without guessing.
    6. Return detailed PDFIngestionResult.
    """
    file_path = Path(file_path)
    ext = file_path.suffix.lower()

    if ext not in SUPPORTED_PDF_EXTENSIONS:
        raise UnsupportedFileFormatError(
            f"Unsupported file format '{ext}'. Only .pdf files are supported by the PDF ingestion service."
        )

    # 1. Content hash
    content_hash = calculate_sha256(file_path)

    # 2. Duplicate check
    stmt = select(DocumentVersion).where(DocumentVersion.content_hash == content_hash)
    existing_version = db.execute(stmt).scalar_one_or_none()
    if existing_version:
        return PDFIngestionResult(
            document_id=str(existing_version.document_id),
            version_id=str(existing_version.id),
            filename=original_filename,
            content_hash=content_hash,
            duplicate_status="duplicate",
            errors=[],
        )

    # 3. Create DataSource, Document, and DocumentVersion
    ds_stmt = select(DataSource).where(DataSource.name == data_source_name)
    data_source = db.execute(ds_stmt).scalar_one_or_none()
    if not data_source:
        data_source = DataSource(
            name=data_source_name,
            source_type=source_type,
            status="active",
        )
        db.add(data_source)
        db.flush()

    doc = Document(
        data_source_id=data_source.id,
        original_filename=original_filename,
        document_type="pdf",
        status="active",
    )
    db.add(doc)
    db.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        content_hash=content_hash,
        storage_path=storage_path or str(file_path),
        status="active",
    )
    db.add(version)
    db.flush()

    result = PDFIngestionResult(
        document_id=str(doc.id),
        version_id=str(version.id),
        filename=original_filename,
        content_hash=content_hash,
        duplicate_status="new",
    )

    # 4. Open PDF using pdfplumber
    try:
        pdf = pdfplumber.open(file_path)
    except Exception as exc:
        result.errors.append(f"Failed to open PDF document: {exc}")
        if auto_commit:
            db.commit()
        else:
            db.flush()
        return result

    result.page_count = len(pdf.pages)

    for page_idx, page in enumerate(pdf.pages, start=1):
        result.pages_processed += 1

        # Extract raw page text
        page_text = page.extract_text() or ""
        clean_page_text = page_text.strip()

        # Create page-level SourceReference for Source Preview
        page_sr = SourceReference(
            document_id=doc.id,
            document_version_id=version.id,
            page_number=page_idx,
            source_text=clean_page_text if clean_page_text else "[Empty Page]",
        )
        db.add(page_sr)
        db.flush()

        # Detect tables with coordinates
        found_tables = page.find_tables()
        if not found_tables:
            # If no tables found and page is essentially empty
            if not clean_page_text:
                result.review_items.append({
                    "page": page_idx,
                    "status": "Needs Review",
                    "reason": "Empty page with no text or tables detected.",
                })
                result.records_needing_review += 1
            continue

        for table in found_tables:
            result.tables_detected += 1
            bbox = table.bbox  # (x0, top, x1, bottom)
            bbox_str = f"bbox:[{bbox[0]:.1f},{bbox[1]:.1f},{bbox[2]:.1f},{bbox[3]:.1f}]"

            extracted_table = table.extract()
            if not extracted_table or len(extracted_table) < 2:
                result.review_items.append({
                    "page": page_idx,
                    "bbox": bbox_str,
                    "status": "Needs Review",
                    "reason": "Table contains no data rows or insufficient rows.",
                })
                result.records_needing_review += 1
                continue

            raw_headers = [str(c).strip() if c is not None else "" for c in extracted_table[0]]
            normalized_headers = [_normalize_header(h) for h in raw_headers]
            concept_type, col_map = _classify_table_headers(normalized_headers)

            if not concept_type:
                result.review_items.append({
                    "page": page_idx,
                    "bbox": bbox_str,
                    "status": "Needs Review",
                    "reason": f"Unknown table column structure. Headers: {raw_headers}",
                })
                result.records_needing_review += 1
                continue

            data_rows = extracted_table[1:]

            for row_idx, row in enumerate(data_rows, start=2):
                if not any(cell is not None and str(cell).strip() != "" for cell in row):
                    continue

                row_dict = {
                    raw_headers[i]: row[i]
                    for i in range(min(len(raw_headers), len(row)))
                    if raw_headers[i]
                }

                # Create row-level SourceReference with real bounding box coordinates
                row_sr = SourceReference(
                    document_id=doc.id,
                    document_version_id=version.id,
                    page_number=page_idx,
                    row_number=row_idx,
                    cell_or_range=bbox_str,
                    source_text=json.dumps(row_dict, default=str),
                )
                db.add(row_sr)
                db.flush()

                # Process based on concept
                if concept_type == "attendance":
                    raw_date = row[col_map["date"]] if col_map.get("date") is not None and col_map["date"] < len(row) else None
                    raw_ghar = row[col_map["ghar"]] if col_map.get("ghar") is not None and col_map["ghar"] < len(row) else None
                    raw_att = row[col_map["attendance"]] if col_map.get("attendance") is not None and col_map["attendance"] < len(row) else None

                    parsed_date = _parse_date(raw_date)
                    parsed_count = _parse_int(raw_att)

                    if not raw_ghar or (parsed_count is None and not raw_att):
                        result.review_items.append({
                            "page": page_idx,
                            "row": row_idx,
                            "status": "Needs Review",
                            "reason": f"Missing required attendance data. Date: {raw_date}, Ghar: {raw_ghar}, Count: {raw_att}",
                        })
                        result.records_needing_review += 1
                        continue

                    ghar = _get_or_create_ghar(db, str(raw_ghar))
                    attendance = Attendance(
                        date=parsed_date,
                        satsang_ghar_id=ghar.id,
                        count_value=parsed_count,
                        raw_value=str(raw_att) if raw_att is not None else None,
                        source_reference_id=row_sr.id,
                        status="active",
                    )
                    db.add(attendance)
                    result.structured_records_created += 1

                elif concept_type == "assignment":
                    raw_date = row[col_map["date"]] if col_map.get("date") is not None and col_map["date"] < len(row) else None
                    raw_ghar = row[col_map["ghar"]] if col_map.get("ghar") is not None and col_map["ghar"] < len(row) else None
                    raw_person = row[col_map["person"]] if col_map.get("person") is not None and col_map["person"] < len(row) else None
                    raw_role = row[col_map["role"]] if col_map.get("role") is not None and col_map["role"] < len(row) else None

                    parsed_date = _parse_date(raw_date)
                    if not raw_ghar and not raw_person:
                        result.review_items.append({
                            "page": page_idx,
                            "row": row_idx,
                            "status": "Needs Review",
                            "reason": f"Missing ghar or person. Row: {row_dict}",
                        })
                        result.records_needing_review += 1
                        continue

                    ghar_id = _get_or_create_ghar(db, str(raw_ghar)).id if raw_ghar else None
                    person_id = _get_or_create_person(db, str(raw_person)).id if raw_person else None
                    role_id = _get_or_create_role(db, str(raw_role)).id if raw_role else None

                    assignment = Assignment(
                        date=parsed_date,
                        satsang_ghar_id=ghar_id,
                        person_id=person_id,
                        role_id=role_id,
                        description=json.dumps(row_dict, default=str),
                        source_reference_id=row_sr.id,
                        status="active",
                    )
                    db.add(assignment)
                    result.structured_records_created += 1

                elif concept_type == "vehicle":
                    raw_date = row[col_map["date"]] if col_map.get("date") is not None and col_map["date"] < len(row) else None
                    raw_ghar = row[col_map["ghar"]] if col_map.get("ghar") is not None and col_map["ghar"] < len(row) else None
                    raw_veh = row[col_map["vehicle"]] if col_map.get("vehicle") is not None and col_map["vehicle"] < len(row) else None

                    parsed_date = _parse_date(raw_date)
                    parsed_count = _parse_int(raw_veh)
                    ghar_id = _get_or_create_ghar(db, str(raw_ghar)).id if raw_ghar else None

                    vehicle_data = VehicleWheelData(
                        date=parsed_date,
                        satsang_ghar_id=ghar_id,
                        count_value=parsed_count,
                        vehicle_type=raw_headers[col_map["vehicle"]],
                        raw_value=str(raw_veh) if raw_veh is not None else None,
                        source_reference_id=row_sr.id,
                        status="active",
                    )
                    db.add(vehicle_data)
                    result.structured_records_created += 1

    pdf.close()
    if auto_commit:
        db.commit()
    else:
        db.flush()
    return result
