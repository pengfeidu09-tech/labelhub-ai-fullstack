from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict


class AIReviewRequest(BaseModel):
    task_id: int
    dataset_item_id: int
    template_id: int


class AIReviewResultResponse(BaseModel):
    id: int
    job_id: int
    submission_id: int
    overall_score: float
    conclusion: str
    dimension_scores: List[Dict]
    issue_tags: List[str]
    review_comment: Optional[str]
    suggested_fix: Optional[str]
    confidence: float
    prompt_template: Optional[str]
    raw_response: Optional[str]
    parsed_result: Optional[Dict]
    mock_mode: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AIReviewJobResponse(BaseModel):
    id: int
    submission_id: int
    status: str
    prompt_template: Optional[str]
    retry_count: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HumanReviewCreate(BaseModel):
    comments: Optional[str] = None
    revised_data: Optional[Dict] = None


class HumanReviewResponse(BaseModel):
    id: int
    submission_id: int
    reviewer_id: int
    action: str
    comments: Optional[str]
    revised_data: Optional[Dict]
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewDetailResponse(BaseModel):
    submission: Dict
    dataset_item: Dict
    ai_review: Optional[AIReviewResultResponse]
    human_review: Optional[HumanReviewResponse]