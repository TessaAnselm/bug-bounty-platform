import enum
from uuid import uuid4
from sqlalchemy import Column, Text, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.db.base import Base


class HuntStatus(enum.Enum):
    active = "active"
    paused = "paused"
    completed = "completed"
    abandoned = "abandoned"


class HuntSession(Base):
    __tablename__ = "hunt_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)

    # What the hunter thinks the vulnerability might be before testing
    hypothesis = Column(Text, nullable=True)

    status = Column(Enum(HuntStatus), nullable=False, default=HuntStatus.active)

    # Which checklists are active for this session e.g. ["idor-api", "oauth-auth"]
    checklists_used = Column(JSONB, nullable=False, default=list)

    # Checked item indices per checklist e.g. {"idor-api": [0, 2, 5]}
    checklist_progress = Column(JSONB, nullable=False, default=dict)

    # Free-form markdown notes taken during the session
    notes = Column(Text, nullable=True)

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    program = relationship("Program")
    asset = relationship("Asset")
