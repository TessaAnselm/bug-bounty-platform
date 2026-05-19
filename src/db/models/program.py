import enum
from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.db.base import Base


class ProgramStatus(enum.Enum):
    active = "active"
    paused = "paused"
    archived = "archived"


class Program(Base):
    __tablename__ = "programs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    scope = Column(JSONB, nullable=False, default=list)
    out_of_scope = Column(JSONB, nullable=False, default=list)
    max_payout = Column(Integer, nullable=True)
    status = Column(Enum(ProgramStatus), nullable=False, default=ProgramStatus.active)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    assets = relationship("Asset", back_populates="program")
    findings = relationship("Finding", back_populates="program")
    recon_runs = relationship("ReconRun", back_populates="program")
    alerts = relationship("Alert", back_populates="program")
    session_notes = relationship("SessionNote", back_populates="program")
    scores = relationship("ProgramScore", back_populates="program")
