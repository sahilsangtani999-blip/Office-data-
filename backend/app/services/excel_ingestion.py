"""
Excel Data Ingestion Service for RSSB Office Data Platform.

Provides:
- Secure reading of .xlsx and .xlsm files (read-only, data-only, no macro execution)
- Format rejection for unsupported file types
- SHA-256 content hashing and duplicate version prevention
- Controlled concept classification for Attendance, Assignment, Vehicle/Wheel
- Granular provenance creation via SourceReference (sheet, row, cell/range, text)
- Preservation of original raw source values
- Strict "Needs Review" flagging for ambiguous columns and missing required data
"""

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import openpyxl
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

# Supported extensions
SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm"}


class UnsupportedFileFormatError(ValueError):
    """Raised when an uploaded file does not have a supported Excel extension."""
    pass


@dataclass
class IngestionResult:
    """Structured report returned after processing an Excel file."""
    document_id: Optional[str]
    version_id: Optional[str]
    filename: str
    content_hash: str
    sheets_discovered: List[str] = field(default_factory=list)
    records_processed: int = 0
    records_accepted: int = 0
    records_requiring_review: int = 0
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
    # Remove special characters like parentheses, colons, slashes
    text = re.sub(r"[^\w\s]", " ", text)
    # Collapse multiple whitespaces
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(val: Any) -> Optional[date]:
    """Parse a date value from an Excel cell into a date object."""
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
    """Parse an integer count from an Excel cell value."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return int(val)
        except (ValueError, OverflowError):
            return None

    val_str = str(val).strip()
    # Remove commas
    clean = val_str.replace(",", "")
    # Check if purely digits
    try:
        return int(float(clean))
    except (ValueError, TypeError):
        return None


def _classify_sheet(headers: List[str]) -> Tuple[Optional[str], Dict[str, int]]:
    """
    Controlled concept classifier.
    Examines normalized headers and maps them to known concepts:
    - 'attendance'
    - 'assignment'
    - 'vehicle'
    
    Returns (concept_type, column_map) where column_map maps role to index.
    If the sheet does not match known concepts, returns (None, {}).
    """
    col_map: Dict[str, int] = {}
    
    # 1. Match Attendance
    # Needs: date, ghar/center, attendance/count
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

    # Classification rules without speculative guessing:
    # 1. Vehicle / Wheel concept (checked before generic attendance to catch vehicle counts)
    if "date" in col_map and "vehicle" in col_map:
        return "vehicle", col_map

    # 2. Attendance concept
    if "date" in col_map and "ghar" in col_map and "attendance" in col_map:
        return "attendance", col_map

    # 3. Assignment concept
    if "date" in col_map and "ghar" in col_map and ("person" in col_map or "role" in col_map):
        return "assignment", col_map

    return None, {}


def _get_or_create_ghar(db: Session, name: str) -> SatsangGhar:
    """Find existing SatsangGhar by name or create a new one."""
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
    """Find existing Person by name or create a new one."""
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
    """Find existing Role by code/name or create a new one."""
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


def ingest_excel_file(
    db: Session,
    file_path: Union[str, Path],
    original_filename: str,
    source_type: str = "manual_upload",
    data_source_name: str = "Manual Upload",
    storage_path: Optional[str] = None,
    auto_commit: bool = True,
) -> IngestionResult:
    """
    Ingest an Excel workbook (.xlsx or .xlsm) into the database.

    Workflow:
    1. Extension validation.
    2. SHA-256 calculation.
    3. Duplicate check on DocumentVersion.
    4. Data source, document, and version registration.
    5. Controlled sheet classification.
    6. Row parsing with SourceReference provenance.
    7. Raw value preservation and "Needs Review" handling.
    """
    file_path = Path(file_path)
    ext = file_path.suffix.lower()

    # 1. Reject unsupported formats
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileFormatError(
            f"Unsupported file format '{ext}'. Only .xlsx and .xlsm files are supported."
        )

    # 2. Content hash
    content_hash = calculate_sha256(file_path)

    # 3. Duplicate check
    stmt = select(DocumentVersion).where(DocumentVersion.content_hash == content_hash)
    existing_version = db.execute(stmt).scalar_one_or_none()
    if existing_version:
        # Load sheets from existing document
        return IngestionResult(
            document_id=str(existing_version.document_id),
            version_id=str(existing_version.id),
            filename=original_filename,
            content_hash=content_hash,
            duplicate_status="duplicate",
            errors=[],
        )

    # 4. Create DataSource, Document, and DocumentVersion
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
        document_type=ext.lstrip("."),
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

    result = IngestionResult(
        document_id=str(doc.id),
        version_id=str(version.id),
        filename=original_filename,
        content_hash=content_hash,
        duplicate_status="new",
    )

    # 5. Open and inspect workbook (read-only, data-only, macros disabled)
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    except Exception as exc:
        result.errors.append(f"Failed to open Excel workbook: {exc}")
        if auto_commit:
            db.commit()
        else:
            db.flush()
        return result

    result.sheets_discovered = wb.sheetnames

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]

        # Read all rows into memory
        rows = list(sheet.iter_rows(values_only=True))

        if not rows:
            result.review_items.append({
                "sheet": sheet_name,
                "status": "Needs Review",
                "reason": "Sheet is completely empty.",
            })
            result.records_requiring_review += 1
            continue

        # Find header row (first non-empty row with text)
        header_row_idx = None
        raw_headers = None

        for idx, row in enumerate(rows):
            if any(cell is not None and str(cell).strip() != "" for cell in row):
                # Count non-empty strings
                non_empty = [str(c).strip() for c in row if c is not None and str(c).strip() != ""]
                if len(non_empty) >= 1:
                    header_row_idx = idx
                    raw_headers = [str(c).strip() if c is not None else "" for c in row]
                    break

        if header_row_idx is None or not raw_headers:
            result.review_items.append({
                "sheet": sheet_name,
                "status": "Needs Review",
                "reason": "No valid header row detected in sheet.",
            })
            result.records_requiring_review += 1
            continue

        normalized_headers = [_normalize_header(h) for h in raw_headers]
        concept_type, col_map = _classify_sheet(normalized_headers)

        if not concept_type:
            result.review_items.append({
                "sheet": sheet_name,
                "status": "Needs Review",
                "reason": f"Unknown column structure. Headers: {raw_headers}",
            })
            result.records_requiring_review += 1
            continue

        # Process data rows starting after the header
        data_rows = rows[header_row_idx + 1 :]

        for offset, row in enumerate(data_rows, start=header_row_idx + 2):
            if not any(cell is not None and str(cell).strip() != "" for cell in row):
                # Blank row, skip silently
                continue

            result.records_processed += 1
            row_dict = {
                raw_headers[i]: row[i]
                for i in range(min(len(raw_headers), len(row)))
                if raw_headers[i]
            }

            # Create SourceReference
            source_ref = SourceReference(
                document_id=doc.id,
                document_version_id=version.id,
                sheet_name=sheet_name,
                row_number=offset,
                source_text=json.dumps(row_dict, default=str),
            )
            db.add(source_ref)
            db.flush()

            # Process according to concept
            if concept_type == "attendance":
                raw_date = row[col_map["date"]] if col_map.get("date") is not None and col_map["date"] < len(row) else None
                raw_ghar = row[col_map["ghar"]] if col_map.get("ghar") is not None and col_map["ghar"] < len(row) else None
                raw_att = row[col_map["attendance"]] if col_map.get("attendance") is not None and col_map["attendance"] < len(row) else None

                parsed_date = _parse_date(raw_date)
                parsed_count = _parse_int(raw_att)

                if not raw_ghar or (parsed_count is None and not raw_att):
                    result.review_items.append({
                        "sheet": sheet_name,
                        "row": offset,
                        "status": "Needs Review",
                        "reason": f"Missing required attendance data. Date: {raw_date}, Ghar: {raw_ghar}, Count: {raw_att}",
                    })
                    result.records_requiring_review += 1
                    continue

                ghar = _get_or_create_ghar(db, str(raw_ghar))
                attendance = Attendance(
                    date=parsed_date,
                    satsang_ghar_id=ghar.id,
                    count_value=parsed_count,
                    raw_value=str(raw_att) if raw_att is not None else None,
                    source_reference_id=source_ref.id,
                    status="active",
                )
                db.add(attendance)
                result.records_accepted += 1

            elif concept_type == "assignment":
                raw_date = row[col_map["date"]] if col_map.get("date") is not None and col_map["date"] < len(row) else None
                raw_ghar = row[col_map["ghar"]] if col_map.get("ghar") is not None and col_map["ghar"] < len(row) else None
                raw_person = row[col_map["person"]] if col_map.get("person") is not None and col_map["person"] < len(row) else None
                raw_role = row[col_map["role"]] if col_map.get("role") is not None and col_map["role"] < len(row) else None

                parsed_date = _parse_date(raw_date)
                if not raw_ghar and not raw_person:
                    result.review_items.append({
                        "sheet": sheet_name,
                        "row": offset,
                        "status": "Needs Review",
                        "reason": f"Missing ghar or person. Row: {row_dict}",
                    })
                    result.records_requiring_review += 1
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
                    source_reference_id=source_ref.id,
                    status="active",
                )
                db.add(assignment)
                result.records_accepted += 1

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
                    source_reference_id=source_ref.id,
                    status="active",
                )
                db.add(vehicle_data)
                result.records_accepted += 1

    wb.close()
    if auto_commit:
        db.commit()
    else:
        db.flush()
    return result
