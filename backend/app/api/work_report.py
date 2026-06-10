from datetime import datetime, date, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from collections import defaultdict

from app.core.database import get_db
from app.models.annotation_work_session import AnnotationWorkSession
from app.models.task import Task
from app.api.workbench_session import calculate_elapsed_seconds
import logging

logger = logging.getLogger("work_report")

router = APIRouter(prefix="/api/work-reports", tags=["work-reports"])


def _make_aware(dt):
    if dt and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _aggregate_work_seconds(db: Session, labeler_id: int, target_date: Optional[str] = None, task_id: Optional[int] = None):
    query = db.query(AnnotationWorkSession).filter(
        AnnotationWorkSession.labeler_id == labeler_id
    )
    if task_id:
        query = query.filter(AnnotationWorkSession.task_id == task_id)

    sessions = query.all()
    now = datetime.now(timezone.utc)

    total_seconds = 0.0
    for s in sessions:
        if target_date:
            opened = _make_aware(s.opened_at or s.created_at)
            if opened and opened.strftime("%Y-%m-%d") != target_date:
                continue

        total_seconds += calculate_elapsed_seconds(s, now)

    return total_seconds


@router.get("/my-stats")
def get_my_stats(
    labeler_id: int = Query(2),
    db: Session = Depends(get_db)
):
    from app.services.annotation_service import get_annotations_by_filter

    today_str = date.today().isoformat()

    annotations = get_annotations_by_filter(labeler_id=labeler_id)

    today_annotations = []
    for ann in annotations:
        updated_at_str = ann.get("updated_at", "")
        if updated_at_str and updated_at_str.startswith(today_str):
            today_annotations.append(ann)

    today_labeled_count = len(today_annotations)

    today_submitted_count = 0
    today_valid_count = 0
    today_invalid_count = 0
    today_approved_count = 0
    today_rejected_count = 0

    for ann in today_annotations:
        status = ann.get("status", "")
        is_invalid = ann.get("is_invalid") is True or status in ("invalid", "invalid_submitted", "invalid_approved")

        if status in ["submitted", "invalid", "invalid_submitted"]:
            today_submitted_count += 1

        if is_invalid:
            today_invalid_count += 1
        else:
            today_valid_count += 1

        if status == "approved":
            today_approved_count += 1

        if status in ["rejected_to_modify", "returned_to_modify", "needs_revision", "rejected"]:
            today_rejected_count += 1

    today_total_seconds = _aggregate_work_seconds(db, labeler_id, target_date=today_str)

    logger.debug(f"[work_report] event=report userId={labeler_id} todayTotalSeconds={int(today_total_seconds)} todayLabeled={today_labeled_count} todaySubmitted={today_submitted_count}")

    avg_seconds_per_item = 0
    if today_labeled_count > 0 and today_total_seconds > 0:
        avg_seconds_per_item = round(today_total_seconds / today_labeled_count, 1)

    review_pass_rate = 0.0
    if today_approved_count + today_rejected_count > 0:
        review_pass_rate = round(today_approved_count / (today_approved_count + today_rejected_count), 2)

    ai_human_agreement_rate = 0.0
    ai_agree = 0
    ai_total = 0
    for ann in today_annotations:
        ai_review = ann.get("ai_review")
        review_info = ann.get("review_info")
        if isinstance(ai_review, dict) and isinstance(review_info, dict):
            ai_passed = ai_review.get("passed") is True
            human_action = review_info.get("action", "")
            human_approved = human_action in ("approve",)
            ai_total += 1
            if ai_passed == human_approved:
                ai_agree += 1
    if ai_total > 0:
        ai_human_agreement_rate = round(ai_agree / ai_total, 2)

    return {
        "today_labeled_count": today_labeled_count,
        "today_submitted_count": today_submitted_count,
        "today_valid_count": today_valid_count,
        "today_invalid_count": today_invalid_count,
        "today_approved_count": today_approved_count,
        "today_rejected_count": today_rejected_count,
        "today_total_seconds": int(today_total_seconds),
        "avg_seconds_per_item": avg_seconds_per_item,
        "review_pass_rate": review_pass_rate,
        "ai_human_agreement_rate": ai_human_agreement_rate,
    }


