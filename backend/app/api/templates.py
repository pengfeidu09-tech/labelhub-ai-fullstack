from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.models.template_schema import TemplateSchema
from app.services.template_service import (
    create_template, get_template, get_templates, update_template, delete_template,
    create_qa_quality_template, create_preference_compare_template, clone_template_version,
    get_task_template,
)
from app.schemas.template_schema import (
    TemplateSchemaCreate, TemplateSchemaUpdate, TemplateSchemaResponse, TemplateListResponse,
    TemplateCloneRequest
)

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.post("", response_model=TemplateSchemaResponse)
def create_template_endpoint(
    template: TemplateSchemaCreate,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    return create_template(db, template, user_id)


@router.get("")
def get_templates_endpoint(
    dataset_type: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    include_legacy: bool = False,
    task_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    result = get_templates(db, dataset_type, page, limit, include_legacy=include_legacy, task_id=task_id)

    # Enrich each template with task_name, linked_task_count, llm_assist_enabled
    from app.models.task import Task
    enriched_items = []
    for tpl in result["items"]:
        item_dict = {
            "id": tpl.id,
            "name": tpl.name,
            "description": tpl.description,
            "schema": tpl.schema,
            "schema_version": tpl.schema_version,
            "dataset_type": tpl.dataset_type,
            "frozen_after_publish": tpl.frozen_after_publish,
            "created_by": tpl.created_by,
            "created_at": tpl.created_at.isoformat() if tpl.created_at else None,
            "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None,
            "parent_template_id": tpl.parent_template_id,
            "is_active": tpl.is_active,
            "changelog": tpl.changelog,
            "task_id": tpl.task_id,
            "template_scope": tpl.template_scope,
            "is_task_bound": tpl.is_task_bound,
            "is_official_base": tpl.is_official_base,
            "is_archived": tpl.is_archived,
            "visible_in_template_page": tpl.visible_in_template_page,
            "legacy_reason": tpl.legacy_reason,
            # Enrichment fields
            "task_name": None,
            "linked_task_count": 0,
            "llm_assist_enabled": True,
        }
        if tpl.task_id:
            linked_task = db.query(Task).filter(Task.id == tpl.task_id).first()
            if linked_task:
                item_dict["task_name"] = linked_task.name
                item_dict["llm_assist_enabled"] = (
                    bool(linked_task.llm_assist_enabled)
                    if linked_task.llm_assist_enabled is not None
                    else True
                )
            item_dict["linked_task_count"] = 1
        enriched_items.append(item_dict)

    return {
        "items": enriched_items,
        "total": result["total"],
        "page": result["page"],
        "limit": result["limit"],
    }


# ── Task-bound template endpoints ──────────────────────────────────────────────
# NOTE: These must be defined BEFORE /{template_id} so that "task" is not
# captured as a template_id path parameter.

@router.get("/task/{task_id}/template")
def get_task_template_endpoint(task_id: int, db: Session = Depends(get_db)):
    """Return the task-bound template for this task."""
    from app.models.task import Task

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    template = None
    if task.template_id:
        template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()

    if not template:
        template = db.query(TemplateSchema).filter(
            TemplateSchema.task_id == task_id,
            TemplateSchema.is_task_bound == True,  # noqa: E712
            TemplateSchema.is_archived != True,  # noqa: E712
        ).first()

    if not template:
        raise HTTPException(status_code=404, detail="No template bound to this task")

    result = {
        "id": template.id,
        "name": template.name,
        "schema": template.schema,
        "schema_version": template.schema_version,
        "dataset_type": template.dataset_type,
        "template_scope": template.template_scope or "task_bound",
        "task_id": task_id,
        "task_name": task.name,
        "llm_assist_enabled": bool(task.llm_assist_enabled) if task.llm_assist_enabled is not None else True,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }
    return result


@router.put("/task/{task_id}/template")
def update_task_template_endpoint(
    task_id: int,
    update_data: dict,
    db: Session = Depends(get_db),
    user_id: int = Query(1),
):
    """Update the task-bound template for this task."""
    from app.models.task import Task

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if not task.template_id:
        raise HTTPException(status_code=400, detail="Task has no bound template")

    template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Bound template not found")

    if update_data.get("name"):
        template.name = update_data["name"]
    if update_data.get("schema"):
        template.schema = update_data["schema"]
    if update_data.get("description"):
        template.description = update_data["description"]

    from datetime import datetime, timezone
    template.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(template)

    return {"id": template.id, "name": template.name, "updated_at": template.updated_at.isoformat()}


@router.get("/{template_id}", response_model=TemplateSchemaResponse)
def get_template_endpoint(template_id: int, db: Session = Depends(get_db)):
    template = get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/{template_id}", response_model=TemplateSchemaResponse)
def update_template_endpoint(
    template_id: int,
    template: TemplateSchemaUpdate,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    updated_template = update_template(db, template_id, template, user_id)
    if not updated_template:
        raise HTTPException(status_code=404, detail="Template not found or frozen")
    return updated_template


@router.delete("/{template_id}")
def delete_template_endpoint(
    template_id: int,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    success = delete_template(db, template_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"message": "Template deleted successfully"}


@router.post("/{template_id}/clone-version", response_model=TemplateSchemaResponse)
def clone_template_version_endpoint(
    template_id: int,
    clone_request: TemplateCloneRequest,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    """
    克隆模板为新版本
    - 创建新版本模板，parent_template_id 指向原模板
    - 原模板 is_active 设为 False
    - 可指定新版本号和变更日志
    """
    new_template = clone_template_version(db, template_id, clone_request, user_id)
    if not new_template:
        raise HTTPException(status_code=404, detail="Template not found")
    return new_template


@router.post("/qa_quality", response_model=TemplateSchemaResponse)
def create_qa_quality_template_endpoint(
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    return create_qa_quality_template(db, user_id)


@router.post("/preference_compare", response_model=TemplateSchemaResponse)
def create_preference_compare_template_endpoint(
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    return create_preference_compare_template(db, user_id)
