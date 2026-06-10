from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON

from app.core.database import Base


class TemplateSchema(Base):
    __tablename__ = "template_schemas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    schema = Column(JSON, nullable=False)
    schema_version = Column(String(16), nullable=False)
    dataset_type = Column(String(32), nullable=False)
    frozen_after_publish = Column(Boolean, nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    parent_template_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, nullable=True)
    changelog = Column(Text, nullable=True)

    # ── 模板-任务绑定字段 ──
    task_id = Column(Integer, nullable=True)
    template_scope = Column(String(32), nullable=True, default="official_base")
    is_task_bound = Column(Boolean, nullable=True, default=False)
    is_official_base = Column(Boolean, nullable=True, default=False)
    is_archived = Column(Boolean, nullable=True, default=False)
    visible_in_template_page = Column(Boolean, nullable=True, default=True)
    legacy_reason = Column(String(64), nullable=True)
