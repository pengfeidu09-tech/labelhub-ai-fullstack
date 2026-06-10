from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime
import logging

from app.core.database import get_db
from app.services.human_review_service import (
    approve_submission, reject_submission, revise_submission,
    get_pending_submissions, get_submission_detail
)
from app.services.annotation_service import (
    get_pending_annotations, get_annotation_by_id, update_annotation_status
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reviews", tags=["reviews"])


class ReviewActionRequest:
    reviewer_id: int
    comment: Optional[str] = None


@router.get("/pending")
def get_pending_reviews(page: int = 1, limit: int = 20) -> Dict[str, Any]:
    try:
        # 从 JSON 文件读取待审核标注
        pending = get_pending_annotations()
        
        logger.debug(f"[reviews pending] pending annotations from JSON: {len(pending)}")
        logger.debug(f"[reviews pending] all statuses: {[a.get('status') for a in pending]}")
        
        # 排序
        pending.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        
        total = len(pending)
        
        # 分页
        start = (page - 1) * limit
        end = start + limit
        items = pending[start:end]
        
        logger.debug(f"[reviews pending] returning {len(items)} items")
        
        return {"items": items, "total": total, "page": page, "limit": limit}
    except Exception as e:
        logger.error(f"[reviews pending] error: {e}")
        import traceback
        logger.error(f"[reviews pending] traceback: {traceback.format_exc()}")
        return {"items": [], "total": 0, "page": page, "limit": limit}


@router.get("/{submission_id}/view-model")
def get_review_view_model(submission_id: int, db: Session = Depends(get_db)):
    """审核详情统一投影层 DTO — 前端直接消费，不再自行拼字段。"""
    from app.services.review_view_model_service import build_review_view_model
    vm = build_review_view_model(db, submission_id)
    if not vm:
        raise HTTPException(status_code=404, detail="Review not found")
    return vm


@router.get("/{submission_id}")
def get_review_detail(submission_id: int, db: Session = Depends(get_db)):
    # 优先从 JSON 文件读取
    annotation = get_annotation_by_id(submission_id)
    if annotation:
        # 获取原始数据 item
        original_data = None
        dataset_item_id = annotation.get("dataset_item_id")
        if dataset_item_id:
            from app.models.dataset_item import DatasetItem
            item = db.query(DatasetItem).filter(DatasetItem.id == dataset_item_id).first()
            if item:
                # 解析 raw_data_json
                raw_data = item.raw_data_json if isinstance(item.raw_data_json, dict) else {}
                original_data = {
                    "id": item.id,
                    "task_id": item.task_id,
                    "dataset_type": item.dataset_type,
                    "prompt": raw_data.get("prompt") or raw_data.get("question") or raw_data.get("input"),
                    "model_answer": raw_data.get("model_answer") or raw_data.get("answer") or raw_data.get("output"),
                    "reference": raw_data.get("reference") or raw_data.get("reference_answer") or raw_data.get("ground_truth"),
                    "category": raw_data.get("category") or raw_data.get("label") or raw_data.get("topic"),
                    "difficulty": raw_data.get("difficulty") or raw_data.get("level"),
                    "media_type": raw_data.get("media_type"),
                    "media_url": raw_data.get("media_url"),
                    "content_detail": raw_data.get("content_markdown"),
                    "status": item.status,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None
                }

        # 从数据库 AIReviewRun 补充最新 AI 预审结果
        task_id = annotation.get("task_id")
        if task_id and dataset_item_id:
            try:
                from app.models.ai_review_run import AIReviewRun
                latest_run = db.query(AIReviewRun).filter(
                    AIReviewRun.task_id == task_id,
                    AIReviewRun.item_id == dataset_item_id,
                ).order_by(AIReviewRun.id.desc()).first()
                if latest_run and latest_run.status in ("success", "failed", "fallback_required"):
                    output_json = latest_run.output_json or {}
                    dimensions = output_json.get("dimensions", {})
                    issue_tags = output_json.get("issue_tags", [])
                    problem_tags = output_json.get("problem_tags", issue_tags)
                    suggestion = output_json.get("suggestion")
                    if not suggestion or not isinstance(suggestion, dict):
                        suggestion = {
                            "relevance": dimensions.get("relevance", {}).get("label", "") if isinstance(dimensions.get("relevance"), dict) else (dimensions.get("relevance") or ""),
                            "accuracy": dimensions.get("accuracy", {}).get("label", "") if isinstance(dimensions.get("accuracy"), dict) else (dimensions.get("accuracy") or ""),
                            "completeness": dimensions.get("completeness", {}).get("label", "") if isinstance(dimensions.get("completeness"), dict) else (dimensions.get("completeness") or ""),
                            "safety": dimensions.get("safety", {}).get("label", "") if isinstance(dimensions.get("safety"), dict) else (dimensions.get("safety") or ""),
                            "reason": output_json.get("summary", ""),
                            "issue_tags": issue_tags,
                        }
                    annotation["ai_review"] = {
                        "score": latest_run.score,
                        "risk_level": latest_run.risk_level,
                        "suggestion_action": latest_run.suggestion_action,
                        "confidence": latest_run.confidence,
                        "model_provider": latest_run.model_provider,
                        "model_name": latest_run.model_name,
                        "base_url": latest_run.base_url,
                        "status": latest_run.status,
                        "used_fallback": bool(latest_run.used_fallback) if latest_run.used_fallback is not None else False,
                        "error_type": latest_run.error_type,
                        "error_message": latest_run.error_message,
                        "latency_ms": latest_run.latency_ms,
                        "run_id": latest_run.id,
                        "passed": (latest_run.score or 0) >= 60,
                        "summary": output_json.get("summary", ""),
                        "issues": output_json.get("problems", []),
                        "suggestions": output_json.get("suggestions", []),
                        "dimensions": dimensions,
                        "tool_checks": output_json.get("tool_checks", []),
                        "issue_tags": issue_tags,
                        "problem_tags": problem_tags,
                        "suggestion": suggestion,
                        "matched_rubrics": output_json.get("matched_rubrics", []),
                        "fallback": bool(latest_run.used_fallback) if latest_run.used_fallback is not None else False,
                        "fallback_used": bool(latest_run.used_fallback) if latest_run.used_fallback is not None else False,
                    }
                    annotation["ai_review_source"] = "agent_run"
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"[get_review_detail] AIReviewRun lookup failed: {e}")

        # 更新 annotation_phase 为 human_review（如果当前还在 annotation_qc 或 submitted 阶段）
        try:
            from app.models.dataset_item import DatasetItem
            if dataset_item_id:
                di = db.query(DatasetItem).filter(DatasetItem.id == dataset_item_id).first()
                if di and di.annotation_phase in ("annotation_qc", "submitted", "qc", None):
                    di.annotation_phase = "human_review"
                    db.commit()
        except Exception as e:
            logger.warning(f"[get_review_detail] failed to update annotation_phase: {e}")

        # 查询 HumanReview 记录
        human_reviews = []
        try:
            from app.models.human_review import HumanReview
            hrs = db.query(HumanReview).filter(
                HumanReview.submission_id == submission_id
            ).order_by(HumanReview.id.desc()).all()
            for hr in hrs:
                human_reviews.append({
                    "id": hr.id,
                    "reviewer_id": hr.reviewer_id,
                    "action": hr.action,
                    "comments": hr.comments,
                    "created_at": hr.created_at.isoformat() if hr.created_at else None,
                })
            if human_reviews:
                annotation["human_reviews"] = human_reviews
                annotation["human_review_id"] = human_reviews[0]["id"]
        except Exception as e:
            logger.warning(f"[get_review_detail] failed to fetch HumanReview: {e}")

        return {
            "annotation": annotation,
            "item": original_data,
            "original_data": original_data
        }
    
    # 如果 JSON 文件中没有，从数据库读取
    result = get_submission_detail(db, submission_id)
    if not result:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # 尝试获取原始数据
    dataset_item_id = result.get("dataset_item_id")
    original_data = None
    if dataset_item_id:
        from app.models.dataset_item import DatasetItem
        item = db.query(DatasetItem).filter(DatasetItem.id == dataset_item_id).first()
        if item:
            raw_data = item.raw_data_json if isinstance(item.raw_data_json, dict) else {}
            original_data = {
                "id": item.id,
                "task_id": item.task_id,
                "dataset_type": item.dataset_type,
                "prompt": raw_data.get("prompt"),
                "model_answer": raw_data.get("model_answer"),
                "reference": raw_data.get("reference"),
                "category": raw_data.get("category"),
                "difficulty": raw_data.get("difficulty")
            }
    
    return {
        "annotation": result,
        "item": original_data,
        "original_data": original_data
    }


