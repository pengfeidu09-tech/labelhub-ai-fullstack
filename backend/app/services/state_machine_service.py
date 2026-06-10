from sqlalchemy.orm import Session
from typing import Optional

from app.core.enums import TaskStatus, ItemStatus, SubmissionStatus, AIReviewStatus
from app.models.task import Task
from app.models.dataset_item import DatasetItem
from app.models.submission import Submission
from app.models.ai_review import AIReviewJob
from app.services.audit_service import create_audit_log
from app.core.enums import AuditAction, AuditTargetType


class TaskStateMachine:
    @staticmethod
    def can_transition(db: Session, task_id: int, new_status: TaskStatus) -> bool:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return False
        
        current_status = TaskStatus(task.status)
        
        transitions = {
            TaskStatus.DRAFT: [TaskStatus.PUBLISHED],
            TaskStatus.PUBLISHED: [TaskStatus.PAUSED, TaskStatus.ENDED],
            TaskStatus.PAUSED: [TaskStatus.PUBLISHED, TaskStatus.ENDED],
            TaskStatus.ENDED: []
        }
        
        return new_status in transitions.get(current_status, [])
    
    @staticmethod
    def transition(db: Session, task_id: int, new_status: TaskStatus, user_id: int) -> bool:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return False
        
        if not TaskStateMachine.can_transition(db, task_id, new_status):
            return False
        
        before_data = {"status": task.status}
        task.status = new_status.value
        db.commit()
        
        action_map = {
            TaskStatus.PUBLISHED: AuditAction.TASK_PUBLISH,
            TaskStatus.PAUSED: AuditAction.TASK_PAUSE,
            TaskStatus.ENDED: AuditAction.TASK_END
        }
        
        action = action_map.get(new_status)
        if action:
            create_audit_log(
                db=db,
                user_id=user_id,
                action=action,
                target_type=AuditTargetType.TASK,
                target_id=task_id,
                before_data=before_data,
                after_data={"status": new_status.value}
            )
        
        return True


class ItemStateMachine:
    @staticmethod
    def can_transition(db: Session, item_id: int, new_status: ItemStatus) -> bool:
        item = db.query(DatasetItem).filter(DatasetItem.id == item_id).first()
        if not item:
            return False
        
        current_status = ItemStatus(item.status)
        
        transitions = {
            ItemStatus.IMPORTED: [ItemStatus.UNCLAIMED],
            ItemStatus.UNCLAIMED: [ItemStatus.CLAIMED],
            ItemStatus.CLAIMED: [ItemStatus.DRAFTING, ItemStatus.UNCLAIMED],
            ItemStatus.DRAFTING: [ItemStatus.SUBMITTED],
            ItemStatus.SUBMITTED: [ItemStatus.AI_REVIEWING],
            ItemStatus.AI_REVIEWING: [ItemStatus.AI_REVIEWED],
            ItemStatus.AI_REVIEWED: [ItemStatus.HUMAN_REVIEWING, ItemStatus.APPROVED, ItemStatus.REJECTED],
            ItemStatus.HUMAN_REVIEWING: [ItemStatus.APPROVED, ItemStatus.REJECTED],
            ItemStatus.APPROVED: [ItemStatus.EXPORT_READY],
            ItemStatus.REJECTED: [ItemStatus.UNCLAIMED],
            ItemStatus.EXPORT_READY: []
        }
        
        return new_status in transitions.get(current_status, [])
    
    @staticmethod
    def transition(db: Session, item_id: int, new_status: ItemStatus, user_id: Optional[int] = None) -> bool:
        item = db.query(DatasetItem).filter(DatasetItem.id == item_id).first()
        if not item:
            return False
        
        if not ItemStateMachine.can_transition(db, item_id, new_status):
            return False
        
        before_data = {"status": item.status}
        item.status = new_status.value
        
        if new_status == ItemStatus.CLAIMED and user_id:
            item.claimed_by = user_id
        elif new_status == ItemStatus.UNCLAIMED:
            item.claimed_by = None
        
        db.commit()
        
        action_map = {
            ItemStatus.CLAIMED: AuditAction.ITEM_CLAIM,
            ItemStatus.UNCLAIMED: AuditAction.ITEM_UNCLAIM,
            ItemStatus.SUBMITTED: AuditAction.SUBMISSION_SUBMIT
        }
        
        action = action_map.get(new_status)
        if action and user_id:
            create_audit_log(
                db=db,
                user_id=user_id,
                action=action,
                target_type=AuditTargetType.DATASET_ITEM,
                target_id=item_id,
                before_data=before_data,
                after_data={"status": new_status.value}
            )
        
        return True


