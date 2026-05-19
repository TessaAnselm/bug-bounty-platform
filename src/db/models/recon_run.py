import enum
from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.db.base import Base


class ReconStatus(enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


class ReconRun(Base):
    __tablename__ = "recon_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False)
    temporal_workflow_id = Column(String, nullable=True)
    status = Column(Enum(ReconStatus), nullable=False, default=ReconStatus.running)
    triggered_by = Column(String, nullable=False, default="manual")
    assets_found = Column(Integer, nullable=False, default=0)
    new_assets = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    program = relationship("Program", back_populates="recon_runs")
