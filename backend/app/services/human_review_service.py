from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from app.models.human_review import HumanReview
from app.models.submission import Submission
from app.models.dataset_item import DatasetItem
from app.models.ai_review import AIReviewResult
from app.models.task import Task
from app.models.template_schema import TemplateSchema
from app.core.enums import HumanReviewAction, SubmissionStatus, ItemStatus
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType



logger = logging.getLogger(__name__)
def create_human_review(db: Session, submission_id: int, reviewer_id: int, action: str, 
                       comments: Optional[str] = None, revised_data: Optional[Dict] = None) -> HumanReview:
    review = HumanReview(
        submission_id=submission_id,
        reviewer_id=reviewer_id,
        action=action,
        comments=comments,
        revised_data=revised_data
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def approve_submission(db: Session, submission_id: int, reviewer_id: int, comments: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        logger.debug(f"[approve_submission] submission_id={submission_id}, reviewer_id={reviewer_id}")
        
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            logger.debug(f"[approve_submission] submission not found: {submission_id}")
            return None
        
        try:
            create_human_review(db, submission_id, reviewer_id, HumanReviewAction.APPROVE.value, comments)
        except Exception as e:
            logger.warning(f"[approve_submission] warning: create_human_review failed: {e}")
        
        submission.status = SubmissionStatus.APPROVED.value
        
        review_info = {
            "reviewer_id": reviewer_id,
            "action": "approve",
            "comment": comments,
            "reviewed_at": datetime.now().isoformat()
        }
        
        if submission.data and isinstance(submission.data, dict):
            submission.data["review_info"] = review_info
        else:
            submission.data = {"review_info": review_info}
        
        try:
            item = db.query(DatasetItem).filter(DatasetItem.id == submission.dataset_item_id).first()
            if item:
                item.status = ItemStatus.APPROVED.value
                item.status = ItemStatus.EXPORT_READY.value
        except Exception as e:
            logger.warning(f"[approve_submission] warning: update item failed: {e}")
        
        db.commit()
        db.refresh(submission)
        
        try:
            log_action(
                db=db,
                user_id=reviewer_id,
                action=AuditAction.HUMAN_REVIEW_APPROVE,
                target_type=AuditTargetType.HUMAN_REVIEW,
                target_id=submission_id,
                after_data={"status": "approved"}
            )
        except Exception as e:
            logger.warning(f"[approve_submission] warning: log_action failed: {e}")
        
        logger.debug(f"[approve_submission] success: {submission_id}")
        
        return {
            "id": submission.id,
            "task_id": submission.task_id,
            "dataset_item_id": submission.dataset_item_id,
            "labeler_id": submission.labeler_id,
            "status": submission.status,
            "data": submission.data,
            "ai_review": submission.ai_review,
            "review_info": review_info,
            "created_at": submission.created_at.isoformat() if submission.created_at else None,
            "updated_at": submission.updated_at.isoformat() if submission.updated_at else None
        }
    except Exception as e:
        logger.error(f"[approve_submission] error: {e}")
        import traceback
        logger.error(f"[approve_submission] traceback: {traceback.format_exc()}")
        return None


def reject_submission(db: Session, submission_id: int, reviewer_id: int, comments: str) -> Optional[Dict[str, Any]]:
    try:
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            return None
        
        create_human_review(db, submission_id, reviewer_id, HumanReviewAction.REJECT.value, comments)
        
        submission.status = SubmissionStatus.REJECTED_TO_MODIFY.value
        submission.rejected_reason = comments
        
        review_info = {
            "reviewer_id": reviewer_id,
            "action": "reject_to_modify",
            "comment": comments,
            "reviewed_at": datetime.now().isoformat()
        }
        
        if submission.data and isinstance(submission.data, dict):
            submission.data["review_info"] = review_info
        else:
            submission.data = {"review_info": review_info}
        
        item = db.query(DatasetItem).filter(DatasetItem.id == submission.dataset_item_id).first()
        if item:
            item.status = ItemStatus.REJECTED.value
        
        db.commit()
        db.refresh(submission)
        
        log_action(
            db=db,
            user_id=reviewer_id,
            action=AuditAction.HUMAN_REVIEW_REJECT,
            target_type=AuditTargetType.HUMAN_REVIEW,
            target_id=submission_id,
            after_data={"status": "rejected", "reason": comments}
        )
        
        return {
            "id": submission.id,
            "task_id": submission.task_id,
            "dataset_item_id": submission.dataset_item_id,
            "labeler_id": submission.labeler_id,
            "status": submission.status,
            "data": submission.data,
            "ai_review": submission.ai_review,
            "review_info": review_info,
            "created_at": submission.created_at.isoformat() if submission.created_at else None,
            "updated_at": submission.updated_at.isoformat() if submission.updated_at else None
        }
    except Exception as e:
        logger.error(f"[reject_submission] error: {e}")
        import traceback
        logger.error(f"[reject_submission] traceback: {traceback.format_exc()}")
        return None


def revise_submission(db: Session, submission_id: int, reviewer_id: int, revised_data: Dict, 
                     comments: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            return None
        
        create_human_review(db, submission_id, reviewer_id, HumanReviewAction.REVISE.value, comments, revised_data)
        
        review_info = {
            "reviewer_id": reviewer_id,
            "action": "revise",
            "comment": comments,
            "reviewed_at": datetime.now().isoformat()
        }
        
        if isinstance(revised_data, dict):
            revised_data["review_info"] = review_info
        
        submission.status = SubmissionStatus.APPROVED.value
        submission.data = revised_data
        
        item = db.query(DatasetItem).filter(DatasetItem.id == submission.dataset_item_id).first()
        if item:
            item.status = ItemStatus.EXPORT_READY.value
        
        db.commit()
        db.refresh(submission)
        
        log_action(
            db=db,
            user_id=reviewer_id,
            action=AuditAction.HUMAN_REVIEW_REVISE,
            target_type=AuditTargetType.HUMAN_REVIEW,
            target_id=submission_id,
            after_data={"status": "approved", "revised": True}
        )
        
        return {
            "id": submission.id,
            "task_id": submission.task_id,
            "dataset_item_id": submission.dataset_item_id,
            "labeler_id": submission.labeler_id,
            "status": submission.status,
            "data": submission.data,
            "ai_review": submission.ai_review,
            "review_info": review_info,
            "created_at": submission.created_at.isoformat() if submission.created_at else None,
            "updated_at": submission.updated_at.isoformat() if submission.updated_at else None
        }
    except Exception as e:
        logger.error(f"[revise_submission] error: {e}")
        import traceback
        logger.error(f"[revise_submission] traceback: {traceback.format_exc()}")
        return None


def get_pending_submissions(db: Session, page: int = 1, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        # 首先打印所有 submissions 的状态分布
        all_submissions = db.query(Submission).all()
        logger.debug(f"[reviews pending] all submissions count: {len(all_submissions)}")
        logger.debug(f"[reviews pending] all statuses: {[s.status for s in all_submissions]}")
        
        query = db.query(Submission)\
            .filter(Submission.status.in_([
                SubmissionStatus.SUBMITTED.value,
                SubmissionStatus.HUMAN_REVIEWING.value,
                SubmissionStatus.AI_NEED_HUMAN.value,
                SubmissionStatus.AI_PASSED.value,
                SubmissionStatus.REJECTED_TO_MODIFY.value
            ]))
        
        total = query.count()
        logger.debug(f"[reviews pending] pending submissions count: {total}")
        
        submissions = query.order_by(Submission.created_at.desc())\
            .offset((page - 1) * limit)\
            .limit(limit)\
            .all()
        
        result = []
        for submission in submissions:
            try:
                item = db.query(DatasetItem).filter(DatasetItem.id == submission.dataset_item_id).first()
                ai_review = db.query(AIReviewResult).filter(AIReviewResult.submission_id == submission.id).first()
                
                task = db.query(Task).filter(Task.id == submission.task_id).first()
                template_name = None
                if task and task.template_id:
                    template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()
                    if template:
                        template_name = template.name
                
                has_ai_review = ai_review is not None and ai_review.conclusion is not None
                
                result.append({
                    "id": submission.id,
                    "task_id": submission.task_id,
                    "dataset_item_id": submission.dataset_item_id,
                    "labeler_id": submission.labeler_id,
                    "template_id": task.template_id if task else None,
                    "template_name": template_name,
                    "status": submission.status,
                    "data": submission.data,
                    "ai_review": ai_review,
                    "has_ai_review": has_ai_review,
                    "created_at": submission.created_at.isoformat() if submission.created_at else None,
                    "updated_at": submission.updated_at.isoformat() if submission.updated_at else None
                })
            except Exception as e:
                logger.debug(f"[get_pending_submissions] error processing submission {submission.id}: {e}")
                continue
        
        return {"items": result, "total": total, "page": page, "limit": limit}
    except Exception as e:
        logger.error(f"[get_pending_submissions] error: {e}")
        import traceback
        logger.error(f"[get_pending_submissions] traceback: {traceback.format_exc()}")
        return {"items": [], "total": 0, "page": page, "limit": limit}


def get_submission_detail(db: Session, submission_id: int) -> Optional[Dict[str, Any]]:
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        return None
    
    item = db.query(DatasetItem).filter(DatasetItem.id == submission.dataset_item_id).first()
    ai_review = db.query(AIReviewResult).filter(AIReviewResult.submission_id == submission.id).first()
    human_review = db.query(HumanReview).filter(HumanReview.submission_id == submission.id).first()
    
    return {
        "submission": submission,
        "dataset_item": item,
        "ai_review": ai_review,
        "human_review": human_review
    }


def get_human_review(db: Session, review_id: int) -> Optional[HumanReview]:
    return db.query(HumanReview).filter(HumanReview.id == review_id).first()