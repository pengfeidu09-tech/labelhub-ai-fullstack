from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from fastapi import HTTPException
import logging

from app.models.draft import Draft
from app.models.submission import Submission
from app.models.dataset_item import DatasetItem
from app.schemas.submission import DraftSaveRequest, SubmissionSubmitRequest
from app.core.enums import ItemStatus, SubmissionStatus
from app.services.audit_service import log_action
from app.services.annotation_service import create_or_update_annotation, save_draft_to_annotations
from app.core.enums import AuditAction, AuditTargetType



logger = logging.getLogger(__name__)
def save_draft(db: Session, request: DraftSaveRequest) -> Draft:
    draft = db.query(Draft)\
        .filter(Draft.dataset_item_id == request.dataset_item_id)\
        .filter(Draft.labeler_id == request.labeler_id)\
        .first()
    
    if draft:
        draft.data = request.data
    else:
        draft = Draft(
            task_id=request.task_id,
            dataset_item_id=request.dataset_item_id,
            labeler_id=request.labeler_id,
            data=request.data
        )
        db.add(draft)
    
    db.commit()
    db.refresh(draft)
    
    item = db.query(DatasetItem).filter(DatasetItem.id == request.dataset_item_id).first()
    if item and item.status != ItemStatus.DRAFTING.value:
        item.status = ItemStatus.DRAFTING.value
        db.commit()
    
    # 同时保存到 JSON 文件
    try:
        save_draft_to_annotations(
            task_id=request.task_id,
            dataset_item_id=request.dataset_item_id,
            labeler_id=request.labeler_id,
            draft_data=request.data,
            template_id=request.template_id
        )
    except Exception as e:
        logger.warning(f"[save_draft] warning: failed to save to JSON: {e}")
    
    log_action(
        db=db,
        user_id=request.labeler_id,
        action=AuditAction.DRAFT_SAVE,
        target_type=AuditTargetType.DATASET_ITEM,
        target_id=request.dataset_item_id,
        after_data={"status": "drafting"}
    )
    
    return draft


def get_draft(db: Session, dataset_item_id: int, labeler_id: int) -> Optional[Draft]:
    return db.query(Draft)\
        .filter(Draft.dataset_item_id == dataset_item_id)\
        .filter(Draft.labeler_id == labeler_id)\
        .first()


