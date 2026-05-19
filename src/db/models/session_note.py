from uuid import uuid4
from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.db.base import Base


class SessionNote(Base):
    __tablename__ = "session_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    program = relationship("Program", back_populates="session_notes")
    asset = relationship("Asset", back_populates="session_notes")
