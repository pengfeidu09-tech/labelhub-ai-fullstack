from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone, timedelta
import traceback
import logging

logger = logging.getLogger("workbench_session")

from app.core.database import get_db
from app.models.annotation_work_session import AnnotationWorkSession
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType

router = APIRouter(prefix="/api/labeler/workbench", tags=["workbench-session"])


def _make_aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def calculate_elapsed_seconds(session: AnnotationWorkSession, server_now: datetime) -> int:
    if session.status == "active":
        started = _make_aware(session.started_at)
        if started:
            delta = (server_now - started).total_seconds()
            return int(session.accumulated_seconds or 0) + max(0, int(delta))
        return int(session.accumulated_seconds or 0)
    return int(session.accumulated_seconds or 0)


def _close_stale_sessions(db: Session, labeler_id: int, now: datetime):
    threshold = now - timedelta(minutes=5)
    stale = db.query(AnnotationWorkSession).filter(
        AnnotationWorkSession.labeler_id == labeler_id,
        AnnotationWorkSession.status == "active",
        AnnotationWorkSession.last_heartbeat_at < threshold
    ).all()
    for s in stale:
        started = _make_aware(s.started_at)
        if started and s.last_heartbeat_at:
            hb = _make_aware(s.last_heartbeat_at)
            delta = max(0, int((hb - started).total_seconds()))
            s.accumulated_seconds = (s.accumulated_seconds or 0) + delta
        s.status = "stopped"
        s.started_at = None
        s.ended_at = s.ended_at or now
        s.closed_at = now
        s.updated_at = now
    if stale:
        db.commit()


def _get_total_elapsed_for_item(db: Session, task_id: int, item_id: int, labeler_id: int, now: datetime) -> int:
    sessions = db.query(AnnotationWorkSession).filter(
        AnnotationWorkSession.task_id == task_id,
        AnnotationWorkSession.item_id == item_id,
        AnnotationWorkSession.labeler_id == labeler_id
    ).all()
    total = 0
    for s in sessions:
        total += calculate_elapsed_seconds(s, now)
    return total


