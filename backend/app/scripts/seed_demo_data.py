import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from datetime import datetime, timezone
from app.core.database import SessionLocal
from app.models.task import Task
from app.models.dataset_item import DatasetItem
from app.models.template_schema import TemplateSchema
from app.services.annotation_service import create_or_update_annotation, mark_annotation_invalid, update_annotation_status
from app.services.audit_service import create_audit_log


DEMO_TASK_NAME = "Demo 评测任务"
LABELER_ID = 2
REVIEWER_ID = 1


DEMO_ITEMS = [
    {"question": "什么是机器学习？", "answer": "机器学习是人工智能的一个分支，通过算法让计算机从数据中学习规律，而无需显式编程。", "reference": "机器学习是一种数据分析方法，自动化分析模型构建。", "category": "AI基础", "difficulty": "easy"},
    {"question": "深度学习和机器学习有什么区别？", "answer": "深度学习是机器学习的子集，使用多层神经网络来学习数据的复杂表示。", "reference": "深度学习使用深层神经网络，能自动提取特征。", "category": "AI基础", "difficulty": "medium"},
    {"question": "什么是过拟合？如何避免？", "answer": "过拟合是模型在训练数据上表现好但泛化能力差。可以通过正则化、增加数据量、早停等方法避免。", "reference": "过拟合指模型学习了训练数据的噪声而非真实规律。常用方法包括L1/L2正则化、Dropout、交叉验证。", "category": "AI基础", "difficulty": "medium"},
    {"question": "解释梯度下降算法的原理", "answer": "梯度下降通过计算损失函数的梯度，沿梯度反方向更新参数来最小化损失。", "reference": "梯度下降是一种优化算法，通过迭代更新参数使损失函数最小化。学习率决定步长。", "category": "AI算法", "difficulty": "hard"},
    {"question": "什么是机器学习？", "answer": "机器学习是AI的分支。", "reference": "机器学习是一种数据分析方法。", "category": "AI基础", "difficulty": "easy"},
    {"question": "请解释Transformer架构", "answer": "", "reference": "Transformer是基于自注意力机制的序列到序列模型。", "category": "AI架构", "difficulty": "hard"},
    {"question": "什么是自然语言处理？", "answer": "NLP是计算机理解和生成人类语言的技术。包括分词、命名实体识别、情感分析等任务。", "reference": "自然语言处理是AI和语言学的交叉领域。", "category": "NLP", "difficulty": "easy"},
    {"question": "解释BERT模型的工作原理", "answer": "BERT是双向编码器，通过掩码语言模型和下一句预测进行预训练。", "reference": "BERT通过双向Transformer编码器学习上下文表示，使用MLM和NSP两个预训练任务。", "category": "NLP", "difficulty": "hard"},
    {"question": "什么是强化学习？", "answer": "强化学习是智能体通过与环境交互获得奖励来学习策略的方法。", "reference": "强化学习是机器学习的三大范式之一，通过试错和延迟奖励学习最优策略。", "category": "AI算法", "difficulty": "medium"},
    {"question": "什么是卷积神经网络？", "answer": "CNN是使用卷积层提取空间特征的神经网络，广泛用于图像处理。", "reference": "卷积神经网络通过卷积运算提取局部特征，具有平移不变性。", "category": "AI架构", "difficulty": "medium"},
]


