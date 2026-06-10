import os
import json
import csv
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List

from app.models.export_job import ExportJob
from app.models.task import Task
from app.models.dataset_item import DatasetItem
from app.models.submission import Submission
from app.models.ai_review import AIReviewResult
from app.models.ai_review_run import AIReviewRun
from app.models.human_review import HumanReview
from app.core.enums import ExportStatus, ExportFormat, ItemStatus, SubmissionStatus
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType
from app.services.annotation_service import normalize_ai_review

ANNOTATIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "annotations.json")


def _load_annotations() -> List[Dict[str, Any]]:
    if not os.path.exists(ANNOTATIONS_FILE):
        return []
    try:
        with open(ANNOTATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _build_ai_review_export_from_db(ai_review: AIReviewResult) -> Dict[str, Any]:
    if not ai_review:
        return {}
    ai_review_dict = {
        "overall_score": ai_review.overall_score,
        "conclusion": ai_review.conclusion,
        "dimension_scores": ai_review.dimension_scores,
        "issue_tags": ai_review.issue_tags,
        "review_comment": ai_review.review_comment,
        "suggested_fix": ai_review.suggested_fix,
        "confidence": ai_review.confidence,
    }
    parsed = ai_review.parsed_result if ai_review.parsed_result else {}
    if isinstance(parsed, dict):
        ai_review_dict.update({
            "score": parsed.get("score"),
            "risk_level": parsed.get("risk_level"),
            "suggestion_action": parsed.get("suggestion_action"),
            "dimensions": parsed.get("dimensions"),
            "summary": parsed.get("summary"),
            "suggestion": parsed.get("suggestion"),
        })
    normalized = normalize_ai_review(ai_review_dict)
    if not normalized:
        return {}
    return {
        "overall_score": normalized.get("overall_score"),
        "risk_level": normalized.get("risk_level"),
        "suggested_action": normalized.get("suggested_action"),
        "confidence": normalized.get("confidence"),
        "summary": normalized.get("summary"),
        "reason": normalized.get("reason"),
        "dimension_scores": normalized.get("dimension_scores"),
        "issue_tags": normalized.get("issue_tags"),
        "prompt_version": normalized.get("prompt_version"),
        "model": normalized.get("model"),
        "run_id": normalized.get("run_id"),
    }


def _build_ai_review_export_from_json(ai_review_data: Dict) -> Dict[str, Any]:
    if not ai_review_data:
        return {}
    normalized = normalize_ai_review(ai_review_data)
    if not normalized:
        return {}
    return {
        "overall_score": normalized.get("overall_score"),
        "risk_level": normalized.get("risk_level"),
        "suggested_action": normalized.get("suggested_action"),
        "confidence": normalized.get("confidence"),
        "summary": normalized.get("summary"),
        "reason": normalized.get("reason"),
        "dimension_scores": normalized.get("dimension_scores"),
        "issue_tags": normalized.get("issue_tags"),
        "prompt_version": normalized.get("prompt_version"),
        "model": normalized.get("model"),
        "run_id": normalized.get("run_id"),
    }


def _try_fallback_ai_review_from_run(db: Session, submission_id: int, task_id: int = None, item_id: int = None) -> Optional[Dict[str, Any]]:
    try:
        run = db.query(AIReviewRun).filter(AIReviewRun.submission_id == submission_id, AIReviewRun.status == "success").order_by(AIReviewRun.id.desc()).first()
        if not run and task_id and item_id:
            run = db.query(AIReviewRun).filter(
                AIReviewRun.task_id == task_id,
                AIReviewRun.item_id == item_id,
                AIReviewRun.status == "success"
            ).order_by(AIReviewRun.id.desc()).first()
        if run and run.output_json:
            output = run.output_json if isinstance(run.output_json, dict) else {}
            normalized = normalize_ai_review(output)
            if normalized and normalized.get("overall_score") is not None:
                return {
                    "overall_score": normalized.get("overall_score"),
                    "risk_level": normalized.get("risk_level"),
                    "suggested_action": normalized.get("suggested_action"),
                    "confidence": normalized.get("confidence"),
                    "summary": normalized.get("summary"),
                    "reason": normalized.get("reason"),
                    "dimension_scores": normalized.get("dimension_scores"),
                    "issue_tags": normalized.get("issue_tags"),
                    "prompt_version": normalized.get("prompt_version"),
                    "model": normalized.get("model"),
                    "run_id": run.id,
                    "run_status": run.status,
                }
    except Exception:
        pass
    return None


def _generate_snapshot_id(task_id: int) -> str:
    return f"snapshot_task_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def create_export_job(db: Session, task_id: int, user_id: int, format: str, snapshot_id: str = None) -> ExportJob:
    now = datetime.now()
    job = ExportJob(
        task_id=task_id,
        user_id=user_id,
        format=format,
        status=ExportStatus.PENDING.value,
        created_at=now,
        updated_at=now
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    log_action(
        db=db,
        user_id=user_id,
        action=AuditAction.EXPORT_CREATE,
        target_type=AuditTargetType.EXPORT,
        target_id=job.id,
        after_data={"task_id": task_id, "format": format}
    )

    return job


def export_task_data(db: Session, task_id: int, user_id: int, format: str) -> ExportJob:
    snapshot_id = _generate_snapshot_id(task_id)
    job = create_export_job(db, task_id, user_id, format, snapshot_id=snapshot_id)

    log_action(
        db=db,
        user_id=user_id,
        action=AuditAction.EXPORT_SNAPSHOT_CREATE,
        target_type=AuditTargetType.EXPORT,
        target_id=job.id,
        after_data={"task_id": task_id, "format": format, "snapshot_id": snapshot_id}
    )

    job.status = ExportStatus.RUNNING.value
    db.commit()

    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            job.status = ExportStatus.FAILED.value
            job.error_message = "Task not found"
            db.commit()
            return job

        submissions = db.query(Submission)\
            .filter(Submission.task_id == task_id)\
            .filter(Submission.status.in_([SubmissionStatus.APPROVED.value]))\
            .all()

        items = []
        seen_dataset_item_ids = set()
        rows_with_ai_review = 0
        rows_without_ai_review = 0

        for submission in submissions:
            item = db.query(DatasetItem).filter(DatasetItem.id == submission.dataset_item_id).first()
            ai_review = db.query(AIReviewResult).filter(AIReviewResult.submission_id == submission.id).first()
            human_review = db.query(HumanReview).filter(HumanReview.submission_id == submission.id).first()

            ai_review_export = _build_ai_review_export_from_db(ai_review) if ai_review else None
            if not ai_review_export:
                ai_review_export = _try_fallback_ai_review_from_run(
                    db, submission.id, task_id=task_id, item_id=submission.dataset_item_id
                ) or {}

            if ai_review_export and ai_review_export.get("overall_score") is not None:
                rows_with_ai_review += 1
            else:
                rows_without_ai_review += 1

            human_review_result = {}
            if human_review:
                human_review_result = {
                    "action": human_review.action,
                    "comments": human_review.comments,
                    "revised_data": human_review.revised_data
                }

            export_item = {
                "task_id": task_id,
                "dataset_item_id": submission.dataset_item_id,
                "raw_data_json": item.raw_data_json if item else {},
                "submission_data": submission.data,
                "ai_review_result": ai_review_export,
                "human_review_result": human_review_result,
                "status": submission.status,
                "exported_at": datetime.now().isoformat()
            }
            items.append(export_item)
            if submission.dataset_item_id:
                seen_dataset_item_ids.add(submission.dataset_item_id)

        annotations = _load_annotations()
        approved_statuses = ("approved", "export_ready")
        for ann in annotations:
            if ann.get("task_id") != task_id:
                continue
            if ann.get("status") not in approved_statuses:
                continue
            ann_dataset_item_id = ann.get("dataset_item_id")
            if ann_dataset_item_id and ann_dataset_item_id in seen_dataset_item_ids:
                continue

            item_snapshot = ann.get("item_snapshot") or {}
            raw_data = item_snapshot.get("item_data") or item_snapshot.get("raw_data") or {}
            submission_data = ann.get("data") or ann.get("result") or ann.get("annotation_result") or {}
            ai_review_data = ann.get("ai_review") or {}

            ai_review_export = _build_ai_review_export_from_json(ai_review_data) if ai_review_data else {}
            if ai_review_export and ai_review_export.get("overall_score") is not None:
                rows_with_ai_review += 1
            else:
                rows_without_ai_review += 1

            export_item = {
                "task_id": task_id,
                "dataset_item_id": ann_dataset_item_id,
                "raw_data_json": raw_data,
                "submission_data": submission_data,
                "ai_review_result": ai_review_export,
                "human_review_result": ann.get("review_info") or {},
                "status": ann.get("status"),
                "exported_at": datetime.now().isoformat()
            }
            items.append(export_item)
            if ann_dataset_item_id:
                seen_dataset_item_ids.add(ann_dataset_item_id)

        export_summary = {
            "snapshot_id": snapshot_id,
            "task_id": task_id,
            "total_rows": len(items),
            "approved_rows": len([i for i in items if i.get("status") in ("approved", "export_ready")]),
            "rows_with_ai_review": rows_with_ai_review,
            "rows_without_ai_review": rows_without_ai_review,
            "rows_with_human_review": len([i for i in items if i.get("human_review_result") and i.get("human_review_result", {}).get("action")]),
            "format": format,
            "quality_policy_version": "quality_policy_v1",
            "data_filter": "approved_only",
            "includes_ai_review": rows_with_ai_review > 0,
            "includes_human_review": True,
            "generated_at": datetime.now().isoformat()
        }

        exports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "exports")
        os.makedirs(exports_dir, exist_ok=True)

        filename = f"task_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
        filepath = os.path.join(exports_dir, filename)

        if format == ExportFormat.JSON.value:
            export_payload = {
                "summary": export_summary,
                "data": items
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_payload, f, ensure_ascii=False, indent=2)
        elif format == ExportFormat.JSONL.value:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(json.dumps({"type": "summary", **export_summary}, ensure_ascii=False) + "\n")
                for item in items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        elif format == ExportFormat.CSV.value:
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "task_id", "dataset_item_id", "prompt", "model_answer",
                    "relevance", "accuracy", "completeness", "safety", "reason",
                    "ai_score", "ai_risk_level", "ai_suggested_action", "ai_confidence", "ai_run_status",
                    "human_review_action", "human_review_comments"
                ])
                for item in items:
                    raw = item.get("raw_data_json") or {}
                    sub = item.get("submission_data") or {}
                    ai = item.get("ai_review_result") or {}
                    hr = item.get("human_review_result") or {}
                    writer.writerow([
                        str(task_id),
                        str(item.get("dataset_item_id") or ""),
                        str(raw.get("prompt", "")),
                        str(raw.get("model_answer", "")),
                        str(sub.get("relevance", "")),
                        str(sub.get("accuracy", "")),
                        str(sub.get("completeness", "")),
                        str(sub.get("safety", "")),
                        str(sub.get("reason", "")),
                        str(ai.get("overall_score", "")),
                        str(ai.get("risk_level", "")),
                        str(ai.get("suggested_action", "")),
                        str(ai.get("confidence", "")),
                        str(ai.get("run_status", "")),
                        str(hr.get("action", "")),
                        str(hr.get("comments", "")),
                    ])
        elif format == ExportFormat.XLSX.value:
            import pandas as pd
            flat_items = []
            for item in items:
                raw = item.get("raw_data_json") or {}
                sub = item.get("submission_data") or {}
                ai = item.get("ai_review_result") or {}
                hr = item.get("human_review_result") or {}
                flat_items.append({
                    "task_id": task_id,
                    "dataset_item_id": item.get("dataset_item_id"),
                    "prompt": raw.get("prompt", ""),
                    "model_answer": raw.get("model_answer", ""),
                    "relevance": sub.get("relevance", ""),
                    "accuracy": sub.get("accuracy", ""),
                    "completeness": sub.get("completeness", ""),
                    "safety": sub.get("safety", ""),
                    "reason": sub.get("reason", ""),
                    "ai_score": ai.get("overall_score", ""),
                    "ai_risk_level": ai.get("risk_level", ""),
                    "ai_suggested_action": ai.get("suggested_action", ""),
                    "human_review_action": hr.get("action", ""),
                    "human_review_comments": hr.get("comments", ""),
                })
            df = pd.DataFrame(flat_items)
            df.to_excel(filepath, index=False, engine="openpyxl")

        job.status = ExportStatus.SUCCESS.value
        job.file_path = filepath
        job.row_count = len(items)
        job.updated_at = datetime.now()
        job.error_message = json.dumps(export_summary, ensure_ascii=False)
        db.commit()

        log_action(
            db=db,
            user_id=user_id,
            action=AuditAction.EXPORT_SNAPSHOT_COMPLETE,
            target_type=AuditTargetType.EXPORT,
            target_id=job.id,
            after_data={"status": "success", "row_count": len(items), "file_path": filepath, "snapshot_id": snapshot_id, "rows_with_ai_review": rows_with_ai_review, "rows_without_ai_review": rows_without_ai_review, "quality_policy_version": "quality_policy_v1"}
        )

    except Exception as e:
        job.status = ExportStatus.FAILED.value
        job.error_message = str(e)
        job.updated_at = datetime.now()
        db.commit()

        log_action(
            db=db,
            user_id=user_id,
            action=AuditAction.EXPORT_FAILED,
            target_type=AuditTargetType.EXPORT,
            target_id=job.id,
            after_data={"status": "failed", "error": str(e)}
        )

    return job


