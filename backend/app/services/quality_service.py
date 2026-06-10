from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.task import Task
from app.models.dataset_item import DatasetItem
from app.models.ai_review_run import AIReviewRun
from app.models.submission import Submission
from app.services.annotation_service import get_annotations_by_filter, normalize_ai_review


def compute_quality_insights(db: Session, task_id: int) -> Dict[str, Any]:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"error": "Task not found"}

    annotations = get_annotations_by_filter(task_id=task_id)

    ai_scores = []
    ai_risk_low = 0
    ai_risk_medium = 0
    ai_risk_high = 0
    human_approve = 0
    human_total = 0
    ai_human_agree = 0
    ai_human_total = 0
    rejected_count = 0
    exportable_count = 0
    low_score_count = 0
    priority_review_count = 0

    for ann in annotations:
        status = ann.get("status", "")
        if status in ("rejected_to_modify", "returned_to_modify", "needs_revision"):
            rejected_count += 1
        if status in ("approved", "export_ready"):
            exportable_count += 1

        ai_review_raw = ann.get("ai_review")
        ai_review = normalize_ai_review(ai_review_raw) if ai_review_raw and isinstance(ai_review_raw, dict) else None

        if ai_review:
            score = ai_review.get("overall_score")
            if isinstance(score, (int, float)):
                ai_scores.append(score)
                if score < 70:
                    low_score_count += 1

            risk = ai_review.get("risk_level", "")
            if risk == "high":
                ai_risk_high += 1
            elif risk == "medium":
                ai_risk_medium += 1
            elif risk == "low":
                ai_risk_low += 1

            suggested = ai_review.get("suggested_action", "")
            if suggested in ("reject", "rework") or (isinstance(score, (int, float)) and score < 70) or risk == "high":
                priority_review_count += 1

        review_info = ann.get("review_info")
        if isinstance(review_info, dict):
            action = review_info.get("action", "")
            human_total += 1
            if action in ("approve", "approve_invalid"):
                human_approve += 1

            if ai_review and ai_review.get("passed") is not None:
                ai_human_total += 1
                ai_passed = ai_review.get("passed") is True
                human_approved = action in ("approve", "approve_invalid")
                if ai_passed == human_approved:
                    ai_human_agree += 1

    ai_avg_score = round(sum(ai_scores) / len(ai_scores), 1) if ai_scores else None
    human_pass_rate = round(human_approve / human_total, 2) if human_total > 0 else None
    ai_human_agreement_rate = round(ai_human_agree / ai_human_total, 2) if ai_human_total > 0 else None

    return {
        "task_id": task_id,
        "ai_avg_score": ai_avg_score,
        "ai_risk_distribution": {
            "low": ai_risk_low,
            "medium": ai_risk_medium,
            "high": ai_risk_high
        },
        "human_pass_rate": human_pass_rate,
        "ai_human_agreement_rate": ai_human_agreement_rate,
        "rejected_count": rejected_count,
        "exportable_count": exportable_count,
        "low_score_count": low_score_count,
        "priority_review_count": priority_review_count,
        "total_with_ai_review": len(ai_scores),
        "total_with_human_review": human_total,
        "stat_notes": {
            "ai_avg_score": "基于已完成 AI 预审的数据计算",
            "ai_human_agreement_rate": "基于已同时存在 AI 结果和人工审核结果的数据计算",
            "priority_review_count": "低分、高风险、AI/人工不一致、曾被打回的数据",
            "low_score_count": "AI 分数低于 70 的样本数量"
        }
    }


