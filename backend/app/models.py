"""
SQLAlchemy ORM models for RSSB Office Data Platform.

Reflects known office data entities without premature assumptions
or speculative business rules.
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# =============================================================================
# 1. DataSource
# =============================================================================
class DataSource(Base):
    """
    Represents an origin or ingestion channel for office data
    (e.g., Google Drive folder, SSM export, manual upload, local directory).
    """
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="data_source"
    )

    def __repr__(self) -> str:
        return f"<DataSource(id={self.id}, name='{self.name}', type='{self.source_type}')>"


# =============================================================================
# 2. Document
# =============================================================================
class Document(Base):
    """
    Represents a discrete file received from a DataSource
    (e.g., PDF schedule, Excel attendance sheet).
    """
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    data_source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(
        String(500), nullable=False, index=True
    )
    document_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    data_source: Mapped[Optional["DataSource"]] = relationship(
        "DataSource", back_populates="documents"
    )
    versions: Mapped[List["DocumentVersion"]] = relationship(
        "DocumentVersion", back_populates="document", cascade="all, delete-orphan"
    )
    source_references: Mapped[List["SourceReference"]] = relationship(
        "SourceReference", back_populates="document"
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename='{self.original_filename}')>"


# =============================================================================
# 3. DocumentVersion
# =============================================================================
class DocumentVersion(Base):
    """
    Represents a specific physical version of a Document, tracking content hash
    and file path for immutability and provenance.
    """
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    storage_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="versions")
    source_references: Mapped[List["SourceReference"]] = relationship(
        "SourceReference", back_populates="document_version"
    )

    def __repr__(self) -> str:
        return f"<DocumentVersion(id={self.id}, doc={self.document_id}, v={self.version_number})>"


# =============================================================================
# 4. SatsangGhar
# =============================================================================
class SatsangGhar(Base):
    """
    Represents a Satsang Ghar location.
    NOTE: MajorCenter foreign key is intentionally omitted until the organizational
    hierarchy is officially confirmed.
    """
    __tablename__ = "satsang_ghars"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    assignments: Mapped[List["Assignment"]] = relationship(
        "Assignment", back_populates="satsang_ghar"
    )
    attendances: Mapped[List["Attendance"]] = relationship(
        "Attendance", back_populates="satsang_ghar"
    )
    vehicle_wheel_records: Mapped[List["VehicleWheelData"]] = relationship(
        "VehicleWheelData", back_populates="satsang_ghar"
    )

    def __repr__(self) -> str:
        return f"<SatsangGhar(id={self.id}, name='{self.name}')>"


# =============================================================================
# 5. MajorCenter
# =============================================================================
class MajorCenter(Base):
    """
    Represents a Major Center entity. Stored independently without premature
    child relationships until official hierarchy rules are defined.
    """
    __tablename__ = "major_centers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<MajorCenter(id={self.id}, name='{self.name}')>"


# =============================================================================
# 6. Person
# =============================================================================
class Person(Base):
    """
    Represents an individual person involved in Satsang duties or administration.
    """
    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    assignments: Mapped[List["Assignment"]] = relationship(
        "Assignment", back_populates="person"
    )

    def __repr__(self) -> str:
        return f"<Person(id={self.id}, name='{self.name}')>"


# =============================================================================
# 7. Role
# =============================================================================
class Role(Base):
    """
    Represents a duty or office role (e.g., SK = Satsang Karta, SR = Satsang Reader, etc.).
    Code is unique and indexed; system does not constrain possible roles.
    """
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    assignments: Mapped[List["Assignment"]] = relationship(
        "Assignment", back_populates="role"
    )

    def __repr__(self) -> str:
        return f"<Role(id={self.id}, code='{self.code}', name='{self.name}')>"


# =============================================================================
# 8. SourceReference
# =============================================================================
class SourceReference(Base):
    """
    Reusable data provenance model tracking exactly where a piece of information
    came from within a document (PDF page or Excel sheet/row/cell).
    All coordinate fields are nullable to accommodate varied source formats.
    """
    __tablename__ = "source_references"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    document_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sheet_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    row_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cell_or_range: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    document: Mapped[Optional["Document"]] = relationship(
        "Document", back_populates="source_references"
    )
    document_version: Mapped[Optional["DocumentVersion"]] = relationship(
        "DocumentVersion", back_populates="source_references"
    )
    assignments: Mapped[List["Assignment"]] = relationship(
        "Assignment", back_populates="source_reference"
    )
    attendances: Mapped[List["Attendance"]] = relationship(
        "Attendance", back_populates="source_reference"
    )
    vehicle_wheel_records: Mapped[List["VehicleWheelData"]] = relationship(
        "VehicleWheelData", back_populates="source_reference"
    )

    def __repr__(self) -> str:
        return f"<SourceReference(id={self.id}, doc={self.document_id}, sheet='{self.sheet_name}', page={self.page_number})>"


# =============================================================================
# 9. Assignment
# =============================================================================
class Assignment(Base):
    """
    Flexible assignment record representing duty assignments.
    Fields are intentionally nullable to handle legacy or partial schedules.
    """
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    satsang_ghar_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("satsang_ghars.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    person_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_reference_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_references.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    satsang_ghar: Mapped[Optional["SatsangGhar"]] = relationship(
        "SatsangGhar", back_populates="assignments"
    )
    person: Mapped[Optional["Person"]] = relationship(
        "Person", back_populates="assignments"
    )
    role: Mapped[Optional["Role"]] = relationship("Role", back_populates="assignments")
    source_reference: Mapped[Optional["SourceReference"]] = relationship(
        "SourceReference", back_populates="assignments"
    )

    def __repr__(self) -> str:
        return f"<Assignment(id={self.id}, date={self.date}, ghar={self.satsang_ghar_id}, person={self.person_id})>"


# =============================================================================
# 10. Attendance
# =============================================================================
class Attendance(Base):
    """
    Represents attendance counts or recorded values for a Satsang Ghar session.
    Stores structured integer count and preserves raw office values.
    """
    __tablename__ = "attendances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    satsang_ghar_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("satsang_ghars.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    count_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_reference_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_references.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    satsang_ghar: Mapped[Optional["SatsangGhar"]] = relationship(
        "SatsangGhar", back_populates="attendances"
    )
    source_reference: Mapped[Optional["SourceReference"]] = relationship(
        "SourceReference", back_populates="attendances"
    )

    def __repr__(self) -> str:
        return f"<Attendance(id={self.id}, date={self.date}, count={self.count_value})>"


# =============================================================================
# 11. VehicleWheelData
# =============================================================================
class VehicleWheelData(Base):
    """
    Represents vehicle and wheel statistics (e.g. 2-wheeler, 4-wheeler counts).
    Preserves raw value and description.
    """
    __tablename__ = "vehicle_wheel_data"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    satsang_ghar_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("satsang_ghars.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    count_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vehicle_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    raw_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_reference_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_references.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    satsang_ghar: Mapped[Optional["SatsangGhar"]] = relationship(
        "SatsangGhar", back_populates="vehicle_wheel_records"
    )
    source_reference: Mapped[Optional["SourceReference"]] = relationship(
        "SourceReference", back_populates="vehicle_wheel_records"
    )

    def __repr__(self) -> str:
        return f"<VehicleWheelData(id={self.id}, date={self.date}, count={self.count_value}, type='{self.vehicle_type}')>"


# =============================================================================
# 12. Report
# =============================================================================
class Report(Base):
    """
    Stores metadata for generated or registered reports (e.g., Monthly Reports,
    SK Reports, SR Reports, Wheel/Vehicle Reports).
    """
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reporting_period_start: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True
    )
    reporting_period_end: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft", index=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Report(id={self.id}, name='{self.name}', type='{self.report_type}')>"