@router.get("/daily")
def get_daily_reports(
    labeler_id: int = Query(2),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    task_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    from app.services.annotation_service import get_annotations_by_filter

    annotations = get_annotations_by_filter(labeler_id=labeler_id, task_id=task_id)

    date_task_data = defaultdict(lambda: {
        "labeled_count": 0,
        "submitted_count": 0,
        "approved_count": 0,
        "rejected_count": 0,
        "invalid_count": 0,
    })

    for ann in annotations:
        updated_at_str = ann.get("updated_at", "")
        if not updated_at_str:
            continue

        ann_date = updated_at_str[:10]
        ann_task_id = ann.get("task_id")

        if start_date and ann_date < start_date:
            continue
        if end_date and ann_date > end_date:
            continue
        if task_id and ann_task_id != task_id:
            continue

        key = (ann_date, ann_task_id)
        data = date_task_data[key]
        data["labeled_count"] += 1

        status = ann.get("status", "")
        if status in ["submitted", "invalid", "invalid_submitted"]:
            data["submitted_count"] += 1
        if status == "approved":
            data["approved_count"] += 1
        if status in ["rejected_to_modify", "returned_to_modify", "needs_revision", "rejected"]:
            data["rejected_count"] += 1
        if status in ("invalid", "invalid_submitted", "invalid_approved") or ann.get("is_invalid") is True:
            data["invalid_count"] += 1

    sessions_query = db.query(AnnotationWorkSession).filter(
        AnnotationWorkSession.labeler_id == labeler_id
    )
    if task_id:
        sessions_query = sessions_query.filter(AnnotationWorkSession.task_id == task_id)
    sessions = sessions_query.all()

    now = datetime.now(timezone.utc)
    date_task_seconds = defaultdict(float)
    for s in sessions:
        try:
            opened = _make_aware(s.opened_at or s.created_at)
            if not opened:
                continue
            s_date = opened.strftime("%Y-%m-%d")
            if start_date and s_date < start_date:
                continue
            if end_date and s_date > end_date:
                continue
            if task_id and s.task_id != task_id:
                continue

            key = (s_date, s.task_id)
            date_task_seconds[key] += calculate_elapsed_seconds(s, now)
        except Exception as e:
            logger.debug(f"[work_report] skip bad session id={s.id}: {e}")
            continue

    all_keys = set(date_task_data.keys()) | set(date_task_seconds.keys())

    result = []
    for ann_date, ann_task_id in sorted(all_keys, reverse=True):
        data = date_task_data.get((ann_date, ann_task_id), {})
        total_seconds = date_task_seconds.get((ann_date, ann_task_id), 0)

        task = db.query(Task).filter(Task.id == ann_task_id).first() if ann_task_id else None
        labeled_count = data.get("labeled_count", 0)
        approved_count = data.get("approved_count", 0)
        rejected_count = data.get("rejected_count", 0)

        pass_rate = 0.0
        if approved_count + rejected_count > 0:
            pass_rate = round(approved_count / (approved_count + rejected_count), 2)

        avg_seconds = round(total_seconds / labeled_count, 1) if labeled_count > 0 and total_seconds > 0 else 0

        result.append({
            "date": ann_date,
            "task_id": ann_task_id,
            "task_name": task.name if task else "",
            "labeled_count": labeled_count,
            "submitted_count": data.get("submitted_count", 0),
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "invalid_count": data.get("invalid_count", 0),
            "total_seconds": int(total_seconds),
            "avg_seconds": avg_seconds,
            "pass_rate": pass_rate,
        })

    return {"reports": result, "total": len(result)}