def compute_rubric_analysis(db: Session, task_id: int) -> Dict[str, Any]:
    from app.models.template_schema import TemplateSchema
    from app.api.rubrics import _extract_rubrics_from_schema

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"error": "Task not found"}

    rubrics = []
    if task.template_id:
        template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()
        if template and template.schema:
            rubrics = _extract_rubrics_from_schema(template.schema)

    if not rubrics:
        rubrics = _generate_default_rubrics()

    annotations = get_annotations_by_filter(task_id=task_id)

    rubric_stats = {}
    for rubric in rubrics:
        rubric_id = rubric.get("id") or rubric.get("key") or rubric.get("criterion", "")
        rubric_name = rubric.get("title") or rubric.get("label") or rubric.get("name") or rubric.get("criterion", "")
        dimension = rubric.get("dimension") or rubric.get("group") or ""
        rtype = rubric.get("type") or rubric.get("rubric_type") or "objective"
        priority = rubric.get("priority") or rubric.get("weight") or "nice_to_have"

        if not dimension:
            for dim in ["relevance", "accuracy", "completeness", "safety"]:
                if dim in rubric_name.lower() or dim in str(rubric_id).lower():
                    dimension = dim
                    break
            if not dimension:
                dimension = "relevance"

        rubric_stats[rubric_id] = {
            "rubric_id": rubric_id,
            "rubric_name": rubric_name,
            "dimension": dimension,
            "type": rtype,
            "priority": priority,
            "human_met": 0,
            "human_not_met": 0,
            "human_uncertain": 0,
            "ai_suggested": 0,
            "ai_human_agree": 0,
            "ai_human_total": 0,
            "rejected_appearances": 0
        }

    if not rubric_stats:
        rubric_stats = _generate_default_rubric_stats()

    for ann in annotations:
        status = ann.get("status", "")
        result = ann.get("result") or ann.get("annotation_result") or ann.get("data") or {}
        ai_review_raw = ann.get("ai_review")
        ai_review = normalize_ai_review(ai_review_raw) if ai_review_raw and isinstance(ai_review_raw, dict) else None
        review_info = ann.get("review_info") or {}

        for rubric_id, stats in rubric_stats.items():
            dim = stats["dimension"]
            human_val = result.get(dim) if isinstance(result, dict) else None

            if human_val:
                if human_val in ("high", "correct", "complete", "safe"):
                    stats["human_met"] += 1
                elif human_val in ("low", "incorrect", "incomplete", "unsafe"):
                    stats["human_not_met"] += 1
                else:
                    stats["human_uncertain"] += 1

            if ai_review:
                suggestion = ai_review.get("suggestion") or {}
                ai_val = suggestion.get(dim)
                if ai_val:
                    stats["ai_suggested"] += 1
                    if human_val:
                        stats["ai_human_total"] += 1
                        if ai_val == human_val:
                            stats["ai_human_agree"] += 1

            if status in ("rejected_to_modify", "returned_to_modify", "needs_revision"):
                stats["rejected_appearances"] += 1

    rubric_list = []
    for stats in rubric_stats.values():
        total_human = stats["human_met"] + stats["human_not_met"] + stats["human_uncertain"]
        agreement_rate = round(stats["ai_human_agree"] / stats["ai_human_total"], 2) if stats["ai_human_total"] > 0 else None
        not_met_rate = round(stats["human_not_met"] / total_human, 2) if total_human > 0 else 0
        uncertain_rate = round(stats["human_uncertain"] / total_human, 2) if total_human > 0 else 0

        is_high_dispute = False
        dispute_reasons = []
        if agreement_rate is not None and agreement_rate < 0.6:
            is_high_dispute = True
            dispute_reasons.append("AI/人工一致率低于60%")
        if not_met_rate > 0.4:
            is_high_dispute = True
            dispute_reasons.append("不满足比例高于40%")
        if uncertain_rate > 0.3:
            is_high_dispute = True
            dispute_reasons.append("不确定比例高于30%")
        if stats["rejected_appearances"] >= 2:
            is_high_dispute = True
            dispute_reasons.append("被打回样本中频繁出现")

        tags = []
        if is_high_dispute:
            tags.append("高争议")
        elif agreement_rate is not None and agreement_rate >= 0.8:
            tags.append("稳定")
        if not_met_rate > 0.3:
            tags.append("高频问题")
        if stats["human_met"] > 0 and (stats["ai_suggested"] / max(stats["human_met"], 1)) < 0.3:
            tags.append("低命中")

        rubric_list.append({
            **stats,
            "agreement_rate": agreement_rate,
            "not_met_rate": not_met_rate,
            "uncertain_rate": uncertain_rate,
            "is_high_dispute": is_high_dispute,
            "dispute_reasons": dispute_reasons,
            "tags": tags
        })

    return {
        "task_id": task_id,
        "rubrics": rubric_list,
        "total_rubrics": len(rubric_list),
        "high_dispute_count": sum(1 for r in rubric_list if r["is_high_dispute"])
    }


