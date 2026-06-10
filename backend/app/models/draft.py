from sqlalchemy import Column, Integer, DateTime, JSON

from app.core.database import Base


class Draft(Base):
    __tablename__ = "drafts"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=True)
    dataset_item_id = Column(Integer, nullable=True)
    labeler_id = Column(Integer, nullable=True)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
