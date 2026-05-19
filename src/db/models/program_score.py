from uuid import uuid4
from sqlalchemy import Column, Float, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.db.base import Base


class ProgramScore(Base):
    __tablename__ = "program_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False)
    total_score = Column(Float, nullable=False)
    payout_score = Column(Float, nullable=False)
    scope_score = Column(Float, nullable=False)
    competition_score = Column(Float, nullable=False)
    fit_score = Column(Float, nullable=False)
    momentum_score = Column(Float, nullable=False)
    top_signals = Column(JSONB, nullable=False, default=list)
    scored_at = Column(DateTime(timezone=True), server_default=func.now())
    scoring_version = Column(String, nullable=False, default="1.0")

    program = relationship("Program", back_populates="scores")
