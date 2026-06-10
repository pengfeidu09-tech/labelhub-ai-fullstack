from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import logging

from app.core.database import get_db
from app.models.submission import Submission
from app.models.draft import Draft
from app.models.task import Task
from app.models.template_schema import TemplateSchema
from app.services.annotation_service import get_all_annotations, get_annotation_by_id, count_annotations


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/owner", tags=["owner"])


@router.get("/annotations")
def get_annotations(
    task_id: Optional[int] = None,
    template_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 50
) -> Dict[str, Any]:
    try:
        # 从 JSON 文件读取所有标注
        annotations = get_all_annotations()
        logger.debug(f"[owner annotations] total annotations from JSON: {len(annotations)}")
        
        # 筛选：默认排除 drafts（drafts 通过 /drafts 接口获取）
        filtered = annotations
        
        # 默认排除 drafts
        if status is None or status != "draft":
            filtered = [a for a in filtered if a.get("status") != "draft"]
        
        if task_id:
            filtered = [a for a in filtered if a.get("task_id") == task_id]
        if status:
            filtered = [a for a in filtered if a.get("status") == status]
        
        # 排序（按 updated_at 降序）
        filtered.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        
        total = len(filtered)
        
        # 分页
        start = (page - 1) * limit
        end = start + limit
        items = filtered[start:end]
        
        logger.debug(f"[owner annotations] filtered count: {len(items)}, total: {total}")
        logger.debug(f"[owner annotations] statuses: {[a.get('status') for a in items]}")
        
        return {"items": items, "total": total, "page": page, "limit": limit}
    except Exception as e:
        logger.error(f"[owner annotations] error: {e}")
        import traceback
        logger.error(f"[owner annotations] traceback: {traceback.format_exc()}")
        return {"items": [], "total": 0, "page": page, "limit": limit}


@router.get("/annotations/{annotation_id}")
def get_annotation_detail(annotation_id: int) -> Optional[Dict[str, Any]]:
    try:
        annotation = get_annotation_by_id(annotation_id)
        if not annotation:
            return {"error": "Annotation not found"}
        return annotation
    except Exception as e:
        logger.error(f"[owner annotation detail] error: {e}")
        return {"error": str(e)}


@router.get("/drafts")
def get_drafts(
    task_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    # 从 JSON 文件读取草稿
    annotations = get_all_annotations()
    drafts = [a for a in annotations if a.get("status") == "draft"]
    
    if task_id:
        drafts = [d for d in drafts if d.get("task_id") == task_id]
    
    return {"items": drafts, "total": len(drafts)}