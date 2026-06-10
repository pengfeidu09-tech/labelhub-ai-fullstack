from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any


class DatasetImportRequest(BaseModel):
    task_id: int
    data: list[dict]


class DatasetImportDemoRequest(BaseModel):
    task_id: int
    dataset_type: str = Field(..., pattern="^(qa_quality|preference_compare)$")


class DatasetItemResponse(BaseModel):
    id: int
    task_id: int
    external_id: Optional[str]
    dataset_type: str
    raw_data_json: dict
    hidden_reference_json: Optional[dict]
    status: str
    claimed_by: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DatasetListResponse(BaseModel):
    items: list[DatasetItemResponse]
    total: int
    page: int
    limit: int