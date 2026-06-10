from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, JSON

from app.core.database import Base


class AIReviewJob(Base):
    __tablename__ = "ai_review_jobs"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False)
    prompt_template = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class AIReviewResult(Base):
    __tablename__ = "ai_review_results"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, nullable=True)
    submission_id = Column(Integer, nullable=True)
    overall_score = Column(Float, nullable=True)
    conclusion = Column(String(32), nullable=False)
    dimension_scores = Column(JSON, nullable=True)
    issue_tags = Column(JSON, nullable=True)
    review_comment = Column(Text, nullable=True)
    suggested_fix = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    prompt_template = Column(Text, nullable=True)
    raw_response = Column(Text, nullable=True)
    parsed_result = Column(JSON, nullable=True)
    mock_mode = Column(Boolean, nullable=True)
    created_at = Column(DateTime, nullable=True)
