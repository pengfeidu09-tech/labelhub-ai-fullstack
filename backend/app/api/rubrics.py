from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.models.template_schema import TemplateSchema

router = APIRouter(prefix="/api/rubrics", tags=["rubrics"])


RUBRIC_LABELS = {"相关性", "准确性", "完整性", "安全性", "relevance", "accuracy", "completeness", "safety"}


def _extract_rubrics_from_schema(schema_json):
    if not schema_json:
        return []
    if isinstance(schema_json, str):
        import json
        try:
            schema_json = json.loads(schema_json)
        except:
            return []
    if not isinstance(schema_json, dict):
        return []

    rubrics = schema_json.get("rubrics", [])
    if not rubrics:
        fields = schema_json.get("fields", [])
        for field in fields:
            if isinstance(field, dict):
                ftype = field.get("type", "")
                label = field.get("label", "")
                if ftype in ("rubric", "rubric_group", "criteria"):
                    rubrics.append(field)
                    continue
                if ftype in ("Radio", "Select", "radio", "select") and label in RUBRIC_LABELS:
                    rubrics.append({
                        **field,
                        "criterion": label,
                        "dimension": label,
                        "type": "rubric",
                        "priority": "must_have",
                        "necessity": "explicit",
                    })
                    continue
                options = field.get("options", [])
                if options and ftype in ("select", "radio", "checkbox", "Select", "Radio"):
                    for opt in options:
                        if isinstance(opt, dict) and opt.get("is_rubric"):
                            rubrics.append({
                                **field,
                                "rubric_option": opt
                            })
    return rubrics


def _check_rubric_health(rubric: dict) -> dict:
    issues = []
    suggestions = []
    score = 100

    criterion = rubric.get("criterion") or rubric.get("title") or rubric.get("label") or rubric.get("name") or ""
    dimension = rubric.get("dimension") or rubric.get("group") or ""
    rtype = rubric.get("type") or rubric.get("rubric_type") or ""
    necessity = rubric.get("necessity") or rubric.get("required_type") or ""
    priority = rubric.get("priority") or rubric.get("level") or ""

    if len(criterion) < 5:
        issues.append("标准描述过短，缺乏明确判断条件")
        suggestions.append("建议补充更详细的判断条件和示例")
        score -= 20

    if not dimension:
        issues.append("缺少维度分类")
        suggestions.append("建议关联到具体评估维度（如相关性、准确性等）")
        score -= 15

    if not priority:
        issues.append("缺少优先级")
        suggestions.append("建议设置优先级（Must have / Nice to have）")
        score -= 10

    if not rtype:
        issues.append("缺少类型标注")
        suggestions.append("建议标注为 Objective 或 Subjective")
        score -= 10

    if len(criterion) > 200:
        issues.append("标准描述过长，可能难以快速判断")
        suggestions.append("建议精简描述，将详细说明放入补充说明")
        score -= 5

    options = rubric.get("options") or rubric.get("choices") or []
    if not options and rtype != "objective":
        pass

    score = max(0, min(100, score))

    risk_level = "low"
    if score < 60:
        risk_level = "high"
    elif score < 80:
        risk_level = "medium"

    return {
        "health_score": score,
        "risk_level": risk_level,
        "issues": issues,
        "suggestions": suggestions
    }


