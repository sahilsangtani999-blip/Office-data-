"""
Seed test documents with validation issues into the database for manual and browser verification.
"""

import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app.database import SessionLocal
from app.models import User, Document, DocumentVersion, SourceReference, Attendance, Assignment, VehicleWheelData, Report
from app.core.security import get_password_hash
from app.services.excel_ingestion import ingest_excel_file
from app.services.validation_service import validate_document

def seed():
    db = SessionLocal()
    try:
        # Check users
        users = [
            ("admin", "admin@rssb.org", "admin", "Admin User", "admin123"),
            ("reviewer", "reviewer@rssb.org", "reviewer", "Reviewer User", "reviewer123"),
            ("uploader", "uploader@rssb.org", "uploader", "Uploader User", "uploader123"),
            ("viewer", "viewer@rssb.org", "viewer", "Viewer User", "viewer123"),
        ]
        for uname, email, role, full_name, pwd in users:
            existing = db.query(User).filter(User.username == uname).first()
            if not existing:
                u = User(
                    username=uname,
                    email=email,
                    role=role,
                    full_name=full_name,
                    hashed_password=get_password_hash(pwd),
                    is_active=True
                )
                db.add(u)
        db.commit()

        # Ingest representative fixtures if not already present
        fixture_dir = backend_dir / "tests" / "fixtures"
        target_files = [
            "multi_sheet_office.xlsx",
            "search_test_data.xlsx",
            "RSSB_Dummy_Vehicle_September_2026.xlsx",
            "excel_missing_date.xlsx",
            "excel_invalid_numeric.xlsx",
        ]

        for fname in target_files:
            fpath = fixture_dir / fname
            if not fpath.exists():
                print(f"Skipping {fname}, file not found")
                continue
            
            existing_doc = db.query(Document).filter(Document.original_filename == fname).first()
            if not existing_doc:
                print(f"Ingesting {fname}...")
                res = ingest_excel_file(db, str(fpath), original_filename=fname, data_source_name="Seed Fixtures")
                print(f"Ingested {fname} -> doc_id {res.document_id}")
                if res.document_id:
                    v_res = validate_document(db, res.document_id)
                    print(f"Validated {fname}: status={v_res.validation_status}, issues={len(v_res.issues)}")
            else:
                print(f"Document {fname} already exists -> doc_id {existing_doc.id}")
                v_res = validate_document(db, existing_doc.id)
                print(f"Validated {fname}: status={v_res.validation_status}, issues={len(v_res.issues)}")

        db.commit()
        print("Workspace seeding complete!")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
