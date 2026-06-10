from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional

from app.core.database import get_db
from app.models.dataset_item import DatasetItem
from app.models.task import Task
from app.core.enums import ItemStatus
import json
import os
import shutil
import logging
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dev", tags=["dev"])

ANNOTATIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "annotations.json")

# 演示用的原始题目数据模板
DEMO_ITEM_TEMPLATES = [
    {
        "prompt": "请评估以下AI回答的质量：\n\n问题：什么是机器学习？\n\nAI回答：机器学习是人工智能的一个分支，它使计算机系统能够从数据中学习并改进性能，而无需显式编程。",
        "model_answer": "机器学习是人工智能的一个分支...",
        "reference": "机器学习（Machine Learning）是人工智能的核心领域之一...",
        "category": "qa_quality",
        "difficulty": "medium"
    },
    {
        "prompt": "请判断以下对话中AI的回答是否准确且有帮助：\n\n用户：Python和Java有什么区别？\n\nAI回答：Python是一种解释型语言，语法简洁；Java是编译型语言，类型严格。",
        "model_answer": "Python和Java的主要区别在于执行方式...",
        "reference": "Python是动态类型、解释型语言；Java是静态类型、编译型语言...",
        "category": "qa_quality",
        "difficulty": "easy"
    },
    {
        "prompt": "请对以下AI生成的摘要进行质量评估：\n\n原文：这是一篇关于深度学习的长文章...\n\nAI摘要：本文介绍了深度学习的基本概念、主要算法和应用场景。",
        "model_answer": "本文介绍了深度学习的基本概念...",
        "reference": "深度学习（Deep Learning）是机器学习的子集...",
        "category": "summarization",
        "difficulty": "hard"
    },
    {
        "prompt": "请评估以下翻译的准确性和流畅度：\n\n源文本：The quick brown fox jumps over the lazy dog.\n\nAI译文：敏捷的棕色狐狸跳过了懒惰的狗。",
        "model_answer": "敏捷的棕色狐狸跳过...",
        "reference": "标准译文应为：那只敏捷的棕色狐狸跳过了懒狗。",
        "category": "translation",
        "difficulty": "medium"
    },
    {
        "prompt": "请分析以下代码生成结果的正确性：\n\n需求：写一个Python函数计算斐波那契数列。\n\n待评估模型回答如下：",
        "model_answer": "def fib(n):\n    return n if n <= 1 else fib(n-1) + fib(n-2)\n\n该函数实现了递归方式的斐波那契数列计算。",
        "reference": "斐波那契数列定义：F(0)=0, F(1)=1, F(n)=F(n-1)+F(n-2)。递归实现逻辑正确，但效率较低（时间复杂度O(n^2)），大数时会栈溢出。",
        "category": "code_generation",
        "difficulty": "hard"
    },
    {
        "prompt": "请评估以下创意写作的质量：\n\n主题：以\"春天\"为主题写一首短诗。\n\nAI作品：春风拂面柳丝长，燕子归来筑新巢。桃花盛开满山红，万物复苏生机旺。",
        "model_answer": "春风拂面柳丝长...",
        "reference": "创意写作应考虑意象、韵律、情感表达等多个维度...",
        "category": "creative_writing",
        "difficulty": "easy"
    },
    {
        "prompt": "请判断以下逻辑推理是否正确：\n\n前提：所有A都是B。所有B都是C。\n\n结论：所有A都是C。\n\nAI判断：正确。",
        "model_answer": "逻辑推理正确...",
        "reference": "这是典型的三段论推理，结论有效...",
        "category": "logical_reasoning",
        "difficulty": "medium"
    },
    {
        "prompt": "请评估以下多轮对话的连贯性：\n\n用户：今天天气怎么样？\nAI：根据最新信息，今天晴朗，气温25度。\n用户：那适合户外运动吗？\nAI：是的，非常适合跑步或骑行。",
        "model_answer": "天气信息查询结果...",
        "reference": "多轮对话评估需关注上下文一致性、信息准确性...",
        "category": "multi_turn_dialogue",
        "difficulty": "hard"
    },
    {
        "prompt": "请检查以下数学计算的准确性：\n\n题目：计算 123 × 456 + 789 的值。\n\nAI答案：56073 + 789 = 56862",
        "model_answer": "56862",
        "reference": "123×456=56073, 56073+789=56862, 计算正确...",
        "category": "math_calculation",
        "difficulty": "easy"
    },
    {
        "prompt": "请评估以下情感分析的合理性：\n\n文本：这部电影太棒了！演员表演出色，剧情紧凑，强烈推荐！\n\nAI判断：正面情绪，置信度95%。",
        "model_answer": "正面情绪，置信度95%...",
        "reference": "文本包含强烈的正面词汇：太棒、出色、强烈推荐...",
        "category": "sentiment_analysis",
        "difficulty": "medium"
    }
]

