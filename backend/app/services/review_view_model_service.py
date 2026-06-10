"""
审核详情统一投影层 ReviewDetailViewModel
将所有审核详情数据聚合为统一 DTO，前端直接消费，不再自行拼字段。
"""
import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ─── Normalize 字典 ───────────────────────────────────────────────────────────

MARGIN_NORMALIZE: Dict[str, str] = {
    "明显差异": "明显优于", "轻微差异": "略优于", "无差异": "相当",
    "明显优于": "明显优于", "略优于": "略优于", "相当": "相当",
    "large": "明显优于", "small": "略优于", "tie": "相当",
}

PREFERRED_NORMALIZE: Dict[str, str] = {
    "a": "A", "A": "A", "response_a": "A",
    "b": "B", "B": "B", "response_b": "B",
    "tie": "tie", "both": "tie", "equal": "tie", "两者相当": "tie",
}

SAFETY_FLAG_NORMALIZE: Dict[str, bool] = {
    "true": True, "是": True, "有风险": True, "risky": True,
    "false": False, "否": False, "safe": False, "无风险": False,
}


def normalize_margin(val: Any) -> Optional[str]:
    if val is None:
        return None
    return MARGIN_NORMALIZE.get(str(val).strip(), str(val).strip())


def normalize_preferred(val: Any) -> Optional[str]:
    if val is None:
        return None
    return PREFERRED_NORMALIZE.get(str(val).strip(), str(val).strip())


def normalize_safety_flag(val: Any) -> Optional[bool]:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("true", "1"):
        return True
    if s in ("false", "0"):
        return False
    return SAFETY_FLAG_NORMALIZE.get(str(val).strip(), None)


# ─── Diff Row Builder ─────────────────────────────────────────────────────────

def _make_diff_row(field: str, label: str, ai_val: Any, human_val: Any,
                   normalize_fn=None, explanation: str = "") -> Dict[str, Any]:
    # Handle array values specially
    if isinstance(ai_val, list) or isinstance(human_val, list):
        ai_list = sorted([str(x) for x in ai_val]) if isinstance(ai_val, list) and ai_val else None
        human_list = sorted([str(x) for x in human_val]) if isinstance(human_val, list) and human_val else None
        if ai_list is None and human_list is None:
            status = "both_missing"
        elif ai_list is None:
            status = "ai_missing"
        elif human_list is None:
            status = "human_missing"
        elif ai_list == human_list:
            status = "match"
        else:
            # Check partial overlap
            ai_set = set(ai_list)
            human_set = set(human_list)
            if ai_set & human_set:
                status = "mismatch"
                explanation = explanation or f"部分一致: 共同={sorted(ai_set & human_set)}"
            else:
                status = "mismatch"
        return {
            "field": field, "label": label,
            "ai_value": ai_list, "human_value": human_list,
            "status": status, "explanation": explanation,
        }

    if normalize_fn:
        ai_norm = normalize_fn(ai_val) if ai_val is not None else None
        human_norm = normalize_fn(human_val) if human_val is not None else None
    else:
        ai_norm = str(ai_val).strip() if ai_val is not None else None
        human_norm = str(human_val).strip() if human_val is not None else None

    if ai_norm is None and human_norm is None:
        status = "both_missing"
    elif ai_norm is None:
        status = "ai_missing"
    elif human_norm is None:
        status = "human_missing"
    elif ai_norm == human_norm:
        status = "match"
    else:
        status = "mismatch"

    return {
        "field": field,
        "label": label,
        "ai_value": ai_norm,
        "human_value": human_norm,
        "status": status,
        "explanation": explanation,
    }


def build_diff_rows_qa_quality(ai_output: Dict, human_result: Dict) -> List[Dict]:
    ai_suggestion = ai_output.get("suggestion") or {}
    ai_dims = ai_output.get("dimensions") or ai_output.get("dimension_scores") or {}

    def _ai_dim_val(dim):
        d = ai_dims.get(dim)
        if isinstance(d, dict):
            return d.get("label") or d.get("value")
        return d

    rows = [
        _make_diff_row("relevance", "相关性", _ai_dim_val("relevance"), human_result.get("relevance")),
        _make_diff_row("accuracy", "准确性", _ai_dim_val("accuracy"), human_result.get("accuracy")),
        _make_diff_row("completeness", "完整性", _ai_dim_val("completeness"), human_result.get("completeness")),
        _make_diff_row("safety", "安全性", _ai_dim_val("safety"), human_result.get("safety")),
        _make_diff_row("issue_tags", "问题标签",
                       ai_output.get("issue_tags") or ai_suggestion.get("issue_tags"),
                       human_result.get("issue_tags") or human_result.get("problem_tags")),
    ]
    # summary quality
    ai_summary = ai_output.get("summary", "")
    human_summary = human_result.get("summary") or human_result.get("reason") or human_result.get("detailed_comment") or ""
    rows.append(_make_diff_row("summary_quality", "理由充分性",
                               "有总结" if ai_summary else None,
                               "有理由" if human_summary else None,
                               explanation="AI 是否有总结 vs 人工是否填写理由"))
    return rows


