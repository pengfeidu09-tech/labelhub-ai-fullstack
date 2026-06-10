from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any


class TaskCreate(BaseModel):
    name: str
    description: Optional[str] = None
    template_id: int
    ai_review_enabled: Optional[bool] = False
    ai_config: Optional[dict] = None
    deadline: Optional[datetime] = None
    llm_assist_enabled: Optional[bool] = True


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template_id: Optional[int] = None
    ai_review_enabled: Optional[bool] = None
    ai_config: Optional[dict] = None
    deadline: Optional[datetime] = None
    llm_assist_enabled: Optional[bool] = None


class TaskResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    template_id: Optional[int] = None
    status: str
    ai_review_enabled: Optional[bool] = False
    ai_config: Optional[dict] = None
    deadline: Optional[datetime] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    source_namespace: Optional[str] = None
    is_official_raw: Optional[bool] = False
    is_default_demo: Optional[bool] = False
    llm_assist_enabled: Optional[bool] = True
    task_no: Optional[str] = None
    work_mode: Optional[str] = None
    phase: Optional[str] = None
    team: Optional[str] = None
    project_no: Optional[str] = None
    annotation_guide_md: Optional[str] = None

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    page: int
    limit: int