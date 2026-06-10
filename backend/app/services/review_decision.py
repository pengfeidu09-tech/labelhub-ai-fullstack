"""
审核决策推导模块 (Review Decision Derivation)

纯规则策略函数，不依赖任何数据库模型或 Web 框架。
根据 AI 预审结果、人工标注结果、Gold 标准答案以及上下文信息，
推导出审核建议（approve / manual_review / revise）及风险等级。

支持的数据集类型:
  - preference_compare: 偏好对比类标注
  - qa_quality: 问答质量类标注
"""

from typing import Optional


# ---------------------------------------------------------------------------
#  常量 / 关键词表
# ---------------------------------------------------------------------------

# 严重问题关键词 —— 出现在 AI reason 或 issue_tags 中时，直接触发返修
_CRITICAL_KEYWORDS = [
    "事实性错误",
    "accuracy_error",
    "语义错误",
    "翻译错误",
    "translation_error",
    "cultural_misinterpretation",
    "严重安全问题",
    "safety_violation",
    "答案明显错误",
]

# 需要人工复核的关键词 —— 出现在 AI reason 中时触发 manual_review
_REVIEW_KEYWORDS = [
    "可能存在错误",
    "信息不足",
    "需核验",
    "翻译不自然",
    "文化误解",
]

# 重大 issue_tag —— 用于 approve 门禁检查
_MAJOR_ISSUE_TAGS = {
    "accuracy_error",
    "safety_violation",
    "factual_error",
    "cultural_misinterpretation",
    "translation_error",
}

# preferred 归一化映射
_PREFERRED_MAP = {
    "a": "A",
    "b": "B",
    "response_a": "A",
    "response_b": "B",
    "tie": "tie",
    "both": "tie",
    "equal": "tie",
    "两者相当": "tie",
    # 已经是标准值的情况
    "A": "A",
    "B": "B",
}

# margin 归一化映射
_MARGIN_MAP = {
    "明显差异": "明显优于",
    "轻微差异": "略优于",
    "无差异": "相当",
    "large": "明显优于",
    "small": "略优于",
    "tie": "相当",
    # 已经是标准值的情况
    "明显优于": "明显优于",
    "略优于": "略优于",
    "相当": "相当",
}

# margin 有序等级，用于判断"非常接近"
_MARGIN_RANK = {
    "明显优于": 2,
    "略优于": 1,
    "相当": 0,
}


# ---------------------------------------------------------------------------
#  工具函数
# ---------------------------------------------------------------------------

def _safe_str(val) -> str:
    """将任意值安全转换为字符串，None 返回空串。"""
    if val is None:
        return ""
    return str(val).strip()


def _safe_get(d: dict, *keys, default=None):
    """
    安全地从嵌套字典中取值。
    示例: _safe_get(d, "a", "b", "c") 等价于 d.get("a", {}).get("b", {}).get("c")
    """
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is None:
            return default
    return current


def _normalize_preferred(val) -> Optional[str]:
    """
    归一化 preferred 字段。
    a → A, b → B, tie/both/equal/两者相当 → tie, None → None
    """
    if val is None:
        return None
    key = _safe_str(val)
    if not key:
        return None
    return _PREFERRED_MAP.get(key, key)


def _normalize_margin(val) -> Optional[str]:
    """
    归一化 margin 字段。
    明显差异 → 明显优于, 轻微差异 → 略优于, 无差异 → 相当, 等等。
    """
    if val is None:
        return None
    key = _safe_str(val)
    if not key:
        return None
    return _MARGIN_MAP.get(key, key)


def _margin_close(margin_a: Optional[str], margin_b: Optional[str]) -> bool:
    """
    判断两个归一化后的 margin 是否"非常接近"（差值 <= 1 级）。
    如果任一为 None，视为无法比较，返回 False。
    """
    if margin_a is None or margin_b is None:
        return False
    rank_a = _MARGIN_RANK.get(margin_a)
    rank_b = _MARGIN_RANK.get(margin_b)
    if rank_a is None or rank_b is None:
        # 未知标签时退化为严格相等比较
        return margin_a == margin_b
    return abs(rank_a - rank_b) <= 1


