from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional

from app.core.database import get_db
from app.models.task import Task
from app.services.task_service import (
    create_task, get_task, get_tasks, update_task, delete_task,
    publish_task, pause_task, end_task
)
from app.schemas.task import TaskCreate, TaskUpdate, TaskResponse, TaskListResponse

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse)
def create_task_endpoint(task: TaskCreate, db: Session = Depends(get_db), user_id: int = Query(1)):
    return create_task(db, task, user_id)


@router.get("", response_model=TaskListResponse)
def get_tasks_endpoint(
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    return get_tasks(db, status, page, limit)


@router.get("/stats")
def get_task_stats(db: Session = Depends(get_db), labeler_id: int = Query(2)):
    from app.services.task_stats_service import compute_task_stats

    tasks = db.query(Task).filter(Task.status.in_(["published", "paused"])).all()
    result = []
    for task in tasks:
        stats = compute_task_stats(db, task.id)
        result.append({
            "id": task.id,
            "name": task.name,
            "task_no": task.task_no,
            "status": task.status,
            "work_mode": task.work_mode,
            "phase": task.phase,
            "team": task.team,
            "project_no": task.project_no,
            "source_namespace": task.source_namespace,
            "is_official_raw": task.is_official_raw,
            "is_default_demo": task.is_default_demo,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "pending_count": stats.get("total_items", 0) - stats.get("claimed_count", 0) - stats.get("submitted_count", 0) - stats.get("approved_count", 0),
            "in_progress_count": stats.get("claimed_count", 0) + stats.get("drafting_count", 0),
            "to_flow_count": stats.get("submitted_count", 0) + stats.get("pending_review_count", 0),
            "to_rework_count": stats.get("rework_count", 0),
            "total_count": stats.get("total_items", 0),
        })
    return {"tasks": result}


@router.get("/{task_id}", response_model=TaskResponse)
def get_task_endpoint(task_id: int, db: Session = Depends(get_db)):
    task = get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=TaskResponse)