def build_diff_rows_preference_compare(ai_output: Dict, human_result: Dict) -> List[Dict]:
    rows = [
        _make_diff_row("preferred", "偏好选择",
                       ai_output.get("preferred"),
                       human_result.get("preferred"),
                       normalize_fn=normalize_preferred),
        _make_diff_row("margin", "差异程度",
                       ai_output.get("margin"),
                       human_result.get("margin"),
                       normalize_fn=normalize_margin),
        _make_diff_row("dimensions", "判断维度",
                       ai_output.get("dimensions") or ai_output.get("pref_dimensions"),
                       human_result.get("dimensions"),
                       explanation="双方选择的判断维度是否一致"),
        _make_diff_row("safety_flag", "安全风险",
                       ai_output.get("safety_flag"),
                       human_result.get("safety_flag"),
                       normalize_fn=normalize_safety_flag),
    ]
    # annotator_note quality
    ai_note = ai_output.get("annotator_note") or ai_output.get("reason") or ""
    human_note = human_result.get("annotator_note") or human_result.get("reason") or ""
    note_quality = "充分" if len(human_note) >= 20 else ("过短" if human_note else "未填写")
    rows.append(_make_diff_row("annotator_note_quality", "理由充分性",
                               "AI已评估" if ai_note else None,
                               note_quality if human_note else None,
                               explanation=f"人工理由长度: {len(human_note)} 字符"))
    return rows


# ─── Rubric Row Builder ──────────────────────────────────────────────────────

