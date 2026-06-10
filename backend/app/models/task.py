from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    template_id = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False)
    ai_review_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    ai_config = Column(JSON, nullable=True)
    deadline = Column(DateTime, nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    task_no = Column(String(32), nullable=True)
    work_mode = Column(String(32), nullable=True, default="single")
    phase = Column(String(32), nullable=True, default="annotation")
    team = Column(String(64), nullable=True)
    project_no = Column(String(32), nullable=True)

    # --- 官方数据集导入字段 ---
    source_namespace = Column(String(64), nullable=True)
    is_official_raw = Column(Boolean, nullable=True, default=False)
    is_default_demo = Column(Boolean, nullable=True, default=False)
    annotation_guide_md = Column(Text, nullable=True)

    # --- 标注 LLM 辅助配置 ---
    llm_assist_enabled = Column(Boolean, nullable=True, default=True)
