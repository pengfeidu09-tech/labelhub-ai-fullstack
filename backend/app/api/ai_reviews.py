# LEGACY: This API uses AIReviewJob/AIReviewResult tables.
# The new Agent API is at /api/agent (using AIReviewRun).
# Kept for backward compatibility only.

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from app.core.database import get_db
from app.services.ai_review_service import run_mock_review, get_ai_review_result, mock_ai_review
from app.schemas.review import AIReviewResultResponse
from app.models.dataset_item import DatasetItem
from app.models.submission import Submission

router = APIRouter(prefix="/api/ai-reviews", tags=["ai-reviews"])


class AIReviewRequestBody(BaseModel):
    task_id: int
    dataset_item_id: int
    template_schema: Optional[Dict[str, Any]] = Field(None, alias="schema_json")

    model_config = ConfigDict(populate_by_name=True)


@router.post("/review")
def generate_review(request: AIReviewRequestBody, db: Session = Depends(get_db)):
    dataset_item = db.query(DatasetItem).filter(DatasetItem.id == request.dataset_item_id).first()
    if not dataset_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    item_data = dataset_item.raw_data_json or {}
    ai_review = mock_ai_review(item_data, request.template_schema)
    
    submission = db.query(Submission).filter(
        Submission.task_id == request.task_id,
        Submission.dataset_item_id == request.dataset_item_id
    ).first()
    
    if submission:
        submission.ai_review = ai_review
        db.commit()
    
    return {"success": True, "ai_review": ai_review}


@router.post("/{submission_id}", response_model=AIReviewResultResponse)
def trigger_ai_review(submission_id: int, db: Session = Depends(get_db)):
    result = run_mock_review(db, submission_id)
    if not result:
        raise HTTPException(status_code=404, detail="Submission not found")
    return result


@router.get("/{submission_id}", response_model=AIReviewResultResponse)
def get_ai_review(submission_id: int, db: Session = Depends(get_db)):
    result = get_ai_review_result(db, submission_id)
    if not result:
        raise HTTPException(status_code=404, detail="AI review result not found")
    return result