def submit_submission(db: Session, request: SubmissionSubmitRequest) -> Dict[str, Any]:
    """
    提交标注 - 直接操作 annotations.json，不再依赖数据库 submissions 表
    """
    logger.debug("[SUBMIT_ROUTE_ENTERED] /api/labeler/submit")
    
    try:
        logger.debug("[submit] ==========================================")
        logger.debug("[submit] === SUBMISSION SERVICE - JSON ONLY ===")
        logger.debug(f"[SUBMIT_ROUTE_TASK_ID] {request.task_id}")
        logger.debug(f"[SUBMIT_ROUTE_DATASET_ITEM_ID] {request.dataset_item_id}")
        logger.debug(f"[SUBMIT_ROUTE_LABELER_ID] {request.labeler_id}")
        
        # 检查最新 annotation 状态（使用统一的 work_key 分组）
        from app.services.annotation_service import create_or_update_annotation, get_work_key_groups
        groups = get_work_key_groups(request.labeler_id)
        latest_by_work_key = groups["latest_by_work_key"]
        
        work_key = f"{request.task_id}:{request.dataset_item_id}:{request.labeler_id}"
        latest_status = None
        latest_ann = None
        
        if work_key in latest_by_work_key:
            latest_ann = latest_by_work_key[work_key]
            latest_status = latest_ann.get("status", "")
        
        logger.debug(f"[SUBMIT_LATEST_STATUS] work_key={work_key}, latest_status={latest_status}")
        
        # 幂等保护：如果已经是 submitted 且属于当前 labeler，返回成功
        if latest_status == "submitted":
            if latest_ann and latest_ann.get("labeler_id") == request.labeler_id:
                logger.debug(f"[SUBMIT_IDEMPOTENT] item already submitted by same labeler")
                return {
                    "success": True,
                    "item_id": request.dataset_item_id,
                    "submission_id": latest_ann.get("id"),
                    "status": "submitted",
                    "message": "该题已提交"
                }
        
        # 检查是否可以提交（只有 approved/passed 才禁止）
        if latest_status in ["approved", "passed"]:
            logger.debug(f"[SUBMIT_DENIED] item already approved")
            raise HTTPException(status_code=409, detail="Item already approved")
        
        # 可以提交的状态
        editable_statuses = ["rejected_to_modify", "draft", "drafting", "claimed", None]
        if latest_status and latest_status not in editable_statuses:
            logger.warning(f"[SUBMIT_WARNING] unexpected status: {latest_status}, proceeding anyway")
        
        # 强制设置 status 为 submitted（这是提交接口，不是草稿接口）
        status = "submitted"
        logger.debug(f"[submit] status forced to 'submitted' (submit interface)")
        
        # 获取 result 数据
        result_data = request.result or request.annotation_result or request.data
        logger.debug(f"[submit] result_data keys: {list(result_data.keys()) if result_data else 'None'}")
        
        # 获取 ai_review 数据
        ai_review_data = request.ai_review if request.ai_review is not None else None
        logger.debug(f"[submit] ai_review: {ai_review_data}")
        
        # 获取 duration_seconds
        duration_seconds = getattr(request, 'duration_seconds', 0)
        
        # 直接操作 annotations.json，不再查询数据库
        annotation = create_or_update_annotation(
            task_id=request.task_id,
            dataset_item_id=request.dataset_item_id,
            labeler_id=request.labeler_id,
            result_data=result_data,
            ai_review=ai_review_data,
            template_id=getattr(request, 'template_id', None),
            template_name="问答质量评估模板",
            status=status  # 强制 submitted
        )
        
        # 添加 duration_seconds
        annotation["duration_seconds"] = duration_seconds
        
        # 重新保存以包含 duration_seconds
        from app.services.annotation_service import _load_annotations, _save_annotations
        annotations = _load_annotations()
        for idx, ann in enumerate(annotations):
            if ann.get("id") == annotation["id"]:
                annotations[idx] = annotation
                break
        _save_annotations(annotations)
        
        work_key = f"{request.task_id}:{request.dataset_item_id}:{request.labeler_id}"
        logger.debug(f"[SUBMIT_SAVED] annotation_id={annotation['id']}, work_key={work_key}, status=submitted")
        
        # 更新 dataset_item 状态：提交后不释放为 unclaimed，保持 submitted 状态
        item = db.query(DatasetItem).filter(DatasetItem.id == request.dataset_item_id).first()
        if item:
            item.status = ItemStatus.SUBMITTED.value
            item.annotation_phase = "submitted"
            db.commit()
            logger.debug(f"[ITEM_SUBMITTED] labeler_id={request.labeler_id}, task_id={request.task_id}, dataset_item_id={request.dataset_item_id}, work_key={work_key}")
        else:
            logger.warning(f"[ITEM_SUBMITTED] warning: dataset_item {request.dataset_item_id} not found")
        
        # 入队 AI 自动预审 Agent
        ai_review_run_id = None
        try:
            from app.services.agent_service import enqueue_ai_review_run
            item_data = {}
            if item and item.raw_data_json:
                item_data = item.raw_data_json if isinstance(item.raw_data_json, dict) else {}

            # ── 解析 dataset_type（item 列 > raw_data > task name > 默认） ──
            from app.models.task import Task as _Task
            task = db.query(_Task).filter(_Task.id == request.task_id).first()

            dataset_type = None
            if item and item.dataset_type:
                dataset_type = item.dataset_type
            if not dataset_type:
                dataset_type = item_data.get("dataset_type")
            if not dataset_type and task:
                task_name = task.name or ""
                if "preference_compare" in task_name:
                    dataset_type = "preference_compare"
            if not dataset_type:
                dataset_type = "qa_quality"

            official_id = (item.official_id if item else None) or item_data.get("official_id") or ""

            # ── 根据 dataset_type 选择 prompt_profile ──
            if dataset_type == "preference_compare":
                prompt_profile = "ai_review_preference_compare_v1"
            else:
                prompt_profile = "ai_review_qa_quality_v1"

            input_snapshot = {
                "item_data": item_data,
                "result_data": result_data,
                "human_result": result_data,       # agent 上下文构建需要
                "schema_json": None,
                "task_id": request.task_id,
                "dataset_item_id": request.dataset_item_id,
                "dataset_type": dataset_type,
                "official_id": official_id,
                "prompt_profile": prompt_profile,
            }
            run = enqueue_ai_review_run(
                db=db,
                task_id=request.task_id,
                item_id=request.dataset_item_id,
                annotation_id=annotation.get("id"),
                labeler_id=request.labeler_id,
                work_key=work_key,
                input_snapshot=input_snapshot,
                trigger_type="auto_on_submit",
            )
            ai_review_run_id = run.id if run else None
            logger.debug(f"[AI_ENQUEUED] run_id={ai_review_run_id}, annotation_id={annotation['id']}")
        except Exception as ai_err:
            logger.warning(f"[AI_ENQUEUE_FAILED] {ai_err} — submission still succeeds")
        
        # 记录审核日志（不影响主流程）
        try:
            log_action(
                db=db,
                user_id=request.labeler_id,
                action=AuditAction.SUBMISSION_SUBMIT,
                target_type=AuditTargetType.SUBMISSION,
                target_id=annotation['id'],
                after_data={
                    "status": "submitted",
                    "dataset_item_id": request.dataset_item_id,
                    "ai_review_run_id": ai_review_run_id,
                }
            )
            logger.debug(f"[AUDIT_LOG_SUCCESS] submission_id={annotation['id']}")
        except Exception as audit_err:
            logger.debug(f"[AUDIT_LOG_FAILED_IGNORED] {audit_err}")
        
        logger.debug(f"[SUBMIT_SUCCESS_RETURN] item_id={request.dataset_item_id}, annotation_id={annotation['id']}, ai_review_run_id={ai_review_run_id}, status=submitted")
        
        # 返回保存的 annotation
        return {
            "success": True,
            "item_id": request.dataset_item_id,
            "submission_id": annotation['id'],
            "annotation_id": annotation['id'],
            "ai_review_run_id": ai_review_run_id,
            "status": "submitted",
            "message": "提交成功，AI 预审已自动触发"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[submit] error: {e}")
        import traceback
        logger.error(f"[submit] traceback: {traceback.format_exc()}")
        raise


def get_submissions(db: Session, task_id: Optional[int] = None, labeler_id: Optional[int] = None,
                   status: Optional[str] = None, page: int = 1, limit: int = 20) -> Dict[str, Any]:
    query = db.query(Submission)
    
    if task_id:
        query = query.filter(Submission.task_id == task_id)
    if labeler_id:
        query = query.filter(Submission.labeler_id == labeler_id)
    if status:
        query = query.filter(Submission.status == status)
    
    total = query.count()
    items = query.order_by(Submission.created_at.desc())\
        .offset((page - 1) * limit)\
        .limit(limit)\
        .all()
    
    return {"items": items, "total": total, "page": page, "limit": limit}


def get_submission(db: Session, submission_id: int) -> Optional[Submission]:
    return db.query(Submission).filter(Submission.id == submission_id).first()