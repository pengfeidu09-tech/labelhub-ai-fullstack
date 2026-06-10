import os
import json
import csv
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List

from app.models.dataset_item import DatasetItem
from app.models.task import Task
from app.core.enums import DatasetType, ItemStatus
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType


class DatasetImportError(Exception):
    """Dataset import error with HTTP status code"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


def get_project_root() -> str:
    """Get project root directory by traversing up from this file"""
    current_file = os.path.abspath(__file__)
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    return os.path.dirname(backend_dir)


def import_dataset(db: Session, task_id: int, data: List[Dict], user_id: int, dataset_type: str = None) -> int:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return 0
    
    if not dataset_type:
        from app.models.template_schema import TemplateSchema
        template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()
        if template:
            dataset_type = template.dataset_type
        else:
            dataset_type = "custom"
    
    imported_count = 0
    for item in data:
        external_id = item.get("id") or item.get("external_id")
        item_dataset_type = item.get("dataset_type", dataset_type)
        
        raw_data_json = {}
        hidden_reference_json = {}
        
        if item_dataset_type == "qa_quality":
            qa_fields = ["prompt", "model_answer", "reference", "media_type", "media_url", 
                         "content_markdown", "category", "difficulty", "expected_dimensions", 
                         "tags", "source"]
            for field in qa_fields:
                if field in item:
                    raw_data_json[field] = item[field]
            if "expected_dimensions" in item:
                hidden_reference_json["expected_dimensions"] = item["expected_dimensions"]
        elif item_dataset_type == "preference_compare":
            pc_fields = ["prompt", "response_a", "response_b", "model_a", "model_b", 
                         "dimensions", "safety_flag"]
            for field in pc_fields:
                if field in item:
                    raw_data_json[field] = item[field]
            for field in ["preferred", "margin", "annotator_note"]:
                if field in item:
                    hidden_reference_json[field] = item[field]
        else:
            raw_data_json = item
        
        dataset_item = DatasetItem(
            task_id=task_id,
            external_id=str(external_id) if external_id else None,
            dataset_type=item_dataset_type,
            raw_data_json=raw_data_json,
            hidden_reference_json=hidden_reference_json if hidden_reference_json else None,
            status=ItemStatus.UNCLAIMED.value
        )
        db.add(dataset_item)
        imported_count += 1
    
    db.commit()
    
    log_action(
        db=db,
        user_id=user_id,
        action=AuditAction.ITEM_IMPORT,
        target_type=AuditTargetType.DATASET_ITEM,
        target_id=task_id,
        extra_info={"imported_count": imported_count, "task_id": task_id}
    )
    
    return imported_count


def find_dataset_files(base_path: str) -> List[str]:
    """Find all dataset files in the given directory and its subdirectories"""
    supported_extensions = [".json", ".jsonl", ".xlsx", ".csv"]
    files = []
    
    for root, dirs, filenames in os.walk(base_path):
        for filename in filenames:
            if any(filename.endswith(ext) for ext in supported_extensions):
                files.append(os.path.join(root, filename))
    
    return files


def load_json_file(filepath: str) -> List[Dict]:
    """Load data from JSON file"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = json.load(f)
        if isinstance(content, dict) and "dataset" in content:
            return content["dataset"]
        elif isinstance(content, list):
            return content
        else:
            return [content]


def load_jsonl_file(filepath: str) -> List[Dict]:
    """Load data from JSONL file"""
    data = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def load_excel_file(filepath: str) -> List[Dict]:
    """Load data from Excel file"""
    import pandas as pd
    df = pd.read_excel(filepath)
    return df.to_dict("records")


def load_csv_file(filepath: str) -> List[Dict]:
    """Load data from CSV file"""
    with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_dataset_file(filepath: str) -> List[Dict]:
    """Load data from dataset file based on extension"""
    if filepath.endswith(".json"):
        return load_json_file(filepath)
    elif filepath.endswith(".jsonl"):
        return load_jsonl_file(filepath)
    elif filepath.endswith(".xlsx"):
        return load_excel_file(filepath)
    elif filepath.endswith(".csv"):
        return load_csv_file(filepath)
    return []


def validate_dataset_path(dataset_type: str) -> str:
    """
    Validate and return the dataset directory path.
    Raises DatasetImportError if path is invalid.
    """
    project_root = get_project_root()
    datasets_dir = os.path.join(project_root, "datasets")
    
    if not os.path.exists(datasets_dir):
        raise DatasetImportError(
            f"datasets directory not found. Please place official datasets under project_root/datasets/",
            status_code=404
        )
    
    dataset_dir = os.path.join(datasets_dir, dataset_type)
    if not os.path.exists(dataset_dir):
        raise DatasetImportError(
            f"dataset directory not found: datasets/{dataset_type}",
            status_code=404
        )
    
    return dataset_dir


