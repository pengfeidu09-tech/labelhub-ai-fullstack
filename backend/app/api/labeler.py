from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
import json
import logging

from app.core.database import get_db
from app.models.task import Task
from app.models.dataset_item import DatasetItem
from app.models.template_schema import TemplateSchema
from app.models.draft import Draft
from app.services.submission_service import save_draft, get_draft, submit_submission, get_submissions
from app.services.audit_service import log_action
from app.core.enums import ItemStatus, AuditAction, AuditTargetType

from app.schemas.submission import (
    DraftSaveRequest, SubmissionSubmitRequest, DraftResponse, SubmissionResponse, SubmissionListResponse
)

logger = logging.getLogger(__name__)


def safe_log_action(**kwargs):
    """写操作日志，失败时只打印错误，不影响主业务"""
    try:
        log_action(**kwargs)
    except Exception as e:
        logger.debug(f"[AUDIT_LOG_FAILED] {e}")

router = APIRouter(prefix="/api/labeler", tags=["labeler"])


@router.post("/tasks/{task_id}/claim")
def claim_task_endpoint(
    task_id: int,
    db: Session = Depends(get_db),
    labeler_id: int = Query(2)
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    logger.debug(f"[claim] task_id: {task_id}, labeler_id: {labeler_id}")
    
    # 先检查当前 labeler 是否已领取但未完成的 items（全局检查，不限制任务）
    existing_items = db.query(DatasetItem)\
        .filter(DatasetItem.claimed_by == labeler_id)\
        .filter(DatasetItem.status.in_([
            ItemStatus.CLAIMED.value, 
            ItemStatus.DRAFTING.value,
            ItemStatus.REJECTED.value
        ]))\
        .all()
    
    logger.debug(f"[claim] existing labeler items count: {len(existing_items)}")
    
    if existing_items:
        existing_item = existing_items[0]
        logger.debug(f"[claim] found existing item: id={existing_item.id}, status={existing_item.status}")
        return {
            "success": False,
            "message": "你已有进行中任务，请先完成当前任务。",
            "item_id": existing_item.id,
            "status": existing_item.status
        }
    
    # 检查 annotations.json 中是否有 rejected_to_modify 的任务
    from app.services.annotation_service import get_annotations_by_filter
    annotations = get_annotations_by_filter(labeler_id=labeler_id)
    rejected_annotations = [a for a in annotations if a.get("status") == "rejected_to_modify"]
    
    if rejected_annotations:
        logger.debug(f"[claim] found rejected_to_modify annotations: {len(rejected_annotations)}")
        rejected_item_id = rejected_annotations[0].get("dataset_item_id")
        return {
            "success": False,
            "message": "你有待修改的任务，请先完成当前任务。",
            "item_id": rejected_item_id,
            "status": "rejected_to_modify"
        }
    
    # 查找未领取的 items（只领取一条）
    item = db.query(DatasetItem)\
        .filter(DatasetItem.task_id == task_id)\
        .filter(DatasetItem.status == ItemStatus.UNCLAIMED.value)\
        .first()
    
    available_count = db.query(DatasetItem)\
        .filter(DatasetItem.task_id == task_id)\
        .filter(DatasetItem.status == ItemStatus.UNCLAIMED.value)\
        .count()
    
    logger.debug(f"[claim] available unclaimed items count: {available_count}")
    
    if item:
        item.status = ItemStatus.CLAIMED.value
        item.claimed_by = labeler_id
        db.commit()
        
        safe_log_action(
            db=db,
            user_id=labeler_id,
            action=AuditAction.ITEM_CLAIM,
            target_type=AuditTargetType.DATASET_ITEM,
            target_id=item.id,
            after_data={"status": item.status, "claimed_by": labeler_id}
        )
        
        return {
            "success": True,
            "message": "Task claimed successfully",
            "item_id": item.id
        }
    else:
        raise HTTPException(status_code=400, detail="No unclaimed items available")


@router.get("/tasks")
def get_labeler_tasks_endpoint(
    db: Session = Depends(get_db),
    labeler_id: int = Query(2)
):
    tasks = db.query(Task)\
        .join(DatasetItem, Task.id == DatasetItem.task_id)\
        .filter(DatasetItem.claimed_by == labeler_id)\
        .filter(DatasetItem.status.in_([ItemStatus.CLAIMED.value, ItemStatus.DRAFTING.value]))\
        .distinct()\
        .all()
    
    return {"items": tasks, "total": len(tasks)}


def _normalize_work_key(work_key: Optional[str], labeler_id: int = 2) -> Optional[str]:
    """统一 work_key 格式为 task_id:item_id:labeler_id 三段式"""
    if not work_key:
        return None
    parts = work_key.split(":")
    if len(parts) == 3:
        return work_key
    elif len(parts) == 2:
        return f"{parts[0]}:{parts[1]}:{labeler_id}"
    return None


@router.get("/items")
def get_labeler_items_endpoint(
    task_id: Optional[int] = None,
    db: Session = Depends(get_db),
    labeler_id: int = Query(2)
):
    # 使用统一的 work_key 分组
    from app.services.annotation_service import get_work_key_groups
    groups = get_work_key_groups(labeler_id)
    
    latest_by_work_key = groups["latest_by_work_key"]
    terminal_work_keys = groups["terminal_work_keys"]
    active_work_keys = groups["active_work_keys"]
    rework_work_keys = groups["rework_work_keys"]
    
    logger.debug(f"[workbench] labeler_id={labeler_id}")
    logger.debug(f"[workbench] terminal_work_keys: {terminal_work_keys}")
    logger.debug(f"[workbench] active_work_keys: {active_work_keys}")
    logger.debug(f"[workbench] rework_work_keys: {rework_work_keys}")
    
    # 获取所有活跃的 work_keys（返修 + 草稿 + 已领取）
    all_active_work_keys = list(active_work_keys.union(rework_work_keys))
    
    logger.debug(f"[workbench] all active work_keys: {all_active_work_keys}")
    
    # 直接基于 work_key 构建队列
    result_items = []
    
    for wk in all_active_work_keys:
        ann = latest_by_work_key.get(wk)
        
        logger.debug(f"[workbench-build-item] start wk={wk}")
        
        if not ann:
            logger.debug(f"[workbench-build-item] skipped wk={wk}, reason=no annotation found in latest_by_work_key")
            continue
        
        # ===== 关键：从 work_key 解析 task_id / item_id / labeler_id =====
        # work_key 是唯一真实来源，不允许被 DB 查询结果覆盖
        wk_parts = wk.split(":")
        if len(wk_parts) >= 2:
            wk_task_id = int(wk_parts[0])
            wk_item_id = int(wk_parts[1])
        else:
            logger.debug(f"[workbench-build-item] skipped wk={wk}, reason=invalid work_key format")
            continue
        
        # 从 annotation 中提取信息（仅供参考，不覆盖 work_key 中的值）
        ann_task_id = ann.get("task_id")
        ann_item_id = ann.get("dataset_item_id")
        
        if not ann_task_id or not ann_item_id:
            logger.debug(f"[workbench-build-item] skipped wk={wk}, reason=missing task_id or dataset_item_id in annotation")
            continue
        
        logger.debug(f"[workbench-build-item] found_annotation id={ann.get('id')}, ann_task_id={ann_task_id}, ann_item_id={ann_item_id}, status={ann.get('status')}")
        
        # ===== 查询 DatasetItem：必须按 task_id + item_id 联合查 =====
        # 不允许 id-only fallback 覆盖 task_id
        item = db.query(DatasetItem)\
            .filter(DatasetItem.id == wk_item_id)\
            .filter(DatasetItem.task_id == wk_task_id)\
            .first()
        
        if not item:
            # 尝试用 annotation 中的 task_id + item_id 查（可能 work_key 中的 task_id 是错的）
            item = db.query(DatasetItem)\
                .filter(DatasetItem.id == ann_item_id)\
                .filter(DatasetItem.task_id == ann_task_id)\
                .first()
        
        if not item:
            # 仍然查不到，用 annotation 数据兜底，但 task_id/work_key 必须保持原始值
            logger.debug(f"[workbench-build-item] DatasetItem not found for wk={wk}, using annotation snapshot")
        else:
            logger.debug(f"[workbench-build-item] found_dataset_item id={item.id}, task_id={item.task_id}")
        
        # ===== task_id 和 work_key 必须来自原始 work_key，不允许被 DB 覆盖 =====
        final_task_id = wk_task_id
        final_item_id = wk_item_id
        final_work_key = wk  # 保持原始 work_key 不变
        
        # 判断模式
        mode = "new"
        is_rework = False
        effective_status = ann.get("status", "")
        if effective_status in ["rejected_to_modify", "returned_to_modify", "needs_revision"]:
            mode = "rework"
            is_rework = True
        elif effective_status in ["draft", "drafting"]:
            if ann.get("rejected_reason") or ann.get("review_info"):
                mode = "rework_draft"
                is_rework = True
            else:
                mode = "draft"
        elif effective_status == "claimed":
            mode = "new"
        
        # 获取审核信息
        review_info = ann.get("review_info", {})
        review_reason = ann.get("rejected_reason", "") or review_info.get("comment", "")
        review_time = review_info.get("reviewed_at", "")
        reviewer_id = review_info.get("reviewer_id", "")
        
        # 获取 task 信息
        task = db.query(Task).filter(Task.id == final_task_id).first()
        if not task:
            # 尝试用 annotation 中的 task_id
            task = db.query(Task).filter(Task.id == ann_task_id).first()
        logger.debug(f"[workbench-build-item] found_task={'yes' if task else 'no'} (task_id={final_task_id})")
        
        display_title = f"Task #{final_task_id} / Item #{final_item_id}"
        
        # 调试日志
        logger.debug(f"[workbench-build-item] wk={wk}, final_task_id={final_task_id}, final_item_id={final_item_id}, status={effective_status}, mode={mode}, is_rework={is_rework}, review_reason={review_reason[:50] if review_reason else 'None'}...")
        
        # 获取 item_data：优先从 DatasetItem，其次从 annotation
        item_data = None
        if item:
            item_data = item.raw_data_json
        if not item_data:
            # 从 annotation 中获取 item_data / raw_item_data
            item_data = ann.get("item_data") or ann.get("raw_item_data") or {}
        
        item_dict = {
            "id": final_item_id,
            "task_id": final_task_id,
            "dataset_item_id": final_item_id,
            "work_key": final_work_key,
            "full_work_key": wk,
            "display_title": display_title,
            "item_status": item.status if item else effective_status,
            "claimed_by": item.claimed_by if item else labeler_id,
            "created_at": item.created_at.isoformat() if item and item.created_at else ann.get("created_at"),
            "updated_at": item.updated_at.isoformat() if item and item.updated_at else ann.get("updated_at"),
            "work_status": effective_status,
            "submission_id": ann.get("id"),
            "annotation_id": ann.get("id"),
            "effectiveStatus": effective_status,
            "mode": mode,
            "is_rework": is_rework,
            "review_reason": review_reason,
            "review_time": review_time,
            "reviewer_id": reviewer_id,
            "reviewed_at": review_time,
            "annotation_result": ann.get("result", {}),
            "item_data": item_data,
            "task_template_id": task.template_id if task else None,
            "task_name": task.name if task else None
        }
        
        result_items.append(item_dict)
        logger.debug(f"[workbench-build-item] returned wk={wk}")
    
    # 排序：rejected_to_modify / rework_draft 优先，然后是 draft，最后是 claimed
    # 同状态内按 updated_at 倒序
    def sort_key(item_dict):
        effective_status = item_dict.get("work_status", "")
        mode = item_dict.get("mode", "")
        
        status_order = {
            "rejected_to_modify": 0,
            "returned_to_modify": 0,
            "needs_revision": 0,
            "rework": 0,
            "rework_draft": 0.5,
            "draft": 1,
            "drafting": 1,
            "claimed": 2
        }
        
        order = status_order.get(effective_status, status_order.get(mode, 99))
        updated_at = item_dict.get("updated_at", "")
        return (order, updated_at)
    
    result_items.sort(key=sort_key, reverse=True)
    
    # 按 work_key 去重：同一个 work_key 只保留优先级最高的一条
    before_count = len(result_items)
    deduped_items = []
    seen_work_keys = {}
    
    # 状态优先级：数字越小优先级越高
    status_priority = {
        "rejected_to_modify": 0,
        "returned_to_modify": 0,
        "needs_revision": 0,
        "rework": 0,
        "rework_draft": 0.5,
        "draft": 1,
        "drafting": 1,
        "claimed": 2,
        "unclaimed": 3,
        "submitted": 4,
        "approved": 4
    }
    
    for item_dict in result_items:
        wk = item_dict.get("work_key", "")
        if not wk:
            # 没有 work_key 的项，用 task_id:dataset_item_id:labeler_id 构造
            wk = f"{item_dict.get('task_id')}:{item_dict.get('dataset_item_id')}:{labeler_id}"
            item_dict["work_key"] = wk
        
        if wk not in seen_work_keys:
            seen_work_keys[wk] = item_dict
            deduped_items.append(item_dict)
        else:
            # 已存在，按状态优先级决定保留哪条
            existing = seen_work_keys[wk]
            existing_priority = status_priority.get(existing.get("work_status", ""), 99)
            new_priority = status_priority.get(item_dict.get("work_status", ""), 99)
            if new_priority < existing_priority:
                # 新的优先级更高，替换
                deduped_items = [item_dict if d.get("work_key") == wk else d for d in deduped_items]
                seen_work_keys[wk] = item_dict
            logger.debug(f"[workbench-dedupe] duplicate work_key={wk}, keeping higher priority item")
    
    duplicate_keys = [wk for wk in seen_work_keys if sum(1 for i in result_items if i.get("work_key") == wk) > 1]
    
    logger.debug(f"[workbench-dedupe] before_count={before_count}")
    logger.debug(f"[workbench-dedupe] after_count={len(deduped_items)}")
    logger.debug(f"[workbench-dedupe] duplicate_keys={duplicate_keys}")
    logger.debug(f"[workbench] returning items: {len(deduped_items)}")
    logger.debug(f"[workbench] work_keys: {[item['work_key'] for item in deduped_items]}")
    logger.debug(f"[workbench] work_statuses: {[item['work_status'] for item in deduped_items]}")
    
    return {"items": deduped_items, "total": len(deduped_items)}


@router.get("/form/{dataset_item_id}")
def get_labeler_form_endpoint(
    dataset_item_id: int,
    task_id: Optional[int] = None,
    submission_id: Optional[int] = None,
    work_key: Optional[str] = None,
    db: Session = Depends(get_db),
    labeler_id: int = Query(2)
):
    logger.debug(f"[getLabelerForm] called with item_id={dataset_item_id}, task_id={task_id}, submission_id={submission_id}, work_key={work_key}")
    
    from app.services.annotation_service import get_work_key_groups, get_annotations_by_filter, get_annotation_by_id
    
    # ===== 优先级 1: submission_id =====
    target_ann = None
    target_wk = None
    
    if submission_id:
        target_ann = get_annotation_by_id(submission_id)
        if target_ann:
            ann_task_id = target_ann.get("task_id")
            ann_item_id = target_ann.get("dataset_item_id")
            ann_labeler_id = target_ann.get("labeler_id", labeler_id)
            target_wk = f"{ann_task_id}:{ann_item_id}:{ann_labeler_id}"
            logger.debug(f"[getLabelerForm] found by submission_id={submission_id}, wk={target_wk}")
        else:
            logger.debug(f"[getLabelerForm] submission_id={submission_id} not found in annotations")
    
    # ===== 优先级 2: work_key =====
    if not target_ann and work_key:
        normalized_wk = _normalize_work_key(work_key, labeler_id)
        if normalized_wk:
            groups = get_work_key_groups(labeler_id)
            latest_by_work_key = groups["latest_by_work_key"]
            if normalized_wk in latest_by_work_key:
                target_ann = latest_by_work_key[normalized_wk]
                target_wk = normalized_wk
                logger.debug(f"[getLabelerForm] found by work_key={normalized_wk}")
            else:
                logger.debug(f"[getLabelerForm] work_key={normalized_wk} not in latest_by_work_key")
    
    # ===== 优先级 3: task_id + dataset_item_id =====
    if not target_ann and task_id:
        groups = get_work_key_groups(labeler_id)
        latest_by_work_key = groups["latest_by_work_key"]
        candidate_wk = f"{task_id}:{dataset_item_id}:{labeler_id}"
        if candidate_wk in latest_by_work_key:
            target_ann = latest_by_work_key[candidate_wk]
            target_wk = candidate_wk
            logger.debug(f"[getLabelerForm] found by task_id+item_id, wk={candidate_wk}")
        else:
            logger.debug(f"[getLabelerForm] candidate_wk={candidate_wk} not in latest_by_work_key")
    
    # ===== 优先级 4: item_id-only fallback =====
    if not target_ann:
        groups = get_work_key_groups(labeler_id)
        latest_by_work_key = groups["latest_by_work_key"]
        # 遍历所有 work_key 找到 dataset_item_id 匹配的
        for wk, ann in latest_by_work_key.items():
            if ann.get("dataset_item_id") == dataset_item_id:
                target_ann = ann
                target_wk = wk
                logger.debug(f"[getLabelerForm] found by item_id fallback, wk={wk}")
                break
    
    # ===== 查找 DatasetItem =====
    # task_id/work_key 必须来自请求参数或 annotation，不允许被 DB 查询结果覆盖
    item = None
    # 最终 task_id：优先使用请求参数中的 task_id，其次用 annotation 中的
    final_task_id = task_id  # URL 参数中的 task_id
    
    if target_ann:
        ann_task_id = target_ann.get("task_id")
        ann_item_id = target_ann.get("dataset_item_id")
        
        # 如果没有 URL task_id，用 annotation 的
        if not final_task_id:
            final_task_id = ann_task_id
        
        # 先用 work_key 解析的 task_id + item_id 精确查
        if target_wk:
            wk_parts = target_wk.split(":")
            if len(wk_parts) >= 2:
                wk_task_id = int(wk_parts[0])
                wk_item_id = int(wk_parts[1])
                item = db.query(DatasetItem)\
                    .filter(DatasetItem.id == wk_item_id)\
                    .filter(DatasetItem.task_id == wk_task_id)\
                    .first()
        
        # 如果没查到，用 annotation 中的 task_id + item_id 查
        if not item:
            item = db.query(DatasetItem)\
                .filter(DatasetItem.id == ann_item_id)\
                .filter(DatasetItem.task_id == ann_task_id)\
                .first()
        
        # 如果还是没查到，不允许 id-only fallback 覆盖 task_id
        # 用 annotation 数据兜底，但保持原始 task_id/work_key
        if not item:
            logger.debug(f"[getLabelerForm] DatasetItem not found for task_id={final_task_id}, item_id={ann_item_id}, using annotation snapshot")
    
    if not item and not target_ann:
        # 最后尝试直接用 dataset_item_id 查
        item = db.query(DatasetItem).filter(DatasetItem.id == dataset_item_id).first()
        if item:
            final_task_id = item.task_id
            if not target_wk:
                target_wk = f"{item.task_id}:{dataset_item_id}:{labeler_id}"
    
    # ===== 如果 DatasetItem 也找不到，用 annotation 数据兜底 =====
    if not item and target_ann:
        logger.debug(f"[getLabelerForm] DatasetItem not found, using annotation data as fallback")
        # final_task_id 保持不变，不覆盖
        if not target_wk:
            target_wk = f"{final_task_id}:{dataset_item_id}:{labeler_id}"
    elif not item and not target_ann:
        raise HTTPException(status_code=404, detail=f"Dataset item {dataset_item_id} not found and no annotation data available")
    
    # 确保 work_key 使用 final_task_id（来自请求参数或 annotation，不被 DB 覆盖）
    if target_wk:
        # 验证 work_key 中的 task_id 与 final_task_id 一致
        wk_parts = target_wk.split(":")
        if len(wk_parts) >= 2 and int(wk_parts[0]) != final_task_id:
            logger.debug(f"[getLabelerForm] correcting work_key task_id from {wk_parts[0]} to {final_task_id}")
            target_wk = f"{final_task_id}:{wk_parts[1]}:{wk_parts[2] if len(wk_parts) == 3 else labeler_id}"
    
    # ===== 权限检查 =====
    latest_status = target_ann.get("status", "") if target_ann else None
    if not latest_status and item:
        latest_status = item.status
    
    logger.debug(f"[FORM_ACCESS_CHECK] item_id={dataset_item_id}, labeler_id={labeler_id}, latest_status={latest_status}, work_key={target_wk}")
    
    editable_statuses = ["rejected_to_modify", "draft", "drafting", "claimed", "returned_to_modify", "needs_revision"]
    
    access_allowed = False
    if latest_status in editable_statuses:
        access_allowed = True
    elif item and item.claimed_by == labeler_id:
        access_allowed = True
    
    if not access_allowed:
        logger.debug(f"[FORM_ACCESS_DENIED] latest_status={latest_status}")
        raise HTTPException(status_code=403, detail="Item not accessible")
    
    logger.debug(f"[FORM_ACCESS_ALLOWED] item_id={dataset_item_id}, work_key={target_wk}")
    
    # ===== 获取 Task 和 Template =====
    task = db.query(Task).filter(Task.id == final_task_id).first()
    if not task and target_ann:
        # 尝试用 annotation 中的 task_id
        task = db.query(Task).filter(Task.id == target_ann.get("task_id")).first()
    
    # 解析模板 - 严格从 task.template_id 加载
    resolved_template = None
    schema_source = 'missing template'

    if task and task.template_id:
        resolved_template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()
        if resolved_template:
            schema_source = 'task.template_id'

    if not resolved_template:
        # 不再使用 fallback，直接报错
        logger.warning(f'[getLabelerForm] task {final_task_id} has no bound template (template_id={task.template_id if task else None})')
        # 仍然返回结果但 schema_json 为 None，前端可以显示错误提示
    
    logger.debug(f'[getLabelerForm] task_id={final_task_id}, template_source={schema_source}')
    if resolved_template:
        logger.debug(f'[getLabelerForm] template.id={resolved_template.id}, template.name={resolved_template.name}')
    
    # ===== 构建返回结果 =====
    # item_data: 优先从 DatasetItem，其次从 annotation snapshot 兜底
    item_data = None
    if item:
        item_data = item.raw_data_json
    
    if not item_data and target_ann:
        # 按优先级从 annotation 中兜底 item_data
        item_data = (
            target_ann.get("item_data") or
            target_ann.get("raw_item_data") or
            target_ann.get("item_snapshot") or
            target_ann.get("dataset_item_snapshot") or
            target_ann.get("source_item") or
            (target_ann.get("metadata") or {}).get("item_data") or
            None
        )
        # 最后尝试从 result_data 中提取原始数据
        if not item_data:
            result_data = target_ann.get("result") or target_ann.get("annotation_result") or target_ann.get("data") or {}
            if isinstance(result_data, dict):
                item_data = (
                    result_data.get("input") or
                    result_data.get("raw_item") or
                    result_data.get("original_data") or
                    None
                )
        
        if item_data:
            logger.debug(f"[FORM_SNAPSHOT_FALLBACK] using annotation snapshot for item_data, work_key={target_wk}")
        else:
            available_keys = list(target_ann.keys()) if target_ann else []
            logger.debug(f"[FORM_SNAPSHOT_MISSING] work_key={target_wk}, annotation_id={target_ann.get('id')}, available_keys={available_keys}")
    
    if not item_data:
        item_data = {}
    
    # 标记原始数据是否来自快照（缺失时前端可提示）
    item_data_from_snapshot = (item is None and bool(item_data))
    item_data_missing = (item is None and not bool(item_data))
    
    result = {
        "task_id": final_task_id,
        "dataset_item_id": dataset_item_id,
        "work_key": target_wk,
        "task_template_id": task.template_id if task else None,
        "resolved_template_id": resolved_template.id if resolved_template else None,
        "resolved_template_name": resolved_template.name if resolved_template else None,
        "schema_json": resolved_template.schema if resolved_template else None,
        "item_data": item_data,
        "annotation_result": {},
        "schema_source": schema_source,
        "template": None,
        "mode": "new",
        "item_data_from_snapshot": item_data_from_snapshot,
        "item_data_missing": item_data_missing
    }

    result["template_version"] = resolved_template.schema_version if resolved_template else None
    result["llm_assist_enabled"] = bool(task.llm_assist_enabled) if task and task.llm_assist_enabled is not None else True
    result["llm_assist_reason"] = None
    if task and not (task.llm_assist_enabled if task.llm_assist_enabled is not None else True):
        result["llm_assist_reason"] = "task_disabled"
    
    if resolved_template:
        result["template"] = {
            "id": resolved_template.id,
            "name": resolved_template.name,
            "schema_json": resolved_template.schema
        }
    
    # ===== 使用 target_ann 填充信息 =====
    if target_ann:
        ann_status = target_ann.get("status", "")
        ann_result = target_ann.get("result", {})
        ann_rejected_reason = target_ann.get("rejected_reason", "")
        ann_review_info = target_ann.get("review_info", {})
        
        result["annotation_result"] = ann_result
        result["submission_id"] = target_ann.get("id")
        result["annotation_id"] = target_ann.get("id")
        result["latest_status"] = ann_status
        
        # 判断 mode
        if ann_status in ["rejected_to_modify", "returned_to_modify", "needs_revision"]:
            result["mode"] = "rework"
            result["is_rework"] = True
        elif ann_status in ["draft", "drafting"]:
            if ann_rejected_reason or ann_review_info:
                result["mode"] = "rework"
                result["is_rework"] = True
            else:
                result["mode"] = "draft"
        elif ann_status == "claimed":
            result["mode"] = "new"
        
        # 添加审核信息
        if ann_rejected_reason or ann_review_info:
            result["rejected_reason"] = ann_rejected_reason
            result["review_info"] = ann_review_info
            result["review_reason"] = ann_rejected_reason or ann_review_info.get("comment", "")
            result["review_time"] = ann_review_info.get("reviewed_at", "")
            result["reviewer_id"] = ann_review_info.get("reviewer_id", "")
            result["is_rework"] = True
            result["mode"] = "rework"
        
        result["draft"] = ann_result

        # AI 预审结果：优先从数据库 AIReviewRun 取最新记录
        ai_review_from_db = None
        try:
            from app.models.ai_review_run import AIReviewRun
            latest_run = db.query(AIReviewRun).filter(
                AIReviewRun.task_id == result.get("task_id"),
                AIReviewRun.item_id == dataset_item_id,
            ).order_by(AIReviewRun.id.desc()).first()
            if latest_run and latest_run.status in ("success", "failed", "fallback_required"):
                output_json = latest_run.output_json or {}
                dimensions = output_json.get("dimensions", {})
                issue_tags = output_json.get("issue_tags", [])
                problem_tags = output_json.get("problem_tags", issue_tags)
                # 生成 suggestion 字段（兼容前端 ReviewDetailPage 的 aiSuggestion 读取）
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
                ai_review_from_db = {
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
                    "raw_response_preview": latest_run.raw_response_preview,
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
                    "prompt_template": output_json.get("prompt_template", ""),
                    "prompt_version": latest_run.prompt_version,
                    "fallback": bool(latest_run.used_fallback) if latest_run.used_fallback is not None else False,
                    "fallback_used": bool(latest_run.used_fallback) if latest_run.used_fallback is not None else False,
                    "fallback_provider": output_json.get("fallback_provider"),
                    "fallback_reason": output_json.get("fallback_reason"),
                }
        except Exception as e:
            logger.debug(f"[getLabelerForm] AIReviewRun lookup failed: {e}")

        if ai_review_from_db:
            result["ai_review"] = ai_review_from_db
            result["ai_review_score"] = ai_review_from_db.get("score")
            result["ai_review_risk_level"] = ai_review_from_db.get("risk_level")
            result["ai_review_passed"] = ai_review_from_db.get("passed")
        elif target_ann.get("ai_review"):
            result["ai_review"] = target_ann["ai_review"]
            result["ai_review_score"] = target_ann["ai_review"].get("score")
            result["ai_review_risk_level"] = target_ann["ai_review"].get("risk_level")
            result["ai_review_passed"] = target_ann["ai_review"].get("passed")
    
    logger.debug(f'[getLabelerForm] result: task_id={result["task_id"]}, work_key={result["work_key"]}, mode={result["mode"]}, is_rework={result.get("is_rework")}, review_reason={result.get("review_reason", "")[:50]}, has_ai_review={bool(result.get("ai_review"))}')
    
    return result


@router.post("/draft")
def save_draft_endpoint(
    request: DraftSaveRequest,
    db: Session = Depends(get_db)
):
    """保存草稿（到 annotations.json）"""
    logger.debug(f"[draft] saving draft for task_id={request.task_id}, dataset_item_id={request.dataset_item_id}")
    
    from app.services.annotation_service import save_draft_to_annotations
    
    # 获取模板信息
    task = db.query(Task).filter(Task.id == request.task_id).first()
    template_name = "问答质量评估模板"
    template_id = None
    if task and task.template_id:
        template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()
        if template:
            template_name = template.name
            template_id = template.id
    
    # 保存到 annotations.json
    annotation = save_draft_to_annotations(
        task_id=request.task_id,
        dataset_item_id=request.dataset_item_id,
        labeler_id=request.labeler_id,
        draft_data=request.data,
        template_id=template_id,
        template_name=template_name,
        ai_review=request.ai_review
    )
    
    logger.debug(f"[draft] saved draft with status: {annotation.get('status')}")
    
    return {
        "id": annotation.get("id"),
        "task_id": annotation.get("task_id"),
        "dataset_item_id": annotation.get("dataset_item_id"),
        "labeler_id": annotation.get("labeler_id"),
        "data": annotation.get("result"),
        "status": annotation.get("status"),
        "created_at": annotation.get("created_at"),
        "updated_at": annotation.get("updated_at")
    }


def _execute_agent_after_submit(
    run_id: int,
    task_id: int,
    item_id: int,
    annotation_id: int,
):
    """提交后异步执行 AI 预审 Agent。

    由 BackgroundTasks 调用，使用独立的 db session，不影响请求响应。
    AI 失败不会导致 submission 丢失。
    """
    from app.core.database import SessionLocal
    from app.models.ai_review_run import AIReviewRun
    from app.services.agent_service import execute_agent_run, _update_annotation_after_agent

    db = SessionLocal()
    try:
        run = db.query(AIReviewRun).filter(AIReviewRun.id == run_id).first()
        if run:
            logger.debug(f"[BG_AGENT] executing run #{run_id} for item #{item_id}")
            execute_agent_run(db, run)
            _update_annotation_after_agent(db, run, annotation_id, item_id, task_id)
            logger.debug(f"[BG_AGENT] run #{run_id} completed: status={run.status}, score={run.score}")
        else:
            logger.warning(f"[BG_AGENT] run #{run_id} not found")
    except Exception as e:
        logger.error(f"[BG_AGENT] run #{run_id} failed: {e}")
    finally:
        db.close()


@router.post("/submit")
def submit_submission_endpoint(
    request: SubmissionSubmitRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    logger.debug("[SUBMIT_ROUTE_ENTERED] /api/labeler/submit")
    logger.debug(f"[SUBMIT_ROUTE_PAYLOAD] task_id={request.task_id}, dataset_item_id={request.dataset_item_id}, labeler_id={request.labeler_id}")

    # ===== 必填项验证（仅对 submitted 状态） =====
    result_data = request.result or request.annotation_result or request.data
    request_status = request.status or "submitted"

    if request_status == "submitted" and result_data:
        # 获取任务的模板 schema
        task = db.query(Task).filter(Task.id == request.task_id).first()
        resolved_template = None
        if task and task.template_id:
            resolved_template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()

        if resolved_template and resolved_template.schema:
            schema_def = resolved_template.schema
            if isinstance(schema_def, str):
                try:
                    schema_def = json.loads(schema_def)
                except (json.JSONDecodeError, TypeError):
                    schema_def = {}

            fields = schema_def.get("fields", []) if isinstance(schema_def, dict) else []

            # 收集必填字段
            missing_fields = []
            field_labels = {}
            for field in fields:
                if not isinstance(field, dict):
                    continue
                field_id = field.get("key") or field.get("id") or field.get("binding")
                if not field_id:
                    continue

                field_label = field.get("title") or field.get("label") or field.get("name") or field_id
                field_labels[field_id] = field_label

                is_required = field.get("required", False)
                if not is_required:
                    rules = field.get("rules", [])
                    if isinstance(rules, list):
                        for rule in rules:
                            if isinstance(rule, dict) and rule.get("required", False):
                                is_required = True
                                break
                    elif isinstance(rules, dict) and rules.get("required", False):
                        is_required = True
                if not is_required:
                    continue

                value = result_data.get(field_id) if isinstance(result_data, dict) else None
                if value is None or value == "" or value == [] or value == {}:
                    missing_fields.append(field_id)
                elif isinstance(value, str) and value.strip() == "":
                    missing_fields.append(field_id)

            # 也检查 schema.required 数组（JSON Schema 风格）
            required_array = schema_def.get("required", []) if isinstance(schema_def, dict) else []
            field_key_map = {}
            for field in fields:
                if isinstance(field, dict):
                    fid = field.get("key") or field.get("id")
                    fname = field.get("name") or field.get("label")
                    if fname:
                        field_key_map[fname] = fid
                    if fid:
                        field_key_map[fid] = fid

            for req_key in required_array:
                resolved_key = field_key_map.get(req_key, req_key)
                value = result_data.get(resolved_key) if isinstance(result_data, dict) else None
                if value is None or value == "" or value == [] or value == {} or (isinstance(value, str) and value.strip() == ""):
                    if resolved_key not in missing_fields:
                        missing_fields.append(resolved_key)

            if missing_fields:
                logger.debug(f"[SUBMIT_VALIDATION] missing required fields: {missing_fields}")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "success": False,
                        "code": "REQUIRED_FIELDS_MISSING",
                        "message": "请完成必填项",
                        "missing_fields": missing_fields,
                        "missing_field_labels": [field_labels.get(f, f) for f in missing_fields]
                    }
                )

    try:
        logger.debug("[SUBMIT_API] calling submit_submission...")
        result = submit_submission(db, request)

        # 后台异步执行 AI 自动预审 Agent (不阻塞前端)
        ai_run_id = result.get("ai_review_run_id")
        annotation_id = result.get("annotation_id") or result.get("submission_id")
        if ai_run_id:
            background_tasks.add_task(
                _execute_agent_after_submit,
                ai_run_id,
                request.task_id,
                request.dataset_item_id,
                annotation_id,
            )
            logger.debug(f"[SUBMIT_API] background AI agent scheduled: run_id={ai_run_id}")

        # Write audit log for submission
        try:
            from app.services.audit_service import create_audit_log
            create_audit_log(
                db=db,
                user_id=request.labeler_id or 2,
                action="submission_submit",
                target_type="annotation",
                target_id=result.get("id", request.dataset_item_id),
                after_data={"status": "submitted"},
                extra_info={"task_id": request.task_id, "dataset_item_id": request.dataset_item_id}
            )
        except Exception as audit_err:
            logger.error(f"[labeler_submit] audit log error: {audit_err}")
        
        logger.debug(f"[SUBMIT_API] result type: {type(result)}")
        logger.debug(f"[SUBMIT_API] result: {result}")
        
        # 确保返回的是 dict
        if not isinstance(result, dict):
            logger.error(f"[SUBMIT_API] ERROR: result is not dict, got {type(result)}")
            raise HTTPException(status_code=500, detail=f"Invalid response type: {type(result)}")
        
        # 添加 debug_route 标记
        return {
            "success": result.get("success", True),
            "debug_route": "api_labeler_submit_v2",
            "annotation": result.get("annotation"),
            "item_id": result.get("item_id"),
            "annotation_id": result.get("annotation_id") or result.get("submission_id"),
            "ai_review_run_id": result.get("ai_review_run_id"),
            "message": result.get("message", "提交成功"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SUBMIT_API] error: {e}")
        import traceback
        logger.error(f"[SUBMIT_API] traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/submissions")
def get_labeler_submissions_endpoint(
    task_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 10,
    db: Session = Depends(get_db),
    labeler_id: int = Query(2)
):
    """获取我的提交记录（从 annotations.json 读取）"""
    logger.debug(f"[my_submissions] labeler_id={labeler_id}, task_id={task_id}, status={status}, page={page}, limit={limit}")
    
    from app.services.annotation_service import get_annotations_by_filter
    
    # 从 annotations.json 读取全部
    all_annotations = get_annotations_by_filter(
        task_id=task_id,
        labeler_id=labeler_id,
        status=None  # 不过滤状态，先拿全量
    )
    
    logger.debug(f"[my_submissions] total_all={len(all_annotations)}")
    
    # 允许进入我的提交的状态：包含 claimed/draft/submitted/rework/approved 等
    # 草稿类：draft, saved_draft, claimed, in_progress, new
    # 提交类：submitted
    # 返修类：rejected_to_modify, returned_to_modify, needs_revision, rework, rework_draft
    # 通过类：approved
    allowed_statuses = [
        "draft", "saved_draft", "claiming", "claimed", "in_progress", "new",
        "submitted", "rejected_to_modify", "returned_to_modify", "needs_revision",
        "rework", "rework_draft", "approved"
    ]
    
    # 过滤允许的状态
    annotations = [a for a in all_annotations if a.get("status") in allowed_statuses]
    
    # 如果前端传了 status 参数，做服务端过滤（注意：status=draft 时要包含 claimed）
    if status:
        if status == "draft":
            # 筛选"草稿"时包含所有草稿类状态
            draft_like_statuses = ["draft", "saved_draft", "claiming", "claimed", "in_progress", "new"]
            annotations = [a for a in annotations if a.get("status") in draft_like_statuses]
        elif status == "rejected":
            # 筛选"待修改"时包含所有返修类状态
            rework_statuses = ["rejected_to_modify", "returned_to_modify", "needs_revision", "rework", "rework_draft"]
            annotations = [a for a in annotations if a.get("status") in rework_statuses]
        else:
            annotations = [a for a in annotations if a.get("status") == status]
    
    logger.debug(f"[my_submissions] filtered_total={len(annotations)}")
    logger.debug(f"[my_submissions] statuses: {[a.get('status') for a in annotations]}")
    
    # 统计全量数据（基于过滤后的全部 annotations，不受分页影响）
    # 注意：这里的 stats 基于当前 task_id 过滤后的全量数据
    stats = {
        "total": len(annotations),
        "draft": len([a for a in annotations if a.get("status") in ["draft", "saved_draft", "claiming", "claimed", "in_progress", "new"]]),
        "submitted": len([a for a in annotations if a.get("status") == "submitted"]),
        "rejected": len([a for a in annotations if a.get("status") in ["rejected_to_modify", "returned_to_modify", "needs_revision", "rework", "rework_draft"]]),
        "approved": len([a for a in annotations if a.get("status") == "approved"]),
    }
    
    logger.debug(f"[my_submissions] stats={stats}")
    
    # 分页
    total = len(annotations)
    pages = (total + limit - 1) // limit if total > 0 else 1
    start = (page - 1) * limit
    end = start + limit
    items = annotations[start:end]
    
    logger.debug(f"[my_submissions] page={page}, limit={limit}, returned={len(items)}, total={total}, pages={pages}")
    
    # 添加 status_label 和 action_type
    for item in items:
        status_val = item.get("status", "")
        if status_val in ["draft", "saved_draft"]:
            item["status_label"] = "草稿"
            item["action_type"] = "continue_edit"
        elif status_val in ["claimed", "in_progress", "new", "claiming"]:
            item["status_label"] = "已领取"
            item["action_type"] = "continue_labeling"
        elif status_val == "submitted":
            item["status_label"] = "已提交"
            item["action_type"] = "view_detail"
        elif status_val in ["rejected_to_modify", "returned_to_modify", "needs_revision", "rework", "rework_draft"]:
            item["status_label"] = "待修改"
            item["action_type"] = "continue_revision"
        elif status_val == "approved":
            item["status_label"] = "已通过"
            item["action_type"] = "view_detail"
        else:
            item["status_label"] = status_val
            item["action_type"] = "view_detail"
        
        # 确保 work_key 存在
        if not item.get("work_key"):
            item["work_key"] = f"{item.get('task_id', 0)}:{item.get('dataset_item_id', 0)}:{labeler_id}"
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": limit,
        "pages": pages,
        "stats": stats
    }