def _count_chinese_chars(text: str) -> int:
    """统计字符串中的中文字符数量（CJK 统一汉字范围）。"""
    if not text:
        return 0
    return sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')


def _contains_any_keyword(haystack: str, keywords: list) -> bool:
    """检查 haystack 是否包含 keywords 列表中的任意一个关键词。"""
    if not haystack:
        return False
    haystack_lower = haystack.lower()
    for kw in keywords:
        if kw.lower() in haystack_lower:
            return True
    return False


def _join_tags_for_search(issue_tags) -> str:
    """将 issue_tags（列表或字符串）拼接成一个用于关键词搜索的字符串。"""
    if isinstance(issue_tags, list):
        return " ".join(str(t) for t in issue_tags)
    return _safe_str(issue_tags)


def _preferred_label(val: Optional[str]) -> str:
    """将归一化后的 preferred 值转为中文展示标签。"""
    mapping = {"A": "A", "B": "B", "tie": "tie（平局）"}
    if val is None:
        return "未知"
    return mapping.get(val, str(val))


def _margin_label(val: Optional[str]) -> str:
    """将归一化后的 margin 值转为中文展示标签。"""
    if val is None:
        return "未知"
    return str(val)


def _build_result(
    decision: str,
    risk_level: str,
    confidence_level: str,
    blocking_reasons: list,
    warning_reasons: list,
    display_summary: str,
    debug_score=None,
) -> dict:
    """构造标准返回值字典。"""
    return {
        "decision": decision,
        "risk_level": risk_level,
        "confidence_level": confidence_level,
        "blocking_reasons": list(blocking_reasons),
        "warning_reasons": list(warning_reasons),
        "display_summary": display_summary,
        "debug_score": debug_score,
    }


# ---------------------------------------------------------------------------
#  preference_compare 决策逻辑
# ---------------------------------------------------------------------------