def build_rubric_rows(task: Any, template_schema: Any, human_result: Dict,
                      ai_output: Dict) -> tuple:
    """返回 (rubric_rows, rubric_empty_state)"""
    # 1. 从 template schema 提取 rubric config
    rubric_config = []
    if template_schema:
        schema = template_schema.schema if hasattr(template_schema, 'schema') else (template_schema or {})
        if isinstance(schema, dict):
            rubric_config = schema.get("rubrics") or []
            # 也尝试从 fields 提取
            if not rubric_config:
                for f in (schema.get("fields") or []):
                    if f.get("type") in ("rubric", "rubric_group", "criteria"):
                        rubric_config.append(f)

    # 2. 人工 rubric evaluations
    human_rubric = human_result.get("_rubric") or human_result.get("rubric_judgements") or {}
    human_rubric_notes = human_result.get("_rubricNotes") or human_result.get("rubric_notes") or {}

    # 3. AI rubric hits
    ai_matched = ai_output.get("matched_rubrics") or []

    if not rubric_config and not human_rubric and not ai_matched:
        return [], "当前任务未配置 Rubric 规则。"

    rows = []
    # 以 rubric_config 为主键
    if rubric_config:
        for rc in rubric_config:
            rid = rc.get("id") or rc.get("rubric_id") or rc.get("key") or ""
            name = rc.get("name") or rc.get("label") or rc.get("criterion") or rid
            dimension = rc.get("dimension") or rc.get("dimensionLabel") or ""
            rtype = (rc.get("type") or "objective").lower()
            priority = (rc.get("priority") or "must_have").lower().replace(" ", "_")

            h_choice = human_rubric.get(str(rid)) or human_rubric.get(rid)
            h_note = human_rubric_notes.get(str(rid)) or human_rubric_notes.get(rid) or ""

            ai_match = None
            for m in ai_matched:
                if str(m.get("rubric_id")) == str(rid):
                    ai_match = m
                    break
            ai_choice = ai_match.get("ai_judgement") if ai_match else None
            ai_note = ""
            if ai_match:
                ev = ai_match.get("ai_evidence") or ai_match.get("evidence") or []
                ai_note = "; ".join(ev) if ev else ""

            if h_choice and ai_choice:
                status = "match" if str(h_choice).lower() == str(ai_choice).lower() else "mismatch"
            elif h_choice and not ai_choice:
                status = "ai_missing"
            elif ai_choice and not h_choice:
                status = "human_missing"
            else:
                status = "not_evaluated"

            rows.append({
                "rubric_id": str(rid),
                "name": name,
                "dimension": dimension,
                "type": rtype,
                "priority": priority,
                "human_choice": str(h_choice) if h_choice else None,
                "human_note": h_note,
                "ai_choice": str(ai_choice) if ai_choice else None,
                "ai_note": ai_note,
                "status": status,
            })
    else:
        # 没有 rubric_config，但有 human 或 AI 的 rubric 数据
        all_rids = set(list(human_rubric.keys()) + [str(m.get("rubric_id")) for m in ai_matched])
        for rid in sorted(all_rids):
            h_choice = human_rubric.get(rid)
            h_note = human_rubric_notes.get(rid) or ""
            ai_match = next((m for m in ai_matched if str(m.get("rubric_id")) == str(rid)), None)
            ai_choice = ai_match.get("ai_judgement") if ai_match else None
            ai_note = ""
            if ai_match:
                ev = ai_match.get("ai_evidence") or ai_match.get("evidence") or []
                ai_note = "; ".join(ev) if ev else ""
            if h_choice and ai_choice:
                status = "match" if str(h_choice).lower() == str(ai_choice).lower() else "mismatch"
            elif h_choice:
                status = "ai_missing"
            elif ai_choice:
                status = "human_missing"
            else:
                status = "not_evaluated"
            rows.append({
                "rubric_id": str(rid),
                "name": rid,
                "dimension": "",
                "type": "objective",
                "priority": "must_have",
                "human_choice": str(h_choice) if h_choice else None,
                "human_note": h_note,
                "ai_choice": str(ai_choice) if ai_choice else None,
                "ai_note": ai_note,
                "status": status,
            })

    empty_state = ""
    if rubric_config and not rows:
        empty_state = "任务已配置 Rubric，但本次提交未逐条评估。"
    elif rubric_config and all(r["status"] == "not_evaluated" for r in rows):
        empty_state = "任务已配置 Rubric，但本次提交未逐条评估。"

    return rows, empty_state


# ─── Main Builder ─────────────────────────────────────────────────────────────