def compute_priority_reviews(db: Session, task_id: int) -> Dict[str, Any]:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"error": "Task not found"}

    annotations = get_annotations_by_filter(task_id=task_id)
    priority_items = []

    for ann in annotations:
        triggers = []
        ai_review_raw = ann.get("ai_review")
        ai_review = normalize_ai_review(ai_review_raw) if ai_review_raw and isinstance(ai_review_raw, dict) else None
        status = ann.get("status", "")
        result = ann.get("result") or ann.get("annotation_result") or ann.get("data") or {}
        review_info = ann.get("review_info") or {}

        ai_score = None
        ai_risk = None
        ai_suggested = None

        if ai_review:
            ai_score = ai_review.get("overall_score")
            ai_risk = ai_review.get("risk_level")
            ai_suggested = ai_review.get("suggested_action")

            if isinstance(ai_score, (int, float)) and ai_score < 70:
                triggers.append("AI 分数低于阈值")
            if ai_risk == "high":
                triggers.append("AI 高风险")
            if ai_suggested in ("reject", "rework"):
                triggers.append("AI 建议打回")

            suggestion = ai_review.get("suggestion") or {}
            if isinstance(result, dict):
                for dim in ["relevance", "accuracy", "completeness", "safety"]:
                    ai_val = suggestion.get(dim)
                    human_val = result.get(dim)
                    if ai_val and human_val and ai_val != human_val:
                        triggers.append(f"AI/人工不一致({dim})")
                        break

        if status in ("rejected_to_modify", "returned_to_modify", "needs_revision"):
            triggers.append("被打回返修")

        if status in ("invalid_submitted", "invalid_pending"):
            triggers.append("无效待审")

        if isinstance(result, dict):
            missing_fields = []
            for field in ["relevance", "accuracy", "completeness", "safety", "reason"]:
                if not result.get(field):
                    missing_fields.append(field)
            if len(missing_fields) >= 2:
                triggers.append(f"关键字段缺失({','.join(missing_fields[:3])})")

        if triggers:
            priority_items.append({
                "submission_id": ann.get("id"),
                "task_id": ann.get("task_id"),
                "dataset_item_id": ann.get("dataset_item_id"),
                "labeler_id": ann.get("labeler_id"),
                "ai_score": ai_score,
                "ai_risk_level": ai_risk,
                "human_status": status,
                "triggers": triggers,
                "updated_at": ann.get("updated_at"),
                "created_at": ann.get("created_at")
            })

    priority_items.sort(key=lambda x: (
        0 if "AI 高风险" in x["triggers"] else 1 if "AI 分数低于阈值" in x["triggers"] else 2,
        -(x["ai_score"] or 0)
    ))

    return {
        "task_id": task_id,
        "items": priority_items,
        "total": len(priority_items)
    }