def update_task_endpoint(
    task_id: int,
    task: TaskUpdate,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    updated_task = update_task(db, task_id, task, user_id)
    if not updated_task:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated_task


@router.delete("/{task_id}")
def delete_task_endpoint(
    task_id: int,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    success = delete_task(db, task_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted successfully"}


@router.post("/{task_id}/publish", response_model=TaskResponse)
def publish_task_endpoint(
    task_id: int,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    task = publish_task(db, task_id, user_id)
    if not task:
        raise HTTPException(status_code=400, detail="Cannot publish task")
    return task


@router.post("/{task_id}/pause", response_model=TaskResponse)
def pause_task_endpoint(
    task_id: int,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    task = pause_task(db, task_id, user_id)
    if not task:
        raise HTTPException(status_code=400, detail="Cannot pause task")
    return task


@router.post("/{task_id}/end", response_model=TaskResponse)
def end_task_endpoint(
    task_id: int,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    task = end_task(db, task_id, user_id)
    if not task:
        raise HTTPException(status_code=400, detail="Cannot end task")
    return task


@router.get("/{task_id}/result-summary")
def get_task_result_summary(task_id: int, db: Session = Depends(get_db)):
    from app.services.task_stats_service import compute_task_stats
    from app.models.template_schema import TemplateSchema

    stats = compute_task_stats(db, task_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Task not found")

    task = db.query(Task).filter(Task.id == task_id).first()
    template_name = ""
    if task and task.template_id:
        template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()
        if template:
            template_name = template.name

    stats["template_name"] = template_name
    stats["created_at"] = task.created_at.isoformat() if task and task.created_at else None
    stats["updated_at"] = task.updated_at.isoformat() if task and task.updated_at else None

    return stats


@router.get("/{task_id}/work-items")
def get_task_work_items(task_id: int, page: int = 1, limit: int = 20, db: Session = Depends(get_db)):
    from app.services.annotation_service import get_annotations_by_filter
    from app.models.task import Task
    from app.models.dataset_item import DatasetItem

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    annotations = get_annotations_by_filter(task_id=task_id)

    dataset_items = {}
    for item in db.query(DatasetItem).filter(DatasetItem.task_id == task_id).all():
        dataset_items[item.id] = item

    work_items = []
    for ann in annotations:
        di = dataset_items.get(ann.get("dataset_item_id"))
        ai_review = ann.get("ai_review") or {}
        review_info = ann.get("review_info") or {}

        work_items.append({
            "task_id": ann.get("task_id"),
            "dataset_item_id": ann.get("dataset_item_id"),
            "work_key": f"{ann.get('task_id')}:{ann.get('dataset_item_id')}:{ann.get('labeler_id')}",
            "annotation_id": ann.get("id"),
            "submission_id": ann.get("id"),
            "labeler_id": ann.get("labeler_id"),
            "status": ann.get("status"),
            "ai_review_score": ai_review.get("score"),
            "ai_review_risk_level": ai_review.get("risk_level"),
            "ai_review_passed": ai_review.get("passed"),
            "human_review_action": review_info.get("action"),
            "human_review_comment": review_info.get("comment"),
            "rejected_reason": ann.get("rejected_reason"),
            "revision_no": ann.get("revision_no"),
            "updated_at": ann.get("updated_at"),
            "created_at": ann.get("created_at"),
            "external_id": di.external_id if di else None,
            "dataset_type": di.dataset_type if di else None,
        })

    annotated_item_ids = {ann.get("dataset_item_id") for ann in annotations}
    for item_id, item in dataset_items.items():
        if item_id not in annotated_item_ids:
            work_items.append({
                "task_id": task_id,
                "dataset_item_id": item.id,
                "work_key": None,
                "annotation_id": None,
                "submission_id": None,
                "labeler_id": None,
                "status": item.status or "unclaimed",
                "ai_review_score": None,
                "ai_review_risk_level": None,
                "ai_review_passed": None,
                "human_review_action": None,
                "human_review_comment": None,
                "rejected_reason": None,
                "revision_no": None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "external_id": item.external_id,
                "dataset_type": item.dataset_type,
            })

    work_items.sort(key=lambda x: (
        1 if x["status"] == "unclaimed" else 0,
        x.get("updated_at") or ""
    ), reverse=True)

    total = len(work_items)
    start = (page - 1) * limit
    end = start + limit
    items = work_items[start:end]

    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/{task_id}/detail-items")
def get_task_detail_items(
    task_id: int,
    item_key: Optional[str] = None,
    pack_id: Optional[str] = None,
    is_valid: Optional[bool] = None,
    is_first_annotated: Optional[bool] = None,
    phase: Optional[str] = None,
    phase_status: Optional[str] = None,
    qc_status: Optional[str] = None,
    category: Optional[str] = None,
    supplier: Optional[str] = None,
    labeler_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    from app.models.task import Task
    from app.models.dataset_item import DatasetItem
    from app.services.annotation_service import get_annotations_by_filter

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    query = db.query(DatasetItem).filter(DatasetItem.task_id == task_id)

    if item_key is not None:
        query = query.filter(DatasetItem.item_key == item_key)
    if pack_id is not None:
        query = query.filter(DatasetItem.pack_id == pack_id)
    if is_valid is not None:
        query = query.filter(DatasetItem.is_valid == is_valid)
    if is_first_annotated is not None:
        query = query.filter(DatasetItem.is_first_annotated == is_first_annotated)
    # ── Phase 别名映射: 前端 'qc' 匹配已提交/AI预审阶段; 'review' 匹配人工审核阶段 ──
    phase_aliases = {
        'qc': ['submitted', 'annotation_qc', 'qc', 'ai_pending', 'ai_reviewing', 'ai_reviewed'],
        'review': ['human_review', 'human_reviewing', 'approved', 'rework', 'rejected_to_modify', 'review'],
    }
    if phase is not None and phase not in ("annotation", None):
        aliases = phase_aliases.get(phase, [phase])
        query = query.filter(or_(*[DatasetItem.annotation_phase == alias for alias in aliases]))
    if phase_status is not None:
        query = query.filter(DatasetItem.phase_status == phase_status)
    if qc_status is not None:
        query = query.filter(DatasetItem.qc_status == qc_status)
    if category is not None:
        query = query.filter(DatasetItem.category == category)
    if supplier is not None:
        query = query.filter(DatasetItem.supplier == supplier)
    if labeler_id is not None:
        query = query.filter(DatasetItem.claimed_by == labeler_id)
    if status is not None:
        query = query.filter(DatasetItem.status == status)

    total = query.count()
    items = query.order_by(DatasetItem.id.asc()).offset((page - 1) * limit).limit(limit).all()

    annotations = get_annotations_by_filter(task_id=task_id)

    # 预加载 HumanReview 记录（按 annotation_id 索引）
    from app.models.human_review import HumanReview
    hr_map = {}
    try:
        all_hrs = db.query(HumanReview).filter(
            HumanReview.submission_id.in_([ann.get("id") for ann in annotations if ann.get("id")])
        ).order_by(HumanReview.id.desc()).all()
        for hr in all_hrs:
            if hr.submission_id not in hr_map:
                hr_map[hr.submission_id] = hr
    except Exception:
        pass

    latest_by_item = {}
    for ann in annotations:
        ds_item_id = ann.get("dataset_item_id")
        ann_labeler_id = ann.get("labeler_id")
        if ds_item_id is None:
            continue
        key = (ds_item_id, ann_labeler_id)
        existing = latest_by_item.get(key)
        if existing is None:
            latest_by_item[key] = ann
        else:
            if ann.get("updated_at", "") > existing.get("updated_at", ""):
                latest_by_item[key] = ann

    item_annotations = {}
    for (ds_item_id, _), ann in latest_by_item.items():
        if ds_item_id not in item_annotations or ann.get("updated_at", "") > item_annotations[ds_item_id].get("updated_at", ""):
            item_annotations[ds_item_id] = ann

    result_items = []
    for item in items:
        ann = item_annotations.get(item.id)
        ai_review = ann.get("ai_review", {}) if ann else {}
        review_info = ann.get("review_info", {}) if ann else {}

        annotation_status = ann.get("status") if ann else None
        submission_status = ann.get("status") if ann else None

        current_stage_status = item.status
        if annotation_status:
            current_stage_status = annotation_status

        # ── 计算 work_key ──
        labeler_id_val = item.claimed_by or (ann.get("labeler_id") if ann else None)
        work_key = f"{item.task_id}:{item.id}:{labeler_id_val}" if labeler_id_val else None

        can_submit = current_stage_status in ["claimed", "draft", "drafting", "rejected_to_modify", "returned_to_modify", "needs_revision"]
        can_review = current_stage_status in ["submitted", "ai_reviewed", "invalid_submitted", "invalid_pending"]
        can_rework = current_stage_status in ["rejected_to_modify", "returned_to_modify", "needs_revision"]
        can_mark_invalid = current_stage_status in ["claimed", "draft", "drafting", "rejected_to_modify", "returned_to_modify", "needs_revision"]

        # ── 从 ai_review 提取 AIReviewRun ID ──
        ai_review_id = ai_review.get("run_id") if ai_review else None

        # ── 从 review_info 提取 HumanReview 关联字段 ──
        ann_id = ann.get("id") if ann else None
        hr_record = hr_map.get(ann_id) if ann_id else None
        human_review_id = hr_record.id if hr_record else (review_info.get("id") if review_info else None)
        review_reviewer_id = hr_record.reviewer_id if hr_record else (review_info.get("reviewer_id") if review_info else None)
        review_reviewed_at = hr_record.created_at.isoformat() if hr_record and hr_record.created_at else (review_info.get("reviewed_at") if review_info else None)

        result_items.append({
            "task_item_id": item.id,
            "item_id": item.id,
            "dataset_item_id": item.id,
            "task_id": item.task_id,
            "work_key": work_key,
            "external_id": item.external_id,
            "dataset_type": item.dataset_type,
            "pack_id": item.pack_id,
            "item_key": item.item_key,
            "labeler_id": labeler_id_val,
            "supplier": item.supplier,
            "is_first_labeled": item.is_first_annotated,
            "is_valid": item.is_valid,
            "current_stage_status": current_stage_status,
            "annotation_status": annotation_status,
            "submission_status": submission_status,
            "ai_score": ai_review.get("score") if ai_review else None,
            "ai_risk": ai_review.get("risk_level") if ai_review else None,
            "ai_review_id": ai_review_id,
            "review_status": review_info.get("action") if review_info else None,
            "review_comment": review_info.get("comment") if review_info else None,
            "human_review_id": human_review_id,
            "review_reviewer_id": review_reviewer_id,
            "review_reviewed_at": review_reviewed_at,
            "rejected_reason": ann.get("rejected_reason") if ann else None,
            "invalid_reason": item.invalid_reason or (ann.get("invalid_reason") if ann else None),
            "invalid_remark": ann.get("invalid_remark") if ann else None,
            "is_invalid": ann.get("is_invalid") is True or item.status in ("invalid_pending", "invalid_approved") if ann else item.status in ("invalid_pending", "invalid_approved"),
            "annotation_phase": item.annotation_phase,
            "phase_status": item.phase_status,
            "qc_status": item.qc_status,
            "round_no": item.round_no,
            "total_rounds": item.total_rounds,
            "category": item.category,
            "annotation_id": ann.get("id") if ann else None,
            "submission_id": ann.get("id") if ann else None,
            "revision_no": ann.get("revision_no") if ann else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else (ann.get("updated_at") if ann else None),
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "operation_flags": {
                "can_submit": can_submit,
                "can_review": can_review,
                "can_rework": can_rework,
                "can_mark_invalid": can_mark_invalid
            }
        })

    return {"items": result_items, "total": total, "page": page, "limit": limit}