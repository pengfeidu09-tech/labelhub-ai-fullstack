from sqlalchemy import Column, Integer, String, Text, DateTime, JSON

from app.core.database import Base


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, nullable=True)
    reviewer_id = Column(Integer, nullable=True)
    action = Column(String(32), nullable=False)
    comments = Column(Text, nullable=True)
    revised_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=True)
