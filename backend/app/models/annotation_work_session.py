from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime, timezone

from app.core.database import Base


class AnnotationWorkSession(Base):
    __tablename__ = "annotation_work_sessions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False)
    item_id = Column(Integer, nullable=False)
    labeler_id = Column(Integer, nullable=False)
    work_key = Column(String(128), nullable=False, index=True)
    annotation_id = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="active")
    opened_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_heartbeat_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    accumulated_seconds = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
