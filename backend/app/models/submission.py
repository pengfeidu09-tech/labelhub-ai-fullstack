from sqlalchemy import Column, Integer, String, Text, DateTime, JSON

from app.core.database import Base


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=True)
    dataset_item_id = Column(Integer, nullable=True)
    labeler_id = Column(Integer, nullable=True)
    data = Column(JSON, nullable=False)
    status = Column(String(32), nullable=False)
    rejected_reason = Column(Text, nullable=True)
    revision_no = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
