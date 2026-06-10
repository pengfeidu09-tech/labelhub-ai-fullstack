from sqlalchemy import Column, Integer, String, Text, Float, DateTime, JSON, Boolean
from datetime import datetime, timezone

from app.core.database import Base


class AIReviewRun(Base):
    __tablename__ = "ai_review_runs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=True)
    item_id = Column(Integer, nullable=True)
    annotation_id = Column(Integer, nullable=True)
    submission_id = Column(Integer, nullable=True)
    labeler_id = Column(Integer, nullable=True)
    prompt_template_id = Column(Integer, nullable=True)
    prompt_version = Column(String(16), nullable=True)
    # provider / model / base_url：实际生效的 provider 信息
    model_provider = Column(String(32), nullable=True)
    model_name = Column(String(64), nullable=True)
    base_url = Column(String(256), nullable=True)
    input_snapshot_json = Column(JSON, nullable=True)
    output_json = Column(JSON, nullable=True)
    score = Column(Float, nullable=True)
    risk_level = Column(String(16), nullable=True)
    suggestion_action = Column(String(32), nullable=True)
    confidence = Column(Float, nullable=True)
    # status: pending / running / success / failed / fallback (使用 mock 兜底成功)
    status = Column(String(16), nullable=False, default="pending")
    error_type = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    raw_response_preview = Column(Text, nullable=True)
    used_fallback = Column(Boolean, nullable=True, default=False)
    retry_count = Column(Integer, nullable=True, default=0)
    latency_ms = Column(Integer, nullable=True)
    token_usage_json = Column(JSON, nullable=True)
    trigger_type = Column(String(32), nullable=True)
    created_at = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