def generate_quality_report(db: Session, task_id: int) -> Dict[str, Any]:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"error": "Task not found"}

    insights = compute_quality_insights(db, task_id)
    rubric_analysis = compute_rubric_analysis(db, task_id)
    priority = compute_priority_reviews(db, task_id)

    total_items = db.query(DatasetItem).filter(DatasetItem.task_id == task_id).count()
    annotations = get_annotations_by_filter(task_id=task_id)

    submitted_count = 0
    ai_reviewed_count = 0
    human_reviewed_count = 0
    approved_count = 0
    exportable_count = 0
    ai_pass_count = 0
    ai_reject_count = 0
    ai_human_review_count = 0
    human_approve_count = 0
    human_reject_count = 0
    human_revise_count = 0
    ai_human_agree = 0
    ai_human_total = 0
    disagreement_dims = {"relevance": 0, "accuracy": 0, "completeness": 0, "safety": 0}
    completeness_low = 0
    reason_short = 0
    accuracy_risk = 0
    safety_risk = 0

    for ann in annotations:
        status = ann.get("status", "")
        if status not in ("draft", "drafting", "claimed", "unclaimed", ""):
            submitted_count += 1
        if status in ("approved", "export_ready"):
            approved_count += 1
            exportable_count += 1

        ai_review_raw = ann.get("ai_review")
        ai_review = normalize_ai_review(ai_review_raw) if ai_review_raw and isinstance(ai_review_raw, dict) else None

        if ai_review:
            ai_reviewed_count += 1
            suggested = ai_review.get("suggested_action", "")
            if suggested == "submit":
                ai_pass_count += 1
            elif suggested in ("reject", "rework"):
                ai_reject_count += 1
            else:
                ai_human_review_count += 1

            suggestion = ai_review.get("suggestion") or {}
            if suggestion.get("completeness") in ("partial", "incomplete"):
                completeness_low += 1
            if suggestion.get("accuracy") in ("incorrect", "partially_correct"):
                accuracy_risk += 1
            if suggestion.get("safety") in ("risky", "unsafe"):
                safety_risk += 1

        result = ann.get("result") or ann.get("annotation_result") or ann.get("data") or {}
        if isinstance(result, dict):
            reason = result.get("reason", "")
            if isinstance(reason, str) and len(reason) < 10:
                reason_short += 1

        review_info = ann.get("review_info")
        if isinstance(review_info, dict):
            human_reviewed_count += 1
            action = review_info.get("action", "")
            if action in ("approve", "approve_invalid"):
                human_approve_count += 1
            elif action in ("reject", "reject_to_modify"):
                human_reject_count += 1
            elif action in ("revise", "rework"):
                human_revise_count += 1

            if ai_review:
                ai_human_total += 1
                ai_passed = ai_review.get("passed") is True
                human_approved = action in ("approve", "approve_invalid")
                if ai_passed == human_approved:
                    ai_human_agree += 1
                else:
                    suggestion = ai_review.get("suggestion") or {}
                    for dim in disagreement_dims:
                        ai_val = suggestion.get(dim)
                        human_val = result.get(dim) if isinstance(result, dict) else None
                        if ai_val and human_val and ai_val != human_val:
                            disagreement_dims[dim] += 1

    human_pass_rate = round(human_approve_count / human_reviewed_count, 2) if human_reviewed_count > 0 else 0
    human_reject_rate = round(human_reject_count / human_reviewed_count, 2) if human_reviewed_count > 0 else 0
    agreement_rate = round(ai_human_agree / ai_human_total, 2) if ai_human_total > 0 else None

    main_disagreement_dim = max(disagreement_dims, key=disagreement_dims.get) if any(disagreement_dims.values()) else None

    quality_issues = []
    if completeness_low > 0:
        quality_issues.append({"issue": "完整性不足", "count": completeness_low, "severity": "medium"})
    if reason_short > 0:
        quality_issues.append({"issue": "理由过短", "count": reason_short, "severity": "low"})
    if accuracy_risk > 0:
        quality_issues.append({"issue": "准确性风险", "count": accuracy_risk, "severity": "high"})
    if safety_risk > 0:
        quality_issues.append({"issue": "安全性风险", "count": safety_risk, "severity": "high"})

    high_dispute_rubrics = [r for r in rubric_analysis.get("rubrics", []) if r.get("is_high_dispute")]
    if high_dispute_rubrics:
        quality_issues.append({"issue": "Rubric 未充分命中", "count": len(high_dispute_rubrics), "severity": "medium"})

    priority_suggestions = []
    if insights.get("ai_risk_distribution", {}).get("high", 0) > 0:
        priority_suggestions.append("建议优先复核高风险样本")
    if completeness_low > 0:
        priority_suggestions.append(f"建议关注 completeness 低分数据（{completeness_low}条）")
    if high_dispute_rubrics:
        priority_suggestions.append(f"建议优化高争议 Rubric（{len(high_dispute_rubrics)}个）")
    ai_missing = submitted_count - ai_reviewed_count
    if ai_missing > 0:
        priority_suggestions.append(f"建议导出前补齐 AI 预审缺失样本（{ai_missing}条）")

    export_ready = exportable_count > 0 and human_pass_rate >= 0.5
    recommended_format = "json" if exportable_count < 100 else "csv"
    export_checklist = []
    if ai_missing > 0:
        export_checklist.append(f"补齐 {ai_missing} 条缺失的 AI 预审结果")
    if human_reject_count > 0:
        export_checklist.append(f"确认 {human_reject_count} 条打回数据已返修通过")
    if insights.get("low_score_count", 0) > 0:
        export_checklist.append(f"复核 {insights['low_score_count']} 条低分样本")
    if not export_checklist:
        export_checklist.append("所有检查项已通过，可以导出")

    sample_note = ""
    if submitted_count < 10:
        sample_note = "当前样本量较少，结论仅供演示参考。"

    from app.models.ai_review_run import AIReviewRun
    agent_runs = db.query(AIReviewRun).filter(AIReviewRun.task_id == task_id).all()
    agent_success = sum(1 for r in agent_runs if r.status == "success")
    agent_failed = sum(1 for r in agent_runs if r.status == "failed")
    agent_fallback = sum(1 for r in agent_runs if r.status == "fallback_required")
    agent_pending = sum(1 for r in agent_runs if r.status == "pending")
    agent_latencies = [r.latency_ms for r in agent_runs if r.latency_ms is not None]
    agent_avg_latency = round(sum(agent_latencies) / len(agent_latencies)) if agent_latencies else None

    report_text = _build_report_text(
        task_id=task_id,
        task_name=task.name or "",
        total_items=total_items,
        submitted_count=submitted_count,
        ai_reviewed_count=ai_reviewed_count,
        human_reviewed_count=human_reviewed_count,
        exportable_count=exportable_count,
        ai_avg_score=insights.get("ai_avg_score"),
        ai_risk_distribution=insights.get("ai_risk_distribution", {}),
        ai_pass_count=ai_pass_count,
        ai_reject_count=ai_reject_count,
        human_approve_count=human_approve_count,
        human_reject_count=human_reject_count,
        human_revise_count=human_revise_count,
        human_pass_rate=human_pass_rate,
        human_reject_rate=human_reject_rate,
        ai_human_agree=ai_human_agree,
        ai_human_total=ai_human_total,
        agreement_rate=agreement_rate,
        main_disagreement_dim=main_disagreement_dim,
        quality_issues=quality_issues,
        priority_suggestions=priority_suggestions,
        export_ready=export_ready,
        recommended_format=recommended_format,
        export_checklist=export_checklist,
        sample_note=sample_note,
        exportable_count_val=exportable_count,
        ai_missing=ai_missing
    )

    return {
        "task_id": task_id,
        "generated_at": datetime.now().isoformat(),
        "generated_by": "LabelHub AI Quality Agent",
        "report_text": report_text,
        "structured": {
            "task_overview": {
                "task_id": task_id,
                "task_name": task.name or "",
                "total_items": total_items,
                "submitted_count": submitted_count,
                "ai_reviewed_count": ai_reviewed_count,
                "human_reviewed_count": human_reviewed_count,
                "exportable_count": exportable_count
            },
            "ai_precheck_overview": {
                "avg_score": insights.get("ai_avg_score"),
                "risk_distribution": insights.get("ai_risk_distribution", {}),
                "pass_count": ai_pass_count,
                "reject_count": ai_reject_count
            },
            "human_review_overview": {
                "approve_count": human_approve_count,
                "reject_count": human_reject_count,
                "revise_count": human_revise_count,
                "pass_rate": human_pass_rate,
                "reject_rate": human_reject_rate
            },
            "ai_human_consistency": {
                "agree_count": ai_human_agree,
                "disagree_count": ai_human_total - ai_human_agree,
                "agreement_rate": agreement_rate,
                "main_disagreement_dim": main_disagreement_dim
            },
            "quality_issues": quality_issues,
            "priority_suggestions": priority_suggestions,
            "export_readiness": {
                "ready": export_ready,
                "recommended_format": recommended_format,
                "checklist": export_checklist
            },
            "quality_policy_and_delivery": {
                "policy_version": "quality_policy_v1",
                "ai_pass_threshold": 80,
                "high_risk_rules": "AI 分数低于 70 或 risk_level = high",
                "must_review_rules": [
                    "AI / 人工不一致",
                    "被打回过",
                    "缺失关键字段",
                    "高争议 Rubric 命中",
                    "AI 低分或高风险"
                ],
                "exportable_count": exportable_count,
                "recommend_immediate_export": export_ready and ai_missing == 0,
                "pre_export_suggestions": export_checklist
            },
            "agent_overview": {
                "total_runs": len(agent_runs),
                "success_count": agent_success,
                "failed_count": agent_failed,
                "fallback_count": agent_fallback,
                "pending_count": agent_pending,
                "avg_latency_ms": agent_avg_latency,
                "model_mode": "mock"
            }
        },
        "sample_note": sample_note
    }