@router.post("/{annotation_id}/approve")
def approve_review(
    annotation_id: int,
    request: dict,
    db: Session = Depends(get_db)
):
    reviewer_id = request.get("reviewer_id", 1)
    comment = request.get("comment", "审核通过")
    
    # 更新 JSON 文件
    review_info = {
        "reviewer_id": reviewer_id,
        "action": "approve",
        "comment": comment,
        "reviewed_at": datetime.now().isoformat()
    }
    
    result = update_annotation_status(
        annotation_id=annotation_id,
        status="approved",
        review_info=review_info
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Annotation not found")
    
    # 同时更新数据库
    approve_submission(db, annotation_id, reviewer_id, comment)

    # 更新 annotation_phase 为 approved
    try:
        from app.models.dataset_item import DatasetItem
        _item_id = result.get("dataset_item_id")
        if _item_id:
            di = db.query(DatasetItem).filter(DatasetItem.id == _item_id).first()
            if di:
                di.annotation_phase = "approved"
                db.commit()
    except Exception as e:
        logger.warning(f"[review_approve] failed to update annotation_phase: {e}")

    # 创建 HumanReview 记录
    try:
        from app.models.human_review import HumanReview
        from datetime import timezone
        hr = HumanReview(
            submission_id=annotation_id,
            reviewer_id=reviewer_id,
            action="approve",
            comments=comment,
            created_at=datetime.now(timezone.utc),
        )
        db.add(hr)
        db.commit()
    except Exception as e:
        logger.warning(f"[review_approve] failed to create HumanReview: {e}")

    # Write audit log
    try:
        from app.services.audit_service import create_audit_log
        _task_id = result.get("task_id")
        _item_id = result.get("dataset_item_id")
        _work_key = f"{_task_id}:{_item_id}:{result.get('labeler_id')}" if _task_id and _item_id and result.get("labeler_id") else None
        create_audit_log(
            db=db,
            user_id=reviewer_id,
            action="review_approve",
            target_type="submission",
            target_id=annotation_id,
            task_id=_task_id,
            item_id=_item_id,
            annotation_id=annotation_id,
            submission_id=annotation_id,
            work_key=_work_key,
            after_data={"status": "approved", "comment": comment},
            extra_info={"task_id": _task_id, "dataset_item_id": _item_id}
        )
    except Exception as audit_err:
        logger.error(f"[review_approve] audit log error: {audit_err}")

    return result


@router.post("/{annotation_id}/reject")
def reject_review(
    annotation_id: int,
    request: dict,
    db: Session = Depends(get_db)
):
    reviewer_id = request.get("reviewer_id", 1)
    comment = request.get("comment", "请补充修改理由或完善标注")
    
    # 更新 JSON 文件
    review_info = {
        "reviewer_id": reviewer_id,
        "action": "reject_to_modify",
        "comment": comment,
        "reviewed_at": datetime.now().isoformat()
    }
    
    result = update_annotation_status(
        annotation_id=annotation_id,
        status="rejected_to_modify",
        review_info=review_info,
        rejected_reason=comment
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Annotation not found")
    
    # 同时更新数据库
    reject_submission(db, annotation_id, reviewer_id, comment)

    # 更新 annotation_phase 为 rework
    try:
        from app.models.dataset_item import DatasetItem
        _item_id = result.get("dataset_item_id")
        if _item_id:
            di = db.query(DatasetItem).filter(DatasetItem.id == _item_id).first()
            if di:
                di.annotation_phase = "rework"
                db.commit()
    except Exception as e:
        logger.warning(f"[review_reject] failed to update annotation_phase: {e}")

    # 创建 HumanReview 记录
    try:
        from app.models.human_review import HumanReview
        from datetime import timezone
        hr = HumanReview(
            submission_id=annotation_id,
            reviewer_id=reviewer_id,
            action="reject",
            comments=comment,
            created_at=datetime.now(timezone.utc),
        )
        db.add(hr)
        db.commit()
    except Exception as e:
        logger.warning(f"[review_reject] failed to create HumanReview: {e}")

    # Write audit log
    try:
        from app.services.audit_service import create_audit_log
        _task_id = result.get("task_id")
        _item_id = result.get("dataset_item_id")
        _work_key = f"{_task_id}:{_item_id}:{result.get('labeler_id')}" if _task_id and _item_id and result.get("labeler_id") else None
        create_audit_log(
            db=db,
            user_id=reviewer_id,
            action="review_reject",
            target_type="submission",
            target_id=annotation_id,
            task_id=_task_id,
            item_id=_item_id,
            annotation_id=annotation_id,
            submission_id=annotation_id,
            work_key=_work_key,
            after_data={"status": "rejected_to_modify", "comment": comment},
            extra_info={"task_id": _task_id, "dataset_item_id": _item_id}
        )
    except Exception as audit_err:
        logger.error(f"[review_reject] audit log error: {audit_err}")

    return result


@router.post("/{submission_id}/revise")
def revise_review(
    submission_id: int,
    request: dict,
    db: Session = Depends(get_db)
):
    reviewer_id = request.get("reviewer_id", 3)
    revised_data = request.get("revised_data")
    comments = request.get("comment")
    
    if not revised_data:
        raise HTTPException(status_code=400, detail="Revised data is required")
    
    result = revise_submission(db, submission_id, reviewer_id, revised_data, comments)
    if not result:
        raise HTTPException(status_code=404, detail="Submission not found")
    return result


@router.get("/{review_id}/timeline")
def get_review_timeline(review_id: int, db: Session = Depends(get_db)):
    """获取审核记录的时间线数据。

    从 audit_logs 中查找与该 review_id 相关的操作记录。
    如果没有数据，返回空列表而不是 404。
    """
    from app.models.audit_log import AuditLog
    from app.models.submission import Submission

    items = []

    # 尝试多种方式关联 audit_logs
    target_ids = [review_id]

    # 尝试从 submission 表获取关联信息
    submission = db.query(Submission).filter(Submission.id == review_id).first()
    if submission:
        if submission.task_id:
            # 查找同 task_id + item_id 的日志
            pass
        if submission.dataset_item_id:
            target_ids.append(submission.dataset_item_id)

    # 查询 audit_logs: 按 target_id 匹配 review/submission/item 类型
    logs = db.query(AuditLog).filter(
        (AuditLog.target_id.in_(target_ids)) &
        (AuditLog.target_type.in_(["review", "submission", "item", "workbench", "annotation"]))
    ).order_by(AuditLog.created_at.desc()).limit(50).all()

    # 也查 annotation_id 匹配
    annotation_logs = db.query(AuditLog).filter(
        AuditLog.annotation_id == review_id
    ).order_by(AuditLog.created_at.desc()).limit(50).all()

    # 合并去重
    seen_ids = set()
    all_logs = list(annotation_logs) + list(logs)
    for log_entry in all_logs:
        if log_entry.id in seen_ids:
            continue
        seen_ids.add(log_entry.id)

        items.append({
            "id": log_entry.id,
            "created_at": log_entry.created_at.isoformat() if log_entry.created_at else None,
            "action": log_entry.action,
            "actor_id": log_entry.user_id,
            "actor_name": log_entry.role or f"User#{log_entry.user_id}",
            "title": log_entry.action_label or log_entry.action,
            "description": log_entry.message or "",
            "status": log_entry.action,
            "metadata": log_entry.payload_json or log_entry.after_data or {},
        })

    # 按时间降序
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    return {"items": items, "total": len(items)}