def find_dataset_files_with_validation(dataset_type: str) -> List[str]:
    """Find dataset files with proper error handling"""
    dataset_dir = validate_dataset_path(dataset_type)
    
    files = find_dataset_files(dataset_dir)
    if not files:
        raise DatasetImportError(
            f"No demo dataset file found under datasets/{dataset_type}",
            status_code=400
        )
    
    return files


def import_demo_data(db: Session, task_id: int, dataset_type: str, user_id: int) -> int:
    """Import demo data from datasets directory"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return 0
    
    files = find_dataset_files_with_validation(dataset_type)
    
    data = []
    for filepath in files:
        try:
            file_data = load_dataset_file(filepath)
            data.extend(file_data)
        except Exception as e:
            pass
    
    if not data:
        data = generate_mock_data(dataset_type)
    
    return import_dataset(db, task_id, data, user_id, dataset_type)


def generate_mock_data(dataset_type: str) -> List[Dict]:
    if dataset_type == "qa_quality":
        return [
            {
                "id": "1",
                "prompt": "什么是人工智能？",
                "model_answer": "人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，旨在研究、开发用于模拟、延伸和扩展人的智能的理论、方法、技术及应用系统。",
                "reference": "人工智能是研究使计算机来模拟人的某些思维过程和智能行为（如学习、推理、思考、规划等）的学科，主要包括计算机实现智能的原理、制造类似于人脑智能的计算机，使计算机能实现更高层次的应用。",
                "category": "基础概念",
                "difficulty": "easy",
                "expected_dimensions": ["相关性", "准确性", "完整性", "安全性"]
            },
            {
                "id": "2",
                "prompt": "地球的直径是多少？",
                "model_answer": "地球的直径约为12742公里。",
                "reference": "地球赤道直径约为12756公里，极直径约为12714公里，平均直径约为12742公里。",
                "category": "科学知识",
                "difficulty": "easy",
                "expected_dimensions": ["准确性", "完整性"]
            },
            {
                "id": "3",
                "prompt": "如何制作巧克力蛋糕？",
                "model_answer": "巧克力蛋糕的制作需要准备可可粉、黄油、糖、鸡蛋、面粉等原料，通过混合、烘焙等步骤完成。",
                "reference": "巧克力蛋糕制作步骤：1.预热烤箱至180°C；2.打发黄油和糖至蓬松；3.逐个加入鸡蛋；4.混合可可粉和面粉；5.倒入模具烤30-40分钟。",
                "category": "生活技能",
                "difficulty": "medium",
                "expected_dimensions": ["完整性", "准确性"]
            }
        ]
    elif dataset_type == "preference_compare":
        return [
            {
                "id": "1",
                "prompt": "什么是机器学习？",
                "response_a": "机器学习是人工智能的一个分支，它使计算机系统能够从数据中学习并改进其性能，而无需进行明确编程。",
                "response_b": "机器学习就是让电脑自己学会做事，不用人写太多代码。",
                "model_a": "Model-X",
                "model_b": "Model-Y",
                "dimensions": ["正确性", "完整性", "易懂性"],
                "preferred": "a",
                "margin": "large"
            },
            {
                "id": "2",
                "prompt": "为什么天空是蓝色的？",
                "response_a": "天空之所以呈现蓝色，是因为大气中的分子对太阳光的散射作用。蓝光波长较短，更容易被散射。",
                "response_b": "天空是蓝色的，因为海水倒映的结果。",
                "model_a": "Model-A",
                "model_b": "Model-B",
                "dimensions": ["正确性", "科学性"],
                "preferred": "a",
                "margin": "large"
            }
        ]
    return []


def get_dataset_items(db: Session, task_id: Optional[int] = None, status: Optional[str] = None,
                     dataset_type: Optional[str] = None,
                     page: int = 1, limit: int = 20) -> Dict[str, Any]:
    query = db.query(DatasetItem)

    if task_id:
        query = query.filter(DatasetItem.task_id == task_id)
    if status:
        query = query.filter(DatasetItem.status == status)
    if dataset_type:
        query = query.filter(DatasetItem.dataset_type == dataset_type)

    total = query.count()
    items = query.order_by(DatasetItem.created_at.desc())\
        .offset((page - 1) * limit)\
        .limit(limit)\
        .all()

    return {"items": items, "total": total, "page": page, "limit": limit}


def get_dataset_item(db: Session, item_id: int) -> Optional[DatasetItem]:
    return db.query(DatasetItem).filter(DatasetItem.id == item_id).first()


def delete_dataset_item(db: Session, item_id: int, user_id: int) -> bool:
    item = get_dataset_item(db, item_id)
    if not item:
        return False
    
    db.delete(item)
    db.commit()
    
    return True