def _build_report_text(**kwargs) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("  AI 质量报告")
    lines.append(f"  生成来源: LabelHub AI Quality Agent")
    lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)
    lines.append("")

    lines.append("一、任务概况")
    lines.append("-" * 40)
    lines.append(f"  任务 ID: {kwargs['task_id']}")
    lines.append(f"  任务名称: {kwargs['task_name']}")
    lines.append(f"  总数据量: {kwargs['total_items']}")
    lines.append(f"  已提交数量: {kwargs['submitted_count']}")
    lines.append(f"  已预审数量: {kwargs['ai_reviewed_count']}")
    lines.append(f"  已审核数量: {kwargs['human_reviewed_count']}")
    lines.append(f"  可导出数量: {kwargs['exportable_count']}")
    lines.append("")

    lines.append("二、AI 预审概况")
    lines.append("-" * 40)
    avg = kwargs['ai_avg_score']
    lines.append(f"  平均分: {avg if avg is not None else '暂无数据'}")
    rd = kwargs['ai_risk_distribution']
    lines.append(f"  低风险: {rd.get('low', 0)}")
    lines.append(f"  中风险: {rd.get('medium', 0)}")
    lines.append(f"  高风险: {rd.get('high', 0)}")
    lines.append(f"  AI 建议提交: {kwargs['ai_pass_count']}")
    lines.append(f"  AI 建议打回: {kwargs['ai_reject_count']}")
    lines.append("")

    lines.append("三、人工审核概况")
    lines.append("-" * 40)
    lines.append(f"  人工通过: {kwargs['human_approve_count']}")
    lines.append(f"  人工打回: {kwargs['human_reject_count']}")
    lines.append(f"  人工修订: {kwargs['human_revise_count']}")
    lines.append(f"  通过率: {kwargs['human_pass_rate']:.0%}" if kwargs['human_pass_rate'] else "  通过率: 暂无数据")
    lines.append(f"  打回率: {kwargs['human_reject_rate']:.0%}" if kwargs['human_reject_rate'] else "  打回率: 暂无数据")
    lines.append("")

    lines.append("四、AI / 人工一致性")
    lines.append("-" * 40)
    lines.append(f"  一致数量: {kwargs['ai_human_agree']}")
    lines.append(f"  不一致数量: {kwargs['ai_human_total'] - kwargs['ai_human_agree']}")
    ar = kwargs['agreement_rate']
    lines.append(f"  一致率: {ar:.0%}" if ar is not None else "  一致率: 暂无数据")
    md = kwargs['main_disagreement_dim']
    dim_labels = {"relevance": "相关性", "accuracy": "准确性", "completeness": "完整性", "safety": "安全性"}
    lines.append(f"  主要不一致维度: {dim_labels.get(md, md) if md else '暂无数据'}")
    lines.append("")

    lines.append("五、主要质量问题")
    lines.append("-" * 40)
    qi = kwargs['quality_issues']
    if qi:
        for item in qi:
            severity_label = {"high": "严重", "medium": "中等", "low": "轻微"}.get(item["severity"], item["severity"])
            lines.append(f"  [{severity_label}] {item['issue']}: {item['count']}条")
    else:
        lines.append("  暂无显著质量问题")
    lines.append("")

    lines.append("六、重点复核建议")
    lines.append("-" * 40)
    ps = kwargs['priority_suggestions']
    if ps:
        for i, s in enumerate(ps, 1):
            lines.append(f"  {i}. {s}")
    else:
        lines.append("  暂无重点复核建议")
    lines.append("")

    lines.append("七、数据交付建议")
    lines.append("-" * 40)
    if kwargs['export_ready']:
        lines.append("  当前适合导出")
    else:
        lines.append("  当前不建议导出，请先处理上述问题")
    lines.append(f"  推荐导出格式: {kwargs['recommended_format'].upper()}")
    lines.append("  导出前检查项:")
    for item in kwargs['export_checklist']:
        lines.append(f"    - {item}")
    lines.append("")

    lines.append("八、质量策略与交付建议")
    lines.append("-" * 40)
    lines.append("  当前任务采用 quality_policy_v1，AI 分数 80 分以上且低风险样本可作为自动放行候选；")
    lines.append("  AI 低分、高风险、AI/人工不一致或曾被打回样本建议进入人工重点复核。")
    lines.append(f"  当前可导出数据: {kwargs.get('exportable_count_val', 0)} 条")
    ai_miss = kwargs.get('ai_missing', 0)
    if ai_miss > 0:
        lines.append(f"  建议在正式交付前补齐 {ai_miss} 条缺失 AI 预审结果的样本。")
    else:
        lines.append("  所有样本均已完成 AI 预审，建议可立即导出。")
    lines.append("")

    if kwargs['sample_note']:
        lines.append(f"备注: {kwargs['sample_note']}")
        lines.append("")

    lines.append("=" * 60)
    lines.append("  报告结束 - LabelHub AI Quality Agent")
    lines.append("=" * 60)

    return "\n".join(lines)


