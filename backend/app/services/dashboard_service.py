from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.task import Task
from app.models.dataset_item import DatasetItem
from app.models.template_schema import TemplateSchema
from app.models.ai_review_run import AIReviewRun
from app.models.submission import Submission
from app.models.audit_log import AuditLog
from app.models.export_job import ExportJob
from app.services.annotation_service import get_annotations_by_filter, normalize_ai_review
from app.services.quality_service import compute_quality_insights, compute_rubric_analysis, compute_priority_reviews


def compute_dashboard_stats(db: Session) -> Dict[str, Any]:
    task_count = db.query(Task).count()
    total_items = db.query(DatasetItem).count()
    template_count = db.query(TemplateSchema).count()
    audit_log_count = db.query(AuditLog).count()
    export_count = db.query(ExportJob).count()

    annotations = get_annotations_by_filter()

    submitted_count = 0
    approved_count = 0
    export_ready_count = 0
    ai_reviewed_count = 0

    for ann in annotations:
        status = ann.get("status", "")
        if status not in ("draft", "drafting", "claimed", "unclaimed", ""):
            submitted_count += 1
        if status in ("approved", "export_ready"):
            approved_count += 1
            export_ready_count += 1
        ai_review_raw = ann.get("ai_review")
        if ai_review_raw and isinstance(ai_review_raw, dict):
            ai_reviewed_count += 1

    first_task = db.query(Task).order_by(Task.id.asc()).first()
    demo_task = None
    if first_task:
        task_annotations = get_annotations_by_filter(task_id=first_task.id)
        task_items = db.query(DatasetItem).filter(DatasetItem.task_id == first_task.id).count()
        task_submitted = 0
        task_approved = 0
        task_ai_reviewed = 0
        task_exportable = 0
        for ann in task_annotations:
            s = ann.get("status", "")
            if s not in ("draft", "drafting", "claimed", "unclaimed", ""):
                task_submitted += 1
            if s in ("approved", "export_ready"):
                task_approved += 1
                task_exportable += 1
            if ann.get("ai_review") and isinstance(ann.get("ai_review"), dict):
                task_ai_reviewed += 1

        template_name = ""
        if first_task.template_id:
            tmpl = db.query(TemplateSchema).filter(TemplateSchema.id == first_task.template_id).first()
            if tmpl:
                template_name = tmpl.name or ""

        demo_task = {
            "task_id": first_task.id,
            "task_name": first_task.name or "",
            "template_name": template_name,
            "total_items": task_items,
            "submitted_count": task_submitted,
            "approved_count": task_approved,
            "ai_reviewed_count": task_ai_reviewed,
            "exportable_count": task_exportable,
        }

    return {
        "project_count": 1,
        "task_count": task_count,
        "total_items": total_items,
        "submitted_count": submitted_count,
        "approved_count": approved_count,
        "exportable_count": export_ready_count,
        "ai_reviewed_count": ai_reviewed_count,
        "audit_log_count": audit_log_count,
        "template_count": template_count,
        "export_count": export_count,
        "demo_task": demo_task,
    }


def compute_dashboard_quality(db: Session) -> Dict[str, Any]:
    first_task = db.query(Task).order_by(Task.id.asc()).first()
    if not first_task:
        return {
            "ai_avg_score": None,
            "ai_risk_distribution": {"low": 0, "medium": 0, "high": 0},
            "ai_human_agreement_rate": None,
            "human_pass_rate": None,
            "priority_review_count": 0,
            "high_dispute_rubric_count": 0,
        }

    insights = compute_quality_insights(db, first_task.id)
    rubric_analysis = compute_rubric_analysis(db, first_task.id)
    priority = compute_priority_reviews(db, first_task.id)

    return {
        "ai_avg_score": insights.get("ai_avg_score"),
        "ai_risk_distribution": insights.get("ai_risk_distribution", {"low": 0, "medium": 0, "high": 0}),
        "ai_human_agreement_rate": insights.get("ai_human_agreement_rate"),
        "human_pass_rate": insights.get("human_pass_rate"),
        "priority_review_count": priority.get("total", 0),
        "high_dispute_rubric_count": rubric_analysis.get("high_dispute_count", 0),
    }


def get_recent_activities(db: Session, limit: int = 10) -> List[Dict[str, Any]]:
    action_filter = [
        "submission_submit", "review_reject",
        "rework_submit", "review_approve", "export_create",
        "export_complete", "agent_enqueue", "agent_run_success",
        "agent_run_failed", "agent_fallback_required",
    ]
    logs = db.query(AuditLog).filter(
        AuditLog.action.in_(action_filter)
    ).order_by(AuditLog.id.desc()).limit(limit).all()

    result = []
    for log in logs:
        result.append({
            "id": log.id,
            "action": log.action,
            "action_label": log.action_label or log.action,
            "user_id": log.user_id,
            "role": log.role,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "task_id": log.task_id,
            "message": log.message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })
    return result


def compute_system_health(db: Session) -> Dict[str, Any]:
    checks = {}

    try:
        db.execute(func.count(1)).scalar()
        checks["database"] = {"status": "ok", "message": "数据库连接正常"}
    except Exception as e:
        checks["database"] = {"status": "error", "message": f"数据库异常: {str(e)[:80]}"}

    checks["api"] = {"status": "ok", "message": "后端 API 正常运行"}

    demo_checks = {}
    try:
        demo_checks["has_task"] = db.query(Task).limit(1).count() > 0
        demo_checks["has_dataset_item"] = db.query(DatasetItem).limit(1).count() > 0
        demo_checks["has_template"] = db.query(TemplateSchema).limit(1).count() > 0
        demo_checks["has_submission"] = db.query(Submission).limit(1).count() > 0
        demo_checks["has_ai_review_run"] = db.query(AIReviewRun).limit(1).count() > 0
        demo_checks["has_audit_log"] = db.query(AuditLog).limit(1).count() > 0
    except Exception:
        pass

    try:
        annotations = get_annotations_by_filter()
        demo_checks["has_review"] = any(a.get("review_info") for a in annotations)
        demo_checks["has_export_record"] = db.query(ExportJob).limit(1).count() > 0
    except Exception:
        demo_checks["has_review"] = False
        demo_checks["has_export_record"] = False

    checks["demo_data"] = demo_checks

    checks["ai_precheck"] = {
        "status": "ok",
        "mode": "mock",
        "model": "mock/mock-v1.0",
        "message": "AI 预审服务运行中（Mock 模式）",
    }

    export_formats = {}
    try:
        import os
        export_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "exports")
        export_formats["json"] = {"available": True, "message": "JSON 导出可用"}
        export_formats["csv"] = {"available": True, "message": "CSV 导出可用"}
        export_formats["xlsx"] = {"available": True, "message": "XLSX 导出可用"}
        export_formats["jsonl"] = {"available": False, "message": "待支持"}
    except Exception:
        export_formats["json"] = {"available": True, "message": "JSON 导出可用"}
        export_formats["csv"] = {"available": True, "message": "CSV 导出可用"}
        export_formats["xlsx"] = {"available": False, "message": "待支持"}
        export_formats["jsonl"] = {"available": False, "message": "待支持"}

    checks["export_formats"] = export_formats

    return checks
