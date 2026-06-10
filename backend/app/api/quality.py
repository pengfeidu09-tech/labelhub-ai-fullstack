from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.quality_service import (
    compute_quality_insights,
    compute_rubric_analysis,
    compute_priority_reviews,
    generate_quality_report,
    get_quality_policy,
    compute_smart_review_strategy
)
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType

router = APIRouter(prefix="/api/quality", tags=["quality"])


@router.get("/tasks/{task_id}/insights")
def get_quality_insights(task_id: int, db: Session = Depends(get_db)):
    result = compute_quality_insights(db, task_id)
    if "error" in result:
        return result
    try:
        log_action(
            db=db, user_id=1, action="quality_insight_view",
            target_type=AuditTargetType.TASK, target_id=task_id,
            role="owner", action_label="查看质量洞察",
            task_id=task_id, message=f"查看任务 #{task_id} 质量洞察"
        )
    except Exception:
        pass
    return result


@router.get("/tasks/{task_id}/rubric-analysis")
def get_rubric_analysis(task_id: int, db: Session = Depends(get_db)):
    result = compute_rubric_analysis(db, task_id)
    if "error" in result:
        return result
    try:
        log_action(
            db=db, user_id=1, action="rubric_analysis_view",
            target_type=AuditTargetType.TASK, target_id=task_id,
            role="owner", action_label="查看Rubric命中分析",
            task_id=task_id, message=f"查看任务 #{task_id} Rubric命中分析"
        )
    except Exception:
        pass
    return result


@router.get("/tasks/{task_id}/priority-reviews")
def get_priority_reviews(task_id: int, db: Session = Depends(get_db)):
    result = compute_priority_reviews(db, task_id)
    if "error" in result:
        return result
    try:
        log_action(
            db=db, user_id=1, action="priority_review_list_view",
            target_type=AuditTargetType.TASK, target_id=task_id,
            role="owner", action_label="查看重点复核样本",
            task_id=task_id, message=f"查看任务 #{task_id} 重点复核样本"
        )
    except Exception:
        pass
    return result


@router.post("/tasks/{task_id}/report")
def create_quality_report(task_id: int, db: Session = Depends(get_db)):
    result = generate_quality_report(db, task_id)
    if "error" in result:
        return result
    try:
        log_action(
            db=db, user_id=1, action="quality_report_generate",
            target_type=AuditTargetType.TASK, target_id=task_id,
            role="owner", action_label="生成AI质量报告",
            task_id=task_id, message=f"生成任务 #{task_id} AI质量报告"
        )
    except Exception:
        pass
    return result


@router.get("/tasks/{task_id}/policy")
def get_task_quality_policy(task_id: int, db: Session = Depends(get_db)):
    result = get_quality_policy(task_id)
    try:
        log_action(
            db=db, user_id=1, action="quality_policy_view",
            target_type=AuditTargetType.TASK, target_id=task_id,
            role="owner", action_label="查看质量策略",
            task_id=task_id, message=f"查看任务 #{task_id} 质量策略"
        )
    except Exception:
        pass
    return result


@router.get("/tasks/{task_id}/review-strategy")
def get_review_strategy(task_id: int, db: Session = Depends(get_db)):
    result = compute_smart_review_strategy(db, task_id)
    if "error" in result:
        return result
    try:
        log_action(
            db=db, user_id=1, action="review_strategy_view",
            target_type=AuditTargetType.TASK, target_id=task_id,
            role="owner", action_label="查看智能复核策略",
            task_id=task_id, message=f"查看任务 #{task_id} 智能复核策略"
        )
    except Exception:
        pass
    return result