def _generate_default_rubrics() -> list:
    return [
        {"id": "rubric_relevance", "key": "rubric_relevance", "criterion": "相关性评估", "title": "相关性", "dimension": "relevance", "type": "objective", "priority": "must_have"},
        {"id": "rubric_accuracy", "key": "rubric_accuracy", "criterion": "准确性评估", "title": "准确性", "dimension": "accuracy", "type": "objective", "priority": "must_have"},
        {"id": "rubric_completeness", "key": "rubric_completeness", "criterion": "完整性评估", "title": "完整性", "dimension": "completeness", "type": "subjective", "priority": "must_have"},
        {"id": "rubric_safety", "key": "rubric_safety", "criterion": "安全性评估", "title": "安全性", "dimension": "safety", "type": "objective", "priority": "must_have"},
    ]


def _generate_default_rubric_stats() -> dict:
    stats = {}
    for rubric in _generate_default_rubrics():
        rid = rubric["id"]
        stats[rid] = {
            "rubric_id": rid,
            "rubric_name": rubric["title"],
            "dimension": rubric["dimension"],
            "type": rubric["type"],
            "priority": rubric["priority"],
            "human_met": 0,
            "human_not_met": 0,
            "human_uncertain": 0,
            "ai_suggested": 0,
            "ai_human_agree": 0,
            "ai_human_total": 0,
            "rejected_appearances": 0
        }
    return stats


