from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.services.dataset_import_service import (
    import_dataset, import_demo_data, get_dataset_items, get_dataset_item, delete_dataset_item,
    DatasetImportError
)
from app.schemas.dataset_item import (
    DatasetImportRequest, DatasetImportDemoRequest, DatasetItemResponse, DatasetListResponse
)

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.post("/import")
def import_dataset_endpoint(
    request: DatasetImportRequest,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    count = import_dataset(db, request.task_id, request.data, user_id)
    return {"message": f"Imported {count} items"}


@router.post("/import-demo")
def import_demo_data_endpoint(
    request: DatasetImportDemoRequest,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    try:
        count = import_demo_data(db, request.task_id, request.dataset_type, user_id)
        return {"message": f"Imported {count} demo items"}
    except DatasetImportError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("")
def get_datasets_endpoint(
    task_id: Optional[int] = None,
    status: Optional[str] = None,
    dataset_type: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    result = get_dataset_items(db, task_id, status, dataset_type, page, limit)
    serialized_items = []
    for item in result["items"]:
        raw_data = item.raw_data_json
        if isinstance(raw_data, str):
            try:
                import json
                raw_data = json.loads(raw_data)
            except:
                raw_data = {}
        hidden_ref = item.hidden_reference_json
        if isinstance(hidden_ref, str):
            try:
                import json
                hidden_ref = json.loads(hidden_ref)
            except:
                hidden_ref = None
        serialized_items.append({
            "id": item.id,
            "task_id": item.task_id,
            "external_id": item.external_id,
            "dataset_type": item.dataset_type,
            "raw_data_json": raw_data or {},
            "hidden_reference_json": hidden_ref,
            "status": item.status,
            "claimed_by": item.claimed_by,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        })
    return {"items": serialized_items, "total": result["total"], "page": result["page"], "limit": result["limit"]}


@router.get("/list")
def get_dataset_list_endpoint(db: Session = Depends(get_db)):
    """获取数据集列表（从 dataset_items 聚合）"""
    from sqlalchemy import func
    from app.models.dataset_item import DatasetItem
    
    # 按 dataset_type 聚合统计
    datasets = db.query(
        DatasetItem.dataset_type,
        func.count(DatasetItem.id).label('item_count'),
        func.min(DatasetItem.created_at).label('created_at'),
        func.max(DatasetItem.updated_at).label('updated_at')
    ).group_by(DatasetItem.dataset_type).order_by(DatasetItem.dataset_type.asc()).all()
    
    result = []
    dataset_names = {
        "qa_quality": "问答质量评估数据集",
        "preference_compare": "偏好比较数据集",
        "safety_eval": "安全评估数据集",
        "content_safety": "内容安全标注数据集",
        "math_calculation": "数学计算核验数据集",
        "writing_quality": "写作质量评估数据集",
        "summarization": "摘要数据集",
        "classification": "分类数据集",
        "custom": "自定义数据集"
    }

    dataset_descriptions = {
        "qa_quality": "用于评估问答模型质量的数据集，包含问题、模型回答和参考答案",
        "preference_compare": "用于比较两个模型响应偏好的数据集",
        "safety_eval": "用于评估模型安全性的数据集",
        "content_safety": "用于标注内容安全等级、违规类型和严重程度的数据集",
        "math_calculation": "用于核验数学计算模型回答正确性的数据集",
        "writing_quality": "用于评估长文本写作质量的数据集",
        "summarization": "用于评估摘要生成质量的数据集",
        "classification": "用于分类任务的数据集",
        "custom": "用户自定义数据集"
    }
    
    for idx, ds in enumerate(datasets, 1):
        result.append({
            "id": idx,
            "name": dataset_names.get(ds.dataset_type, ds.dataset_type),
            "dataset_type": ds.dataset_type,
            "description": dataset_descriptions.get(ds.dataset_type, ""),
            "item_count": ds.item_count,
            "created_at": ds.created_at.isoformat() if ds.created_at else None,
            "updated_at": ds.updated_at.isoformat() if ds.updated_at else None
        })
    
    # 如果没有数据，返回一个默认数据集
    if not result:
        result.append({
            "id": 1,
            "name": "问答质量评估数据集",
            "dataset_type": "qa_quality",
            "description": "用于评估问答模型质量的数据集",
            "item_count": 0,
            "created_at": None,
            "updated_at": None
        })
    
    return {"items": result, "total": len(result)}


@router.get("/{dataset_item_id}", response_model=DatasetItemResponse)
def get_dataset_item_endpoint(dataset_item_id: int, db: Session = Depends(get_db)):
    item = get_dataset_item(db, dataset_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Dataset item not found")
    return item


@router.delete("/{dataset_item_id}")
def delete_dataset_item_endpoint(
    dataset_item_id: int,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    success = delete_dataset_item(db, dataset_item_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Dataset item not found")
    return {"message": "Dataset item deleted successfully"}