@router.get("/current")
def get_current_session(
    task_id: int,
    item_id: int,
    labeler_id: int = 2,
    db: Session = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    _close_stale_sessions(db, labeler_id, now)

    active_session = db.query(AnnotationWorkSession).filter(
        AnnotationWorkSession.task_id == task_id,
        AnnotationWorkSession.item_id == item_id,
        AnnotationWorkSession.labeler_id == labeler_id,
        AnnotationWorkSession.status == "active"
    ).first()

    if active_session:
        elapsed = calculate_elapsed_seconds(active_session, now)
        return {
            "success": True,
            "is_active": True,
            "session": {
                "id": active_session.id,
                "status": active_session.status,
                "started_at": active_session.started_at.isoformat() if active_session.started_at else None,
                "accumulated_seconds": active_session.accumulated_seconds,
            },
            "elapsed_seconds": elapsed
        }

    paused_session = db.query(AnnotationWorkSession).filter(
        AnnotationWorkSession.task_id == task_id,
        AnnotationWorkSession.item_id == item_id,
        AnnotationWorkSession.labeler_id == labeler_id,
        AnnotationWorkSession.status == "paused"
    ).first()

    if paused_session:
        elapsed = calculate_elapsed_seconds(paused_session, now)
        return {
            "success": True,
            "is_active": False,
            "session": {
                "id": paused_session.id,
                "status": paused_session.status,
                "started_at": paused_session.started_at.isoformat() if paused_session.started_at else None,
                "accumulated_seconds": paused_session.accumulated_seconds,
            },
            "elapsed_seconds": elapsed
        }

    total_elapsed = _get_total_elapsed_for_item(db, task_id, item_id, labeler_id, now)
    return {
        "success": True,
        "is_active": False,
        "session": None,
        "elapsed_seconds": total_elapsed
    }


@router.post("/start")
def start_work_session(request: dict, db: Session = Depends(get_db)):
    task_id = request.get("task_id")
    item_id = request.get("item_id")
    labeler_id = request.get("labeler_id", 2)
    work_key = request.get("work_key")
    annotation_id = request.get("annotation_id")

    if not task_id or not item_id:
        raise HTTPException(status_code=400, detail="task_id and item_id required")

    now = datetime.now(timezone.utc)
    _close_stale_sessions(db, labeler_id, now)

    active_session = db.query(AnnotationWorkSession).filter(
        AnnotationWorkSession.task_id == task_id,
        AnnotationWorkSession.item_id == item_id,
        AnnotationWorkSession.labeler_id == labeler_id,
        AnnotationWorkSession.status == "active"
    ).first()

    if active_session:
        elapsed = calculate_elapsed_seconds(active_session, now)
        total_elapsed = _get_total_elapsed_for_item(db, task_id, item_id, labeler_id, now)
        active_session.last_heartbeat_at = now
        active_session.updated_at = now
        db.commit()

        logger.debug(f"[work_session] event=open_resume userId={labeler_id} taskId={task_id} itemId={item_id} sessionId={active_session.id} accumulated={active_session.accumulated_seconds} elapsed={elapsed} totalElapsed={total_elapsed}")

        try:
            log_action(
                db=db, user_id=labeler_id, action=AuditAction.OPEN_ITEM,
                target_type=AuditTargetType.DATASET_ITEM, target_id=item_id,
                role="labeler", action_label="恢复工作会话",
                task_id=task_id, item_id=item_id, work_key=work_key,
                message=f"恢复活跃会话 Session #{active_session.id}",
                payload_json={"session_id": active_session.id, "action": "work_session_resume", "elapsed_seconds": total_elapsed}
            )
        except Exception:
            pass

        return {
            "success": True,
            "session_id": active_session.id,
            "status": "resumed",
            "session_status": "active",
            "accumulated_seconds": int(active_session.accumulated_seconds or 0),
            "persisted_elapsed_seconds": total_elapsed,
            "started_at": active_session.started_at.isoformat() if active_session.started_at else None
        }

    paused_session = db.query(AnnotationWorkSession).filter(
        AnnotationWorkSession.task_id == task_id,
        AnnotationWorkSession.item_id == item_id,
        AnnotationWorkSession.labeler_id == labeler_id,
        AnnotationWorkSession.status == "paused"
    ).first()

    if paused_session:
        paused_session.status = "active"
        paused_session.started_at = now
        paused_session.last_heartbeat_at = now
        paused_session.updated_at = now
        db.commit()

        total_elapsed = _get_total_elapsed_for_item(db, task_id, item_id, labeler_id, now)

        logger.debug(f"[work_session] event=open_resume_paused userId={labeler_id} taskId={task_id} itemId={item_id} sessionId={paused_session.id} accumulated={paused_session.accumulated_seconds} totalElapsed={total_elapsed}")

        try:
            log_action(
                db=db, user_id=labeler_id, action=AuditAction.OPEN_ITEM,
                target_type=AuditTargetType.DATASET_ITEM, target_id=item_id,
                role="labeler", action_label="恢复工作会话",
                task_id=task_id, item_id=item_id, work_key=work_key,
                message=f"恢复暂停会话 Session #{paused_session.id}",
                payload_json={"session_id": paused_session.id, "action": "work_session_resume", "elapsed_seconds": total_elapsed}
            )
        except Exception:
            pass

        return {
            "success": True,
            "session_id": paused_session.id,
            "status": "resumed",
            "session_status": "active",
            "accumulated_seconds": int(paused_session.accumulated_seconds or 0),
            "persisted_elapsed_seconds": total_elapsed,
            "started_at": paused_session.started_at.isoformat() if paused_session.started_at else None
        }

    session = AnnotationWorkSession(
        task_id=task_id,
        item_id=item_id,
        labeler_id=labeler_id,
        work_key=work_key or f"{task_id}:{item_id}:{labeler_id}",
        annotation_id=annotation_id,
        status="active",
        opened_at=now,
        started_at=now,
        last_heartbeat_at=now,
        accumulated_seconds=0.0
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    prior_seconds = _get_total_elapsed_for_item(db, task_id, item_id, labeler_id, now)

    logger.debug(f"[work_session] event=open_new userId={labeler_id} taskId={task_id} itemId={item_id} sessionId={session.id} accumulated=0 priorSeconds={prior_seconds}")

    try:
        log_action(
            db=db, user_id=labeler_id, action=AuditAction.OPEN_ITEM,
            target_type=AuditTargetType.DATASET_ITEM, target_id=item_id,
            role="labeler", action_label="打开题目",
            task_id=task_id, item_id=item_id, work_key=work_key,
            message=f"打开 Task #{task_id} / Item #{item_id}",
            payload_json={"session_id": session.id, "action": "work_session_start", "elapsed_seconds": prior_seconds}
        )
    except Exception:
        pass

    return {
        "success": True,
        "session_id": session.id,
        "status": "created",
        "session_status": "active",
        "accumulated_seconds": 0,
        "persisted_elapsed_seconds": prior_seconds,
        "started_at": session.started_at.isoformat() if session.started_at else None
    }


@router.post("/pause")
def pause_work_session(request: dict, db: Session = Depends(get_db)):
    session_id = request.get("session_id")
    labeler_id = request.get("labeler_id", 2)

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    now = datetime.now(timezone.utc)
    session = db.query(AnnotationWorkSession).filter(AnnotationWorkSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status == "active":
        started = _make_aware(session.started_at)
        if started:
            delta = max(0, int((now - started).total_seconds()))
            session.accumulated_seconds = (session.accumulated_seconds or 0) + delta
        session.status = "paused"
        session.started_at = None
        session.updated_at = now
        db.commit()

    total_elapsed = _get_total_elapsed_for_item(db, session.task_id, session.item_id, session.labeler_id, now)

    try:
        log_action(
            db=db, user_id=labeler_id, action=AuditAction.SESSION_CLOSE,
            target_type=AuditTargetType.DATASET_ITEM, target_id=session.item_id,
            role="labeler", action_label="暂停工作会话",
            task_id=session.task_id, item_id=session.item_id, work_key=session.work_key,
            message=f"暂停会话，累计 {int(session.accumulated_seconds or 0)}秒",
            payload_json={"session_id": session.id, "action": "work_session_pause", "accumulated_seconds": int(session.accumulated_seconds or 0), "elapsed_seconds": total_elapsed}
        )
    except Exception:
        pass

    return {
        "success": True,
        "session_id": session.id,
        "status": session.status,
        "accumulated_seconds": int(session.accumulated_seconds or 0),
        "elapsed_seconds": total_elapsed
    }


@router.post("/stop")
def stop_work_session(request: dict, db: Session = Depends(get_db)):
    session_id = request.get("session_id")
    labeler_id = request.get("labeler_id", 2)

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    now = datetime.now(timezone.utc)
    session = db.query(AnnotationWorkSession).filter(AnnotationWorkSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 幂等：如果 session 已关闭，直接返回不重复写入审计日志
    if session.status in ["stopped", "skipped", "submitted"]:
        total_elapsed = _get_total_elapsed_for_item(db, session.task_id, session.item_id, session.labeler_id, now)
        return {
            "success": True,
            "session_id": session.id,
            "status": session.status,
            "accumulated_seconds": int(session.accumulated_seconds or 0),
            "elapsed_seconds": total_elapsed
        }

    if session.status == "active":
        started = _make_aware(session.started_at)
        if started:
            delta = max(0, int((now - started).total_seconds()))
            session.accumulated_seconds = (session.accumulated_seconds or 0) + delta
        session.status = "stopped"
        session.started_at = None
        session.ended_at = session.ended_at or now
        session.closed_at = now
        session.updated_at = now
        db.commit()

    total_elapsed = _get_total_elapsed_for_item(db, session.task_id, session.item_id, session.labeler_id, now)

    logger.debug(f"[work_session] event=close sessionId={session.id} userId={labeler_id} taskId={session.task_id} itemId={session.item_id} accumulated={session.accumulated_seconds} totalElapsed={total_elapsed}")

    try:
        log_action(
            db=db, user_id=labeler_id, action=AuditAction.SESSION_CLOSE,
            target_type=AuditTargetType.DATASET_ITEM, target_id=session.item_id,
            role="labeler", action_label="停止工作会话",
            task_id=session.task_id, item_id=session.item_id, work_key=session.work_key,
            message=f"停止会话，累计 {int(session.accumulated_seconds or 0)}秒",
            payload_json={"session_id": session.id, "action": "work_session_stop", "accumulated_seconds": int(session.accumulated_seconds or 0), "elapsed_seconds": total_elapsed}
        )
    except Exception:
        pass

    return {
        "success": True,
        "session_id": session.id,
        "status": session.status,
        "accumulated_seconds": int(session.accumulated_seconds or 0),
        "elapsed_seconds": total_elapsed
    }


@router.post("/submit")
def submit_work_session(request: dict, db: Session = Depends(get_db)):
    session_id = request.get("session_id")
    labeler_id = request.get("labeler_id", 2)
    duration_seconds = request.get("duration_seconds")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    now = datetime.now(timezone.utc)
    session = db.query(AnnotationWorkSession).filter(AnnotationWorkSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status == "active":
        started = _make_aware(session.started_at)
        if started:
            delta = max(0, int((now - started).total_seconds()))
            session.accumulated_seconds = (session.accumulated_seconds or 0) + delta
        session.status = "submitted"
        session.started_at = None
        session.ended_at = now
        session.closed_at = now
        session.updated_at = now
        if duration_seconds is not None:
            try:
                session.accumulated_seconds = float(duration_seconds)
            except (ValueError, TypeError):
                pass
        db.commit()

    total_elapsed = _get_total_elapsed_for_item(db, session.task_id, session.item_id, session.labeler_id, now)

    try:
        log_action(
            db=db, user_id=labeler_id, action=AuditAction.WORK_SESSION_SUBMIT,
            target_type=AuditTargetType.DATASET_ITEM, target_id=session.item_id,
            role="labeler", action_label="提交工作会话",
            task_id=session.task_id, item_id=session.item_id, work_key=session.work_key,
            message=f"提交会话，累计 {int(session.accumulated_seconds or 0)}秒",
            payload_json={"session_id": session.id, "action": "work_session_submit", "accumulated_seconds": int(session.accumulated_seconds or 0), "elapsed_seconds": total_elapsed}
        )
    except Exception:
        pass

    return {
        "success": True,
        "session_id": session.id,
        "status": session.status,
        "accumulated_seconds": int(session.accumulated_seconds or 0),
        "elapsed_seconds": total_elapsed
    }


@router.post("/heartbeat")
def heartbeat_session(request: dict, db: Session = Depends(get_db)):
    session_id = request.get("session_id")
    labeler_id = request.get("labeler_id", 2)

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    now = datetime.now(timezone.utc)
    session = db.query(AnnotationWorkSession).filter(AnnotationWorkSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status == "active":
        session.last_heartbeat_at = now
        session.updated_at = now
        db.commit()

    total_elapsed = _get_total_elapsed_for_item(db, session.task_id, session.item_id, session.labeler_id, now)

    logger.debug(f"[work_session] event=heartbeat sessionId={session.id} userId={labeler_id} taskId={session.task_id} itemId={session.item_id} accumulated={session.accumulated_seconds} totalElapsed={total_elapsed}")

    return {
        "success": True,
        "session_id": session.id,
        "persisted_elapsed_seconds": total_elapsed,
        "accumulated_seconds": int(session.accumulated_seconds or 0),
        "status": session.status
    }


@router.post("/open")
def open_session_alias(request: dict, db: Session = Depends(get_db)):
    return start_work_session(request, db)


@router.post("/close")
def close_session_alias(request: dict, db: Session = Depends(get_db)):
    return stop_work_session(request, db)


@router.post("/skip")
def skip_workbench_item(request: dict, db: Session = Depends(get_db)):
    task_id = request.get("task_id")
    item_id = request.get("item_id") or request.get("dataset_item_id")
    labeler_id = request.get("labeler_id", 2)
    work_key = request.get("work_key")
    skip_reason = request.get("skip_reason")

    if not task_id or not item_id:
        raise HTTPException(status_code=400, detail="task_id and item_id required")

    now = datetime.now(timezone.utc)

    # Find the active or paused session for this task/item/labeler
    session = db.query(AnnotationWorkSession).filter(
        AnnotationWorkSession.task_id == task_id,
        AnnotationWorkSession.item_id == item_id,
        AnnotationWorkSession.labeler_id == labeler_id,
        AnnotationWorkSession.status.in_(["active", "paused"])
    ).first()

    elapsed_seconds = 0
    skipped_item_id = item_id

    if session:
        # Accumulate time if active
        if session.status == "active":
            started = _make_aware(session.started_at)
            if started:
                delta = max(0, int((now - started).total_seconds()))
                session.accumulated_seconds = (session.accumulated_seconds or 0) + delta

        # Mark session as skipped
        session.status = "skipped"
        session.started_at = None
        session.ended_at = session.ended_at or now
        session.closed_at = now
        session.updated_at = now
        db.commit()

        elapsed_seconds = _get_total_elapsed_for_item(db, task_id, item_id, labeler_id, now)
        skipped_item_id = session.item_id

    # Create audit log for the skip action
    try:
        log_action(
            db=db,
            user_id=labeler_id,
            action=AuditAction.SKIP_ITEM,
            target_type=AuditTargetType.DATASET_ITEM,
            target_id=item_id,
            role="labeler",
            action_label="跳过题目",
            task_id=task_id,
            item_id=item_id,
            work_key=work_key,
            message=f"跳过题目{f'，原因: {skip_reason}' if skip_reason else ''}",
            payload_json={"skip_reason": skip_reason, "elapsed_seconds": elapsed_seconds} if skip_reason else {"elapsed_seconds": elapsed_seconds},
        )
    except Exception:
        pass

    # 更新 annotations.json 中对应的 annotation 状态为 skipped
    from app.services.annotation_service import _load_annotations, _save_annotations
    annotations = _load_annotations()
    skip_work_key = f"{task_id}:{item_id}:{labeler_id}"
    for ann in annotations:
        ann_wk = f"{ann.get('task_id')}:{ann.get('dataset_item_id')}:{ann.get('labeler_id')}"
        if ann_wk == skip_work_key and ann.get("status") in ["claimed", "draft", "drafting", "in_progress"]:
            ann["status"] = "skipped"
            ann["updated_at"] = now.isoformat()
    _save_annotations(annotations)

    # 释放 DatasetItem，让其他标注员可领取，但标记当前 labeler 已跳过
    from app.models.dataset_item import DatasetItem
    from app.core.enums import ItemStatus
    
    item = db.query(DatasetItem).filter(DatasetItem.id == item_id).first()
    if item:
        # 将状态设置为 unclaimed，清除 claimed_by，但标记 skipped_by 防止同一 labeler 再领
        item.status = ItemStatus.UNCLAIMED.value
        item.claimed_by = None
        item.skipped_by = labeler_id  # 标记当前 labeler 已跳过
        item.updated_at = now
        db.commit()

    # 查找下一个可用 item（排除当前 labeler 已跳过的）
    from sqlalchemy import or_
    next_item = None
    next_item_query = db.query(DatasetItem).filter(
        DatasetItem.status == ItemStatus.UNCLAIMED.value,
        or_(DatasetItem.skipped_by == None, DatasetItem.skipped_by != labeler_id)
    )
    if task_id:
        next_item_query = next_item_query.filter(DatasetItem.task_id == task_id)
    
    # 也排除已有 terminal annotation 的 item
    from app.services.annotation_service import get_work_key_groups
    groups = get_work_key_groups(labeler_id)
    terminal_work_keys = groups["terminal_work_keys"]
    
    candidate_items = next_item_query.all()
    for candidate in candidate_items:
        candidate_wk = f"{candidate.task_id}:{candidate.id}:{labeler_id}"
        if candidate_wk in terminal_work_keys:
            continue
        # 防回流：不允许 next_item 和 skipped_item 相同
        if candidate.id == skipped_item_id:
            continue
        next_item = candidate
        break

    next_item_info = None
    if next_item:
        from app.models.task import Task
        from app.models.template_schema import TemplateSchema
        task_obj = db.query(Task).filter(Task.id == next_item.task_id).first()
        template_id = task_obj.template_id if task_obj else None
        resolved_template = None
        if task_obj and task_obj.template_id:
            resolved_template = db.query(TemplateSchema).filter(TemplateSchema.id == task_obj.template_id).first()

        next_work_key = f"{next_item.task_id}:{next_item.id}:{labeler_id}"
        next_item_info = {
            "id": next_item.id,
            "task_id": next_item.task_id,
            "work_key": next_work_key,
            "display_title": f"Task #{next_item.task_id} / Item #{next_item.id}",
            "status": "unclaimed",
            "item_data": next_item.raw_data_json,
            "template_id": template_id,
            "schema_json": resolved_template.schema if resolved_template else None,
            "task_name": task_obj.name if task_obj else None
        }
    else:
        logger.warning(f"[skip] no next_item found after skipping item_id={skipped_item_id}, labeler_id={labeler_id}")

    return {
        "success": True,
        "message": "已跳过当前数据",
        "skipped_item_id": skipped_item_id,
        "elapsed_seconds": elapsed_seconds,
        "next_item": next_item_info,
    }


@router.get("/elapsed")
def get_elapsed_time(
    task_id: int,
    item_id: int,
    labeler_id: int = 2,
    db: Session = Depends(get_db)
):
    now = datetime.now(timezone.utc)

    sessions = db.query(AnnotationWorkSession).filter(
        AnnotationWorkSession.task_id == task_id,
        AnnotationWorkSession.item_id == item_id,
        AnnotationWorkSession.labeler_id == labeler_id
    ).all()

    total_seconds = 0
    active_session = None

    for s in sessions:
        if s.status == "active":
            active_session = s
        total_seconds += calculate_elapsed_seconds(s, now)

    logger.debug(f"[work_session] event=elapsed userId={labeler_id} taskId={task_id} itemId={item_id} totalSeconds={total_seconds} sessionsCount={len(sessions)}")

    return {
        "success": True,
        "persisted_elapsed_seconds": total_seconds,
        "active_session_id": active_session.id if active_session else None,
        "sessions_count": len(sessions)
    }


@router.post("/mark-invalid")
def mark_workbench_item_invalid(request: dict, db: Session = Depends(get_db)):
    task_id = request.get("task_id")
    item_id = request.get("item_id") or request.get("dataset_item_id")
    labeler_id = request.get("labeler_id", 2)
    work_key = request.get("work_key")
    reason = request.get("invalid_reason") or request.get("reason")
    remark = request.get("invalid_remark") or request.get("remark") or ""

    if not task_id or not item_id:
        raise HTTPException(status_code=400, detail="task_id and item_id required")

    now = datetime.now(timezone.utc)

    # 1. 找到当前 work session
    session = db.query(AnnotationWorkSession).filter(
        AnnotationWorkSession.task_id == task_id,
        AnnotationWorkSession.item_id == item_id,
        AnnotationWorkSession.labeler_id == labeler_id,
        AnnotationWorkSession.status.in_(["active", "paused"])
    ).first()

    elapsed_seconds = 0

    if session:
        # 2. 累计并保存当前工时
        if session.status == "active":
            started = _make_aware(session.started_at)
            if started:
                delta = max(0, int((now - started).total_seconds()))
                session.accumulated_seconds = (session.accumulated_seconds or 0) + delta

        # 3. 将 session.status 设置为 stopped
        session.status = "stopped"
        session.started_at = None
        session.ended_at = session.ended_at or now
        session.closed_at = now
        session.updated_at = now
        db.commit()

        elapsed_seconds = _get_total_elapsed_for_item(db, task_id, item_id, labeler_id, now)

    # 4. 将 DatasetItem.status 设置为 invalid
    from app.models.dataset_item import DatasetItem
    from app.core.enums import ItemStatus
    
    item = db.query(DatasetItem).filter(DatasetItem.id == item_id).first()
    if item:
        item.is_valid = False
        item.invalid_reason = reason
        item.status = ItemStatus.INVALID.value
        item.updated_at = now
        db.commit()

    # 5. 写入审计日志
    try:
        log_action(
            db=db,
            user_id=labeler_id,
            action=AuditAction.MARK_INVALID,
            target_type=AuditTargetType.DATASET_ITEM,
            target_id=item_id,
            role="labeler",
            action_label="标记无效",
            task_id=task_id,
            item_id=item_id,
            work_key=work_key,
            message=f"标记数据项为无效{f'，原因: {reason}' if reason else ''}",
            payload_json={"reason": reason, "remark": remark, "elapsed_seconds": elapsed_seconds} if reason else {"elapsed_seconds": elapsed_seconds},
        )
    except Exception:
        pass

    # 6. 创建或更新 Annotation 记录到 annotations.json
    from app.services.annotation_service import _load_annotations, _save_annotations

    # 先尝试查找现有 annotation
    annotations = _load_annotations()
    existing_annotation = None
    for ann in annotations:
        if (ann.get("task_id") == task_id and 
            ann.get("dataset_item_id") == item_id and 
            ann.get("labeler_id") == labeler_id):
            existing_annotation = ann
            break

    now_iso = now.isoformat()

    if existing_annotation:
        # 更新现有 annotation
        for idx, ann in enumerate(annotations):
            if ann.get("id") == existing_annotation["id"]:
                annotations[idx]["status"] = "invalid_submitted"
                annotations[idx]["is_invalid"] = True
                annotations[idx]["invalid_reason"] = reason or ""
                annotations[idx]["invalid_remark"] = remark  # 保存用户填写的备注
                annotations[idx]["updated_at"] = now_iso
                # 保留 result_data，但标记为无效
                if "result" not in annotations[idx]:
                    annotations[idx]["result"] = {}
                annotations[idx]["result"]["is_invalid"] = True
                annotations[idx]["result"]["invalid_reason"] = reason or ""
                annotations[idx]["result"]["invalid_remark"] = remark  # 保存到result中
                break
    else:
        # 创建新 annotation
        new_id = max([a.get("id", 0) for a in annotations], default=0) + 1
        new_annotation = {
            "id": new_id,
            "task_id": task_id,
            "dataset_item_id": item_id,
            "labeler_id": labeler_id,
            "status": "invalid_submitted",
            "is_invalid": True,
            "invalid_reason": reason or "",
            "invalid_remark": remark,  # 保存用户填写的备注
            "result": {
                "is_invalid": True,
                "invalid_reason": reason or "",
                "invalid_remark": remark  # 保存到result中
            },
            "created_at": now_iso,
            "updated_at": now_iso,
            "revision_no": 1
        }
        annotations.append(new_annotation)

    _save_annotations(annotations)

    return {
        "success": True,
        "message": "已标记为无效，等待审核",
        "item_id": item_id,
        "elapsed_seconds": elapsed_seconds,
        "should_refresh_queue": True  # 提示前端刷新队列
    }
