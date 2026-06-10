from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class ExportCreateRequest(BaseModel):
    format: str = Field(..., pattern="^(json|jsonl|csv|xlsx)$")


class ExportJobResponse(BaseModel):
    id: int
    task_id: int
    user_id: int
    format: str
    status: str
    file_path: Optional[str]
    row_count: Optional[int]
    error_message: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ExportListResponse(BaseModel):
    items: list[ExportJobResponse]
    total: int
    page: int
    limit: int