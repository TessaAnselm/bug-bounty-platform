import enum
from uuid import uuid4
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.db.base import Base




class AssetType(enum.Enum):
    subdomain = "subdomain"
    ip = "ip"
    url = "url"
    api_endpoint = "api_endpoint"
    mobile = "mobile"
    other = "other"


class AssetStatus(enum.Enum):
    active = "active"
    inactive = "inactive"
    out_of_scope = "out_of_scope"


class Asset(Base):
    __tablename__ = "assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False)
    type = Column(Enum(AssetType), nullable=False)
    value = Column(String, nullable=False)
    status = Column(Enum(AssetStatus), nullable=False, default=AssetStatus.active)
    technologies = Column(JSONB, nullable=False, default=list)
    ports = Column(JSONB, nullable=False, default=list)
    screenshot_path = Column(String, nullable=True)
    http_status = Column(Integer, nullable=True)
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_new = Column(Boolean, nullable=False, default=True)
    risk_score = Column(Integer, nullable=True)
    tags = Column(JSONB, nullable=False, default=list)
    source_tool = Column(String, nullable=True)
    interesting = Column(Boolean, nullable=False, default=False)

    program = relationship("Program", back_populates="assets")
    findings = relationship("Finding", back_populates="asset")
    alerts = relationship("Alert", back_populates="asset")
    session_notes = relationship("SessionNote", back_populates="asset")
    artifacts = relationship("Artifact", back_populates="asset")