def get_export_jobs(db: Session, task_id: Optional[int] = None, page: int = 1, limit: int = 20) -> Dict[str, Any]:
    query = db.query(ExportJob)

    if task_id:
        query = query.filter(ExportJob.task_id == task_id)

    total = query.count()
    items = query.order_by(ExportJob.created_at.desc())\
        .offset((page - 1) * limit)\
        .limit(limit)\
        .all()

    return {"items": items, "total": total, "page": page, "limit": limit}


def get_export_job(db: Session, job_id: int) -> Optional[ExportJob]:
    return db.query(ExportJob).filter(ExportJob.id == job_id).first()


def get_submission_export(db: Session, submission_id: int, format: str = "json") -> Optional[Dict[str, Any]]:
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        return None

    item = db.query(DatasetItem).filter(DatasetItem.id == submission.dataset_item_id).first()
    ai_review = db.query(AIReviewResult).filter(AIReviewResult.submission_id == submission.id).first()
    human_review = db.query(HumanReview).filter(HumanReview.submission_id == submission.id).first()

    ai_review_export = _build_ai_review_export_from_db(ai_review) if ai_review else None
    if not ai_review_export:
        ai_review_export = _try_fallback_ai_review_from_run(
            db, submission.id, task_id=submission.task_id, item_id=submission.dataset_item_id
        ) or {}

    human_review_result = {}
    if human_review:
        human_review_result = {
            "action": human_review.action,
            "comments": human_review.comments,
            "revised_data": human_review.revised_data
        }

    result = {
        "task_id": submission.task_id,
        "dataset_item_id": submission.dataset_item_id,
        "raw_data_json": item.raw_data_json if item else {},
        "submission_data": submission.data,
        "ai_review_result": ai_review_export,
        "human_review_result": human_review_result,
        "status": submission.status,
        "exported_at": datetime.now().isoformat()
    }

    if format == "jsonl":
        return json.dumps(result, ensure_ascii=False)
    return result
