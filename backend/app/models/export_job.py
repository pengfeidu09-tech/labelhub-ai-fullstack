from sqlalchemy import Column, Integer, String, Text, DateTime

from app.core.database import Base


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    format = Column(String(16), nullable=False)
    status = Column(String(32), nullable=False)
    file_path = Column(String(512), nullable=True)
    row_count = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
