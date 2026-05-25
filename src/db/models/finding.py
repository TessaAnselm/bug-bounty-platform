import enum
from uuid import uuid4
from sqlalchemy import Column, String, Numeric, Text, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.db.base import Base


class Severity(enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    informational = "informational"


class FindingStatus(enum.Enum):
    draft = "draft"
    submitted = "submitted"
    triaged = "triaged"
    resolved = "resolved"
    duplicate = "duplicate"
    not_applicable = "not_applicable"
    paid = "paid"


class Finding(Base):
    __tablename__ = "findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=True)
    title = Column(String, nullable=False)
    vuln_type = Column(String, nullable=False)
    severity = Column(Enum(Severity), nullable=False)
    status = Column(Enum(FindingStatus), nullable=False, default=FindingStatus.draft)
    summary = Column(Text, nullable=True)
    vulnerability_details = Column(Text, nullable=True)
    steps_to_reproduce = Column(Text, nullable=True)
    impact = Column(Text, nullable=True)
    recommended_fix = Column(Text, nullable=True)
    report_url = Column(String, nullable=True)
    payout_amount = Column(Numeric(10, 2), nullable=True)
    confidence_score = Column(Numeric(3, 2), nullable=True)  # 0.00–1.00, human-assigned
    temporal_workflow_id = Column(String, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    triaged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    program = relationship("Program", back_populates="findings")
    asset = relationship("Asset", back_populates="findings")
    outcomes = relationship("Outcome", back_populates="finding")
    artifacts = relationship("Artifact", back_populates="finding")
