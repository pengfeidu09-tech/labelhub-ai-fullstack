from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging

from app.core.database import get_db
from app.core.enums import AuditAction, AuditTargetType, ItemStatus
from app.models.dataset_item import DatasetItem
from app.models.draft_version import DraftVersion
from app.services.audit_service import log_action

logger = logging.getLogger("item_actions")

router = APIRouter(prefix="/api/items", tags=["items"])

VERSION_TYPE_TEXT = {
    "draft": "保存草稿",
    "submitted": "提交标注",
    "rework_draft": "返修草稿",
    "rework_submitted": "返修提交",
    "initial": "初始领取",
}


class MarkInvalidRequest(BaseModel):
    reason: str
    task_id: int
    labeler_id: int
    work_key: str


class SkipRequest(BaseModel):
    task_id: int
    labeler_id: int
    work_key: str


class SaveVersionRequest(BaseModel):
    task_id: int
    item_id: int
    labeler_id: int
    work_key: str
    snapshot_json: Optional[dict] = None
    summary: Optional[str] = None
    version_type: Optional[str] = None    # draft / submitted / rework_draft / rework_submitted
    operator_role: Optional[str] = None    # labeler / reviewer


@router.post("/{item_id}/mark-invalid")
def mark_item_invalid(item_id: int, body: MarkInvalidRequest, db: Session = Depends(get_db)):
    item = db.query(DatasetItem).filter(DatasetItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    item.is_valid = False
    item.invalid_reason = body.reason
    item.status = ItemStatus.INVALID.value
    item.updated_at = datetime.now(timezone.utc)
    db.commit()

    log_action(
        db=db,
        user_id=body.labeler_id,
        action=AuditAction.MARK_INVALID,
        target_type=AuditTargetType.DATASET_ITEM,
        target_id=item_id,
        role="labeler",
        action_label="标记无效",
        task_id=body.task_id,
        item_id=item_id,
        work_key=body.work_key,
        message=f"Item marked as invalid: {body.reason}",
        payload_json={"reason": body.reason},
    )

    return {"success": True, "message": "Item marked as invalid"}


@router.post("/{item_id}/skip")
def skip_item(item_id: int, body: SkipRequest, db: Session = Depends(get_db)):
    item = db.query(DatasetItem).filter(DatasetItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    log_action(
        db=db,
        user_id=body.labeler_id,
        action=AuditAction.SKIP_ITEM,
        target_type=AuditTargetType.DATASET_ITEM,
        target_id=item_id,
        role="labeler",
        action_label="跳过题目",
        task_id=body.task_id,
        item_id=item_id,
        work_key=body.work_key,
        message="Item skipped",
    )

    return {"success": True, "message": "Item skipped"}


@router.post("/{item_id}/save-version")
def save_version(item_id: int, body: SaveVersionRequest, db: Session = Depends(get_db)):
    item = db.query(DatasetItem).filter(DatasetItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    last_version = db.query(DraftVersion).filter(
        DraftVersion.item_id == item_id,
        DraftVersion.labeler_id == body.labeler_id,
        DraftVersion.work_key == body.work_key,
    ).order_by(DraftVersion.version_no.desc()).first()

    next_version_no = (last_version.version_no + 1) if last_version else 1

    now = datetime.now(timezone.utc)
    draft_version = DraftVersion(
        task_id=body.task_id,
        item_id=item_id,
        labeler_id=body.labeler_id,
        work_key=body.work_key,
        version_no=next_version_no,
        version_type=body.version_type or "draft",
        operator_role=body.operator_role or "labeler",
        snapshot_json=body.snapshot_json,
        summary=body.summary,
        created_at=now,
    )
    db.add(draft_version)
    db.commit()
    db.refresh(draft_version)

    log_action(
        db=db,
        user_id=body.labeler_id,
        action=AuditAction.SAVE_VERSION,
        target_type=AuditTargetType.DATASET_ITEM,
        target_id=item_id,
        role="labeler",
        action_label="保存版本快照",
        task_id=body.task_id,
        item_id=item_id,
        work_key=body.work_key,
        message=f"Draft version {next_version_no} saved",
        payload_json={"version_no": next_version_no, "summary": body.summary},
    )

    return {
        "version_no": draft_version.version_no,
        "created_at": draft_version.created_at.isoformat() if draft_version.created_at else None,
    }


@router.get("/{item_id}/versions")
def get_item_versions(
    item_id: int,
    work_key: Optional[str] = Query(None),
    labeler_id: int = Query(2),
    db: Session = Depends(get_db)
):
    query = db.query(DraftVersion).filter(DraftVersion.item_id == item_id)

    if work_key:
        query = query.filter(DraftVersion.work_key == work_key)

    versions = query.order_by(DraftVersion.version_no.desc()).all()

    result = []
    for v in versions:
        vt = v.version_type or "draft"
        result.append({
            "id": v.id,
            "task_id": v.task_id,
            "item_id": v.item_id,
            "labeler_id": v.labeler_id,
            "work_key": v.work_key,
            "version_no": v.version_no,
            "version_type": vt,
            "version_type_text": VERSION_TYPE_TEXT.get(vt, vt),
            "operator_role": v.operator_role or "labeler",
            "snapshot_json": v.snapshot_json,
            "summary": v.summary,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        })

    # Plan A: 如果没有版本记录，但有 annotation 数据，生成一条只读 derived version
    if not result:
        try:
            from app.services.annotation_service import _load_annotations
            annotations = _load_annotations()
            for ann in annotations:
                ann_wk = f"{ann.get('task_id')}:{ann.get('dataset_item_id')}:{ann.get('labeler_id')}"
                match = False
                if work_key and ann_wk == work_key:
                    match = True
                elif ann.get('dataset_item_id') == item_id and ann.get('labeler_id') == labeler_id:
                    match = True
                if not match:
                    continue

                status = ann.get('status', '')
                type_map = {
                    'submitted': 'submitted', 'approved': 'submitted',
                    'rejected_to_modify': 'submitted', 'returned_to_modify': 'submitted',
                    'needs_revision': 'submitted', 'draft': 'draft',
                    'drafting': 'draft', 'claimed': 'draft', 'skipped': 'draft',
                }
                derived_type = type_map.get(status, 'submitted')
                derived_text = VERSION_TYPE_TEXT.get(derived_type, "历史提交")
                result.append({
                    "id": 0,
                    "version_no": 1,
                    "version_type": derived_type,
                    "version_type_text": derived_text,
                    "operator_role": "labeler",
                    "snapshot_json": ann.get('result') or ann.get('annotation_result') or ann.get('data') or {},
                    "summary": f"历史记录 (原始状态: {status})",
                    "created_at": ann.get('updated_at') or ann.get('created_at'),
                    "task_id": ann.get('task_id'),
                    "item_id": ann.get('dataset_item_id'),
                    "labeler_id": ann.get('labeler_id'),
                    "work_key": ann_wk,
                })
                break
        except Exception as e:
            logger.warning(f"[versions] Plan A derived version failed: {e}")

    return {"versions": result, "total": len(result)}