ACTIVE_STATUSES = ["claimed", "draft", "rejected_to_modify", "returned_to_modify", "needs_revision"]
TERMINAL_STATUSES = ["submitted", "approved", "export_ready"]


def get_latest_annotations_by_item(annotations):
    """按 dataset_item_id 分组，取每组最新 updated_at 的 annotation"""
    latest_by_item = {}
    for ann in annotations:
        item_id = ann.get("dataset_item_id")
        if not item_id:
            continue
        
        updated_at_str = ann.get("updated_at", "1970-01-01T00:00:00")
        try:
            from datetime import datetime
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        except:
            updated_at = datetime(1970, 1, 1)
        
        if item_id not in latest_by_item:
            latest_by_item[item_id] = (ann, updated_at)
        else:
            _, current_updated_at = latest_by_item[item_id]
            if updated_at > current_updated_at:
                latest_by_item[item_id] = (ann, updated_at)
    
    return {item_id: ann for item_id, (ann, _) in latest_by_item.items()}


def get_active_annotations(labeler_id: int):
    """获取标注员的活跃标注（非终端状态）"""
    from app.services.annotation_service import get_annotations_by_filter
    
    annotations = get_annotations_by_filter(labeler_id=labeler_id)
    
    # 按 item 分组，取最新的 annotation
    latest_by_item = get_latest_annotations_by_item(annotations)
    
    active = []
    processed_item_ids = set()
    rework_item_ids = set()
    
    for item_id, ann in latest_by_item.items():
        status = ann.get("status", "")
        if status in TERMINAL_STATUSES:
            processed_item_ids.add(item_id)
        elif status == "rejected_to_modify":
            rework_item_ids.add(item_id)
            active.append(ann)
        elif status in ACTIVE_STATUSES or status == "draft":
            active.append(ann)
    
    # 打印状态分类日志
    intersection = processed_item_ids & rework_item_ids
    logger.debug(f"[STATUS_CLASSIFY]")
    logger.debug(f"[STATUS_CLASSIFY] latest_by_item keys: {list(latest_by_item.keys())}")
    logger.debug(f"[STATUS_CLASSIFY] processed_item_ids: {processed_item_ids}")
    logger.debug(f"[STATUS_CLASSIFY] rework_item_ids: {rework_item_ids}")
    logger.debug(f"[STATUS_CLASSIFY] intersection: {intersection}")
    
    if intersection:
        logger.warning(f"[STATUS_CLASSIFY] WARNING: processed and rework item ids should be disjoint!")
    
    return active, processed_item_ids


