from datetime import datetime, timezone
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any

from app.models.template_schema import TemplateSchema
from app.schemas.template_schema import TemplateSchemaCreate, TemplateSchemaUpdate, TemplateCloneRequest
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType

_FALLBACK_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _ensure_timestamps(template: TemplateSchema) -> TemplateSchema:
    """确保模板对象的时间戳不为 None（脏数据兜底）。"""
    if not template.created_at:
        template.created_at = _FALLBACK_TS
    if not template.updated_at:
        template.updated_at = template.created_at or _FALLBACK_TS
    return template


def create_template(db: Session, template_create: TemplateSchemaCreate, user_id: int) -> TemplateSchema:
    now = datetime.now(timezone.utc)
    template = TemplateSchema(
        name=template_create.name,
        description=template_create.description,
        schema=template_create.form_schema,
        schema_version=template_create.schema_version,
        dataset_type=template_create.dataset_type,
        frozen_after_publish=template_create.frozen_after_publish,
        parent_template_id=template_create.parent_template_id,
        is_active=template_create.is_active,
        changelog=template_create.changelog,
        created_by=user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    
    log_action(
        db=db,
        user_id=user_id,
        action=AuditAction.TEMPLATE_CREATE,
        target_type=AuditTargetType.TEMPLATE,
        target_id=template.id,
        after_data={"name": template.name, "dataset_type": template.dataset_type, "schema_version": template.schema_version}
    )
    
    return template


def get_template(db: Session, template_id: int) -> Optional[TemplateSchema]:
    template = db.query(TemplateSchema).filter(TemplateSchema.id == template_id).first()
    if template:
        _ensure_timestamps(template)
    return template


def get_templates(
    db: Session,
    dataset_type: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    include_legacy: bool = False,
    task_id: Optional[int] = None,
) -> Dict[str, Any]:
    query = db.query(TemplateSchema)

    if dataset_type:
        query = query.filter(TemplateSchema.dataset_type == dataset_type)

    if task_id is not None:
        query = query.filter(TemplateSchema.task_id == task_id)

    if not include_legacy:
        # Default filter: only return non-archived templates that are visible on the template page
        from sqlalchemy import or_
        query = query.filter(
            or_(TemplateSchema.is_archived != True, TemplateSchema.is_archived == None)  # noqa: E711
        ).filter(
            or_(TemplateSchema.visible_in_template_page != False, TemplateSchema.visible_in_template_page == None)  # noqa: E711
        )

    total = query.count()
    items = query.order_by(TemplateSchema.id.desc())\
        .offset((page - 1) * limit)\
        .limit(limit)\
        .all()

    # 脏数据兜底：确保每条记录的时间戳不为 None
    for item in items:
        _ensure_timestamps(item)

    return {"items": items, "total": total, "page": page, "limit": limit}


def get_task_template(db: Session, task_id: int) -> Optional[TemplateSchema]:
    """Return the task-bound template for a given task, or None."""
    template = (
        db.query(TemplateSchema)
        .filter(
            TemplateSchema.task_id == task_id,
            TemplateSchema.is_task_bound == True,  # noqa: E712
            TemplateSchema.is_archived != True,  # noqa: E712
        )
        .first()
    )
    if template:
        _ensure_timestamps(template)
    return template


def update_template(db: Session, template_id: int, template_update: TemplateSchemaUpdate, user_id: int) -> Optional[TemplateSchema]:
    template = get_template(db, template_id)
    if not template:
        return None
    
    if template.frozen_after_publish:
        return None
    
    if template_update.name is not None:
        template.name = template_update.name
    if template_update.description is not None:
        template.description = template_update.description
    if template_update.form_schema is not None:
        template.schema = template_update.form_schema
    if template_update.schema_version is not None:
        template.schema_version = template_update.schema_version
    if template_update.frozen_after_publish is not None:
        template.frozen_after_publish = template_update.frozen_after_publish
    if template_update.is_active is not None:
        template.is_active = template_update.is_active
    if template_update.changelog is not None:
        template.changelog = template_update.changelog
    
    template.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(template)
    
    log_action(
        db=db,
        user_id=user_id,
        action=AuditAction.TEMPLATE_UPDATE,
        target_type=AuditTargetType.TEMPLATE,
        target_id=template.id,
        after_data={"name": template.name, "schema_version": template.schema_version}
    )
    
    return template


def delete_template(db: Session, template_id: int, user_id: int) -> bool:
    template = get_template(db, template_id)
    if not template:
        return False
    
    db.delete(template)
    db.commit()
    
    return True


def clone_template_version(db: Session, template_id: int, clone_request: TemplateCloneRequest, user_id: int) -> Optional[TemplateSchema]:
    """克隆模板为新版本"""
    original = get_template(db, template_id)
    if not original:
        return None
    
    # 生成新版本号
    current_version = original.schema_version
    if clone_request.schema_version:
        new_version = clone_request.schema_version
    else:
        # 自动递增版本号
        parts = current_version.split('.')
        if len(parts) >= 3:
            patch = int(parts[2]) + 1
            new_version = f"{parts[0]}.{parts[1]}.{patch}"
        else:
            new_version = f"{current_version}.1"
    
    # 更新原模板的 schema_version 和 is_active
    original.is_active = False
    original.schema_version = current_version
    
    # 创建新版本
    new_schema = original.schema.copy() if isinstance(original.schema, dict) else original.schema
    if isinstance(new_schema, dict):
        new_schema['schema_version'] = new_version
    
    template_create = TemplateSchemaCreate(
        name=original.name,
        description=original.description,
        schema=new_schema,
        schema_version=new_version,
        dataset_type=original.dataset_type,
        frozen_after_publish=False,
        parent_template_id=template_id,
        is_active=True,
        changelog=clone_request.changelog or f"基于版本 {current_version} 创建"
    )
    
    new_template = create_template(db, template_create, user_id)
    
    log_action(
        db=db,
        user_id=user_id,
        action=AuditAction.TEMPLATE_CREATE,
        target_type=AuditTargetType.TEMPLATE,
        target_id=new_template.id,
        after_data={
            "name": new_template.name,
            "schema_version": new_version,
            "parent_template_id": template_id,
            "changelog": clone_request.changelog
        }
    )
    
    return new_template


def create_qa_quality_template(db: Session, user_id: int) -> TemplateSchema:
    """创建升级后的问答质量评估模板"""
    schema = {
        "schema_version": "1.0.0",
        "dataset_type": "qa_quality",
        "name": "问答质量评估模板",
        "description": "用于评估大模型回答质量的标注模板",
        "layout": {
            "type": "single_column",
            "sections": []
        },
        "fields": [
            {
                "id": "prompt_show",
                "type": "ShowItem",
                "label": "问题",
                "binding": "{{item.prompt}}",
                "format": "text",
                "required": False,
                "props": {}
            },
            {
                "id": "model_answer_show",
                "type": "ShowItem",
                "label": "模型回答",
                "binding": "{{item.model_answer}}",
                "format": "markdown",
                "required": False,
                "props": {}
            },
            {
                "id": "reference_show",
                "type": "ShowItem",
                "label": "参考答案",
                "binding": "{{item.reference}}",
                "format": "text",
                "required": False,
                "props": {}
            },
            {
                "id": "category_show",
                "type": "ShowItem",
                "label": "类别",
                "binding": "{{item.category}}",
                "format": "text",
                "required": False,
                "props": {}
            },
            {
                "id": "difficulty_show",
                "type": "ShowItem",
                "label": "难度",
                "binding": "{{item.difficulty}}",
                "format": "text",
                "required": False,
                "props": {}
            },
            {
                "id": "tags_show",
                "type": "ShowItem",
                "label": "标签",
                "binding": "{{item.tags}}",
                "format": "text",
                "required": False,
                "props": {}
            },
            {
                "id": "relevance",
                "type": "Radio",
                "label": "相关性",
                "required": True,
                "options": [
                    {"label": "高", "value": "high"},
                    {"label": "中", "value": "medium"},
                    {"label": "低", "value": "low"}
                ],
                "validation": {
                    "required": True
                },
                "props": {}
            },
            {
                "id": "accuracy",
                "type": "Radio",
                "label": "准确性",
                "required": True,
                "options": [
                    {"label": "正确", "value": "correct"},
                    {"label": "部分正确", "value": "partially_correct"},
                    {"label": "错误", "value": "incorrect"}
                ],
                "validation": {
                    "required": True
                },
                "props": {}
            },
            {
                "id": "completeness",
                "type": "Radio",
                "label": "完整性",
                "required": True,
                "options": [
                    {"label": "完整", "value": "complete"},
                    {"label": "部分", "value": "partial"},
                    {"label": "不完整", "value": "incomplete"}
                ],
                "validation": {
                    "required": True
                },
                "props": {}
            },
            {
                "id": "safety",
                "type": "Radio",
                "label": "安全性",
                "required": True,
                "options": [
                    {"label": "安全", "value": "safe"},
                    {"label": "风险", "value": "risky"},
                    {"label": "不安全", "value": "unsafe"}
                ],
                "validation": {
                    "required": True
                },
                "props": {}
            },
            {
                "id": "overall_comment",
                "type": "Textarea",
                "label": "总体评价",
                "required": False,
                "placeholder": "请输入总体评价...",
                "rows": 3,
                "props": {}
            },
            {
                "id": "reason",
                "type": "Textarea",
                "label": "详细理由",
                "required": True,
                "placeholder": "请详细说明评分理由...",
                "rows": 4,
                "validation": {
                    "required": True
                },
                "props": {}
            },
            {
                "id": "issue_tags",
                "type": "TagSelect",
                "label": "问题标签",
                "required": False,
                "options": [
                    {"label": "事实错误", "value": "fact_error"},
                    {"label": "信息不全", "value": "incomplete"},
                    {"label": "偏离主题", "value": "off_topic"},
                    {"label": "安全风险", "value": "unsafe"},
                    {"label": "表述模糊", "value": "ambiguous"}
                ],
                "props": {}
            },
            {
                "id": "correction_json",
                "type": "JsonEditor",
                "label": "修正内容",
                "required": False,
                "height": 150,
                "props": {}
            }
        ],
        "rules": [
            {
                "id": "show_correction_when_low_accuracy",
                "type": "visibility",
                "when": {
                    "field": "accuracy",
                    "operator": "in",
                    "value": ["incorrect", "partially_correct"]
                },
                "target": "correction_json",
                "effect": "show"
            }
        ],
        "llm_assist": [
            {
                "id": "quality_assist",
                "name": "AI 质量建议",
                "prompt_template": "请根据问题、模型回答和参考答案，给出质量评估建议。",
                "input_bindings": ["prompt", "model_answer", "reference"],
                "output_target": "overall_comment"
            }
        ],
        "export_mapping": [
            {"source": "relevance", "target": "relevance", "include": True},
            {"source": "accuracy", "target": "accuracy", "include": True},
            {"source": "completeness", "target": "completeness", "include": True},
            {"source": "safety", "target": "safety", "include": True},
            {"source": "reason", "target": "reason", "include": True}
        ],
        "ai_review_config": {
            "enabled": True,
            "scoreDimensions": [
                {"name": "相关性", "weight": 0.2},
                {"name": "准确性", "weight": 0.3},
                {"name": "完整性", "weight": 0.2},
                {"name": "安全性", "weight": 0.2},
                {"name": "总评", "weight": 0.1}
            ],
            "passThreshold": 80,
            "rejectThreshold": 60
        }
    }
    
    template_create = TemplateSchemaCreate(
        name="问答质量评估模板",
        description="用于评估大模型问答质量的标注模板",
        schema=schema,
        schema_version="1.0.0",
        dataset_type="qa_quality",
        frozen_after_publish=False
    )
    
    return create_template(db, template_create, user_id)


def create_preference_compare_template(db: Session, user_id: int) -> TemplateSchema:
    """创建升级后的偏好对比模板"""
    schema = {
        "schema_version": "1.0.0",
        "dataset_type": "preference_compare",
        "name": "A/B 偏好对比模板",
        "description": "用于对比两个回答的偏好选择",
        "layout": {
            "type": "two_column",
            "sections": []
        },
        "fields": [
            {
                "id": "prompt_show",
                "type": "ShowItem",
                "label": "问题",
                "binding": "{{item.prompt}}",
                "format": "text",
                "required": False,
                "props": {}
            },
            {
                "id": "response_a_show",
                "type": "ShowItem",
                "label": "回答 A",
                "binding": "{{item.response_a}}",
                "format": "markdown",
                "required": False,
                "props": {}
            },
            {
                "id": "response_b_show",
                "type": "ShowItem",
                "label": "回答 B",
                "binding": "{{item.response_b}}",
                "format": "markdown",
                "required": False,
                "props": {}
            },
            {
                "id": "model_a_show",
                "type": "ShowItem",
                "label": "模型 A",
                "binding": "{{item.model_a}}",
                "format": "text",
                "required": False,
                "props": {}
            },
            {
                "id": "model_b_show",
                "type": "ShowItem",
                "label": "模型 B",
                "binding": "{{item.model_b}}",
                "format": "text",
                "required": False,
                "props": {}
            },
            {
                "id": "preferred",
                "type": "Radio",
                "label": "更优回答",
                "required": True,
                "options": [
                    {"label": "回答 A", "value": "a"},
                    {"label": "回答 B", "value": "b"},
                    {"label": "两者相当", "value": "tie"}
                ],
                "validation": {
                    "required": True
                },
                "props": {}
            },
            {
                "id": "margin",
                "type": "Radio",
                "label": "差异程度",
                "required": True,
                "options": [
                    {"label": "明显差异", "value": "large"},
                    {"label": "轻微差异", "value": "small"},
                    {"label": "无差异", "value": "none"}
                ],
                "validation": {
                    "required": True
                },
                "props": {}
            },
            {
                "id": "safety_flag",
                "type": "Radio",
                "label": "安全标记",
                "required": True,
                "options": [
                    {"label": "安全", "value": "safe"},
                    {"label": "风险", "value": "risky"},
                    {"label": "不安全", "value": "unsafe"}
                ],
                "validation": {
                    "required": True
                },
                "props": {}
            },
            {
                "id": "dimensions",
                "type": "Checkbox",
                "label": "评估维度",
                "required": False,
                "options": [
                    {"label": "正确性", "value": "correctness"},
                    {"label": "完整性", "value": "completeness"},
                    {"label": "逻辑性", "value": "logic"},
                    {"label": "流畅性", "value": "fluency"}
                ],
                "props": {}
            },
            {
                "id": "reason",
                "type": "Textarea",
                "label": "判断理由",
                "required": True,
                "placeholder": "请说明选择理由...",
                "rows": 4,
                "validation": {
                    "required": True
                },
                "props": {}
            }
        ],
        "rules": [],
        "llm_assist": [
            {
                "id": "preference_assist",
                "name": "AI 偏好建议",
                "prompt_template": "请根据问题、回答A和回答B，给出偏好选择建议。",
                "input_bindings": ["prompt", "response_a", "response_b"],
                "output_target": "reason"
            }
        ],
        "export_mapping": [
            {"source": "preferred", "target": "preferred", "include": True},
            {"source": "margin", "target": "margin", "include": True},
            {"source": "safety_flag", "target": "safety_flag", "include": True},
            {"source": "reason", "target": "reason", "include": True}
        ],
        "ai_review_config": {
            "enabled": True,
            "scoreDimensions": [
                {"name": "正确性", "weight": 0.4},
                {"name": "完整性", "weight": 0.3},
                {"name": "逻辑性", "weight": 0.3}
            ],
            "passThreshold": 85,
            "rejectThreshold": 70
        }
    }
    
    template_create = TemplateSchemaCreate(
        name="A/B 偏好对比模板",
        description="用于对比两个回答的偏好选择",
        schema=schema,
        schema_version="1.0.0",
        dataset_type="preference_compare",
        frozen_after_publish=False
    )
    
    return create_template(db, template_create, user_id)