def _decide_preference_compare(
    ai_result: dict,
    human_result: dict,
    gold_result: dict,
    context: dict,
) -> dict:
    """
    偏好对比类数据的审核决策推导。

    ai_result   示例: {"preferred": "A", "margin": "明显差异", "reason": "...",
                       "issue_tags": [...], "confidence": 0.85, "overall_score": 72,
                       "safety_flag": "safe"}
    human_result 示例: {"preferred": "A", "margin": "轻微差异", "annotator_note": "...",
                       "dimensions": [...], "safety_flag": "safe"}
    gold_result  示例: {"preferred": "A", "margin": "明显优于"}  (可选)
    context      示例: {"response_a": "...", "response_b": "...", "prompt": "..."}
    """

    ai = ai_result or {}
    human = human_result or {}
    gold = gold_result or {}
    ctx = context or {}

    # ---- 提取并归一化关键字段 ----
    ai_preferred = _normalize_preferred(ai.get("preferred"))
    human_preferred = _normalize_preferred(human.get("preferred"))
    gold_preferred = _normalize_preferred(gold.get("preferred")) if gold else None

    ai_margin = _normalize_margin(ai.get("margin"))
    human_margin = _normalize_margin(human.get("margin"))
    gold_margin = _normalize_margin(gold.get("margin")) if gold else None

    ai_reason = _safe_str(ai.get("reason"))
    ai_issue_tags = ai.get("issue_tags") or []
    ai_confidence = ai.get("confidence")
    if ai_confidence is not None:
        try:
            ai_confidence = float(ai_confidence)
        except (ValueError, TypeError):
            ai_confidence = None

    ai_overall_score = ai.get("overall_score")
    if ai_overall_score is not None:
        try:
            ai_overall_score = int(ai_overall_score)
        except (ValueError, TypeError):
            ai_overall_score = None

    ai_safety = _safe_str(ai.get("safety_flag"))
    human_safety = _safe_str(human.get("safety_flag"))

    annotator_note = _safe_str(human.get("annotator_note"))
    dimensions = human.get("dimensions")

    # 拼接 AI reason + issue_tags 用于关键词检索
    tags_text = _join_tags_for_search(ai_issue_tags)
    combined_ai_text = f"{ai_reason} {tags_text}"

    # ---- 收集阻断原因(blocking)和警告原因(warning) ----
    blocking_reasons = []
    warning_reasons = []

    # ========== 强制返修 / 高风险检查 ==========

    # 规则 1: response_a 或 response_b 为空（仅在 context 提供了该字段时才检查）
    if ctx and "response_a" in ctx:
        response_a = _safe_str(ctx.get("response_a"))
        if not response_a:
            blocking_reasons.append("response_a 为空，无法进行偏好对比")
    if ctx and "response_b" in ctx:
        response_b = _safe_str(ctx.get("response_b"))
        if not response_b:
            blocking_reasons.append("response_b 为空，无法进行偏好对比")

    # 规则 2: prompt 为空（仅在 context 提供了 prompt 字段时才检查）
    if ctx and "prompt" in ctx:
        prompt_text = _safe_str(ctx.get("prompt"))
        if not prompt_text:
            blocking_reasons.append("prompt 为空，缺少评估所需的原始问题")

    # 规则 3: AI reason / issue_tags 包含严重关键词
    has_critical_keyword = _contains_any_keyword(combined_ai_text, _CRITICAL_KEYWORDS)
    if has_critical_keyword:
        # 找出具体命中的关键词，拼入原因
        hit_keywords = [kw for kw in _CRITICAL_KEYWORDS if kw.lower() in combined_ai_text.lower()]
        blocking_reasons.append(
            f"AI 标注中包含严重问题关键词：{', '.join(hit_keywords[:3])}"
        )

    # 规则 4: 人工 preferred 与 Gold preferred 冲突，且 annotator_note 过短或缺失
    human_gold_conflict = False
    if gold and gold_preferred is not None and human_preferred is not None:
        if human_preferred != gold_preferred:
            human_gold_conflict = True
            note_insufficient = len(annotator_note) < 15
            if note_insufficient:
                blocking_reasons.append(
                    f"人工选择 {_preferred_label(human_preferred)} 与 Gold "
                    f"{_preferred_label(gold_preferred)} 不一致，"
                    f"且标注备注不足 15 字（当前 {len(annotator_note)} 字），缺少充分理由"
                )

    # 规则 5: AI preferred != human preferred 且 AI confidence >= 0.8
    ai_human_high_conf_disagree = False
    if ai_preferred is not None and human_preferred is not None:
        if ai_preferred != human_preferred:
            if ai_confidence is not None and ai_confidence >= 0.8:
                ai_human_high_conf_disagree = True
                blocking_reasons.append(
                    f"AI 判断 {_preferred_label(ai_preferred)}（置信度 {ai_confidence:.0%}），"
                    f"但人工选择 {_preferred_label(human_preferred)}，高置信度不一致"
                )

    # 如果存在任何 blocking 原因，直接返回 revise / high
    if blocking_reasons:
        summary_parts = ["建议返修："]
        summary_parts.append("；".join(blocking_reasons[:3]))
        return _build_result(
            decision="revise",
            risk_level="high",
            confidence_level="high" if len(blocking_reasons) >= 2 else "medium",
            blocking_reasons=blocking_reasons,
            warning_reasons=[],
            display_summary="".join(summary_parts),
            debug_score=ai_overall_score,
        )

    # ========== 强制人工复核 / 中风险检查 ==========

    # 规则 1: AI preferred != human preferred（任意置信度）
    ai_human_disagree = False
    if ai_preferred is not None and human_preferred is not None:
        if ai_preferred != human_preferred:
            ai_human_disagree = True
            warning_reasons.append(
                f"AI 偏好 {_preferred_label(ai_preferred)} 与人工 "
                f"{_preferred_label(human_preferred)} 不一致"
            )

    # 规则 2: AI preferred != Gold preferred
    ai_gold_disagree = False
    if gold and gold_preferred is not None and ai_preferred is not None:
        if ai_preferred != gold_preferred:
            ai_gold_disagree = True
            warning_reasons.append(
                f"AI 偏好 {_preferred_label(ai_preferred)} 与 Gold "
                f"{_preferred_label(gold_preferred)} 不一致"
            )

    # 规则 3: human preferred != Gold preferred（无短 note 的情况下也会触发 warning）
    if gold and gold_preferred is not None and human_preferred is not None:
        if human_preferred != gold_preferred and not human_gold_conflict:
            warning_reasons.append(
                f"人工选择 {_preferred_label(human_preferred)} 与 Gold "
                f"{_preferred_label(gold_preferred)} 不一致"
            )

    # 规则 4: margin 归一化后不匹配
    margin_mismatch = False
    if human_margin is not None:
        # 比较 human margin 与 AI margin
        if ai_margin is not None and human_margin != ai_margin and not _margin_close(human_margin, ai_margin):
            margin_mismatch = True
            warning_reasons.append(
                f"margin 不一致：人工 {_margin_label(human_margin)}，"
                f"AI {_margin_label(ai_margin)}"
            )
        # 比较 human margin 与 Gold margin
        if gold_margin is not None and human_margin != gold_margin and not _margin_close(human_margin, gold_margin):
            if not margin_mismatch:
                margin_mismatch = True
            warning_reasons.append(
                f"margin 与 Gold 不一致：人工 {_margin_label(human_margin)}，"
                f"Gold {_margin_label(gold_margin)}"
            )

    # 规则 5: dimensions 缺失或仅有一个弱条目
    dimensions_weak = False
    if dimensions is None:
        dimensions_weak = True
        warning_reasons.append("dimensions 字段缺失")
    elif isinstance(dimensions, list):
        if len(dimensions) == 0:
            dimensions_weak = True
            warning_reasons.append("dimensions 为空列表")
        elif len(dimensions) == 1:
            # 单个条目且内容较弱（没有 score 或 reason 为空）
            single = dimensions[0] if isinstance(dimensions[0], dict) else {}
            if not single.get("reason") and not single.get("score"):
                dimensions_weak = True
                warning_reasons.append("dimensions 仅有一个弱条目（缺少 score 或 reason）")

    # 规则 6: annotator_note 少于 15 个中文字符
    note_short = False
    if len(annotator_note) < 15:
        note_short = True
        warning_reasons.append(
            f"标注备注过短（{len(annotator_note)} 字），建议至少 15 字以上"
        )

    # 规则 7: AI reason 包含需复核关键词
    has_review_keyword = _contains_any_keyword(ai_reason, _REVIEW_KEYWORDS)
    if has_review_keyword:
        hit_kws = [kw for kw in _REVIEW_KEYWORDS if kw in ai_reason]
        warning_reasons.append(
            f"AI 理由中包含需关注表述：{', '.join(hit_kws[:3])}"
        )

    # 如果存在任何 warning 原因，返回 manual_review / medium
    if warning_reasons:
        # 构造摘要
        summary = _build_review_summary(
            ai_preferred, human_preferred, gold_preferred,
            ai_margin, human_margin, gold_margin,
            ai_human_disagree, ai_gold_disagree, human_gold_conflict,
            margin_mismatch, note_short, has_review_keyword,
            ai_reason, gold,
        )
        return _build_result(
            decision="manual_review",
            risk_level="medium",
            confidence_level="medium",
            blocking_reasons=[],
            warning_reasons=warning_reasons,
            display_summary=summary,
            debug_score=ai_overall_score,
        )

    # ========== approve / 低风险评估 ==========
    # 必须同时满足全部条件才可放行

    approve_ok = True
    approve_blockers = []

    # 条件 1: AI preferred == human preferred
    if ai_preferred is None or human_preferred is None or ai_preferred != human_preferred:
        approve_ok = False
        approve_blockers.append("AI 与人工偏好不一致")

    # 条件 2: 如果存在 Gold，human preferred == Gold preferred
    if gold and gold_preferred is not None:
        if human_preferred is None or human_preferred != gold_preferred:
            approve_ok = False
            approve_blockers.append("人工与 Gold 偏好不一致")

    # 条件 3: margin 归一化匹配或非常接近
    if ai_margin is not None and human_margin is not None:
        if human_margin != ai_margin and not _margin_close(human_margin, ai_margin):
            approve_ok = False
            approve_blockers.append("margin 差异较大")
    # 如果 AI 或 human margin 都为 None，不阻断（容忍缺失）

    # 条件 4: safety_flag 不是 risky
    if ai_safety.lower() in ("risky", "unsafe", "high"):
        approve_ok = False
        approve_blockers.append("AI 安全标记为高风险")
    if human_safety.lower() in ("risky", "unsafe", "high"):
        approve_ok = False
        approve_blockers.append("人工安全标记为高风险")

    # 条件 5: annotator_note 充分 (>= 15 字符) 或包含具体推理
    has_concrete_reasoning = False
    if annotator_note:
        # 包含因果/对比/理由等关键词视为有具体推理
        reasoning_signals = ["因为", "所以", "由于", "因此", "但", "然而", "理由", "原因", "优于", "更好"]
        has_concrete_reasoning = any(sig in annotator_note for sig in reasoning_signals)
    if len(annotator_note) < 15 and not has_concrete_reasoning:
        approve_ok = False
        approve_blockers.append("标注备注不充分（少于 15 字且无具体推理）")

    # 条件 6: AI 没有重大 issue_tag
    if isinstance(ai_issue_tags, list):
        major_hits = [t for t in ai_issue_tags if str(t).strip() in _MAJOR_ISSUE_TAGS]
    else:
        major_hits = []
    if major_hits:
        approve_ok = False
        approve_blockers.append(f"AI 存在重大 issue_tag：{', '.join(str(t) for t in major_hits)}")

    # 条件 7: 必填字段已填写
    required_ai_fields = ["preferred"]
    required_human_fields = ["preferred"]
    for f in required_ai_fields:
        if not ai.get(f):
            approve_ok = False
            approve_blockers.append(f"AI 结果缺少必填字段：{f}")
    for f in required_human_fields:
        if not human.get(f):
            approve_ok = False
            approve_blockers.append(f"人工结果缺少必填字段：{f}")

    if not approve_ok:
        # 无法放行，降级为 manual_review
        summary = _build_review_summary(
            ai_preferred, human_preferred, gold_preferred,
            ai_margin, human_margin, gold_margin,
            ai_human_disagree, ai_gold_disagree, human_gold_conflict,
            margin_mismatch, note_short, has_review_keyword,
            ai_reason, gold,
            extra_notes=approve_blockers,
        )
        return _build_result(
            decision="manual_review",
            risk_level="medium",
            confidence_level="low",
            blocking_reasons=approve_blockers,
            warning_reasons=[],
            display_summary=summary,
            debug_score=ai_overall_score,
        )

    # ---- 全部通过，approve ----
    gold_hit_text = "，Gold 命中" if (gold and gold_preferred is not None and human_preferred == gold_preferred) else ""
    summary = f"建议通过：AI 与人工判断一致{gold_hit_text}，风险低"

    return _build_result(
        decision="approve",
        risk_level="low",
        confidence_level="high",
        blocking_reasons=[],
        warning_reasons=[],
        display_summary=summary,
        debug_score=ai_overall_score,
    )


