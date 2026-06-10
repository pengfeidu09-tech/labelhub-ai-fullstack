from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any


class DraftSaveRequest(BaseModel):
    task_id: int
    dataset_item_id: int
    labeler_id: int
    template_id: Optional[int] = None
    data: dict
    ai_review: Optional[dict] = None


class SubmissionSubmitRequest(BaseModel):
    task_id: int
    dataset_item_id: int
    labeler_id: int
    template_id: Optional[int] = None
    data: dict
    result: Optional[dict] = None
    annotation_result: Optional[dict] = None
    ai_review: Optional[dict] = None
    status: Optional[str] = None


class DraftResponse(BaseModel):
    id: int
    task_id: int
    dataset_item_id: int
    labeler_id: int
    data: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubmissionResponse(BaseModel):
    id: int
    task_id: int
    dataset_item_id: int
    labeler_id: int
    data: dict
    status: str
    rejected_reason: Optional[str]
    revision_no: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubmissionListResponse(BaseModel):
    items: list[SubmissionResponse]
    total: int
    page: int
    limit: int