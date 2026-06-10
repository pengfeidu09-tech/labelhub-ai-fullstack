from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.dataset_item import DatasetItem
from app.models.task import Task
from app.services.annotation_service import get_annotations_by_filter


def compute_task_stats(db: Session, task_id: int) -> Dict[str, Any]:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {}

    total_items = db.query(DatasetItem).filter(DatasetItem.task_id == task_id).count()

    annotations = get_annotations_by_filter(task_id=task_id)

    claimed_count = 0
    drafting_count = 0
    submitted_count = 0
    ai_reviewed_count = 0
    pending_review_count = 0
    approved_count = 0
    rejected_count = 0
    rework_count = 0
    invalid_pending_count = 0
    invalid_approved_count = 0
    export_ready_count = 0

    ai_pass = 0
    ai_reject = 0
    ai_human_review = 0
    ai_scores = []
    ai_risk_low = 0
    ai_risk_medium = 0
    ai_risk_high = 0

    human_approve = 0
    human_reject = 0
    human_revise = 0
    ai_human_agree = 0
    ai_human_total = 0

    issue_counter = {}

    for ann in annotations:
        status = ann.get("status", "")

        if status in ("claimed",):
            claimed_count += 1
        elif status in ("draft", "drafting"):
            drafting_count += 1
        elif status == "submitted":
            submitted_count += 1
            pending_review_count += 1
        elif status in ("ai_reviewing", "ai_reviewed"):
            ai_reviewed_count += 1
            pending_review_count += 1
        elif status == "human_reviewing":
            pending_review_count += 1
        elif status == "approved":
            approved_count += 1
            export_ready_count += 1
        elif status == "export_ready":
            export_ready_count += 1
            approved_count += 1
        elif status in ("rejected_to_modify", "returned_to_modify", "needs_revision"):
            rejected_count += 1
            rework_count += 1
        elif status in ("rework_submitted", "revised_submitted"):
            submitted_count += 1
            pending_review_count += 1
        elif status == "invalid_submitted":
            invalid_pending_count += 1
            pending_review_count += 1
        elif status == "invalid_approved":
            invalid_approved_count += 1

        ai_review = ann.get("ai_review")
        if isinstance(ai_review, dict):
            ai_reviewed_count += 1
            if ai_review.get("passed") is True:
                ai_pass += 1
            elif ai_review.get("passed") is False and ai_review.get("risk_level") == "high":
                ai_reject += 1
            else:
                ai_human_review += 1

            score = ai_review.get("score")
            if isinstance(score, (int, float)):
                ai_scores.append(score)

            risk = ai_review.get("risk_level", "")
            if risk == "high":
                ai_risk_high += 1
            elif risk == "medium":
                ai_risk_medium += 1
            elif risk == "low":
                ai_risk_low += 1

            for issue in (ai_review.get("issues") or []):
                if isinstance(issue, dict):
                    msg = issue.get("message", "")
                    if msg:
                        issue_counter[msg] = issue_counter.get(msg, 0) + 1

        review_info = ann.get("review_info")
        if isinstance(review_info, dict):
            action = review_info.get("action", "")
            if action == "approve":
                human_approve += 1
            elif action in ("reject", "reject_to_modify"):
                human_reject += 1
            elif action in ("revise", "rework"):
                human_revise += 1

            if isinstance(ai_review, dict) and ai_review.get("passed") is not None:
                ai_human_total += 1
                ai_passed = ai_review.get("passed") is True
                human_approved = action in ("approve", "approve_invalid")
                if ai_passed == human_approved:
                    ai_human_agree += 1

    submitted_total = submitted_count + approved_count + rejected_count + invalid_pending_count + invalid_approved_count
    approved_rate = round(approved_count / submitted_total, 2) if submitted_total > 0 else 0
    reject_rate = round(rejected_count / submitted_total, 2) if submitted_total > 0 else 0

    overall_score_avg = round(sum(ai_scores) / len(ai_scores), 1) if ai_scores else 0
    ai_human_agreement_rate = round(ai_human_agree / ai_human_total, 2) if ai_human_total > 0 else None

    top_issues = sorted(issue_counter.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "task_id": task_id,
        "task_name": task.name or "",
        "total_items": total_items,
        "task_status": task.status or "",
        "claimed_count": claimed_count,
        "drafting_count": drafting_count,
        "submitted_count": submitted_count,
        "ai_reviewed_count": ai_reviewed_count,
        "pending_review_count": pending_review_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "rework_count": rework_count,
        "invalid_pending_count": invalid_pending_count,
        "invalid_approved_count": invalid_approved_count,
        "export_ready_count": export_ready_count,
        "approved_rate": approved_rate,
        "reject_rate": reject_rate,
        "ai_decision_stats": {
            "pass": ai_pass,
            "reject": ai_reject,
            "human_review": ai_human_review
        },
        "ai_risk_distribution": {
            "low": ai_risk_low,
            "medium": ai_risk_medium,
            "high": ai_risk_high
        },
        "overall_score_avg": overall_score_avg,
        "ai_human_agreement_rate": ai_human_agreement_rate,
        "human_review_stats": {
            "approve": human_approve,
            "reject": human_reject,
            "revise": human_revise
        },
        "top_issues": [{"message": msg, "count": count} for msg, count in top_issues],
    }
