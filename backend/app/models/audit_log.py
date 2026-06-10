from sqlalchemy import Column, Integer, String, DateTime, JSON, Text

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    role = Column(String(32), nullable=True)
    action = Column(String(64), nullable=False)
    action_label = Column(String(128), nullable=True)
    target_type = Column(String(32), nullable=False)
    target_id = Column(Integer, nullable=False)
    task_id = Column(Integer, nullable=True)
    item_id = Column(Integer, nullable=True)
    annotation_id = Column(Integer, nullable=True)
    submission_id = Column(Integer, nullable=True)
    work_key = Column(String(128), nullable=True)
    message = Column(Text, nullable=True)
    payload_json = Column(JSON, nullable=True)
    before_data = Column(JSON, nullable=True)
    after_data = Column(JSON, nullable=True)
    extra_info = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=True)