QUALITY_POLICY_V1 = {
    "version": "quality_policy_v1",
    "ai_pass_threshold": 80,
    "high_risk_threshold": {
        "score_below": 70,
        "risk_level": "high"
    },
    "auto_suggestion_rules": [
        {
            "name": "建议提交",
            "condition": "score >= 80 且 risk_level = low",
            "action": "submit",
            "enabled": True
        },
        {
            "name": "建议复核",
            "condition": "70 <= score < 80 或 risk_level = medium",
            "action": "manual_review",
            "enabled": True
        },
        {
            "name": "建议打回",
            "condition": "score < 70 或 risk_level = high",
            "action": "rework",
            "enabled": True
        }
    ],
    "must_review_rules": [
        {"name": "AI / 人工不一致", "enabled": True},
        {"name": "被打回过", "enabled": True},
        {"name": "缺失关键字段", "enabled": True},
        {"name": "高争议 Rubric 命中", "enabled": True},
        {"name": "AI 低分或高风险", "enabled": True}
    ],
    "export_admission_rules": [
        {"name": "必须人工审核通过", "enabled": True},
        {"name": "必须无无效待审", "enabled": True},
        {"name": "建议包含 AI 预审结果", "enabled": True},
        {"name": "如缺失 AI 预审，需要在导出摘要中提示", "enabled": True}
    ]
}


def get_quality_policy(task_id: int) -> Dict[str, Any]:
    policy = {**QUALITY_POLICY_V1}
    policy["task_id"] = task_id
    policy["scope"] = "task"
    policy["note"] = "当前为任务级质量策略，使用默认配置"
    return policy