class SubmissionStateMachine:
    @staticmethod
    def can_transition(db: Session, submission_id: int, new_status: SubmissionStatus) -> bool:
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            return False
        
        current_status = SubmissionStatus(submission.status)
        
        transitions = {
            SubmissionStatus.DRAFT: [SubmissionStatus.SUBMITTED],
            SubmissionStatus.SUBMITTED: [SubmissionStatus.AI_REVIEWING],
            SubmissionStatus.AI_REVIEWING: [SubmissionStatus.AI_PASSED, SubmissionStatus.AI_REJECTED, SubmissionStatus.AI_NEED_HUMAN],
            SubmissionStatus.AI_PASSED: [SubmissionStatus.APPROVED, SubmissionStatus.HUMAN_REVIEWING],
            SubmissionStatus.AI_REJECTED: [SubmissionStatus.REJECTED_TO_MODIFY],
            SubmissionStatus.AI_NEED_HUMAN: [SubmissionStatus.HUMAN_REVIEWING],
            SubmissionStatus.HUMAN_REVIEWING: [SubmissionStatus.APPROVED, SubmissionStatus.REJECTED_TO_MODIFY],
            SubmissionStatus.APPROVED: [],
            SubmissionStatus.REJECTED_TO_MODIFY: [SubmissionStatus.REVISED_SUBMITTED],
            SubmissionStatus.REVISED_SUBMITTED: [SubmissionStatus.AI_REVIEWING]
        }
        
        return new_status in transitions.get(current_status, [])
    
    @staticmethod
    def transition(db: Session, submission_id: int, new_status: SubmissionStatus, user_id: Optional[int] = None) -> bool:
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            return False
        
        if not SubmissionStateMachine.can_transition(db, submission_id, new_status):
            return False
        
        before_data = {"status": submission.status}
        submission.status = new_status.value
        
        if new_status == SubmissionStatus.REVISED_SUBMITTED:
            submission.revision_no = (submission.revision_no or 0) + 1
        
        db.commit()
        
        action_map = {
            SubmissionStatus.SUBMITTED: AuditAction.SUBMISSION_SUBMIT,
            SubmissionStatus.REVISED_SUBMITTED: AuditAction.SUBMISSION_REVISE
        }
        
        action = action_map.get(new_status)
        if action and user_id:
            create_audit_log(
                db=db,
                user_id=user_id,
                action=action,
                target_type=AuditTargetType.SUBMISSION,
                target_id=submission_id,
                before_data=before_data,
                after_data={"status": new_status.value}
            )
        
        return True


class AIReviewStateMachine:
    @staticmethod
    def can_transition(db: Session, job_id: int, new_status: AIReviewStatus) -> bool:
        job = db.query(AIReviewJob).filter(AIReviewJob.id == job_id).first()
        if not job:
            return False
        
        current_status = AIReviewStatus(job.status)
        
        transitions = {
            AIReviewStatus.PENDING: [AIReviewStatus.RUNNING],
            AIReviewStatus.RUNNING: [AIReviewStatus.SUCCESS, AIReviewStatus.FAILED],
            AIReviewStatus.SUCCESS: [],
            AIReviewStatus.FAILED: [AIReviewStatus.PENDING, AIReviewStatus.RUNNING]
        }
        
        return new_status in transitions.get(current_status, [])
    
    @staticmethod
    def transition(db: Session, job_id: int, new_status: AIReviewStatus, user_id: Optional[int] = None) -> bool:
        job = db.query(AIReviewJob).filter(AIReviewJob.id == job_id).first()
        if not job:
            return False
        
        if not AIReviewStateMachine.can_transition(db, job_id, new_status):
            return False
        
        before_data = {"status": job.status}
        job.status = new_status.value
        db.commit()
        
        action_map = {
            AIReviewStatus.RUNNING: AuditAction.AI_REVIEW_START,
            AIReviewStatus.SUCCESS: AuditAction.AI_REVIEW_COMPLETE,
            AIReviewStatus.FAILED: AuditAction.AI_REVIEW_COMPLETE
        }
        
        action = action_map.get(new_status)
        if action:
            actor_id = user_id if user_id else 1
            create_audit_log(
                db=db,
                user_id=actor_id,
                action=action,
                target_type=AuditTargetType.AI_REVIEW,
                target_id=job_id,
                before_data=before_data,
                after_data={"status": new_status.value}
            )
        
        return True