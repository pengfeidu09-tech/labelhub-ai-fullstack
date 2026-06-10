from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, Union, List
from datetime import datetime, timezone

from app.models.audit_log import AuditLog
from app.core.enums import AuditAction, AuditTargetType


def _normalize_enum(value):
    if hasattr(value, 'value'):
        return value.value
    return str(value)


def create_audit_log(
    db: Session,
    user_id: int,
    action,
    target_type,
    target_id: int,
    role: Optional[str] = None,
    action_label: Optional[str] = None,
    task_id: Optional[int] = None,
    item_id: Optional[int] = None,
    annotation_id: Optional[int] = None,
    submission_id: Optional[int] = None,
    work_key: Optional[str] = None,
    message: Optional[str] = None,
    payload_json: Optional[Dict[str, Any]] = None,
    before_data: Optional[Dict[str, Any]] = None,
    after_data: Optional[Dict[str, Any]] = None,
    extra_info: Optional[Dict[str, Any]] = None
):
    log = AuditLog(
        user_id=user_id,
        role=role,
        action=_normalize_enum(action),
        action_label=action_label,
        target_type=_normalize_enum(target_type),
        target_id=target_id,
        task_id=task_id,
        item_id=item_id,
        annotation_id=annotation_id,
        submission_id=submission_id,
        work_key=work_key,
        message=message,
        payload_json=payload_json,
        before_data=before_data,
        after_data=after_data,
        extra_info=extra_info,
        created_at=datetime.now(timezone.utc)
    )
    db.add(log)
    db.commit()
    return log


def log_action(
    db: Session,
    user_id: int,
    action: AuditAction,
    target_type: AuditTargetType,
    target_id: int,
    role: Optional[str] = None,
    action_label: Optional[str] = None,
    task_id: Optional[int] = None,
    item_id: Optional[int] = None,
    annotation_id: Optional[int] = None,
    submission_id: Optional[int] = None,
    work_key: Optional[str] = None,
    message: Optional[str] = None,
    payload_json: Optional[Dict[str, Any]] = None,
    before_data: Optional[Dict[str, Any]] = None,
    after_data: Optional[Dict[str, Any]] = None,
    extra_info: Optional[Dict[str, Any]] = None
):
    return create_audit_log(
        db=db,
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        role=role,
        action_label=action_label,
        task_id=task_id,
        item_id=item_id,
        annotation_id=annotation_id,
        submission_id=submission_id,
        work_key=work_key,
        message=message,
        payload_json=payload_json,
        before_data=before_data,
        after_data=after_data,
        extra_info=extra_info
    )


def get_audit_logs(
    db: Session,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    task_id: Optional[int] = None,
    item_id: Optional[int] = None,
    work_key: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    page: int = 1,
    limit: int = 20
):
    query = db.query(AuditLog)

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        action_str = _normalize_enum(action)
        query = query.filter(AuditLog.action == action_str)
    if target_type:
        query = query.filter(AuditLog.target_type == _normalize_enum(target_type))
    if target_id:
        query = query.filter(AuditLog.target_id == target_id)
    if task_id:
        query = query.filter(AuditLog.task_id == task_id)
    if item_id:
        query = query.filter(AuditLog.item_id == item_id)
    if work_key:
        query = query.filter(AuditLog.work_key == work_key)
    if start_time:
        query = query.filter(AuditLog.created_at >= start_time)
    if end_time:
        query = query.filter(AuditLog.created_at <= end_time)

    total = query.count()
    items = query.order_by(AuditLog.id.desc())\
        .offset((page - 1) * limit)\
        .limit(limit)\
        .all()

    return {"items": items, "total": total, "page": page, "limit": limit}


def get_workbench_logs(
    db: Session,
    task_id: int,
    item_id: int,
    labeler_id: int,
    work_key: Optional[str] = None,
    limit: int = 100
):
    query = db.query(AuditLog).filter(
        AuditLog.task_id == task_id,
        AuditLog.item_id == item_id,
        AuditLog.user_id == labeler_id
    )
    if work_key:
        query = query.filter(AuditLog.work_key == work_key)

    workbench_actions = [
        "open_item", "claim_item", "draft_save", "ai_precheck_run",
        "ai_precheck_success", "ai_precheck_failed", "submission_submit",
        "session_heartbeat", "session_close", "resume_active_item",
        "item_claim"
    ]
    query = query.filter(AuditLog.action.in_(workbench_actions))

    items = query.order_by(AuditLog.id.desc()).limit(limit).all()
    return items
