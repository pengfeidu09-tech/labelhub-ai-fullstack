import json
import random
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List

# LEGACY: This module uses AIReviewJob/AIReviewResult tables.
# The new Agent main line uses AIReviewRun via agent_service.py.
# Kept for backward compatibility only.

from app.models.ai_review import AIReviewJob, AIReviewResult
from app.models.submission import Submission
from app.models.dataset_item import DatasetItem
from app.core.enums import AIReviewStatus, AIReviewDecision, SubmissionStatus, ItemStatus
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType


def create_ai_review_job(db: Session, submission_id: int) -> AIReviewJob:
    job = AIReviewJob(
        submission_id=submission_id,
        status=AIReviewStatus.PENDING.value
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def run_mock_review(db: Session, submission_id: int) -> AIReviewResult:
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        return None
    
    job = create_ai_review_job(db, submission_id)
    
    job.status = AIReviewStatus.RUNNING.value
    db.commit()
    
    log_action(
        db=db,
        user_id=1,
        action=AuditAction.AI_REVIEW_START,
        target_type=AuditTargetType.AI_REVIEW,
        target_id=job.id,
        after_data={"status": "running"}
    )
    
    data = submission.data
    submission_id_hash = hash(submission_id) % 100
    
    reason = data.get("reason", "")
    has_required_fields = all(key in data for key in ["relevance", "accuracy", "completeness", "safety"])
    
    if len(reason) >= 10 and has_required_fields:
        base_score = 82 + (submission_id_hash % 11)
    elif len(reason) < 10 or not has_required_fields:
        base_score = 45 + (submission_id_hash % 14)
    else:
        base_score = 65 + (submission_id_hash % 14)
    
    overall_score = min(100, max(0, base_score))
    
    dimension_scores = [
        {"name": "相关性", "score": min(100, max(0, overall_score + (submission_id_hash % 10) - 5)), "reason": "评估回答与问题的相关性"},
        {"name": "准确性", "score": min(100, max(0, overall_score + ((submission_id_hash * 7) % 10) - 5)), "reason": "评估回答的准确性"},
        {"name": "完整性", "score": min(100, max(0, overall_score + ((submission_id_hash * 11) % 10) - 5)), "reason": "评估回答的完整性"},
        {"name": "安全性", "score": min(100, max(0, overall_score + ((submission_id_hash * 13) % 10) - 5)), "reason": "评估回答的安全性"}
    ]
    
    if overall_score >= 80:
        decision = AIReviewDecision.PASS.value
        issue_tags = []
        review_comment = "标注质量优秀，通过审核。"
        suggested_fix = ""
    elif overall_score < 60:
        decision = AIReviewDecision.REJECT.value
        issue_tags = ["low_quality", "needs_revision"]
        review_comment = "标注质量不足，需要修改。"
        suggested_fix = "请补充详细的标注理由，并确保所有必填字段都已填写。"
    else:
        decision = AIReviewDecision.HUMAN_REVIEW.value
        issue_tags = ["needs_human_review"]
        review_comment = "标注质量中等，需要人工复核。"
        suggested_fix = "建议人工审核确认标注质量。"
    
    confidence = min(1.0, 0.7 + (submission_id_hash % 30) / 100)
    
    prompt_template = """请评估以下标注的质量：
问题：{prompt}
回答：{model_answer}
参考：{reference}
标注：相关性={relevance}，准确性={accuracy}，完整性={completeness}，安全性={safety}
理由：{reason}

请给出评分和建议。"""
    
    raw_response = json.dumps({
        "decision": decision,
        "overall_score": overall_score,
        "dimension_scores": dimension_scores,
        "issue_tags": issue_tags,
        "review_comment": review_comment,
        "suggested_fix": suggested_fix,
        "confidence": confidence
    }, ensure_ascii=False)
    
    parsed_result = {
        "decision": decision,
        "overall_score": overall_score,
        "dimension_scores": dimension_scores,
        "issue_tags": issue_tags,
        "review_comment": review_comment,
        "suggested_fix": suggested_fix,
        "confidence": confidence
    }
    
    result = AIReviewResult(
        job_id=job.id,
        submission_id=submission_id,
        overall_score=overall_score,
        conclusion=decision,
        dimension_scores=dimension_scores,
        issue_tags=issue_tags,
        review_comment=review_comment,
        suggested_fix=suggested_fix,
        confidence=confidence,
        prompt_template=prompt_template,
        raw_response=raw_response,
        parsed_result=parsed_result,
        mock_mode=True
    )
    db.add(result)
    
    job.status = AIReviewStatus.SUCCESS.value
    db.commit()
    
    log_action(
        db=db,
        user_id=1,
        action=AuditAction.AI_REVIEW_COMPLETE,
        target_type=AuditTargetType.AI_REVIEW,
        target_id=job.id,
        after_data={"status": "success", "conclusion": decision}
    )
    
    update_statuses_after_ai_review(db, submission_id, decision)
    
    return result


def update_statuses_after_ai_review(db: Session, submission_id: int, decision: str):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        return
    
    item = db.query(DatasetItem).filter(DatasetItem.id == submission.dataset_item_id).first()
    
    if decision == AIReviewDecision.PASS.value:
        submission.status = SubmissionStatus.AI_PASSED.value
        submission.status = SubmissionStatus.HUMAN_REVIEWING.value
        if item:
            item.status = ItemStatus.AI_REVIEWED.value
            item.status = ItemStatus.HUMAN_REVIEWING.value
    elif decision == AIReviewDecision.REJECT.value:
        submission.status = SubmissionStatus.REJECTED_TO_MODIFY.value
        if item:
            item.status = ItemStatus.REJECTED.value
    elif decision == AIReviewDecision.HUMAN_REVIEW.value:
        submission.status = SubmissionStatus.HUMAN_REVIEWING.value
        if item:
            item.status = ItemStatus.AI_REVIEWED.value
            item.status = ItemStatus.HUMAN_REVIEWING.value
    
    db.commit()


def get_ai_review_result(db: Session, submission_id: int) -> Optional[AIReviewResult]:
    return db.query(AIReviewResult).filter(AIReviewResult.submission_id == submission_id).first()


def get_ai_review_job(db: Session, job_id: int) -> Optional[AIReviewJob]:
    return db.query(AIReviewJob).filter(AIReviewJob.id == job_id).first()


def generate_ai_review_for_item(db: Session, task_id: int, dataset_item_id: int, schema_json: Optional[Dict] = None) -> Optional[Dict]:
    """
    根据任务ID、数据项ID和schema_json生成AI预审建议
    """
    dataset_item = db.query(DatasetItem).filter(DatasetItem.id == dataset_item_id).first()
    if not dataset_item:
        return None
    
    item_data = dataset_item.raw_data_json or {}
    
    ai_review = mock_ai_review(item_data, schema_json)
    
    submission = db.query(Submission).filter(
        Submission.task_id == task_id,
        Submission.dataset_item_id == dataset_item_id
    ).first()
    
    if submission:
        submission.ai_review = ai_review
        db.commit()
    
    return ai_review


def mock_ai_review(item_data: Dict, schema_json: Optional[Dict] = None) -> Dict:
    """
    Mock AI预审逻辑
    根据item_data简单生成建议
    """
    model_answer = item_data.get('model_answer', '') or item_data.get('answer', '')
    reference = item_data.get('reference', '')
    question = item_data.get('question', '')
    
    completeness = "complete"
    accuracy = "correct"
    safety = "safe"
    relevance = "high"
    issue_tags: List[str] = []
    
    if len(model_answer) < 20:
        completeness = "partial"
        issue_tags.append("incomplete")
    
    if reference and len(reference) > 0:
        reference_keywords = set([w for w in reference.lower().split() if len(w) > 2])
        answer_keywords = set([w for w in model_answer.lower().split() if len(w) > 2])
        
        if reference_keywords and answer_keywords:
            overlap = reference_keywords.intersection(answer_keywords)
            if len(overlap) >= 3:
                accuracy = "correct"
            elif len(overlap) >= 1:
                accuracy = "partial"
            else:
                accuracy = "incorrect"
                issue_tags.append("inaccuracy")
    else:
        if len(model_answer) >= 50:
            accuracy = "correct"
        else:
            accuracy = "partial"
    
    if random.random() < 0.1:
        relevance = "medium"
    
    reasons = [
        "AI 预审认为该回答整体相关，核心事实基本正确。",
        "该回答与问题的相关性较高，但完整性仍有提升空间。",
        "回答内容较为全面，建议人工复核确认。",
        "回答基本满足要求，建议重点检查准确性。"
    ]
    
    reason = random.choice(reasons)
    if issue_tags:
        reason += " 发现以下问题：" + "、".join(issue_tags)
    
    confidence = round(0.75 + random.random() * 0.2, 2)
    
    ai_review = {
        "provider": "mock",
        "status": "completed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "confidence": confidence,
        "suggestion": {
            "relevance": relevance,
            "accuracy": accuracy,
            "completeness": completeness,
            "safety": safety,
            "reason": reason,
            "issue_tags": issue_tags
        },
        "raw_text": f"这是 Mock AI 根据问题「{question[:50]}...」生成的预审建议。"
    }
    
    return ai_review