"""
Unit and integration tests for Phase 1.1 SQLAlchemy models and schema.

Verifies:
1. All 12 tables exist in Base.metadata and the connected database.
2. UUID primary keys are generated properly.
3. Foreign key constraints and relationships function correctly.
4. Flexible/nullable fields accept partial records as required.
5. All test database operations run in isolated transactions and roll back cleanly.
"""

import unittest
import uuid
from datetime import date, datetime

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.models import (
    Assignment,
    Attendance,
    DataSource,
    Document,
    DocumentVersion,
    MajorCenter,
    Person,
    Report,
    Role,
    SatsangGhar,
    SourceReference,
    VehicleWheelData,
)


class TestDatabaseSchema(unittest.TestCase):
    """Verifies table definitions and database reflection."""

    def test_metadata_contains_all_12_tables(self):
        """Ensure Base.metadata has registered all 12 Phase 1.1 tables."""
        expected_tables = {
            "data_sources",
            "documents",
            "document_versions",
            "satsang_ghars",
            "major_centers",
            "persons",
            "roles",
            "source_references",
            "assignments",
            "attendances",
            "vehicle_wheel_data",
            "reports",
        }
        registered_tables = set(Base.metadata.tables.keys())
        self.assertTrue(
            expected_tables.issubset(registered_tables),
            f"Missing tables in metadata: {expected_tables - registered_tables}",
        )

    def test_database_tables_exist(self):
        """Ensure all 12 tables are present in the actual PostgreSQL database."""
        inspector = inspect(engine)
        db_tables = set(inspector.get_table_names())
        expected_tables = {
            "alembic_version",
            "data_sources",
            "documents",
            "document_versions",
            "satsang_ghars",
            "major_centers",
            "persons",
            "roles",
            "source_references",
            "assignments",
            "attendances",
            "vehicle_wheel_data",
            "reports",
        }
        for table in expected_tables:
            self.assertIn(table, db_tables, f"Table '{table}' missing from PostgreSQL database")

    def test_satsang_ghar_has_no_major_center_fk(self):
        """Verify SatsangGhar intentionally lacks a foreign key to MajorCenter."""
        inspector = inspect(engine)
        fks = inspector.get_foreign_keys("satsang_ghars")
        referred_tables = [fk["referred_table"] for fk in fks]
        self.assertNotIn(
            "major_centers",
            referred_tables,
            "SatsangGhar must NOT have a foreign key to MajorCenter at this stage.",
        )


class TestModelOperations(unittest.TestCase):
    """Verifies model instantiation, UUID generation, and rollback isolation."""

    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.session = Session(bind=self.connection)

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def test_data_source_and_document_creation(self):
        """Test creating a DataSource, Document, and DocumentVersion with UUID PKs."""
        ds = DataSource(
            name="HQ Drive Folder",
            source_type="google_drive",
            status="active",
        )
        self.session.add(ds)
        self.session.flush()

        self.assertIsInstance(ds.id, uuid.UUID)

        doc = Document(
            data_source_id=ds.id,
            original_filename="Attendance_June_2026.xlsx",
            document_type="xlsx",
            status="active",
        )
        self.session.add(doc)
        self.session.flush()

        self.assertIsInstance(doc.id, uuid.UUID)
        self.assertEqual(doc.data_source_id, ds.id)

        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            storage_path="data/uploads/sample.xlsx",
            status="active",
        )
        self.session.add(version)
        self.session.flush()

        self.assertIsInstance(version.id, uuid.UUID)
        self.assertEqual(version.document_id, doc.id)

    def test_independent_entities(self):
        """Test creating MajorCenter, SatsangGhar, Person, and Role."""
        center = MajorCenter(name="Delhi", status="active")
        ghar = SatsangGhar(name="Karol Bagh", status="active")
        person = Person(name="Test Volunteer", status="active")
        role = Role(code="SK", name="Satsang Karta", description="Speaker duty")

        self.session.add_all([center, ghar, person, role])
        self.session.flush()

        self.assertIsInstance(center.id, uuid.UUID)
        self.assertIsInstance(ghar.id, uuid.UUID)
        self.assertIsInstance(person.id, uuid.UUID)
        self.assertIsInstance(role.id, uuid.UUID)
        self.assertEqual(role.code, "SK")

    def test_flexible_source_reference_provenance(self):
        """Test SourceReference with partial/nullable coordinates."""
        sr = SourceReference(
            sheet_name="June Attendance",
            row_number=14,
            cell_or_range="C14",
            source_text="Raw attendance note",
        )
        self.session.add(sr)
        self.session.flush()

        self.assertIsInstance(sr.id, uuid.UUID)
        self.assertIsNone(sr.page_number)
        self.assertIsNone(sr.document_id)

    def test_flexible_assignment_attendance_vehicle(self):
        """Test flexible entry models with partial/nullable fields."""
        ghar = SatsangGhar(name="Test Center", status="active")
        self.session.add(ghar)
        self.session.flush()

        # Assignment with date and ghar only
        assignment = Assignment(
            date=date(2026, 6, 15),
            satsang_ghar_id=ghar.id,
            description="Morning Satsang",
            status="active",
        )
        self.session.add(assignment)
        self.session.flush()
        self.assertIsInstance(assignment.id, uuid.UUID)
        self.assertIsNone(assignment.person_id)
        self.assertIsNone(assignment.role_id)

        # Attendance with count and raw value
        attendance = Attendance(
            date=date(2026, 6, 15),
            satsang_ghar_id=ghar.id,
            count_value=350,
            raw_value="approx 350",
            status="active",
        )
        self.session.add(attendance)
        self.session.flush()
        self.assertIsInstance(attendance.id, uuid.UUID)
        self.assertEqual(attendance.count_value, 350)

        # Vehicle record
        vehicle = VehicleWheelData(
            date=date(2026, 6, 15),
            satsang_ghar_id=ghar.id,
            count_value=45,
            vehicle_type="2-wheeler",
            status="active",
        )
        self.session.add(vehicle)
        self.session.flush()
        self.assertIsInstance(vehicle.id, uuid.UUID)
        self.assertEqual(vehicle.vehicle_type, "2-wheeler")

    def test_report_metadata(self):
        """Test Report entity creation."""
        rep = Report(
            name="June 2026 Monthly Summary",
            report_type="monthly",
            reporting_period_start=date(2026, 6, 1),
            reporting_period_end=date(2026, 6, 30),
            status="draft",
        )
        self.session.add(rep)
        self.session.flush()
        self.assertIsInstance(rep.id, uuid.UUID)


if __name__ == "__main__":
    unittest.main()
