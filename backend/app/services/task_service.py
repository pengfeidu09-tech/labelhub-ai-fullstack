from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any

from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate
from app.core.enums import TaskStatus
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType


def create_task(db: Session, task_create: TaskCreate, user_id: int) -> Task:
    task = Task(
        name=task_create.name,
        description=task_create.description,
        template_id=task_create.template_id,
        status=TaskStatus.DRAFT.value,
        ai_review_enabled=task_create.ai_review_enabled,
        ai_config=task_create.ai_config,
        deadline=task_create.deadline,
        created_by=user_id,
        llm_assist_enabled=task_create.llm_assist_enabled if task_create.llm_assist_enabled is not None else True,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    
    log_action(
        db=db,
        user_id=user_id,
        action=AuditAction.TASK_CREATE,
        target_type=AuditTargetType.TASK,
        target_id=task.id,
        after_data={"name": task.name, "status": task.status}
    )
    
    return task


def get_task(db: Session, task_id: int) -> Optional[Task]:
    task = db.query(Task).filter(Task.id == task_id).first()
    if task and task.ai_review_enabled is None:
        task.ai_review_enabled = False
    return task


def get_tasks(db: Session, status: Optional[str] = None, page: int = 1, limit: int = 20) -> Dict[str, Any]:
    query = db.query(Task)
    
    if status:
        query = query.filter(Task.status == status)
    
    total = query.count()
    items = query.order_by(Task.created_at.desc())\
        .offset((page - 1) * limit)\
        .limit(limit)\
        .all()
    
    for item in items:
        if item.ai_review_enabled is None:
            item.ai_review_enabled = False
    
    return {"items": items, "total": total, "page": page, "limit": limit}


def update_task(db: Session, task_id: int, task_update: TaskUpdate, user_id: int) -> Optional[Task]:
    task = get_task(db, task_id)
    if not task:
        return None
    
    before_data = {
        "name": task.name,
        "description": task.description,
        "template_id": task.template_id,
        "ai_review_enabled": task.ai_review_enabled
    }
    
    if task_update.name is not None:
        task.name = task_update.name
    if task_update.description is not None:
        task.description = task_update.description
    if task_update.template_id is not None:
        task.template_id = task_update.template_id
    if task_update.ai_review_enabled is not None:
        task.ai_review_enabled = task_update.ai_review_enabled
    if task_update.ai_config is not None:
        task.ai_config = task_update.ai_config
    if task_update.deadline is not None:
        task.deadline = task_update.deadline
    if task_update.llm_assist_enabled is not None:
        task.llm_assist_enabled = task_update.llm_assist_enabled
    
    db.commit()
    db.refresh(task)
    
    return task


def delete_task(db: Session, task_id: int, user_id: int) -> bool:
    task = get_task(db, task_id)
    if not task:
        return False
    
    before_data = {"name": task.name, "status": task.status}
    db.delete(task)
    db.commit()
    
    log_action(
        db=db,
        user_id=user_id,
        action=AuditAction.TASK_END,
        target_type=AuditTargetType.TASK,
        target_id=task_id,
        before_data=before_data,
        after_data={"status": "deleted"}
    )
    
    return True


def publish_task(db: Session, task_id: int, user_id: int) -> Optional[Task]:
    task = get_task(db, task_id)
    if not task:
        return None
    
    if task.status != TaskStatus.DRAFT.value:
        return None
    
    before_data = {"status": task.status}
    task.status = TaskStatus.PUBLISHED.value
    db.commit()
    db.refresh(task)
    
    log_action(
        db=db,
        user_id=user_id,
        action=AuditAction.TASK_PUBLISH,
        target_type=AuditTargetType.TASK,
        target_id=task_id,
        before_data=before_data,
        after_data={"status": task.status}
    )
    
    return task


def pause_task(db: Session, task_id: int, user_id: int) -> Optional[Task]:
    task = get_task(db, task_id)
    if not task:
        return None
    
    if task.status != TaskStatus.PUBLISHED.value:
        return None
    
    before_data = {"status": task.status}
    task.status = TaskStatus.PAUSED.value
    db.commit()
    db.refresh(task)
    
    log_action(
        db=db,
        user_id=user_id,
        action=AuditAction.TASK_PAUSE,
        target_type=AuditTargetType.TASK,
        target_id=task_id,
        before_data=before_data,
        after_data={"status": task.status}
    )
    
    return task


def resume_task(db: Session, task_id: int, user_id: int) -> Optional[Task]:
    task = get_task(db, task_id)
    if not task:
        return None
    
    if task.status != TaskStatus.PAUSED.value:
        return None
    
    before_data = {"status": task.status}
    task.status = TaskStatus.PUBLISHED.value
    db.commit()
    db.refresh(task)
    
    log_action(
        db=db,
        user_id=user_id,
        action=AuditAction.TASK_PAUSE,
        target_type=AuditTargetType.TASK,
        target_id=task_id,
        before_data=before_data,
        after_data={"status": task.status}
    )
    
    return task


def end_task(db: Session, task_id: int, user_id: int) -> Optional[Task]:
    task = get_task(db, task_id)
    if not task:
        return None
    
    if task.status not in [TaskStatus.PUBLISHED.value, TaskStatus.PAUSED.value]:
        return None
    
    before_data = {"status": task.status}
    task.status = TaskStatus.ENDED.value
    db.commit()
    db.refresh(task)
    
    log_action(
        db=db,
        user_id=user_id,
        action=AuditAction.TASK_END,
        target_type=AuditTargetType.TASK,
        target_id=task_id,
        before_data=before_data,
        after_data={"status": task.status}
    )
    
    return task