def build_review_view_model(db: Session, submission_id: int) -> Optional[Dict[str, Any]]:
    """构建审核详情统一 DTO。"""
    from app.services.annotation_service import get_annotation_by_id
    from app.models.dataset_item import DatasetItem
    from app.models.task import Task
    from app.models.ai_review_run import AIReviewRun
    from app.models.template_schema import TemplateSchema

    annotation = get_annotation_by_id(submission_id)
    if not annotation:
        return None

    dataset_item_id = annotation.get("dataset_item_id")
    task_id = annotation.get("task_id")

    # ── Task ──
    task = db.query(Task).filter(Task.id == task_id).first() if task_id else None
    task_info = {}
    if task:
        task_info = {
            "id": task.id, "name": task.name, "source_namespace": task.source_namespace,
            "is_official_raw": task.is_official_raw, "template_id": task.template_id,
        }

    # ── Item ──
    item = db.query(DatasetItem).filter(DatasetItem.id == dataset_item_id).first() if dataset_item_id else None
    raw_data = {}
    if item and item.raw_data_json and isinstance(item.raw_data_json, dict):
        raw_data = item.raw_data_json

    dataset_type = (item.dataset_type if item and item.dataset_type
                    else raw_data.get("dataset_type", None))
    if not dataset_type:
        if task and "preference_compare" in (task.name or ""):
            dataset_type = "preference_compare"
        else:
            dataset_type = "qa_quality"
    official_id = (item.official_id if item else None) or raw_data.get("official_id") or ""

    # ── original_view ──
    if dataset_type == "preference_compare":
        original_fields = [
            {"key": "official_id", "label": "Official ID", "value": official_id},
            {"key": "prompt", "label": "用户问题", "value": raw_data.get("prompt") or raw_data.get("question") or ""},
            {"key": "response_a", "label": "回答 A", "value": raw_data.get("response_a") or ""},
            {"key": "response_b", "label": "回答 B", "value": raw_data.get("response_b") or ""},
            {"key": "model_a", "label": "模型 A", "value": raw_data.get("model_a") or ""},
            {"key": "model_b", "label": "模型 B", "value": raw_data.get("model_b") or ""},
            {"key": "task_type", "label": "任务类型", "value": raw_data.get("task_type") or ""},
            {"key": "lang", "label": "语言", "value": raw_data.get("lang") or "zh"},
        ]
    else:
        original_fields = [
            {"key": "official_id", "label": "Official ID", "value": official_id},
            {"key": "prompt", "label": "问题", "value": raw_data.get("prompt") or raw_data.get("question") or ""},
            {"key": "model_answer", "label": "模型回答", "value": raw_data.get("model_answer") or raw_data.get("answer") or ""},
            {"key": "reference", "label": "参考答案", "value": raw_data.get("reference") or raw_data.get("reference_answer") or ""},
            {"key": "category", "label": "类别", "value": raw_data.get("category") or ""},
            {"key": "difficulty", "label": "难度", "value": raw_data.get("difficulty") or ""},
            {"key": "lang", "label": "语言", "value": raw_data.get("lang") or "zh"},
            {"key": "media_type", "label": "媒体类型", "value": raw_data.get("media_type") or ""},
            {"key": "media_url", "label": "媒体链接", "value": raw_data.get("media_url") or ""},
            {"key": "content_markdown", "label": "正文", "value": raw_data.get("content_markdown") or ""},
            {"key": "expected_dimensions", "label": "重点维度", "value": raw_data.get("expected_dimensions") or []},
        ]
    original_view = {"title": f"{dataset_type} - {official_id}", "fields": original_fields}

    # ── human_view ──
    human_result = annotation.get("result") or annotation.get("annotation_result") or annotation.get("data") or {}
    if dataset_type == "preference_compare":
        human_display_fields = [
            {"key": "preferred", "label": "偏好选择", "value": human_result.get("preferred"),
             "empty_hint": "该字段未由标注员填写"},
            {"key": "margin", "label": "优势幅度", "value": human_result.get("margin"),
             "empty_hint": "该字段未由标注员填写"},
            {"key": "dimensions", "label": "判断维度", "value": human_result.get("dimensions"),
             "empty_hint": "该字段未由标注员填写"},
            {"key": "safety_flag", "label": "安全标记", "value": human_result.get("safety_flag"),
             "empty_hint": "该字段未由标注员填写"},
            {"key": "summary", "label": "摘要", "value": human_result.get("summary"),
             "empty_hint": "该字段未由标注员填写"},
            {"key": "annotator_note", "label": "标注理由", "value": human_result.get("annotator_note") or human_result.get("reason"),
             "empty_hint": "该字段未由标注员填写"},
            {"key": "revision_suggestion", "label": "修正建议", "value": human_result.get("revision_suggestion"),
             "empty_hint": "该字段未由标注员填写"},
        ]
        summary_cards = [
            {"label": "偏好", "value": human_result.get("preferred") or "-"},
            {"label": "幅度", "value": human_result.get("margin") or "-"},
            {"label": "安全", "value": "是" if human_result.get("safety_flag") else "否"},
        ]
    else:
        human_display_fields = [
            {"key": "relevance", "label": "相关性", "value": human_result.get("relevance") or human_result.get("relevance_answer")},
            {"key": "accuracy", "label": "准确性", "value": human_result.get("accuracy") or human_result.get("accuracy_answer")},
            {"key": "completeness", "label": "完整性", "value": human_result.get("completeness") or human_result.get("completeness_answer")},
            {"key": "safety", "label": "安全性", "value": human_result.get("safety") or human_result.get("safety_answer")},
            {"key": "issue_tags", "label": "问题标签", "value": human_result.get("issue_tags") or human_result.get("problem_tags")},
            {"key": "summary", "label": "摘要", "value": human_result.get("summary"),
             "empty_hint": "该字段未由标注员填写"},
            {"key": "reason", "label": "详细理由", "value": human_result.get("reason") or human_result.get("detailed_comment"),
             "empty_hint": "该字段未由标注员填写"},
            {"key": "revision_suggestion", "label": "修正建议", "value": human_result.get("revision_suggestion"),
             "empty_hint": "该字段未由标注员填写"},
        ]
        summary_cards = [
            {"label": "相关性", "value": human_result.get("relevance") or "-"},
            {"label": "准确性", "value": human_result.get("accuracy") or "-"},
            {"label": "完整性", "value": human_result.get("completeness") or "-"},
            {"label": "安全性", "value": human_result.get("safety") or "-"},
        ]

    human_view = {
        "summary_cards": summary_cards,
        "raw_result": human_result,
        "display_fields": human_display_fields,
    }

    # ── ai_view ──
    ai_view = None
    ai_run = None
    # 正式审核只看 auto_on_submit / manual_review_run，排除标注辅助
    REVIEW_TRIGGER_TYPES = {"auto_on_submit", "manual_review_run"}
    if task_id and dataset_item_id:
        try:
            # 取最新有效 run：只看正式审核 trigger
            all_runs = db.query(AIReviewRun).filter(
                AIReviewRun.task_id == task_id,
                AIReviewRun.item_id == dataset_item_id,
                AIReviewRun.trigger_type.in_(list(REVIEW_TRIGGER_TYPES)),
            ).order_by(AIReviewRun.id.desc()).all()

            for run in all_runs:
                # 跳过 wrong_prompt_profile 标记
                if run.status == "success" and run.error_message and "wrong_prompt_profile" in (run.error_message or ""):
                    continue
                # 验证 prompt_profile 与 dataset_type 匹配
                snap = run.input_snapshot_json or {}
                run_profile = snap.get("prompt_profile") or ""
                if dataset_type == "preference_compare" and "qa_quality" in run_profile:
                    continue  # 跳过 profile 不匹配的 run
                if dataset_type == "qa_quality" and "preference_compare" in run_profile:
                    continue
                if run.status in ("success", "failed", "fallback_required"):
                    ai_run = run
                    break

            if ai_run:
                ai_output = ai_run.output_json or {}
                input_snap = ai_run.input_snapshot_json or {}
                prompt_profile = input_snap.get("prompt_profile") or ""

                if dataset_type == "preference_compare":
                    ai_display_fields = [
                        {"key": "preferred", "label": "AI 偏好", "value": ai_output.get("preferred")},
                        {"key": "margin", "label": "AI 幅度", "value": ai_output.get("margin")},
                        {"key": "dimensions", "label": "AI 维度", "value": ai_output.get("dimensions") or ai_output.get("pref_dimensions")},
                        {"key": "safety_flag", "label": "AI 安全标记", "value": ai_output.get("safety_flag")},
                        {"key": "summary", "label": "总结", "value": ai_output.get("summary")},
                        {"key": "reason", "label": "判断依据", "value": ai_output.get("reason") or ai_output.get("annotator_note")},
                    ]
                else:
                    dims = ai_output.get("dimension_scores") or ai_output.get("dimensions") or {}
                    ai_display_fields = [
                        {"key": "relevance", "label": "相关性", "value": dims.get("relevance")},
                        {"key": "accuracy", "label": "准确性", "value": dims.get("accuracy")},
                        {"key": "completeness", "label": "完整性", "value": dims.get("completeness")},
                        {"key": "safety", "label": "安全性", "value": dims.get("safety")},
                        {"key": "summary", "label": "总结", "value": ai_output.get("summary")},
                        {"key": "issue_tags", "label": "问题标签", "value": ai_output.get("issue_tags")},
                    ]

                action_map = {"submit": "approve", "approve": "approve", "reject": "revise", "rework": "revise", "manual_review": "manual_review"}
                raw_action = action_map.get(ai_run.suggestion_action or "", ai_run.suggestion_action or "manual_review")

                # ── 规则化决策 Policy ──
                from app.services.review_decision import derive_review_decision
                gold_payload = None
                if item and item.gold_payload:
                    gold_payload = item.gold_payload if isinstance(item.gold_payload, dict) else None
                context_for_policy = {}
                if dataset_type == "preference_compare":
                    context_for_policy = {
                        "prompt": raw_data.get("prompt") or raw_data.get("question") or "",
                        "response_a": raw_data.get("response_a") or "",
                        "response_b": raw_data.get("response_b") or "",
                    }
                policy = derive_review_decision(
                    dataset_type=dataset_type,
                    ai_result=ai_output,
                    human_result=human_result,
                    gold_result=gold_payload,
                    context=context_for_policy,
                )

                ai_view = {
                    "run_id": ai_run.id,
                    "status": ai_run.status,
                    "score": ai_run.score,
                    # Policy 覆盖模型自报
                    "decision": policy["decision"],
                    "risk_level": policy["risk_level"],
                    "confidence_level": policy["confidence_level"],
                    "action": policy["decision"],
                    "blocking_reasons": policy["blocking_reasons"],
                    "warning_reasons": policy["warning_reasons"],
                    "display_summary": policy["display_summary"],
                    "debug_score": policy["debug_score"],
                    "prompt_profile": prompt_profile,
                    "confidence": ai_run.confidence,
                    "model_provider": ai_run.model_provider,
                    "model_name": ai_run.model_name,
                    "latency_ms": ai_run.latency_ms,
                    "used_fallback": bool(ai_run.used_fallback),
                    "normalized_result": ai_output,
                    "display_fields": ai_display_fields,
                    "summary": ai_output.get("summary", ""),
                    "issue_tags": ai_output.get("issue_tags", []),
                    "matched_rubrics": ai_output.get("matched_rubrics", []),
                }

                # ── Gold 对比结论 ──
                if gold_payload and dataset_type == "preference_compare":
                    gold_pref = normalize_preferred(gold_payload.get("preferred"))
                    human_pref = normalize_preferred(human_result.get("preferred"))
                    ai_pref = normalize_preferred(ai_output.get("preferred"))
                    gold_conclusion_parts = []
                    if human_pref == gold_pref and ai_pref == gold_pref:
                        gold_conclusion = "人工命中，AI 命中"
                    elif human_pref != gold_pref and ai_pref == gold_pref:
                        gold_conclusion = "人工与 Gold 不一致，AI 与 Gold 一致，建议复核或返修"
                    elif human_pref == gold_pref and ai_pref != gold_pref:
                        gold_conclusion = "人工命中，AI 与 Gold 不一致"
                    else:
                        gold_conclusion = "人工与 Gold 不一致，AI 与 Gold 不一致，需要人工复核"
                    ai_view["gold_comparison"] = {
                        "gold_preferred": gold_pref,
                        "human_preferred": human_pref,
                        "ai_preferred": ai_pref,
                        "gold_margin": normalize_margin(gold_payload.get("margin")),
                        "human_margin": normalize_margin(human_result.get("margin")),
                        "ai_margin": normalize_margin(ai_output.get("margin")),
                        "conclusion": gold_conclusion,
                        "available": True,
                    }
        except Exception as e:
            logger.error(f"[build_review_view_model] AI run lookup failed: {e}")

    # ── diff_rows ──
    ai_output_for_diff = (ai_view or {}).get("normalized_result") or {}
    if dataset_type == "preference_compare":
        diff_rows = build_diff_rows_preference_compare(ai_output_for_diff, human_result)
    else:
        diff_rows = build_diff_rows_qa_quality(ai_output_for_diff, human_result)

    # ── rubric_rows ──
    template_schema = None
    if task and task.template_id:
        template_schema = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()
    rubric_rows, rubric_empty_state = build_rubric_rows(task, template_schema, human_result, ai_output_for_diff)

    # ── gold_view ──
    gold_view = None
    if item and item.gold_payload:
        gold_view = {
            "available": True,
            "note": "Gold 参考答案仅供管理员查看",
            "payload": item.gold_payload,
        }

    # ── annotation metadata ──
    annotation_meta = {
        "id": annotation.get("id"),
        "status": annotation.get("status"),
        "task_id": task_id,
        "dataset_item_id": dataset_item_id,
        "labeler_id": annotation.get("labeler_id"),
        "work_key": annotation.get("work_key") or (f"{task_id}:{dataset_item_id}:{annotation.get('labeler_id', 2)}" if task_id else None),
        "is_invalid": annotation.get("is_invalid", False) or annotation.get("status") in ("invalid_submitted", "invalid_approved"),
        "invalid_reason": annotation.get("invalid_reason"),
        "invalid_remark": annotation.get("invalid_remark"),
        "ai_review_source": "agent_run" if ai_run else None,
    }

    return {
        "task": task_info,
        "item": {
            "id": item.id if item else None,
            "task_id": task_id,
            "dataset_type": dataset_type,
            "official_id": official_id,
        },
        "dataset_type": dataset_type,
        "official_id": official_id,
        "annotation": annotation_meta,
        "original_view": original_view,
        "human_view": human_view,
        "ai_view": ai_view,
        "diff_rows": diff_rows,
        "rubric_rows": rubric_rows,
        "rubric_empty_state": rubric_empty_state,
        "timeline": [],  # 前端单独请求 timeline 接口
        "gold_view": gold_view,
    }
