from uuid import uuid4
from sqlalchemy import Column, String, Numeric, Float, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.db.base import Base


class Outcome(Base):
    __tablename__ = "outcomes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    finding_id = Column(UUID(as_uuid=True), ForeignKey("findings.id"), nullable=False)
    result = Column(String, nullable=False)
    payout_amount = Column(Numeric(10, 2), nullable=True)
    time_spent_hours = Column(Float, nullable=True)
    lessons = Column(Text, nullable=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())

    finding = relationship("Finding", back_populates="outcomes")
