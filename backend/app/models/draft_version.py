from sqlalchemy import Column, Integer, String, DateTime, JSON

from app.core.database import Base


class DraftVersion(Base):
    __tablename__ = "draft_versions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False)
    item_id = Column(Integer, nullable=False)
    labeler_id = Column(Integer, nullable=False)
    work_key = Column(String(128), nullable=False)
    version_no = Column(Integer, nullable=False, default=1)
    version_type = Column(String(32), nullable=True)    # draft / submitted / rework_draft / rework_submitted
    operator_role = Column(String(16), nullable=True)    # labeler / reviewer
    snapshot_json = Column(JSON, nullable=True)
    summary = Column(String(256), nullable=True)
    created_at = Column(DateTime, nullable=True)
