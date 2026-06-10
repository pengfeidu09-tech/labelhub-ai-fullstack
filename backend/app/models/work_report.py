from sqlalchemy import Column, Integer, String, Float, DateTime

from app.core.database import Base


class WorkReport(Base):
    __tablename__ = "work_reports"

    id = Column(Integer, primary_key=True, index=True)
    labeler_id = Column(Integer, nullable=False)
    task_id = Column(Integer, nullable=True)
    report_date = Column(String(10), nullable=False)
    annotated_count = Column(Integer, nullable=True, default=0)
    submitted_count = Column(Integer, nullable=True, default=0)
    valid_count = Column(Integer, nullable=True, default=0)
    invalid_count = Column(Integer, nullable=True, default=0)
    approved_count = Column(Integer, nullable=True, default=0)
    rejected_count = Column(Integer, nullable=True, default=0)
    total_seconds = Column(Float, nullable=True, default=0)
    avg_seconds = Column(Float, nullable=True, default=0)
    approval_rate = Column(Float, nullable=True, default=0)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
