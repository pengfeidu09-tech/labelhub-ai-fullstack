from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.services.audit_service import get_audit_logs, get_workbench_logs, log_action
from app.core.enums import AuditAction, AuditTargetType

router = APIRouter(prefix="/api/audit-logs", tags=["audit-logs"])


@router.get("")
def get_audit_logs_endpoint(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    task_id: Optional[int] = None,
    item_id: Optional[int] = None,
    work_key: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    result = get_audit_logs(db, user_id, action, target_type, target_id,
                            task_id=task_id, item_id=item_id, work_key=work_key,
                            page=page, limit=limit)
    items = []
    for item in result["items"]:
        items.append({
            "id": item.id,
            "user_id": item.user_id,
            "role": getattr(item, 'role', None),
            "action": item.action,
            "action_label": getattr(item, 'action_label', None),
            "target_type": item.target_type,
            "target_id": item.target_id,
            "task_id": getattr(item, 'task_id', None),
            "item_id": getattr(item, 'item_id', None),
            "annotation_id": getattr(item, 'annotation_id', None),
            "submission_id": getattr(item, 'submission_id', None),
            "work_key": getattr(item, 'work_key', None),
            "message": getattr(item, 'message', None),
            "payload_json": getattr(item, 'payload_json', None),
            "before_data": item.before_data,
            "after_data": item.after_data,
            "extra_info": item.extra_info,
            "created_at": item.created_at.isoformat() if item.created_at else None
        })
    return {"items": items, "total": result["total"], "page": result["page"], "limit": result["limit"]}


@router.get("/workbench")
def get_workbench_logs_endpoint(
    task_id: int,
    item_id: int,
    labeler_id: int = Query(2),
    work_key: Optional[str] = None,
    limit: int = Query(100),
    db: Session = Depends(get_db)
):
    items = get_workbench_logs(db, task_id, item_id, labeler_id, work_key, limit)
    result = []
    for item in items:
        result.append({
            "id": item.id,
            "user_id": item.user_id,
            "role": getattr(item, 'role', None),
            "action": item.action,
            "action_label": getattr(item, 'action_label', None),
            "target_type": item.target_type,
            "target_id": item.target_id,
            "task_id": getattr(item, 'task_id', None),
            "item_id": getattr(item, 'item_id', None),
            "work_key": getattr(item, 'work_key', None),
            "message": getattr(item, 'message', None),
            "payload_json": getattr(item, 'payload_json', None),
            "after_data": item.after_data,
            "extra_info": item.extra_info,
            "created_at": item.created_at.isoformat() if item.created_at else None
        })
    return {"items": result, "total": len(result)}


@router.post("")
def create_audit_log_entry(request: dict, db: Session = Depends(get_db)):
    try:
        action = request.get("action", "")
        user_id = request.get("user_id", 1)
        role = request.get("role", "owner")
        target_type = request.get("target_type", "system")
        target_id = request.get("target_id", 0)
        task_id = request.get("task_id")
        item_id = request.get("item_id")
        message = request.get("message", "")
        work_key = request.get("work_key")

        action_enum = None
        try:
            action_enum = AuditAction(action)
        except ValueError:
            pass

        target_type_enum = None
        try:
            target_type_enum = AuditTargetType(target_type)
        except ValueError:
            pass

        log_action(
            db=db,
            user_id=user_id,
            action=action_enum or action,
            target_type=target_type_enum or target_type,
            target_id=target_id,
            role=role,
            action_label=request.get("action_label", message[:30] if message else action),
            task_id=task_id,
            item_id=item_id,
            work_key=work_key,
            message=message,
            payload_json=request.get("payload_json") or request.get("detail")
        )

        return {"success": True, "message": "Audit log created"}
    except Exception as e:
        return {"success": False, "message": str(e)}
