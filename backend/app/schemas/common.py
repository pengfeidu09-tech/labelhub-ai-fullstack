from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any, List


class HealthResponse(BaseModel):
    status: str


class PageResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    limit: int


class AuditLogSchema(BaseModel):
    id: int
    user_id: int
    action: str
    target_type: str
    target_id: int
    before_data: Optional[dict]
    after_data: Optional[dict]
    extra_info: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    error: str
    message: str
    code: int = 400