@router.get("")
def get_rubrics(
    task_id: Optional[int] = None,
    template_id: Optional[int] = None,
    search: Optional[str] = None,
    dimension: Optional[str] = None,
    priority: Optional[str] = None,
    rtype: Optional[str] = None,
    db: Session = Depends(get_db)
):
    templates = db.query(TemplateSchema).filter(TemplateSchema.is_active == True).all()

    if template_id:
        templates = [t for t in templates if t.id == template_id]

    all_rubrics = []
    for template in templates:
        schema_json = template.schema
        rubrics = _extract_rubrics_from_schema(schema_json)

        for idx, rubric in enumerate(rubrics):
            health = _check_rubric_health(rubric)
            rubric_item = {
                "rubric_id": f"{template.id}-{idx}",
                "template_id": template.id,
                "template_name": template.name,
                "criterion": rubric.get("criterion") or rubric.get("title") or rubric.get("label") or rubric.get("name") or "",
                "dimension": rubric.get("dimension") or rubric.get("group") or "",
                "type": rubric.get("type") or rubric.get("rubric_type") or "subjective",
                "necessity": rubric.get("necessity") or rubric.get("required_type") or "implicit",
                "priority": rubric.get("priority") or rubric.get("level") or "nice_to_have",
                "version": rubric.get("version") or template.schema_version or "1.0",
                "enabled": rubric.get("enabled", True),
                "health_score": health["health_score"],
                "risk_level": health["risk_level"],
                "issues": health["issues"],
                "suggestions": health["suggestions"],
                "updated_at": template.updated_at.isoformat() if template.updated_at else None,
                "raw": rubric
            }

            if search and search.lower() not in rubric_item["criterion"].lower():
                continue
            if dimension and rubric_item["dimension"] != dimension:
                continue
            if priority and rubric_item["priority"] != priority:
                continue
            if rtype and rubric_item["type"] != rtype:
                continue

            all_rubrics.append(rubric_item)

    return {"items": all_rubrics, "total": len(all_rubrics)}


@router.get("/health-check")
def rubric_health_check(
    task_id: Optional[int] = None,
    template_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    return _do_health_check(db, task_id, template_id)


@router.post("/health-check")
def rubric_health_check_post(
    request: dict = None,
    db: Session = Depends(get_db)
):
    task_id = request.get("task_id") if request else None
    template_id = request.get("template_id") if request else None
    return _do_health_check(db, task_id, template_id)


def _do_health_check(db, task_id=None, template_id=None):
    from datetime import timezone as _tz
    templates = db.query(TemplateSchema).filter(TemplateSchema.is_active == True).all()

    if template_id:
        templates = [t for t in templates if t.id == template_id]

    all_rubrics = []
    all_issues = []
    for template in templates:
        schema_json = template.schema
        rubrics = _extract_rubrics_from_schema(schema_json)

        for idx, rubric in enumerate(rubrics):
            rubric_item = {
                "rubric_id": f"{template.id}-{idx}",
                "template_id": template.id,
                "template_name": template.name,
                "criterion": rubric.get("criterion") or rubric.get("title") or rubric.get("label") or rubric.get("name") or "",
                "dimension": rubric.get("dimension") or rubric.get("group") or "",
                "type": rubric.get("type") or rubric.get("rubric_type") or "subjective",
                "necessity": rubric.get("necessity") or rubric.get("required_type") or "implicit",
                "priority": rubric.get("priority") or rubric.get("level") or "nice_to_have",
                "version": rubric.get("version") or template.schema_version or "1.0",
                "enabled": rubric.get("enabled", True),
                "updated_at": template.updated_at.isoformat() if template.updated_at else None,
            }

            health = _check_rubric_health(rubric)
            rubric_item.update(health)
            all_rubrics.append(rubric_item)
            for issue in health.get("issues", []):
                all_issues.append(f"[{rubric_item['criterion'][:30]}] {issue}")

    total = len(all_rubrics)
    healthy = len([r for r in all_rubrics if r["risk_level"] == "low"])
    at_risk = len([r for r in all_rubrics if r["risk_level"] != "low"])
    avg_score = round(sum(r["health_score"] for r in all_rubrics) / total, 1) if total > 0 else 0

    return {
        "status": "ok",
        "items": all_rubrics,
        "total": total,
        "healthy_count": healthy,
        "at_risk_count": at_risk,
        "average_health_score": avg_score,
        "issues": all_issues,
        "checked_at": datetime.now(_tz.utc).isoformat()
    }


@router.get("/dimensions")
def get_rubric_dimensions(db: Session = Depends(get_db)):
    templates = db.query(TemplateSchema).filter(TemplateSchema.is_active == True).all()

    dimensions = set()
    for template in templates:
        rubrics = _extract_rubrics_from_schema(template.schema)
        for rubric in rubrics:
            dim = rubric.get("dimension") or rubric.get("group") or ""
            if dim:
                dimensions.add(dim)

    return {"dimensions": sorted(list(dimensions))}