def seed():
    db = SessionLocal()
    try:
        existing = db.query(Task).filter(Task.name == DEMO_TASK_NAME).first()
        if existing:
            print(f"[SEED] Demo task already exists: id={existing.id}")
            task_id = existing.id
        else:
            template = db.query(TemplateSchema).filter(TemplateSchema.name.like('%问答质量%')).first()
            template_id = template.id if template else None

            task = Task(
                name=DEMO_TASK_NAME,
                description="用于演示5条完整业务链路的评测任务",
                status="published",
                template_id=template_id,
                work_mode="single",
                phase="annotation",
                created_by=1,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(task)
            db.flush()
            task_id = task.id
            print(f"[SEED] Created demo task: id={task_id}")

        existing_items = db.query(DatasetItem).filter(DatasetItem.task_id == task_id).count()
        if existing_items >= 10:
            print(f"[SEED] Demo items already exist: {existing_items} items")
            items = db.query(DatasetItem).filter(DatasetItem.task_id == task_id).order_by(DatasetItem.id).all()
        else:
            items = []
            for idx, item_data in enumerate(DEMO_ITEMS):
                di = DatasetItem(
                    task_id=task_id,
                    dataset_type="qa",
                    raw_data_json=item_data,
                    status="unclaimed",
                    is_valid=True,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.add(di)
                db.flush()
                items.append(di)
                print(f"[SEED] Created item {idx+1}: id={di.id}")

        db.commit()

        item_ids = [item.id for item in items]

        if len(item_ids) < 10:
            print(f"[SEED] Not enough items: {len(item_ids)}")
            return

        now = datetime.now().isoformat()

        for i in [0, 1]:
            item = items[i]
            item.status = "approved"
            item.claimed_by = LABELER_ID
            item.is_first_annotated = True

            ann = create_or_update_annotation(
                task_id=task_id,
                dataset_item_id=item.id,
                labeler_id=LABELER_ID,
                result_data={
                    "relevance": "high", "accuracy": "high",
                    "completeness": "complete", "safety": "safe",
                    "reason": "回答准确完整，与参考答案高度一致",
                    "problem_tags": [],
                    "rubric_judgements": {"R1": "pass", "R2": "pass"},
                },
                ai_review={
                    "score": 92 if i == 0 else 88,
                    "risk_level": "low",
                    "passed": True,
                    "suggestion": {"relevance": "high", "accuracy": "high", "completeness": "complete", "safety": "safe"},
                    "issues": [],
                    "summary": "高质量回答，建议通过",
                    "confidence": 0.95,
                    "matched_rubrics": [
                        {"rubric_id": "R1", "criterion": "回答与问题相关", "dimension": "relevance", "ai_judgement": "pass", "evidence": "回答直接回应了问题"},
                        {"rubric_id": "R2", "criterion": "回答准确无误", "dimension": "accuracy", "ai_judgement": "pass", "evidence": "与参考答案一致"}
                    ]
                },
                status="approved",
                item_snapshot={"id": item.id, "task_id": task_id, "raw_data": item.raw_data_json, "item_data": item.raw_data_json}
            )

            update_annotation_status(
                annotation_id=ann.get("id"),
                status="approved",
                review_info={"reviewer_id": REVIEWER_ID, "action": "approve", "comment": "审核通过", "reviewed_at": now}
            )

            print(f"[SEED] Scenario 1: item {item.id} approved")

        for i in [2, 3]:
            item = items[i]
            item.status = "approved" if i == 2 else "rejected_to_modify"
            item.claimed_by = LABELER_ID
            item.is_first_annotated = True

            ann = create_or_update_annotation(
                task_id=task_id,
                dataset_item_id=item.id,
                labeler_id=LABELER_ID,
                result_data={
                    "relevance": "high", "accuracy": "medium",
                    "completeness": "partial", "safety": "safe",
                    "reason": "回答部分正确但不够完整" if i == 2 else "回答有误",
                    "problem_tags": ["incomplete"] if i == 2 else ["incorrect", "incomplete"],
                    "rubric_judgements": {"R1": "pass", "R2": "fail"},
                },
                ai_review={
                    "score": 65 if i == 2 else 45,
                    "risk_level": "medium",
                    "passed": False,
                    "suggestion": {"relevance": "high", "accuracy": "medium", "completeness": "partial", "safety": "safe"},
                    "issues": [{"field": "completeness", "level": "medium", "message": "回答不够完整"}],
                    "summary": "回答存在不完整之处，建议补充",
                    "confidence": 0.78,
                    "matched_rubrics": [
                        {"rubric_id": "R1", "criterion": "回答与问题相关", "dimension": "relevance", "ai_judgement": "pass", "evidence": "回答与问题相关"},
                        {"rubric_id": "R2", "criterion": "回答准确无误", "dimension": "accuracy", "ai_judgement": "fail", "evidence": "部分内容不准确"}
                    ]
                },
                status="submitted",
                item_snapshot={"id": item.id, "task_id": task_id, "raw_data": item.raw_data_json, "item_data": item.raw_data_json}
            )

            if i == 2:
                update_annotation_status(
                    annotation_id=ann.get("id"),
                    status="approved",
                    review_info={"reviewer_id": REVIEWER_ID, "action": "approve", "comment": "虽有不足但可接受", "reviewed_at": now}
                )
                item.status = "approved"
            else:
                update_annotation_status(
                    annotation_id=ann.get("id"),
                    status="rejected_to_modify",
                    review_info={"reviewer_id": REVIEWER_ID, "action": "reject", "comment": "请补充准确性评估理由", "reviewed_at": now},
                    rejected_reason="请补充准确性评估理由"
                )

            print(f"[SEED] Scenario 2: item {item.id} {'approved' if i == 2 else 'rejected'}")

        for i in [4, 5]:
            item = items[i]
            item.claimed_by = LABELER_ID
            item.is_first_annotated = True

            reason = "数据重复" if i == 4 else "模型回答为空"
            ann = mark_annotation_invalid(
                task_id=task_id,
                dataset_item_id=item.id,
                labeler_id=LABELER_ID,
                invalid_reason=reason,
                invalid_remark="",
                work_key=f"{task_id}:{item.id}:{LABELER_ID}"
            )

            if i == 4:
                update_annotation_status(
                    annotation_id=ann.get("id"),
                    status="invalid_approved",
                    review_info={"reviewer_id": REVIEWER_ID, "action": "approve_invalid", "comment": "确认无效，数据重复", "reviewed_at": now}
                )
                item.status = "invalid_approved"
                item.is_valid = False
                print(f"[SEED] Scenario 3a: item {item.id} invalid_approved")
            else:
                item.status = "invalid_pending"
                item.is_valid = None
                print(f"[SEED] Scenario 3b: item {item.id} invalid_submitted (pending review)")

        item = items[6]
        item.claimed_by = LABELER_ID
        item.is_first_annotated = True

        ann = mark_annotation_invalid(
            task_id=task_id,
            dataset_item_id=item.id,
            labeler_id=LABELER_ID,
            invalid_reason="其他",
            invalid_remark="我认为这题可以标注，只是需要更多时间",
            work_key=f"{task_id}:{item.id}:{LABELER_ID}"
        )

        update_annotation_status(
            annotation_id=ann.get("id"),
            status="rejected_to_modify",
            review_info={"reviewer_id": REVIEWER_ID, "action": "reject", "comment": "无效理由不成立，请继续标注", "reviewed_at": now, "invalid_rejected": True},
            rejected_reason="无效理由不成立，请继续标注"
        )
        item.status = "rejected_to_modify"
        item.is_valid = None
        print(f"[SEED] Scenario 4: item {item.id} invalid rejected -> rework")

        for i in [7, 8]:
            item = items[i]
            item.claimed_by = LABELER_ID
            item.is_first_annotated = True

            ann = create_or_update_annotation(
                task_id=task_id,
                dataset_item_id=item.id,
                labeler_id=LABELER_ID,
                result_data={
                    "relevance": "high", "accuracy": "low",
                    "completeness": "partial", "safety": "safe",
                    "reason": "回答不够准确",
                    "problem_tags": ["incorrect"],
                },
                ai_review={
                    "score": 55,
                    "risk_level": "high",
                    "passed": False,
                    "suggestion": {"relevance": "high", "accuracy": "high", "completeness": "complete", "safety": "safe"},
                    "issues": [{"field": "accuracy", "level": "high", "message": "回答存在明显错误"}],
                    "summary": "回答存在错误，建议修改",
                    "confidence": 0.85,
                },
                status="submitted",
                item_snapshot={"id": item.id, "task_id": task_id, "raw_data": item.raw_data_json, "item_data": item.raw_data_json}
            )

            update_annotation_status(
                annotation_id=ann.get("id"),
                status="rejected_to_modify",
                review_info={"reviewer_id": REVIEWER_ID, "action": "reject", "comment": "请补充准确性评估理由", "reviewed_at": now},
                rejected_reason="请补充准确性评估理由"
            )

            if i == 8:
                update_annotation_status(
                    annotation_id=ann.get("id"),
                    status="submitted",
                    review_info=None
                )
                item.status = "submitted"
                print(f"[SEED] Scenario 5b: item {item.id} re-submitted after rework")
            else:
                item.status = "rejected_to_modify"
                print(f"[SEED] Scenario 5a: item {item.id} pending rework")

        items[9].status = "unclaimed"
        print(f"[SEED] Item {items[9].id} stays unclaimed")

        db.commit()

        for i, item in enumerate(items[:9]):
            try:
                create_audit_log(
                    db=db,
                    user_id=LABELER_ID,
                    action="item_claim",
                    target_type="dataset_item",
                    target_id=item.id,
                    task_id=task_id,
                    item_id=item.id,
                    message=f"领取 Item #{item.id}",
                    after_data={"status": "claimed"}
                )
            except Exception as e:
                print(f"[SEED] Audit log error: {e}")

        db.commit()

        print(f"\n[SEED] Demo data setup complete!")
        print(f"[SEED] Task ID: {task_id}")
        print(f"[SEED] Item IDs: {item_ids}")
        print(f"[SEED] Scenarios:")
        print(f"[SEED]   1. 高质量通过: items {item_ids[0]}, {item_ids[1]}")
        print(f"[SEED]   2. 中风险复核: items {item_ids[2]} (approved), {item_ids[3]} (rejected)")
        print(f"[SEED]   3. 无效确认: item {item_ids[4]} (invalid_approved), {item_ids[5]} (invalid_submitted)")
        print(f"[SEED]   4. 无效打回: item {item_ids[6]} (rejected_to_modify)")
        print(f"[SEED]   5. 返修: item {item_ids[7]} (pending rework), {item_ids[8]} (re-submitted)")
        print(f"[SEED]   + 未领取: item {item_ids[9]}")

    except Exception as e:
        print(f"[SEED] Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
