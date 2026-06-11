from uuid import uuid4
from sqlalchemy import Column, Text, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.db.base import Base


class HttpExchange(Base):
    """A single request/response sent through the Repeater.

    Every send is scope-validated and compliance-enforced before it leaves the
    platform, then recorded here as evidence and for MCP/AI review. Response
    bodies are capped by the caller to keep rows small.
    """
    __tablename__ = "http_exchanges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    hunt_session_id = Column(UUID(as_uuid=True), ForeignKey("hunt_sessions.id"), nullable=True)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=True)
    # Set when this exchange is saved as evidence and attached to a finding;
    # the report exporter pulls these (redacted) into the submission.
    finding_id = Column(UUID(as_uuid=True), ForeignKey("findings.id"), nullable=True)
    is_evidence = Column(Boolean, nullable=False, default=False)

    request_method = Column(Text, nullable=False)
    request_url = Column(Text, nullable=False)
    request_headers = Column(JSONB, nullable=False, default=dict)
    request_body = Column(Text, nullable=True)

    response_status = Column(Integer, nullable=True)
    response_headers = Column(JSONB, nullable=True)
    response_body = Column(Text, nullable=True)
    response_time_ms = Column(Integer, nullable=True)

    # Optional hunter annotations — e.g. "acct A baseline" / "acct B swap" for IDOR.
    label = Column(Text, nullable=True)
    note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    program = relationship("Program")
    hunt_session = relationship("HuntSession")