@router.get("/current-item")
def get_current_item_endpoint(
    db: Session = Depends(get_db),
    labeler_id: int = Query(2)
):
    """获取当前标注员正在处理的题（active item）"""
    logger.debug(f"[current-item] labeler_id={labeler_id}")
    
    # 使用统一的 work_key 分组
    from app.services.annotation_service import get_work_key_groups
    groups = get_work_key_groups(labeler_id)
    
    latest_by_work_key = groups["latest_by_work_key"]
    terminal_work_keys = groups["terminal_work_keys"]
    
    # 筛选出活跃的 work_keys（排除 terminal）
    active_work_keys = []
    for wk, ann in latest_by_work_key.items():
        status = ann.get("status", "")
        if wk not in terminal_work_keys and status in ["claimed", "draft", "drafting", "rejected_to_modify", "returned_to_modify", "needs_revision"]:
            active_work_keys.append((wk, ann))
    
    logger.debug(f"[current-item] active work_keys: {len(active_work_keys)}")
    
    # 优先级排序：
    # 1. rejected_to_modify / returned_to_modify / needs_revision (返修)
    # 2. draft / drafting (草稿，包括返修草稿)
    # 3. claimed (已领取)
    def sort_priority(item):
        wk, ann = item
        status = ann.get("status", "")
        if status in ["rejected_to_modify", "returned_to_modify", "needs_revision"]:
            return 0
        elif status in ["draft", "drafting"]:
            return 1
        elif status == "claimed":
            return 2
        return 99
    
    active_work_keys.sort(key=sort_priority)
    
    if active_work_keys:
        wk, active_ann = active_work_keys[0]
        dataset_item_id = active_ann.get("dataset_item_id")
        task_id = active_ann.get("task_id")
        annotation_id = active_ann.get("id")
        status = active_ann.get("status")
        
        # 判断 mode
        mode = "new"
        if status in ["rejected_to_modify", "returned_to_modify", "needs_revision"]:
            mode = "rework"
        elif status in ["draft", "drafting"]:
            # 检查是否是返修草稿（有 rejected_reason 或 review_info）
            if active_ann.get("rejected_reason") or active_ann.get("review_info"):
                mode = "rework"
            else:
                mode = "draft"
        elif status == "claimed":
            mode = "new"
        
        # 获取 item 和 task 信息
        # task_id 必须来自 work_key，不允许被 DB 覆盖
        item = db.query(DatasetItem)\
            .filter(DatasetItem.id == dataset_item_id)\
            .filter(DatasetItem.task_id == task_id)\
            .first()
        
        # 如果按 task_id + item_id 查不到，尝试只用 item_id 查但不覆盖 task_id
        if not item:
            item = db.query(DatasetItem).filter(DatasetItem.id == dataset_item_id).first()
        
        # task_id 保持原始值，不覆盖
        final_task_id = task_id
        
        task = db.query(Task).filter(Task.id == final_task_id).first()
        
        # 获取模板信息
        resolved_template = None
        if task and task.template_id:
            resolved_template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()
        
        # 获取审核信息
        review_info = active_ann.get("review_info", {})
        
        result = {
            "has_active": True,
            "work_key": wk,
            "task_id": final_task_id,
            "item_id": dataset_item_id,
            "dataset_item_id": dataset_item_id,
            "submission_id": annotation_id,
            "mode": mode,
            "item_status": item.status if item else None,
            "submission_status": status,
            "review_reason": active_ann.get("rejected_reason", "") or review_info.get("comment", ""),
            "review_time": review_info.get("reviewed_at", ""),
            "reviewer_id": review_info.get("reviewer_id", ""),
            "annotation_result": active_ann.get("result", {}),
            "raw_item_data": item.raw_data_json if item else {},
            "timer_seconds": active_ann.get("duration_seconds", 0),
            "task_name": task.name if task else "",
            "template_id": task.template_id if task else None,
            "template_name": resolved_template.name if resolved_template else "",
            "schema_json": resolved_template.schema if resolved_template else None,
            "logs": []  # 预留日志字段
        }
        
        logger.debug(f"[current-item] found active item: work_key={wk}, mode={mode}, status={status}")
        return result
    
    logger.debug("[current-item] no active item found")
    return {
        "has_active": False,
        "work_key": None,
        "item_id": None,
        "message": "暂无进行中的任务"
    }