def _build_review_summary(
    ai_preferred, human_preferred, gold_preferred,
    ai_margin, human_margin, gold_margin,
    ai_human_disagree, ai_gold_disagree, human_gold_conflict,
    margin_mismatch, note_short, has_review_keyword,
    ai_reason, gold,
    extra_notes=None,
) -> str:
    """
    为 manual_review / revise 场景生成人类可读的中文摘要。
    """
    parts = ["建议复核："]
    details = []

    if ai_human_disagree:
        detail = (
            f"AI 偏好 {_preferred_label(ai_preferred)}，"
            f"人工选择 {_preferred_label(human_preferred)}，需人工复核"
        )
        # 追加 margin 信息
        if ai_margin:
            detail += f"（AI margin: {_margin_label(ai_margin)}）"
        details.append(detail)

    if ai_gold_disagree and gold:
        details.append(
            f"AI 偏好 {_preferred_label(ai_preferred)} 与 Gold "
            f"{_preferred_label(gold_preferred)} 不一致"
        )

    if human_gold_conflict and gold:
        details.append(
            f"Gold 为 {_preferred_label(gold_preferred)}，"
            f"与人工 {_preferred_label(human_preferred)} 不一致"
        )

    if margin_mismatch:
        details.append(
            f"margin 差异：人工 {_margin_label(human_margin)}，"
            f"AI {_margin_label(ai_margin)}"
            + (f"，Gold {_margin_label(gold_margin)}" if gold_margin else "")
        )

    if note_short:
        details.append("标注备注过短")

    if has_review_keyword:
        details.append("AI 理由中包含需关注表述")

    if extra_notes:
        details.extend(extra_notes)

    # 如果 AI reason 提到了具体问题（事实性/翻译等），追加到摘要
    if ai_reason:
        issue_hints = []
        for kw in ["事实性", "翻译", "语义", "安全", "accuracy", "translation"]:
            if kw.lower() in ai_reason.lower():
                issue_hints.append(kw)
        if issue_hints:
            details.append(f"AI 指出回答存在{'/'.join(issue_hints[:2])}问题")

    if not details:
        details.append("存在需关注的差异项，建议人工复核")

    parts.append("；".join(details[:4]))  # 最多展示 4 条
    return "".join(parts)


