import json
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

# JSON 文件路径

logger = logging.getLogger(__name__)
ANNOTATIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "annotations.json")

def _ensure_file():
    """确保文件存在"""
    os.makedirs(os.path.dirname(ANNOTATIONS_FILE), exist_ok=True)
    if not os.path.exists(ANNOTATIONS_FILE):
        with open(ANNOTATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

def _load_annotations() -> List[Dict[str, Any]]:
    """加载所有标注"""
    _ensure_file()
    try:
        with open(ANNOTATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[annotation_service] load error: {e}")
        return []

def _save_annotations(annotations: List[Dict[str, Any]]) -> None:
    """保存所有标注"""
    os.makedirs(os.path.dirname(ANNOTATIONS_FILE), exist_ok=True)
    try:
        logger.debug(f"[annotation_service] saving {len(annotations)} annotations to {ANNOTATIONS_FILE}")
        logger.debug(f"[annotation_service] all statuses before save: {[a.get('status') for a in annotations]}")
        with open(ANNOTATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(annotations, f, ensure_ascii=False, indent=2)
        # 验证写入
        with open(ANNOTATIONS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        logger.debug(f"[annotation_service] verify: {len(saved)} annotations saved")
        logger.debug(f"[annotation_service] verify statuses: {[a.get('status') for a in saved]}")
    except Exception as e:
        logger.error(f"[annotation_service] save error: {e}")
        import traceback
        logger.error(f"[annotation_service] save traceback: {traceback.format_exc()}")
        raise

def get_all_annotations() -> List[Dict[str, Any]]:
    """获取所有标注"""
    return _load_annotations()

def get_annotation_by_id(annotation_id: int) -> Optional[Dict[str, Any]]:
    """根据 ID 获取标注"""
    annotations = _load_annotations()
    for ann in annotations:
        if ann.get("id") == annotation_id:
            return ann
    return None

def get_annotations_by_filter(
    task_id: Optional[int] = None,
    labeler_id: Optional[int] = None,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """根据条件筛选标注"""
    annotations = _load_annotations()
    result = []
    
    for ann in annotations:
        if task_id and ann.get("task_id") != task_id:
            continue
        if labeler_id and ann.get("labeler_id") != labeler_id:
            continue
        if status and ann.get("status") != status:
            continue
        result.append(ann)
    
    return result

def get_pending_annotations() -> List[Dict[str, Any]]:
    """获取待审核的标注"""
    annotations = _load_annotations()
    pending_statuses = [
        "submitted",           # 普通待审
        "invalid_submitted",   # 无效待审
        "human_reviewing",     # 人工审核中
        "revised_submitted",   # 返修后重新提交
    ]
    result = []
    
    for ann in annotations:
        status = ann.get("status", "")
        if status in pending_statuses:
            result.append(ann)
    
    logger.debug(f"[annotation_service] all annotations: {len(annotations)}")
    logger.debug(f"[annotation_service] all statuses: {[a.get('status') for a in annotations]}")
    logger.debug(f"[annotation_service] pending annotations: {len(result)}")
    logger.debug(f"[annotation_service] pending statuses: {[a.get('status') for a in result]}")
    return result

def get_latest_annotations_by_work_key(labeler_id: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    """
    按 work_key 分组，获取每组最新的 annotation
    work_key = f"{task_id}:{dataset_item_id}:{labeler_id}"
    
    最新判断优先级：
    1. updated_at 最大
    2. 如果 updated_at 缺失，用 revision_no 最大
    3. 如果 revision_no 也缺失，用 id 最大
    """
    annotations = _load_annotations()
    
    # 过滤 labeler_id(如果指定)
    if labeler_id is not None:
        annotations = [a for a in annotations if a.get("labeler_id") == labeler_id]
        
    # 过滤 status="skipped" 的 annotation,避免被跳过的 item 再次出现在队列中
    annotations = [a for a in annotations if a.get("status") != "skipped"]
    
    latest_by_work_key: Dict[str, Dict[str, Any]] = {}
    
    for ann in annotations:
        task_id = ann.get("task_id")
        dataset_item_id = ann.get("dataset_item_id")
        ann_labeler_id = ann.get("labeler_id")
        
        if task_id is None or dataset_item_id is None or ann_labeler_id is None:
            continue
        
        work_key = f"{task_id}:{dataset_item_id}:{ann_labeler_id}"
        
        if work_key not in latest_by_work_key:
            latest_by_work_key[work_key] = ann
            continue
        
        # 比较哪个更新
        existing = latest_by_work_key[work_key]
        
        # 优先比较 updated_at
        existing_updated = existing.get("updated_at", "")
        new_updated = ann.get("updated_at", "")
        
        if new_updated > existing_updated:
            latest_by_work_key[work_key] = ann
            continue
        
        if new_updated == existing_updated:
            # updated_at 相同，比较 revision_no
            existing_rev = existing.get("revision_no", 0)
            new_rev = ann.get("revision_no", 0)
            
            if new_rev > existing_rev:
                latest_by_work_key[work_key] = ann
                continue
            
            if new_rev == existing_rev:
                # revision_no 也相同，比较 id
                existing_id = existing.get("id", 0)
                new_id = ann.get("id", 0)
                
                if new_id > existing_id:
                    latest_by_work_key[work_key] = ann
    
    logger.debug(f"[STATE_LATEST_BY_WORK_KEY] keys={list(latest_by_work_key.keys())}")
    return latest_by_work_key


def get_work_key_groups(labeler_id: Optional[int] = None):
    """
    获取 work_key 分组统计
    返回：terminal_work_keys, active_work_keys, rework_work_keys
    """
    latest_by_work_key = get_latest_annotations_by_work_key(labeler_id)
    
    terminal_work_keys = set()
    active_work_keys = set()
    rework_work_keys = set()
    
    terminal_statuses = ["submitted", "ai_reviewing", "ai_reviewed", "human_reviewing", "approved", "export_ready", "skipped", "invalid_submitted", "invalid_approved"]
    active_statuses = ["claimed", "draft", "drafting"]
    rework_statuses = ["rejected_to_modify", "rejected"]
    
    for work_key, ann in latest_by_work_key.items():
        status = ann.get("status", "")
        
        if status in terminal_statuses:
            terminal_work_keys.add(work_key)
        elif status in active_statuses:
            active_work_keys.add(work_key)
        elif status in rework_statuses:
            rework_work_keys.add(work_key)
    
    logger.debug(f"[STATE_TERMINAL_WORK_KEYS] {terminal_work_keys}")
    logger.debug(f"[STATE_ACTIVE_WORK_KEYS] {active_work_keys}")
    logger.debug(f"[STATE_REWORK_WORK_KEYS] {rework_work_keys}")
    
    return {
        "latest_by_work_key": latest_by_work_key,
        "terminal_work_keys": terminal_work_keys,
        "active_work_keys": active_work_keys,
        "rework_work_keys": rework_work_keys
    }


def normalize_annotations_latest_state():
    """
    清理/修复 annotations.json 中的状态冲突
    不删除旧记录，但确保 latest_by_work_key 返回正确的最新状态
    """
    annotations = _load_annotations()
    
    # 按 work_key 分组
    groups: Dict[str, list] = {}
    for ann in annotations:
        task_id = ann.get("task_id")
        dataset_item_id = ann.get("dataset_item_id")
        labeler_id = ann.get("labeler_id")
        
        if task_id is None or dataset_item_id is None or labeler_id is None:
            continue
        
        work_key = f"{task_id}:{dataset_item_id}:{labeler_id}"
        if work_key not in groups:
            groups[work_key] = []
        groups[work_key].append(ann)
    
    logger.debug(f"[NORMALIZE] found {len(groups)} work_key groups")
    
    # 检查每个组
    for work_key, anns in groups.items():
        if len(anns) <= 1:
            continue
        
        # 找到最新的
        latest = anns[0]
        for ann in anns[1:]:
            # 比较 updated_at
            latest_updated = latest.get("updated_at", "")
            ann_updated = ann.get("updated_at", "")
            
            if ann_updated > latest_updated:
                latest = ann
                continue
            
            if ann_updated == latest_updated:
                latest_rev = latest.get("revision_no", 0)
                ann_rev = ann.get("revision_no", 0)
                
                if ann_rev > latest_rev:
                    latest = latest = ann
                    continue
                
                if ann_rev == latest_rev:
                    if ann.get("id", 0) > latest.get("id", 0):
                        latest = ann
        
        latest_status = latest.get("status", "")
        logger.debug(f"[NORMALIZE] work_key={work_key}, latest_status={latest_status}, total_records={len(anns)}")
    
    logger.debug("[NORMALIZE] completed")


def create_or_update_annotation(
    task_id: int,
    dataset_item_id: int,
    labeler_id: int,
    result_data: Dict[str, Any],
    ai_review: Optional[Dict[str, Any]] = None,
    template_id: Optional[int] = None,
    template_name: Optional[str] = None,
    status: str = "submitted",
    item_snapshot: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """创建或更新标注（基于 task_id + dataset_item_id + labeler_id 防重）"""
    
    work_key = f"{task_id}:{dataset_item_id}:{labeler_id}"
    annotations = _load_annotations()
    
    # 查找是否存在
    existing_idx = None
    existing_id = None
    existing_status = None
    for idx, ann in enumerate(annotations):
        if (ann.get("task_id") == task_id and 
            ann.get("dataset_item_id") == dataset_item_id and 
            ann.get("labeler_id") == labeler_id):
            existing_idx = idx
            existing_id = ann.get("id")
            existing_status = ann.get("status")
            break
    
    now = datetime.now(timezone.utc).isoformat()
    
    # 禁止状态回退规则
    terminal_statuses = ["submitted", "approved", "ai_reviewing", "ai_reviewed", "human_reviewing", "export_ready", "skipped", "invalid_submitted", "invalid_approved"]
    editable_statuses = ["claimed", "draft", "drafting", "rejected_to_modify", "returned_to_modify", "needs_revision"]
    
    if existing_idx is not None:
        # 更新现有记录
        existing = annotations[existing_idx]
        
        # 检查状态回退
        if existing_status in terminal_statuses and status == "claimed":
            # 不能从终端状态回退到 claimed
            logger.debug(f"[annotation_service] SKIP_CLAIM_ON_TERMINAL work_key={work_key}, existing_status={existing_status}, requested_status={status}")
            return existing
        
        # 检查状态回退：不能从 submitted/approved 回退到 draft/drafting
        if existing_status in terminal_statuses and status in ["draft", "drafting"]:
            logger.debug(f"[annotation_service] SKIP_DRAFT_ON_TERMINAL work_key={work_key}, existing_status={existing_status}, requested_status={status}")
            return existing
        
        # 累加 revision_no
        revision_no = (existing.get("revision_no") or 0) + 1
        
        annotations[existing_idx] = {
            **existing,
            "task_id": task_id,
            "dataset_item_id": dataset_item_id,
            "labeler_id": labeler_id,
            "template_id": template_id or existing.get("template_id"),
            "template_name": template_name or existing.get("template_name"),
            "result": result_data,
            "annotation_result": result_data,
            "data": result_data,
            "ai_review": ai_review or existing.get("ai_review"),
            "status": status,
            "revision_no": revision_no,
            "updated_at": now
        }
        # 保存 item_snapshot（如果提供了新的快照，覆盖旧的；否则保留旧的）
        if item_snapshot:
            annotations[existing_idx]["item_snapshot"] = item_snapshot
            annotations[existing_idx]["item_data"] = item_snapshot.get("item_data") or item_snapshot.get("raw_data")
        elif not existing.get("item_snapshot") and item_snapshot is None:
            pass  # 旧记录没有快照，也没有新快照，不处理
        annotation = annotations[existing_idx]
        logger.debug(f"[annotation_service] updated annotation id={existing_id}, revision_no={revision_no}, status={status}, work_key={work_key}")
    else:
        # 创建新记录
        new_id = max([a.get("id", 0) for a in annotations], default=0) + 1
        
        annotation = {
            "id": new_id,
            "task_id": task_id,
            "dataset_item_id": dataset_item_id,
            "labeler_id": labeler_id,
            "template_id": template_id,
            "template_name": template_name or "问答质量评估模板",
            "result": result_data,
            "annotation_result": result_data,
            "data": result_data,
            "ai_review": ai_review,
            "status": status,
            "revision_no": 1,
            "created_at": now,
            "updated_at": now
        }
        # 保存 item_snapshot
        if item_snapshot:
            annotation["item_snapshot"] = item_snapshot
            annotation["item_data"] = item_snapshot.get("item_data") or item_snapshot.get("raw_data")
        annotations.append(annotation)
        logger.debug(f"[annotation_service] created new annotation id={new_id}, status={status}, work_key={work_key}")
    
    _save_annotations(annotations)
    return annotation

def update_annotation_status(
    annotation_id: int,
    status: str,
    review_info: Optional[Dict[str, Any]] = None,
    rejected_reason: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """更新标注状态"""
    annotations = _load_annotations()
    
    for idx, ann in enumerate(annotations):
        if ann.get("id") == annotation_id:
            now = datetime.now(timezone.utc).isoformat()
            
            annotations[idx] = {
                **ann,
                "status": status,
                "updated_at": now
            }
            
            if review_info:
                annotations[idx]["review_info"] = review_info
            
            if rejected_reason:
                annotations[idx]["rejected_reason"] = rejected_reason
            
            _save_annotations(annotations)
            logger.debug(f"[annotation_service] updated annotation id={annotation_id} status to {status}")
            return annotations[idx]
    
    logger.debug(f"[annotation_service] annotation id={annotation_id} not found")
    return None

def save_draft_to_annotations(
    task_id: int,
    dataset_item_id: int,
    labeler_id: int,
    draft_data: Dict[str, Any],
    template_id: Optional[int] = None,
    template_name: Optional[str] = None,
    ai_review: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """保存草稿到标注（status=draft）"""
    return create_or_update_annotation(
        task_id=task_id,
        dataset_item_id=dataset_item_id,
        labeler_id=labeler_id,
        result_data=draft_data,
        ai_review=ai_review,
        template_id=template_id,
        template_name=template_name,
        status="draft"
    )

def update_ai_review(
    task_id: int,
    dataset_item_id: int,
    labeler_id: int,
    ai_review: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    annotations = _load_annotations()
    for idx, ann in enumerate(annotations):
        if (ann.get("task_id") == task_id and
            ann.get("dataset_item_id") == dataset_item_id and
            ann.get("labeler_id") == labeler_id):
            annotations[idx]["ai_review"] = ai_review
            annotations[idx]["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_annotations(annotations)
            return annotations[idx]
    return None

def count_annotations() -> int:
    """统计标注总数"""
    return len(_load_annotations())


def normalize_ai_review(ai_review: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """将不同格式的 AI 审核数据统一为标准结构。

    支持的输入格式：
    - 旧格式 (AIReviewResult): overall_score, conclusion, dimension_scores, ...
    - 新格式 (AIReviewRun): score, risk_level, suggestion_action, confidence, ...
    - 混合格式: 同时包含两种字段
    """
    if not ai_review or not isinstance(ai_review, dict):
        return None

    overall_score = ai_review.get("overall_score")
    if overall_score is None:
        overall_score = ai_review.get("score")

    risk_level = ai_review.get("risk_level")
    suggested_action = ai_review.get("suggested_action") or ai_review.get("suggestion_action")
    confidence = ai_review.get("confidence")
    summary = ai_review.get("summary") or ai_review.get("conclusion") or ai_review.get("review_comment")
    reason = ai_review.get("reason") or ai_review.get("suggested_fix")
    dimension_scores = ai_review.get("dimension_scores") or ai_review.get("dimensions")
    issue_tags = ai_review.get("issue_tags") or ai_review.get("problems")
    prompt_version = ai_review.get("prompt_version")
    model = ai_review.get("model") or ai_review.get("model_name")
    run_id = ai_review.get("run_id")
    passed = ai_review.get("passed")
    fallback = ai_review.get("fallback")
    fallback_required = ai_review.get("fallback_required")

    if overall_score is None and risk_level is None and not summary:
        return None

    result = {
        "overall_score": overall_score,
        "risk_level": risk_level,
        "suggested_action": suggested_action,
        "confidence": confidence,
        "summary": summary,
        "reason": reason,
        "dimension_scores": dimension_scores,
        "issue_tags": issue_tags,
        "prompt_version": prompt_version,
        "model": model,
        "run_id": run_id,
    }

    if passed is not None:
        result["passed"] = passed
    if fallback is not None:
        result["fallback"] = fallback
    if fallback_required is not None:
        result["fallback_required"] = fallback_required

    return result