def compute_smart_review_strategy(db: Session, task_id: int) -> Dict[str, Any]:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"error": "Task not found"}

    annotations = get_annotations_by_filter(task_id=task_id)

    rubric_analysis = compute_rubric_analysis(db, task_id)
    high_dispute_dims = set()
    for r in rubric_analysis.get("rubrics", []):
        if r.get("is_high_dispute"):
            high_dispute_dims.add(r.get("dimension", ""))

    auto_pass_count = 0
    manual_review_count = 0
    rework_suggested_count = 0
    must_review_count = 0
    high_risk_count = 0
    ai_human_disagree_count = 0
    strategy_items = []

    for ann in annotations:
        status = ann.get("status", "")
        ai_review_raw = ann.get("ai_review")
        ai_review = normalize_ai_review(ai_review_raw) if ai_review_raw and isinstance(ai_review_raw, dict) else None
        result = ann.get("result") or ann.get("annotation_result") or ann.get("data") or {}
        review_info = ann.get("review_info") or {}

        ai_score = None
        ai_risk = None
        ai_suggested = None
        triggers = []
        strategy = "manual_review_required"
        suggested_action = "manual_review"

        if ai_review:
            ai_score = ai_review.get("overall_score")
            ai_risk = ai_review.get("risk_level")
            ai_suggested = ai_review.get("suggested_action")

            if isinstance(ai_score, (int, float)) and ai_score < 70:
                triggers.append("AI 分数低于阈值")
            if ai_risk == "high":
                triggers.append("AI 高风险")
                high_risk_count += 1

            suggestion = ai_review.get("suggestion") or {}
            if isinstance(result, dict):
                for dim in ["relevance", "accuracy", "completeness", "safety"]:
                    ai_val = suggestion.get(dim)
                    human_val = result.get(dim)
                    if ai_val and human_val and ai_val != human_val:
                        triggers.append(f"AI/人工不一致({dim})")
                        ai_human_disagree_count += 1
                        break

        if status in ("rejected_to_modify", "returned_to_modify", "needs_revision"):
            triggers.append("曾被打回")

        if isinstance(result, dict):
            missing = [f for f in ["relevance", "accuracy", "completeness", "safety", "reason"] if not result.get(f)]
            if len(missing) >= 2:
                triggers.append(f"关键字段缺失({','.join(missing[:3])})")

        if high_dispute_dims:
            triggers.append("高争议Rubric")

        human_action = review_info.get("action", "") if isinstance(review_info, dict) else ""

        if status in ("approved", "export_ready"):
            strategy = "export_ready"
            suggested_action = "export"
            if not triggers:
                auto_pass_count += 1
        elif triggers:
            must_review_count += 1
            if any(t in triggers for t in ["AI 分数低于阈值", "AI 高风险"]):
                strategy = "rework_suggested"
                suggested_action = "rework"
                rework_suggested_count += 1
            elif any(t in triggers for t in ["AI/人工不一致", "曾被打回", "关键字段缺失", "高争议Rubric"]):
                strategy = "manual_review_required"
                suggested_action = "manual_review"
                manual_review_count += 1
            else:
                strategy = "manual_review_required"
                suggested_action = "manual_review"
                manual_review_count += 1
        else:
            if ai_score is not None and ai_score >= 80 and ai_risk == "low":
                strategy = "auto_pass_candidate"
                suggested_action = "auto_pass"
                auto_pass_count += 1
            else:
                strategy = "manual_review_required"
                suggested_action = "manual_review"
                manual_review_count += 1

        if status in ("approved", "export_ready") and triggers:
            strategy = "blocked"
            suggested_action = "review_before_export"

        strategy_items.append({
            "submission_id": ann.get("id"),
            "task_id": ann.get("task_id", task_id),
            "dataset_item_id": ann.get("dataset_item_id"),
            "ai_score": ai_score,
            "risk_level": ai_risk,
            "human_status": status,
            "review_strategy": strategy,
            "trigger_reasons": triggers,
            "suggested_action": suggested_action
        })

    return {
        "task_id": task_id,
        "policy_version": QUALITY_POLICY_V1["version"],
        "summary": {
            "auto_pass_candidate": auto_pass_count,
            "manual_review_required": manual_review_count,
            "rework_suggested": rework_suggested_count,
            "must_review": must_review_count,
            "high_risk": high_risk_count,
            "ai_human_disagree": ai_human_disagree_count
        },
        "items": strategy_items,
        "total": len(strategy_items),
        "note": "AI 复核策略只辅助分流，最终审核由 Reviewer 决定"
    }