# ---------------------------------------------------------------------------
#  qa_quality 决策逻辑
# ---------------------------------------------------------------------------

def _decide_qa_quality(
    ai_result: dict,
    human_result: dict,
    gold_result: dict,
    context: dict,
) -> dict:
    """
    问答质量类数据的审核决策推导（基于分数的简化规则）。

    ai_result   示例: {"overall_score": 85, "risk_level": "low",
                       "issue_tags": [...], "reason": "..."}
    human_result 示例: {"quality_pass": true, "annotator_note": "..."}
    gold_result  示例: {"expected_answer": "..."}  (可选)
    """

    ai = ai_result or {}
    human = human_result or {}

    # ---- 提取关键字段 ----
    overall_score = ai.get("overall_score")
    if overall_score is not None:
        try:
            overall_score = int(overall_score)
        except (ValueError, TypeError):
            overall_score = None

    ai_risk = _safe_str(ai.get("risk_level")).lower()
    ai_issue_tags = ai.get("issue_tags") or []
    ai_reason = _safe_str(ai.get("reason"))
    tags_text = _join_tags_for_search(ai_issue_tags)
    combined_text = f"{ai_reason} {tags_text}"

    blocking_reasons = []
    warning_reasons = []

    # ========== 强制返修 / 高风险 ==========

    # 规则 1: overall_score < 50
    if overall_score is not None and overall_score < 50:
        blocking_reasons.append(f"AI 评分过低（{overall_score} 分），低于 50 分阈值")

    # 规则 2: AI risk_level 为 high
    if ai_risk == "high":
        blocking_reasons.append("AI 风险等级为 high")

    if blocking_reasons:
        summary = f"建议返修：{'；'.join(blocking_reasons)}"
        return _build_result(
            decision="revise",
            risk_level="high",
            confidence_level="high",
            blocking_reasons=blocking_reasons,
            warning_reasons=[],
            display_summary=summary,
            debug_score=overall_score,
        )

    # ========== 强制人工复核 / 中风险 ==========

    # 规则 1: score < 70
    if overall_score is not None and overall_score < 70:
        warning_reasons.append(f"AI 评分偏低（{overall_score} 分），处于 50~70 区间")

    # 规则 2: risk_level 为 medium
    if ai_risk == "medium":
        warning_reasons.append("AI 风险等级为 medium")

    # 规则 3: issue_tags 包含严重问题
    has_serious_tag = _contains_any_keyword(combined_text, _CRITICAL_KEYWORDS)
    if has_serious_tag:
        hit_kws = [kw for kw in _CRITICAL_KEYWORDS if kw.lower() in combined_text.lower()]
        warning_reasons.append(
            f"AI issue_tags 中包含严重问题标签：{', '.join(hit_kws[:3])}"
        )

    # 额外：检查是否有需关注关键词
    has_review_kw = _contains_any_keyword(ai_reason, _REVIEW_KEYWORDS)
    if has_review_kw:
        hit_kws = [kw for kw in _REVIEW_KEYWORDS if kw in ai_reason]
        warning_reasons.append(
            f"AI 理由中包含需关注表述：{', '.join(hit_kws[:3])}"
        )

    if warning_reasons:
        summary = f"建议复核：{'；'.join(warning_reasons[:3])}"
        return _build_result(
            decision="manual_review",
            risk_level="medium",
            confidence_level="medium",
            blocking_reasons=[],
            warning_reasons=warning_reasons,
            display_summary=summary,
            debug_score=overall_score,
        )

    # ========== approve / 低风险 ==========
    # 条件：score >= 80 且 risk_level 为 low 且无重大问题

    approve_blockers = []

    # 分数检查
    if overall_score is None:
        approve_blockers.append("AI 未提供 overall_score")
    elif overall_score < 80:
        approve_blockers.append(f"AI 评分 {overall_score} 分，未达到 80 分自动通过阈值")

    # 风险检查
    if ai_risk and ai_risk != "low":
        approve_blockers.append(f"AI 风险等级为 {ai_risk}，非 low")

    # 重大 issue_tag 检查
    if isinstance(ai_issue_tags, list):
        major_hits = [t for t in ai_issue_tags if str(t).strip() in _MAJOR_ISSUE_TAGS]
    else:
        major_hits = []
    if major_hits:
        approve_blockers.append(
            f"存在重大 issue_tag：{', '.join(str(t) for t in major_hits)}"
        )

    if approve_blockers:
        summary = f"建议复核：{'；'.join(approve_blockers[:3])}"
        return _build_result(
            decision="manual_review",
            risk_level="medium",
            confidence_level="low",
            blocking_reasons=approve_blockers,
            warning_reasons=[],
            display_summary=summary,
            debug_score=overall_score,
        )

    # ---- 全部通过 ----
    summary = f"建议通过：AI 评分 {overall_score} 分，风险低，无重大问题"
    return _build_result(
        decision="approve",
        risk_level="low",
        confidence_level="high",
        blocking_reasons=[],
        warning_reasons=[],
        display_summary=summary,
        debug_score=overall_score,
    )