# 演示用的标注结果模板
DEMO_RESULT_TEMPLATES = [
    {"relevance": "excellent", "accuracy": "good", "completeness": "excellent", "safety": "pass", "overall_score": 4.5},
    {"relevance": "good", "accuracy": "fair", "completeness": "good", "safety": "pass", "overall_score": 3.5},
    {"relevance": "fair", "accuracy": "poor", "completeness": "fair", "safety": "pass", "overall_score": 2.5},
    {"relevance": "poor", "accuracy": "poor", "completeness": "poor", "safety": "fail", "overall_score": 1.5},
]


def _load_annotations() -> List[Dict[str, Any]]:
    """加载当前 annotations"""
    if os.path.exists(ANNOTATIONS_FILE):
        with open(ANNOTATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_annotations(annotations: List[Dict[str, Any]]) -> None:
    """保存 annotations"""
    os.makedirs(os.path.dirname(ANNOTATIONS_FILE), exist_ok=True)
    with open(ANNOTATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(annotations, f, ensure_ascii=False, indent=2)


def _get_next_annotation_id(annotations: List[Dict[str, Any]]) -> int:
    """获取下一个可用的 annotation id"""
    max_id = max([a.get("id", 0) for a in annotations], default=0)
    return max_id + 1


def _get_available_dataset_items(db: Session, labeler_id: int = 2) -> List[DatasetItem]:
    """获取可用于演示的 DatasetItem 列表"""
    items = db.query(DatasetItem).all()
    # 优先返回有 raw_data_json 的 item
    valid_items = [item for item in items if item.raw_data_json]
    
    # 如果没有足够的 items，创建一些
    tasks = db.query(Task).all()
    if len(valid_items) < 15 and tasks:
        existing_ids = {item.id for item in items}
        for i in range(15 - len(valid_items)):
            task = tasks[i % len(tasks)]
            template_idx = i % len(DEMO_ITEM_TEMPLATES)
            new_item = DatasetItem(
                task_id=task.id,
                external_id=f"demo_auto_{i}",
                dataset_type="demo",
                raw_data_json=DEMO_ITEM_TEMPLATES[template_idx],
                status=ItemStatus.UNCLAIMED.value
            )
            db.add(new_item)
        db.commit()
        
        # 重新加载
        items = db.query(DatasetItem).all()
        valid_items = [item for item in items if item.raw_data_json]
    
    return valid_items


@router.post("/reset-demo-data")
def reset_demo_data(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    重置/生成演示数据
    
    生成分布：
    - 3 条 unclaimed（可领取）
    - 2 条 claimed（已领取）
    - 2 条 rejected_to_modify（返修）
    - 3 条 submitted（待审核）
    - 1 条 approved（已通过）
    """
    try:
        now = datetime.now().isoformat()
        
        # 1. 备份当前 annotations.json
        backup_name = f"annotations.backup.{now.replace(':', '-')}.json"
        backup_path = os.path.join(os.path.dirname(ANNOTATIONS_FILE), backup_name)
        if os.path.exists(ANNOTATIONS_FILE):
            shutil.copy2(ANNOTATIONS_FILE, backup_path)
            logger.debug(f"[reset-demo] backed up to {backup_name}")
        
        # 2. 获取可用 dataset items
        available_items = _get_available_dataset_items(db)
        labeler_id = 2
        
        if not available_items:
            return {"success": False, "message": "没有可用的 DatasetItem，无法生成演示数据"}
        
        # 3. 重置所有 dataset items 为 UNCLAIMED
        for item in available_items:
            item.status = ItemStatus.UNCLAIMED.value
            item.claimed_by = None
        db.commit()
        
        # 4. 构建新的演示 annotations
        new_annotations = []
        next_id = 1
        
        # === 3 条 unclaimed（不创建 annotation，保持 DB 中 UNCLAIMED）===
        # 这些通过 claim-next 领取时自动创建 annotation
        unclaimed_count = min(3, len(available_items))
        for i in range(unclaimed_count):
            item = available_items[i]
            # 不创建 annotation，只确保 DB 中状态为 UNCLAIMED
            item.status = ItemStatus.UNCLAIMED.value
            item.claimed_by = None
        
        # === 2 条 claimed（已领取）===
        claimed_start = unclaimed_count
        for i in range(claimed_start, claimed_start + 2):
            if i >= len(available_items):
                break
            item = available_items[i]
            item.status = ItemStatus.CLAIMED.value
            item.claimed_by = labeler_id
            
            template_idx = i % len(DEMO_ITEM_TEMPLATES)
            ann = {
                "id": next_id,
                "task_id": item.task_id,
                "dataset_item_id": item.id,
                "labeler_id": labeler_id,
                "template_id": None,
                "template_name": "问答质量评估模板",
                "result": {},
                "annotation_result": {},
                "data": {},
                "ai_review": None,
                "status": "claimed",
                "revision_no": 1,
                "created_at": (datetime.now() - timedelta(minutes=i * 10)).isoformat(),
                "updated_at": (datetime.now() - timedelta(minutes=i * 5)).isoformat(),
                "item_snapshot": {
                    "id": item.id,
                    "task_id": item.task_id,
                    "raw_data": item.raw_data_json if item.raw_data_json else DEMO_ITEM_TEMPLATES[template_idx],
                    "item_data": item.raw_data_json if item.raw_data_json else DEMO_ITEM_TEMPLATES[template_idx]
                },
                "item_data": item.raw_data_json if item.raw_data_json else DEMO_ITEM_TEMPLATES[template_idx]
            }
            new_annotations.append(ann)
            next_id += 1
        
        # === 2 条 rejected_to_modify（返修）===
        rework_start = claimed_start + 2
        for i in range(rework_start, rework_start + 2):
            if i >= len(available_items):
                break
            item = available_items[i]
            item.status = ItemStatus.CLAIMED.value
            item.claimed_by = labeler_id
            
            template_idx = i % len(DEMO_ITEM_TEMPLATES)
            result_template = DEMO_RESULT_TEMPLATES[i % len(DEMO_RESULT_TEMPLATES)]
            ann = {
                "id": next_id,
                "task_id": item.task_id,
                "dataset_item_id": item.id,
                "labeler_id": labeler_id,
                "template_id": None,
                "template_name": "问答质量评估模板",
                "result": result_template,
                "annotation_result": result_template,
                "data": result_template,
                "ai_review": None,
                "status": "rejected_to_modify",
                "revision_no": 2,
                "rejected_reason": f"第{i}条返修原因：相关性评分不足，请重新评估AI回答与问题的匹配程度。",
                "review_info": {
                    "comment": f"相关性评分只有{result_template.get('relevance', 'N/A')}，需要提升至good以上级别。",
                    "reviewed_at": (datetime.now() - timedelta(hours=i)).isoformat(),
                    "reviewer_id": str(i + 10)
                },
                "created_at": (datetime.now() - timedelta(hours=i * 2 + 1)).isoformat(),
                "updated_at": (datetime.now() - timedelta(hours=i)).isoformat(),
                "item_snapshot": {
                    "id": item.id,
                    "task_id": item.task_id,
                    "raw_data": item.raw_data_json if item.raw_data_json else DEMO_ITEM_TEMPLATES[template_idx],
                    "item_data": item.raw_data_json if item.raw_data_json else DEMO_ITEM_TEMPLATES[template_idx]
                },
                "item_data": item.raw_data_json if item.raw_data_json else DEMO_ITEM_TEMPLATES[template_idx]
            }
            new_annotations.append(ann)
            next_id += 1
        
        # === 3 条 submitted（待审核）===
        submitted_start = rework_start + 2
        for i in range(submitted_start, submitted_start + 3):
            if i >= len(available_items):
                break
            item = available_items[i]
            
            template_idx = i % len(DEMO_ITEM_TEMPLATES)
            result_template = DEMO_RESULT_TEMPLATES[i % len(DEMO_RESULT_TEMPLATES)]
            ann = {
                "id": next_id,
                "task_id": item.task_id,
                "dataset_item_id": item.id,
                "labeler_id": labeler_id,
                "template_id": None,
                "template_name": "问答质量评估模板",
                "result": result_template,
                "annotation_result": result_template,
                "data": result_template,
                "ai_review": None,
                "status": "submitted",
                "revision_no": 1,
                "created_at": (datetime.now() - timedelta(days=i + 1)).isoformat(),
                "updated_at": (datetime.now() - timedelta(hours=i * 3)).isoformat(),
                "item_snapshot": {
                    "id": item.id,
                    "task_id": item.task_id,
                    "raw_data": item.raw_data_json if item.raw_data_json else DEMO_ITEM_TEMPLATES[template_idx],
                    "item_data": item.raw_data_json if item.raw_data_json else DEMO_ITEM_TEMPLATES[template_idx]
                },
                "item_data": item.raw_data_json if item.raw_data_json else DEMO_ITEM_TEMPLATES[template_idx]
            }
            new_annotations.append(ann)
            next_id += 1
        
        # === 1 条 approved（已通过）===
        approved_start = submitted_start + 3
        if approved_start < len(available_items):
            item = available_items[approved_start]
            
            template_idx = approved_start % len(DEMO_ITEM_TEMPLATES)
            result_template = DEMO_RESULT_TEMPLATES[0]  # 用最好的结果
            ann = {
                "id": next_id,
                "task_id": item.task_id,
                "dataset_item_id": item.id,
                "labeler_id": labeler_id,
                "template_id": None,
                "template_name": "问答质量评估模板",
                "result": result_template,
                "annotation_result": result_template,
                "data": result_template,
                "ai_review": None,
                "status": "approved",
                "revision_no": 1,
                "created_at": (datetime.now() - timedelta(days=7)).isoformat(),
                "updated_at": (datetime.now() - timedelta(days=5)).isoformat(),
                "item_snapshot": {
                    "id": item.id,
                    "task_id": item.task_id,
                    "raw_data": item.raw_data_json if item.raw_data_json else DEMO_ITEM_TEMPLATES[template_idx],
                    "item_data": item.raw_data_json if item.raw_data_json else DEMO_ITEM_TEMPLATES[template_idx]
                },
                "item_data": item.raw_data_json if item.raw_data_json else DEMO_ITEM_TEMPLATES[template_idx]
            }
            new_annotations.append(ann)
            next_id += 1
        
        # 5. 提交 DB 变更
        db.commit()
        
        # 6. 写入新的 annotations.json
        _save_annotations(new_annotations)
        
        # 统计
        status_counts = {}
        for a in new_annotations:
            s = a["status"]
            status_counts[s] = status_counts.get(s, 0) + 1
        
        logger.debug(f"[reset-demo] generated {len(new_annotations)} annotations")
        logger.debug(f"[reset-demo] status distribution: {status_counts}")
        logger.debug(f"[reset-demo] unclaimed items in DB: {unclaimed_count}")
        
        return {
            "success": True,
            "message": "演示数据已重置",
            "backup_file": backup_name if os.path.exists(backup_path) else None,
            "annotations_generated": len(new_annotations),
            "unclaimed_items": unclaimed_count,
            "status_distribution": status_counts
        }
    
    except Exception as e:
        logger.error(f"[reset-demo-data] error: {e}")
        import traceback
        logger.error(f"[reset-demo-data] traceback: {traceback.format_exc()}")
        return {"success": False, "message": str(e)}


@router.post("/seed-more-items")
def seed_more_items(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    追加更多可领取的演示数据（不影响已有提交记录）
    
    向 DB 追加 5-10 条新 DatasetItem（UNCLAIMED 状态）
    不创建 annotation，让 claim-next 能领到
    """
    try:
        now = datetime.now().isoformat()
        labeler_id = 2
        
        # 获取现有 items 数量
        existing_count = db.query(DatasetItem).count()
        tasks = db.query(Task).all()
        
        if not tasks:
            return {"success": False, "message": "没有可用的 Task"}
        
        # 创建 8 条新的 unclaimed items
        created_items = []
        start_id = existing_count + 1
        
        for i in range(8):
            task = tasks[i % len(tasks)]
            template_idx = (start_id + i) % len(DEMO_ITEM_TEMPLATES)
            
            item = DatasetItem(
                task_id=task.id,
                external_id=f"seed_{start_id + i}_{now.replace(':', '-')}",
                dataset_type="demo_seed",
                raw_data_json=DEMO_ITEM_TEMPLATES[template_idx],
                status=ItemStatus.UNCLAIMED.value
            )
            db.add(item)
            created_items.append({
                "id": start_id + i,
                "task_id": task.id,
                "work_key": f"{task.id}:{start_id + i}:{labeler_id}"
            })
        
        db.commit()
        
        logger.debug(f"[seed-more-items] created {len(created_items)} new unclaimed items")
        
        return {
            "success": True,
            "message": f"已追加 {len(created_items)} 条可领取数据",
            "items_created": len(created_items),
            "items": created_items
        }
    
    except Exception as e:
        logger.error(f"[seed-more-items] error: {e}")
        import traceback
        logger.error(f"[seed-more-items] traceback: {traceback.format_exc()}")
        return {"success": False, "message": str(e)}