@router.post("/claim-next")
def claim_next_endpoint(
    task_id: Optional[int] = None,
    db: Session = Depends(get_db),
    labeler_id: int = Query(2)
):
    """领取下一个可处理的任务"""
    logger.debug(f"[claim-next] labeler_id={labeler_id}, task_id={task_id}")
    
    # 使用统一的 work_key 分组函数
    from app.services.annotation_service import get_work_key_groups
    groups = get_work_key_groups(labeler_id)
    
    latest_by_work_key = groups["latest_by_work_key"]
    terminal_work_keys = groups["terminal_work_keys"]
    active_work_keys = groups["active_work_keys"]
    rework_work_keys = groups["rework_work_keys"]
    
    # 先检查是否有 active item（包括返修）
    all_active_work_keys = active_work_keys.union(rework_work_keys)
    
    # 防御校验：再次检查 work_key 的最新状态
    terminal_statuses = ["submitted", "ai_reviewing", "ai_reviewed", "human_reviewing", "approved", "export_ready", "skipped", "invalid_submitted", "invalid_approved"]
    
    # 过滤掉已经变成 terminal 状态的 work_key
    valid_active_work_keys = []
    for wk in all_active_work_keys:
        ann = latest_by_work_key.get(wk)
        if ann:
            status = ann.get("status", "")
            if status in terminal_statuses:
                logger.debug(f"[CLAIM_NEXT_SKIP_TERMINAL] work_key={wk}, status={status}")
                continue
            valid_active_work_keys.append(wk)
    
    if valid_active_work_keys:
        # 优先返回返修题
        wk = None
        for key in valid_active_work_keys:
            if key in rework_work_keys:
                wk = key
                break
        
        if wk is None:
            wk = valid_active_work_keys[0]
        
        active_ann = latest_by_work_key[wk]
        dataset_item_id = active_ann.get("dataset_item_id")
        ann_task_id = active_ann.get("task_id")
        
        logger.debug(f"[claim-next] active item found, work_key={wk}")
        
        item = db.query(DatasetItem).filter(DatasetItem.id == dataset_item_id).first()
        task = db.query(Task).filter(Task.id == ann_task_id).first()
        
        resolved_template = None
        if task and task.template_id:
            resolved_template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()
        
        work_key = f"{ann_task_id}:{dataset_item_id}:{labeler_id}"
        display_title = f"Task #{ann_task_id} / Item #{dataset_item_id}"
        
        # 写入"继续处理题目"日志
        safe_log_action(
            db=db,
            user_id=labeler_id,
            action="resume_active_item",
            target_type=AuditTargetType.DATASET_ITEM,
            target_id=dataset_item_id,
            after_data={
                "work_key": work_key,
                "task_id": ann_task_id,
                "item_id": dataset_item_id,
                "description": f"继续处理 Task #{ann_task_id} / Item #{dataset_item_id}"
            }
        )
        
        item_result = {
            "id": dataset_item_id,
            "item_id": dataset_item_id,
            "dataset_item_id": dataset_item_id,
            "task_id": ann_task_id,
            "work_key": work_key,
            "display_title": display_title,
            "annotation_id": active_ann.get("id"),
            "status": active_ann.get("status"),
            "item_data": item.raw_data_json if item else {},
            "annotation_result": active_ann.get("result", {}),
            "rejected_reason": active_ann.get("rejected_reason", ""),
            "duration_seconds": active_ann.get("duration_seconds", 0),
            "task_name": task.name if task else "",
            "template_id": task.template_id if task else None,
            "schema_json": resolved_template.schema if resolved_template else None
        }
        
        return {
            "success": False,
            "has_active": True,
            "message": "你已有进行中任务，已为你打开当前题。",
            "item": item_result,
            "item_id": dataset_item_id,
            "dataset_item_id": dataset_item_id,
            "task_id": ann_task_id,
            "work_key": work_key,
            "display_title": display_title,
            "status": active_ann.get("status")
        }
    
    logger.debug("[claim-next] no active item, proceeding to claim new item")
    
    # 查找可领取的 item（排除当前 labeler 已跳过的）
    from sqlalchemy import or_
    query = db.query(DatasetItem)\
        .filter(DatasetItem.status == ItemStatus.UNCLAIMED.value)\
        .filter(or_(DatasetItem.skipped_by == None, DatasetItem.skipped_by != labeler_id))  # 排除当前 labeler 已跳过的
    
    if task_id:
        query = query.filter(DatasetItem.task_id == task_id)
    
    available_items = query.all()
    logger.debug(f"[claim-next] available unclaimed items: {len(available_items)}")
    
    # 过滤掉已有 terminal 状态的 work_key
    valid_items = []
    for item in available_items:
        wk = f"{item.task_id}:{item.id}:{labeler_id}"
        logger.debug(f"[CLAIM_NEXT_CANDIDATE] task_id={item.task_id}, dataset_item_id={item.id}, work_key={wk}")
        
        if wk in terminal_work_keys:
            logger.debug(f"[CLAIM_NEXT_SKIP_SUBMITTED] work_key={wk}")
            continue
        
        valid_items.append(item)
    
    if not valid_items:
        logger.debug("[CLAIM_NEXT_NO_AVAILABLE_ITEM]")
        return {
            "has_active": False,
            "success": False,
            "code": "NO_AVAILABLE_ITEM",
            "message": "暂无可领取的新任务"
        }
    
    # 领取一条
    item = valid_items[0]
    item.status = ItemStatus.CLAIMED.value
    item.claimed_by = labeler_id
    db.commit()
    
    work_key = f"{item.task_id}:{item.id}:{labeler_id}"
    logger.debug(f"[claim-next] claiming new item: work_key={work_key}")
    
    # 创建初始 annotation（状态为 claimed），同时保存原始题目快照
    from app.services.annotation_service import create_or_update_annotation
    
    task = db.query(Task).filter(Task.id == item.task_id).first()
    template_id = task.template_id if task else None
    
    # 保存原始题目快照，确保返修时即使 DatasetItem 被删除也能回显
    item_snapshot = None
    if item and item.raw_data_json:
        item_snapshot = {
            "id": item.id,
            "task_id": item.task_id,
            "raw_data": item.raw_data_json,
            "item_data": item.raw_data_json,
        }
    
    annotation = create_or_update_annotation(
        task_id=item.task_id,
        dataset_item_id=item.id,
        labeler_id=labeler_id,
        result_data={},
        template_id=template_id,
        status="claimed",
        item_snapshot=item_snapshot
    )
    
    logger.debug(f"[CLAIM_NEXT_CREATED_CLAIM] annotation_id={annotation.get('id')}, work_key={work_key}, status=claimed")
    
    safe_log_action(
        db=db,
        user_id=labeler_id,
        action=AuditAction.ITEM_CLAIM,
        target_type=AuditTargetType.DATASET_ITEM,
        target_id=item.id,
        after_data={"status": item.status, "claimed_by": labeler_id}
    )
    
    resolved_template = None
    if task and task.template_id:
        resolved_template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()
    
    display_work_key = f"{item.task_id}:{item.id}:{labeler_id}"
    display_title = f"Task #{item.task_id} / Item #{item.id}"
    
    # 写入"领取题目"日志
    safe_log_action(
        db=db,
        user_id=labeler_id,
        action="claim_item",
        target_type=AuditTargetType.DATASET_ITEM,
        target_id=item.id,
        after_data={
            "work_key": display_work_key,
            "task_id": item.task_id,
            "item_id": item.id,
            "description": f"领取 Task #{item.task_id} / Item #{item.id}"
        }
    )
    
    item_result = {
        "id": item.id,
        "item_id": item.id,
        "dataset_item_id": item.id,
        "task_id": item.task_id,
        "work_key": display_work_key,
        "display_title": display_title,
        "annotation_id": annotation.get("id"),
        "status": "claimed",
        "item_data": item.raw_data_json,
        "annotation_result": {},
        "duration_seconds": 0,
        "task_name": task.name if task else "",
        "template_id": template_id,
        "schema_json": resolved_template.schema if resolved_template else None
    }
    
    return {
        "success": True,
        "has_active": True,
        "message": "领取成功",
        "item": item_result,
        "item_id": item.id,
        "dataset_item_id": item.id,
        "task_id": item.task_id,
        "work_key": display_work_key,
        "display_title": display_title,
        "status": "claimed"
    }