# ---------------------------------------------------------------------------
#  主入口
# ---------------------------------------------------------------------------

def derive_review_decision(
    dataset_type: str,
    ai_result: dict,
    human_result: dict,
    gold_result: dict = None,
    context: dict = None,
) -> dict:
    """
    审核决策推导函数（纯规则策略，无外部依赖）。

    根据数据集类型 (dataset_type) 分派到对应的决策逻辑：
      - "preference_compare": 偏好对比类，比较 AI / 人工 / Gold 的 preferred + margin
      - "qa_quality": 问答质量类，基于 AI overall_score + risk_level 判断

    参数:
        dataset_type:  数据集类型字符串
        ai_result:     AI 预审结果字典（可为 None 或空字典）
        human_result:  人工标注结果字典（可为 None 或空字典）
        gold_result:   Gold 标准答案字典（可选，默认 None）
        context:       上下文信息字典（可选，默认 None；包含 prompt, response_a 等）

    返回:
        {
            "decision": "approve" | "manual_review" | "revise",
            "risk_level": "low" | "medium" | "high",
            "confidence_level": "low" | "medium" | "high",
            "blocking_reasons": [str, ...],
            "warning_reasons": [str, ...],
            "display_summary": str,
            "debug_score": int | None,
        }
    """

    # 防御性处理：确保输入都是字典
    ai_result = ai_result if isinstance(ai_result, dict) else {}
    human_result = human_result if isinstance(human_result, dict) else {}
    gold_result = gold_result if isinstance(gold_result, dict) else {}
    context = context if isinstance(context, dict) else {}
    dataset_type = _safe_str(dataset_type) if dataset_type else ""

    # 按数据集类型分派
    if dataset_type == "preference_compare":
        return _decide_preference_compare(ai_result, human_result, gold_result, context)

    if dataset_type == "qa_quality":
        return _decide_qa_quality(ai_result, human_result, gold_result, context)

    # ---- 未知数据集类型：降级为人工复核 ----
    ai_score = ai_result.get("overall_score")
    if ai_score is not None:
        try:
            ai_score = int(ai_score)
        except (ValueError, TypeError):
            ai_score = None

    return _build_result(
        decision="manual_review",
        risk_level="medium",
        confidence_level="low",
        blocking_reasons=[],
        warning_reasons=[f"未知的 dataset_type「{dataset_type}」，无法自动推导决策，已降级为人工复核"],
        display_summary=f"建议复核：数据集类型「{dataset_type}」暂不支持自动策略，需人工审核",
        debug_score=ai_score,
    )
