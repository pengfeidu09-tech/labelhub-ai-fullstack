import json
import re
import time
import math
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from app.models.ai_review_run import AIReviewRun
from app.services.ai_provider import (
    get_ai_provider,
    AIProvider,
    classify_error,
    _extract_json_object,
)
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType
from app.core.config import settings
from app.services.ai_config_service import get_runtime_config

logger = logging.getLogger(__name__)


PROMPT_TEMPLATE_NAME = "labelhub_qa_quality_v1"
PROMPT_VERSION = "v1.0"

SYSTEM_PROMPT = """你是 LabelHub 的 AI 辅助审核 Agent。你的角色是辅助审核员，不是最终裁判。

核心语义：你评估的是"人工标注质量"，而非"模型回答质量"。

你必须输出 JSON，不要输出 Markdown，不要输出解释性正文。

你要判断：
1. 模型回答本身是否正确。
2. 人工标注的 relevance / accuracy / completeness / safety 是否与事实一致。
3. 人工填写的 reason 是否与选择项一致。
4. 如果人工选择和理由矛盾，要指出（annotation_self_contradiction）。
5. 如果参考答案可能错误，要指出 reference_conflict，不要盲从参考答案。
6. 如果无法确定，建议 manual_review，而不是高分通过。

重要判定原则：
- 只有当人工标注与原始数据、Gold 参考或 Rubric 明显冲突时，才建议返修（reject）。
- 如果四个维度判断和理由整体自洽，不能因为措辞不够完美就建议返修。
- 不允许仅因为出现 accuracy_error、idiom_misinterpretation、grammatical_incompleteness 等关键词就直接建议返修，必须结合人工选择、人工理由、Gold 参考、原始数据综合判断。
- 理由略短、表达不够充分时，应为 review（建议人工复核），不要 reject。
- 选择正确且理由基本自洽时，应为 approve（建议通过）。

风险等级规则：
- 明显事实错误、选项反了、漏填关键字段 → high / reject
- 理由略短、表达不够充分 → medium / review
- 选择正确且理由基本自洽 → low / approve

输出 JSON schema：
{
  "overall_score": <0-100的整数>,
  "risk_level": "<low|medium|high>",
  "suggested_action": "<approve|review|reject>",
  "confidence": <0.0-1.0的浮点数>,
  "summary": "<一句话总结>",
  "reason": "<详细原因>",
  "dimension_scores": {
    "relevance": {"value": "<high|medium|low|irrelevant>", "score": <0-100>, "evidence": ["<证据>"]},
    "accuracy": {"value": "<correct|partially_correct|incorrect|unknown>", "score": <0-100>, "evidence": ["<证据>"]},
    "completeness": {"value": "<complete|partial|incomplete>", "score": <0-100>, "evidence": ["<证据>"]},
    "safety": {"value": "<safe|risky|unsafe>", "score": <0-100>, "evidence": ["<证据>"]}
  },
  "issue_tags": ["<问题标签>"],
  "suggested_fix": "<修正建议>",
  "should_return_for_revision": false,
  "tool_checks": []
}

issue_tags 可选值：annotation_fact_mismatch, annotation_self_contradiction, math_error, reference_conflict, model_error_correctly_identified

评分规则：
- 模型回答正确 + 人工标正确 → 高分(>=80)，low risk，approve
- 模型回答错误 + 人工标错误 → 高分(>=80)，low risk，approve（人工正确识别了错误）
- 模型回答错误 + 人工标正确 → 低分(<=50)，high risk，reject（人工标注不合理）
- 人工 accuracy 与 reason 矛盾 → annotation_self_contradiction，中低分(<=60)，reject
- 人工选择正确但理由略短 → 中高分(>=65)，medium risk，review

should_return_for_revision 规则：
- 只在明显事实错误、选项反了、漏填关键字段时为 true
- 不能只由关键词触发，必须综合判断"""


def _safe_eval_math(expr: str) -> Optional[float]:
    """安全计算数学表达式，不使用 eval。支持 + - * / 和括号。"""
    try:
        cleaned = expr.strip()
        # 只保留数字、运算符、括号、小数点、空格
        cleaned = re.sub(r'[^\d+\-*/().\s]', '', cleaned)
        cleaned = cleaned.strip()
        if not cleaned:
            return None
        # 检查是否只包含安全字符
        if not re.match(r'^[\d+\-*/().\s]+$', cleaned):
            return None
        # 进一步检查：不允许连续运算符等异常模式
        if re.search(r'[+\-*/]{2,}', cleaned.replace(' ', '')):
            return None
        # 使用 ast 模式安全计算
        import ast
        tree = ast.parse(cleaned, mode='eval')
        # 只允许数字和基本运算
        for node in ast.walk(tree):
            if isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
                                ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd,
                                ast.Mod, ast.Pow)):
                continue
            elif isinstance(node, ast.Call):
                return None
            elif isinstance(node, ast.Name):
                return None
            elif isinstance(node, ast.Attribute):
                return None
        result = eval(compile(tree, '<math>', 'eval'), {"__builtins__": {}}, {})
        if isinstance(result, (int, float)) and math.isfinite(result):
            return float(result)
    except Exception:
        pass
    return None


def _try_eval_math_expression(expr: str) -> Optional[float]:
    try:
        cleaned = expr.strip()
        cleaned = re.sub(r'[^\d+\-*/().×÷\s]', '', cleaned)
        cleaned = cleaned.replace('×', '*').replace('÷', '/')
        if not cleaned:
            return None
        return _safe_eval_math(cleaned)
    except Exception:
        pass
    return None


def _extract_math_expression(text: str) -> Optional[str]:
    patterns = [
        r'计算\s*(.+?)(?:的值|等于|=|$)',
        r'求\s*(.+?)(?:的值|等于|=|$)',
        r'算\s*(.+?)(?:的值|等于|=|$)',
        r'(\d+\s*[×\*]\s*\d+\s*[+\-]\s*\d+)',
        r'(\d+\s*[+\-]\s*\d+\s*[×\*]\s*\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return None


def _extract_number_from_text(text: str) -> Optional[float]:
    if not text:
        return None
    text = str(text).strip()
    match = re.search(r'-?\d+\.?\d*', text)
    if match:
        return float(match.group(0))
    return None


def run_math_tool_check(question: str, model_answer: str, reference_answer: str) -> List[Dict[str, Any]]:
    tool_checks = []
    expr = _extract_math_expression(question)
    if not expr:
        return tool_checks

    expected = _try_eval_math_expression(expr)
    if expected is None:
        return tool_checks

    expected_str = str(int(expected)) if expected == int(expected) else str(expected)
    actual_num = _extract_number_from_text(model_answer)
    reference_num = _extract_number_from_text(reference_answer)

    check = {
        "name": "math_calculation_check",
        "status": "passed",
        "expected": expected_str,
        "actual": model_answer.strip() if model_answer else "",
        "message": ""
    }

    if actual_num is not None and abs(actual_num - expected) > 0.01:
        check["status"] = "failed"
        check["message"] = f"数学工具核验发现答案不一致：工具计算结果为 {expected_str}，模型回答为 {model_answer.strip()}"
    elif actual_num is not None:
        check["message"] = f"数学工具核验通过：计算结果 {expected_str} 与模型回答一致"

    tool_checks.append(check)

    if reference_num is not None and abs(reference_num - expected) > 0.01:
        ref_check = {
            "name": "reference_math_check",
            "status": "failed",
            "expected": expected_str,
            "actual": reference_answer.strip() if reference_answer else "",
            "message": f"参考答案疑似存在计算错误：工具计算结果为 {expected_str}，参考答案为 {reference_answer.strip()}"
        }
        tool_checks.append(ref_check)

    return tool_checks


def _is_math_question(item_data: Dict) -> bool:
    category = str(item_data.get("category", "")).lower()
    if "math" in category or "calculation" in category:
        return True
    question = str(item_data.get("question", "") or item_data.get("prompt", ""))
    math_patterns = [r'计算', r'求值', r'等于多少', r'\d+\s*[×\*÷/\+\-]\s*\d+']
    for pattern in math_patterns:
        if re.search(pattern, question):
            return True
    return False


def _validate_required_fields(result_data: Dict, schema_json: Dict) -> List[Dict]:
    issues = []
    required_fields = list(schema_json.get("required", [])) if isinstance(schema_json, dict) else []
    if isinstance(schema_json, dict) and "fields" in schema_json:
        for field in schema_json["fields"]:
            if not isinstance(field, dict):
                continue
            is_required = field.get("required", False)
            if not is_required:
                rules = field.get("rules", [])
                if isinstance(rules, list):
                    for rule in rules:
                        if isinstance(rule, dict) and rule.get("required", False):
                            is_required = True
                            break
                elif isinstance(rules, dict) and rules.get("required", False):
                    is_required = True
            if is_required:
                field_key = field.get("key") or field.get("id") or field.get("name")
                if field_key and field_key not in required_fields:
                    required_fields.append(field_key)

    for field in required_fields:
        value = result_data.get(field) if isinstance(result_data, dict) else None
        is_empty = (
            value is None or value == "" or value == [] or value == {} or
            (isinstance(value, str) and value.strip() == "")
        )
        if is_empty:
            issues.append({"field": field, "severity": "high", "message": f"必填字段 '{field}' 缺失"})
    return issues


def _validate_field_types(result_data: Dict, schema_json: Dict) -> List[Dict]:
    issues = []
    if not isinstance(schema_json, dict) or "fields" not in schema_json:
        return issues
    for field in schema_json["fields"]:
        if not isinstance(field, dict):
            continue
        field_key = field.get("key") or field.get("id")
        if not field_key or field_key not in result_data:
            continue
        value = result_data[field_key]
        field_type = str(field.get("type", "")).lower()
        if field_type in ("select", "radio") and field.get("options"):
            valid_values = [opt.get("value", opt.get("label", "")) for opt in field.get("options", []) if isinstance(opt, dict)]
            if value not in valid_values and str(value) not in valid_values:
                issues.append({"field": field_key, "severity": "medium", "message": f"字段 '{field_key}' 的值不在合法枚举范围内"})
    return issues


def _validate_json_validity(result_data: Dict) -> List[Dict]:
    issues = []
    try:
        json.dumps(result_data)
    except (TypeError, ValueError) as e:
        issues.append({"field": "result_data", "severity": "high", "message": f"标注结果JSON不合法: {str(e)}"})
    return issues


def _repair_json(raw_text: str) -> Optional[Dict]:
    try:
        return json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        match = re.search(r'\{[\s\S]*\}', raw_text)
        if match:
            return json.loads(match.group(0))
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _normalize_annotation_values(result_data: Dict) -> Dict:
    """将前端表单的非标准标注值映射到 AI 评估的标准值。

    前端表单可能使用 excellent/good/fair/poor 或 pass/warning/fail，
    AI 评估期望 high/medium/low/irrelevant / correct/partially_correct/incorrect /
    complete/partial/incomplete / safe/risky/unsafe。
    """
    if not result_data:
        return result_data

    relevance_map = {
        "excellent": "high", "high": "high",
        "good": "medium", "medium": "medium",
        "fair": "low", "low": "low",
        "poor": "irrelevant", "irrelevant": "irrelevant",
    }
    accuracy_map = {
        "excellent": "correct", "correct": "correct",
        "good": "partially_correct", "partially_correct": "partially_correct",
        "partial": "partially_correct",
        "fair": "incorrect", "incorrect": "incorrect",
        "poor": "incorrect", "wrong": "incorrect",
    }
    completeness_map = {
        "excellent": "complete", "complete": "complete",
        "good": "partial", "partial": "partial",
        "fair": "incomplete", "incomplete": "incomplete",
        "poor": "incomplete",
    }
    safety_map = {
        "pass": "safe", "safe": "safe",
        "warning": "risky", "risky": "risky", "caution": "risky", "risk": "risky",
        "fail": "unsafe", "unsafe": "unsafe",
    }

    normalized = dict(result_data)
    for field, mapping in [("relevance", relevance_map), ("accuracy", accuracy_map),
                           ("completeness", completeness_map), ("safety", safety_map)]:
        val = str(normalized.get(field, "")).lower().strip()
        if val in mapping:
            normalized[field] = mapping[val]

    return normalized


def _build_llm_prompt(item_data: Dict, result_data: Dict, schema_json: Dict, tool_checks: List[Dict]) -> str:
    question = item_data.get("question", "") or item_data.get("prompt", "")
    model_answer = item_data.get("model_answer", "") or item_data.get("answer", "")
    reference = item_data.get("reference", "") or item_data.get("reference_answer", "")

    # 归一化标注值，确保 LLM 看到的是标准词汇
    normalized_result = _normalize_annotation_values(result_data)

    prompt = f"""请评估以下标注数据的质量：

## 原始题目
{question}

## 待评估模型回答
{model_answer}

## 参考答案
{reference}

## 人工标注结果（维度值已归一化为标准词汇）
{json.dumps(normalized_result, ensure_ascii=False, indent=2)}

## 标注模板 Schema
{json.dumps(schema_json, ensure_ascii=False, indent=2) if schema_json else '无'}

标注值归一化说明：
- relevance: excellent→high, good→medium, fair→low, poor→irrelevant
- accuracy: excellent→correct, good→partially_correct, fair→incorrect, poor→incorrect
- completeness: excellent→complete, good→partial, fair→incomplete, poor→incomplete
- safety: pass→safe, warning→risky, fail→unsafe
"""
    if tool_checks:
        prompt += "## 工具核验结果（确定性计算，结论优先于你的判断）\n"
        for check in tool_checks:
            prompt += f"- {check['name']}: {check['status']} | {check.get('message', '')}\n"
        prompt += "\n重要：工具核验结果是基于确定性计算的，如果工具发现计算不一致，你必须以工具结论为准，accuracy 维度必须标记为 incorrect，不能给高分。\n\n"

    prompt += "请输出 JSON 评估结果。"
    return prompt


def _normalize_llm_output(llm_result: Dict, tool_checks: List[Dict], check_tool_conflict: bool = True) -> Dict:
    """将 Qwen 返回的 overall_score/dimension_scores 格式统一为内部 score/dimensions 格式。

    同时处理工具校验与 LLM 判断冲突的情况。
    """
    normalized = dict(llm_result)

    # 统一 score 字段
    if "overall_score" in normalized and "score" not in normalized:
        try:
            normalized["score"] = int(normalized["overall_score"])
        except (TypeError, ValueError):
            normalized["score"] = 0

    # 统一 suggested_action 字段
    if "suggested_action" in normalized and "suggestion_action" not in normalized:
        normalized["suggestion_action"] = normalized["suggested_action"]
    elif "suggestion_action" in normalized and "suggested_action" not in normalized:
        normalized["suggested_action"] = normalized["suggestion_action"]

    # 统一 dimension_scores → dimensions
    if "dimension_scores" in normalized and "dimensions" not in normalized:
        dims = normalized.pop("dimension_scores")
        dimensions = {}
        for dim_name, dim_data in dims.items():
            if isinstance(dim_data, dict):
                dimensions[dim_name] = {
                    "label": dim_data.get("value", dim_data.get("label", "unknown")),
                    "score": dim_data.get("score", 0),
                    "evidence": dim_data.get("evidence", []),
                    "issues": dim_data.get("issues", [])
                }
            else:
                dimensions[dim_name] = {"label": str(dim_data), "score": 0, "evidence": [], "issues": []}
        normalized["dimensions"] = dimensions
    elif "dimensions" not in normalized:
        normalized["dimensions"] = {}

    # 统一 problems 字段
    if "problems" not in normalized:
        problems = []
        if normalized.get("issue_tags"):
            for tag in normalized["issue_tags"]:
                problems.append({"field": tag, "severity": "high" if tag in ("annotation_fact_mismatch", "annotation_self_contradiction", "math_error") else "medium", "message": tag})
        normalized["problems"] = problems

    # 统一 suggestions 字段
    if "suggestions" not in normalized:
        suggestions = []
        if normalized.get("suggested_fix"):
            suggestions.append(normalized["suggested_fix"])
        if normalized.get("recommendation") and normalized["recommendation"] not in suggestions:
            suggestions.append(normalized["recommendation"])
        if normalized.get("advice") and normalized["advice"] not in suggestions:
            suggestions.append(normalized["advice"])
        normalized["suggestions"] = suggestions

    # 确保 issue_tags 存在，同时生成 problem_tags 别名
    if "issue_tags" not in normalized:
        # 从 problems 提取
        tags = []
        for p in normalized.get("problems", []):
            if isinstance(p, dict) and p.get("field"):
                tags.append(p["field"])
        normalized["issue_tags"] = tags
    if "problem_tags" not in normalized:
        normalized["problem_tags"] = list(normalized.get("issue_tags", []))

    # 确保 tool_checks 存在
    if "tool_checks" not in normalized:
        normalized["tool_checks"] = tool_checks

    # 生成 suggestion 字段（兼容前端 ReviewDetailPage 的 aiSuggestion 读取）
    dims = normalized.get("dimensions", {})
    if "suggestion" not in normalized or not isinstance(normalized.get("suggestion"), dict):
        normalized["suggestion"] = {
            "relevance": dims.get("relevance", {}).get("label", "") if isinstance(dims.get("relevance"), dict) else (dims.get("relevance") or ""),
            "accuracy": dims.get("accuracy", {}).get("label", "") if isinstance(dims.get("accuracy"), dict) else (dims.get("accuracy") or ""),
            "completeness": dims.get("completeness", {}).get("label", "") if isinstance(dims.get("completeness"), dict) else (dims.get("completeness") or ""),
            "safety": dims.get("safety", {}).get("label", "") if isinstance(dims.get("safety"), dict) else (dims.get("safety") or ""),
            "reason": normalized.get("summary", ""),
            "issue_tags": normalized.get("issue_tags", []),
        }
    else:
        # 补全 suggestion 中缺失的字段
        sug = normalized["suggestion"]
        if not sug.get("relevance"):
            sug["relevance"] = dims.get("relevance", {}).get("label", "") if isinstance(dims.get("relevance"), dict) else (dims.get("relevance") or "")
        if not sug.get("accuracy"):
            sug["accuracy"] = dims.get("accuracy", {}).get("label", "") if isinstance(dims.get("accuracy"), dict) else (dims.get("accuracy") or "")
        if not sug.get("completeness"):
            sug["completeness"] = dims.get("completeness", {}).get("label", "") if isinstance(dims.get("completeness"), dict) else (dims.get("completeness") or "")
        if not sug.get("safety"):
            sug["safety"] = dims.get("safety", {}).get("label", "") if isinstance(dims.get("safety"), dict) else (dims.get("safety") or "")
        if not sug.get("issue_tags"):
            sug["issue_tags"] = normalized.get("issue_tags", [])
        if not sug.get("reason"):
            sug["reason"] = normalized.get("summary", "")

    # 统一 summary 字段
    if "summary" not in normalized:
        if normalized.get("reason"):
            normalized["summary"] = normalized["reason"]
        elif normalized.get("recommendation"):
            normalized["summary"] = normalized["recommendation"]

    # 工具校验与 LLM 判断冲突检测（仅对真实 LLM 结果生效）
    if check_tool_conflict:
        math_check_failed = any(tc.get("status") == "failed" and tc.get("name") == "math_calculation_check" for tc in tool_checks)
        if math_check_failed:
            accuracy_dim = normalized.get("dimensions", {}).get("accuracy", {})
            accuracy_label = accuracy_dim.get("label", "").lower() if isinstance(accuracy_dim, dict) else ""
            accuracy_score = accuracy_dim.get("score", 100) if isinstance(accuracy_dim, dict) else 100

            # 如果工具说模型答案错误，但 LLM 给 accuracy 高分，以工具为准
            if accuracy_label in ("correct", "high") or accuracy_score >= 70:
                if "model_tool_conflict" not in normalized.get("issue_tags", []):
                    normalized.setdefault("issue_tags", []).append("model_tool_conflict")
                # 强制降分
                if isinstance(accuracy_dim, dict):
                    accuracy_dim["label"] = "incorrect"
                    accuracy_dim["score"] = min(accuracy_dim.get("score", 100), 20)
                    accuracy_dim.setdefault("issues", []).append("工具确定性计算结果与 LLM 判断冲突，以工具为准")
                    normalized["dimensions"]["accuracy"] = accuracy_dim
                # 重新计算总分
                try:
                    normalized["score"] = min(normalized.get("score", 100), 50)
                except (TypeError, ValueError):
                    normalized["score"] = 50
                normalized["risk_level"] = "high"
                normalized["suggestion_action"] = "rework"

    return normalized


def _generate_mock_llm_result(item_data: Dict, result_data: Dict, tool_checks: List[Dict], rule_issues: List[Dict]) -> Dict:
    """生成 mock 预审结果，基于规则判断人工标注质量。

    核心语义：AI 预审评估的是"人工标注是否合理"，而非"模型回答是否正确"。
    """
    question = str(item_data.get("question", "") or item_data.get("prompt", ""))
    model_answer = str(item_data.get("model_answer", "") or item_data.get("answer", ""))
    reference = str(item_data.get("reference", "") or item_data.get("reference_answer", ""))

    # 归一化标注值，确保后续逻辑使用标准词汇
    normalized_data = _normalize_annotation_values(result_data) if result_data else {}

    math_check_failed = any(tc.get("status") == "failed" and tc.get("name") == "math_calculation_check" for tc in tool_checks)
    ref_check_failed = any(tc.get("status") == "failed" and tc.get("name") == "reference_math_check" for tc in tool_checks)

    # 从 tool_checks 中获取计算结果
    math_expected = None
    for tc in tool_checks:
        if tc.get("name") == "math_calculation_check" and tc.get("expected"):
            try:
                math_expected = float(tc["expected"])
            except (ValueError, TypeError):
                pass

    # 提取人工标注关键字段（使用归一化后的值）
    accuracy = str(normalized_data.get("accuracy", "")).lower().strip()
    reason_text = str(normalized_data.get("reason", "")).lower().strip()
    relevance_val = str(normalized_data.get("relevance", "")).lower().strip()
    completeness_val = str(normalized_data.get("completeness", "")).lower().strip()
    safety_val = str(normalized_data.get("safety", "")).lower().strip()

    # 判断人工标注的 accuracy 是否表示"正确"
    accuracy_is_positive = accuracy in ("correct", "yes", "true", "1", "对", "正确", "准确", "right", "excellent")
    # 判断人工标注的 accuracy 是否表示"部分正确"（中性，非完全正确也非完全错误）
    accuracy_is_partial = accuracy in ("partially_correct", "partial", "good")
    # 判断人工标注的 accuracy 是否表示"错误"
    accuracy_is_negative = accuracy in ("incorrect", "wrong", "no", "false", "0", "错", "错误", "不准确", "fair", "poor")

    # 判断 reason 文本是否暗示"模型回答错误"
    reason_implies_error = any(kw in reason_text for kw in ["错误", "不正确", "不对", "算错", "计算错", "有误", "偏差", "不准确", "wrong", "error", "incorrect", "mistake"])
    # 判断 reason 文本是否暗示"模型回答正确"（排除"正确结果应为"等语境）
    reason_implies_correct = False
    if any(kw in reason_text for kw in ["正确", "准确", "无误"]):
        # 排除"正确结果应为"、"正确答案"等语境——这些是在说参考答案，不是在说模型回答
        if not any(exclude in reason_text for exclude in ["正确结果", "正确答案", "正确值", "应为", "应该是"]):
            reason_implies_correct = True
    if any(kw in reason_text for kw in ["回答正确", "答案正确", "模型正确", "correct", "right", "accurate"]):
        reason_implies_correct = True

    # 检测自相矛盾：accuracy=correct 但 reason 暗示错误
    self_contradiction = False
    if accuracy_is_positive and reason_implies_error:
        self_contradiction = True
    # 反向矛盾：accuracy=incorrect 但 reason 暗示正确
    if accuracy_is_negative and reason_implies_correct:
        self_contradiction = True

    # --- 评分逻辑 ---
    relevance_score = 85
    accuracy_score = 80
    completeness_score = 75
    safety_score = 95

    relevance_issues = []
    accuracy_issues = []
    completeness_issues = []
    safety_issues = []

    relevance_evidence = ["回答确实围绕题目展开"]
    accuracy_evidence = ["回答与题目相关"]
    completeness_evidence = ["给出了标注结果"]
    safety_evidence = ["内容不涉及安全风险"]

    issue_tags = []
    problems = []
    suggestions = []
    summary = "整体标注较完整"

    # --- 数学题特殊逻辑 ---
    if math_check_failed:
        # 模型答案计算错误
        if accuracy_is_positive:
            # 人工标注说"正确"，但模型实际算错了 → 人工标注不合理
            accuracy_score = 15
            accuracy_issues.append("模型答案计算错误，人工却标为正确")
            accuracy_evidence = [f"工具计算正确结果为 {math_expected}，模型回答 {model_answer.strip()} 错误，人工标注 accuracy={accuracy} 不合理"]
            issue_tags.extend(["annotation_fact_mismatch", "math_error"])
            problems.append({"field": "accuracy", "severity": "high",
                           "message": f"模型答案计算错误（正确结果={math_expected}，模型回答={model_answer.strip()}），人工却标为正确，标注不合理"})
            suggestions.append("请修正 accuracy 字段为 incorrect/wrong，模型答案实际计算错误")
            summary = f"模型答案计算错误（正确={math_expected}），人工标注不合理"
        elif accuracy_is_negative:
            # 人工标注说"错误"，模型确实算错了 → 人工标注合理
            accuracy_score = 90
            accuracy_issues = []
            accuracy_evidence = [f"人工正确识别了模型计算错误（正确结果={math_expected}，模型回答={model_answer.strip()}）"]
            issue_tags.append("model_error_correctly_identified")
            suggestions.append("人工正确识别了模型计算错误，标注质量良好")
            summary = f"人工正确识别了模型计算错误，标注质量较好"
        elif accuracy_is_partial:
            # 人工标注说"部分正确"，模型实际完全算错了 → 部分正确不准确
            accuracy_score = 35
            accuracy_issues.append("模型答案计算错误，人工标为部分正确不够准确")
            accuracy_evidence = [f"工具计算正确结果为 {math_expected}，模型回答 {model_answer.strip()} 实际完全错误，人工标注 accuracy={accuracy} 不够准确"]
            issue_tags.extend(["annotation_fact_mismatch", "math_error"])
            problems.append({"field": "accuracy", "severity": "high",
                           "message": f"模型答案计算完全错误（正确={math_expected}），人工标为部分正确，建议改为 incorrect"})
            suggestions.append("模型答案实际完全计算错误，建议将 accuracy 改为 incorrect")
            summary = f"模型答案计算完全错误（正确={math_expected}），人工标为部分正确不够准确"
        else:
            # 人工没有明确标注 accuracy
            accuracy_score = 40
            accuracy_issues.append("模型答案计算错误，但人工未明确标注 accuracy")
            accuracy_evidence = [f"工具计算正确结果为 {math_expected}，模型回答 {model_answer.strip()} 错误，人工未标注 accuracy"]
            issue_tags.append("math_error")
            problems.append({"field": "accuracy", "severity": "high",
                           "message": f"模型答案计算错误（正确={math_expected}），人工未明确标注 accuracy"})
            suggestions.append("建议明确标注 accuracy 为 incorrect/wrong")
            summary = "模型答案计算错误，人工标注不完整"

    # --- 自相矛盾检测 ---
    if self_contradiction:
        issue_tags.append("annotation_self_contradiction")
        if accuracy_is_positive and reason_implies_error:
            problems.append({"field": "accuracy", "severity": "high",
                           "message": f"accuracy 标为 {accuracy}（正确），但 reason 暗示模型回答错误，存在自相矛盾"})
            accuracy_score = min(accuracy_score, 25)
            suggestions.append("accuracy 与 reason 内容矛盾，请统一修正")
            summary = "标注存在自相矛盾：accuracy 与 reason 不一致"
        elif accuracy_is_negative and reason_implies_correct:
            problems.append({"field": "accuracy", "severity": "medium",
                           "message": f"accuracy 标为 {accuracy}（错误），但 reason 暗示模型回答正确，存在自相矛盾"})
            accuracy_score = min(accuracy_score, 40)
            suggestions.append("accuracy 与 reason 内容矛盾，请统一修正")

    # --- 参考答案冲突 ---
    if ref_check_failed:
        accuracy_issues.append("参考答案疑似存在计算错误，建议人工复核数据源")
        issue_tags.append("reference_conflict")
        problems.append({"field": "reference", "severity": "medium",
                       "message": "参考答案疑似存在计算错误，建议人工复核数据源"})

    # --- 通用规则检查 ---
    if len(model_answer) < 20:
        completeness_score = 50
        completeness_issues.append("回答内容过短")

    if not result_data:
        completeness_score = 10
        completeness_issues.append("标注结果为空")

    has_required_issues = any(i.get("severity") == "high" for i in rule_issues)
    if has_required_issues:
        completeness_score = min(completeness_score, 30)
        completeness_issues.append("存在必填字段缺失")

    # --- 计算总分 ---
    overall_score = int((relevance_score + accuracy_score + completeness_score + safety_score) / 4)

    # 如果数学检查失败且人工标注不合理，强制降分
    if math_check_failed and accuracy_is_positive:
        overall_score = min(overall_score, 45)

    # 如果自相矛盾，强制降分
    if self_contradiction:
        overall_score = min(overall_score, 55)

    # 如果人工标注合理（模型错+人工标错），给高分
    if math_check_failed and accuracy_is_negative and not self_contradiction:
        overall_score = max(overall_score, 85)

    risk_level = "low" if overall_score >= 80 else ("medium" if overall_score >= 60 else "high")
    suggestion_action = "submit" if overall_score >= 80 else ("manual_review" if overall_score >= 60 else "rework")

    if self_contradiction:
        suggestion_action = "rework"
        risk_level = "high" if overall_score < 50 else "medium"

    if math_check_failed and accuracy_is_positive:
        suggestion_action = "rework"
        risk_level = "high"

    confidence = 0.92 if (math_check_failed or self_contradiction) else 0.85

    for issue in rule_issues:
        problems.append({"field": issue.get("field", ""), "severity": issue.get("severity", "medium"), "message": issue.get("message", "")})

    if overall_score >= 80:
        suggestions.append("标注质量较好，可以提交")
    elif overall_score >= 60:
        suggestions.append("建议人工复核确认标注质量")

    return {
        "score": overall_score,
        "risk_level": risk_level,
        "suggestion_action": suggestion_action,
        "confidence": confidence,
        "summary": summary,
        "dimensions": {
            "relevance": {
                "label": "high" if relevance_score >= 80 else ("medium" if relevance_score >= 60 else "low"),
                "score": relevance_score,
                "evidence": relevance_evidence,
                "issues": relevance_issues
            },
            "accuracy": {
                "label": "correct" if accuracy_score >= 80 else ("partially_correct" if accuracy_score >= 40 else "incorrect"),
                "score": accuracy_score,
                "evidence": accuracy_evidence,
                "issues": accuracy_issues
            },
            "completeness": {
                "label": "complete" if completeness_score >= 80 else ("partial" if completeness_score >= 40 else "incomplete"),
                "score": completeness_score,
                "evidence": completeness_evidence,
                "issues": completeness_issues
            },
            "safety": {
                "label": "safe" if safety_score >= 80 else ("risky" if safety_score >= 40 else "unsafe"),
                "score": safety_score,
                "evidence": safety_evidence,
                "issues": safety_issues
            }
        },
        "tool_checks": tool_checks,
        "problems": problems,
        "suggestions": suggestions,
        "issue_tags": issue_tags
    }


def run_pipeline(
    db: Session,
    task_id: int,
    item_id: int,
    labeler_id: int,
    work_key: str,
    item_data: Dict,
    result_data: Dict,
    schema_json: Optional[Dict] = None,
    annotation_id: Optional[int] = None,
    submission_id: Optional[int] = None,
) -> Dict:
    start_time = time.time()
    provider = get_ai_provider()
    provider_name = provider.get_provider_name()
    model_name = provider.get_model_name()
    base_url = getattr(provider, "get_base_url", lambda: "")()
    is_mock = provider_name == "mock"

    # 读取运行时配置以获取 mock_fallback
    runtime_config = get_runtime_config()
    mock_fallback = bool(runtime_config.get("mock_fallback", True))

    run_record = AIReviewRun(
        task_id=task_id,
        item_id=item_id,
        annotation_id=annotation_id,
        submission_id=submission_id,
        labeler_id=labeler_id,
        prompt_template_id=None,
        prompt_version=PROMPT_VERSION,
        model_provider=provider_name,
        model_name=model_name,
        base_url=base_url,
        status="running",
        used_fallback=False,
        retry_count=0
    )
    db.add(run_record)
    db.commit()
    db.refresh(run_record)

    try:
        # Stage 1: Collect input context
        input_snapshot = {
            "task_id": task_id,
            "item_id": item_id,
            "item_data": item_data,
            "result_data": result_data,
            "schema_json": schema_json,
            "labeler_id": labeler_id,
            "work_key": work_key
        }
        run_record.input_snapshot_json = input_snapshot

        # Stage 2: Programmatic validation
        rule_issues = []
        if not result_data:
            rule_issues.append({"field": "result_data", "severity": "high", "message": "标注结果为空"})
        else:
            if schema_json:
                rule_issues.extend(_validate_required_fields(result_data, schema_json))
                rule_issues.extend(_validate_field_types(result_data, schema_json))
            rule_issues.extend(_validate_json_validity(result_data))

        # Stage 3: Math tool check
        tool_checks = []
        is_math = _is_math_question(item_data)
        if is_math:
            question = str(item_data.get("question", "") or item_data.get("prompt", ""))
            model_answer = str(item_data.get("model_answer", "") or item_data.get("answer", ""))
            reference = str(item_data.get("reference", "") or item_data.get("reference_answer", ""))
            tool_checks = run_math_tool_check(question, model_answer, reference)

        # Stage 4: LLM-as-Judge
        llm_result = None
        llm_error_type = None
        llm_error_message = None
        raw_response_preview = None
        if provider.get_provider_name() == "mock":
            llm_result = _generate_mock_llm_result(item_data, result_data, tool_checks, rule_issues)
        else:
            prompt = _build_llm_prompt(item_data, result_data, schema_json or {}, tool_checks)
            llm_response = provider.generate(prompt, system_prompt=SYSTEM_PROMPT)

            if llm_response.get("error") or llm_response.get("error_type"):
                llm_error_type = llm_response.get("error_type") or "unknown_error"
                llm_error_message = llm_response.get("error_message") or "AI模型调用失败"
                raw_response_preview = (llm_response.get("raw_text") or "")[:500]
                run_record.error_type = llm_error_type
                run_record.error_message = llm_error_message
                run_record.raw_response_preview = raw_response_preview
                run_record.retry_count = (run_record.retry_count or 0) + 1
            else:
                raw_response_preview = (llm_response.get("raw_text") or "")[:500]
                run_record.raw_response_preview = raw_response_preview

            if llm_response.get("parsed"):
                llm_result = llm_response["parsed"]
            else:
                repaired = _repair_json(llm_response.get("raw_text", ""))
                if repaired:
                    llm_result = repaired
                else:
                    run_record.status = "failed"
                    if not llm_error_type:
                        llm_error_type = "json_parse_error"
                        llm_error_message = "LLM 返回内容无法解析为 JSON"
                    run_record.error_type = llm_error_type
                    run_record.error_message = llm_error_message or "LLM JSON parse failed"
                    if raw_response_preview:
                        run_record.error_message = (
                            f"{run_record.error_message} | raw_preview={raw_response_preview[:500]}"
                        )
                    run_record.latency_ms = int((time.time() - start_time) * 1000)
                    db.commit()

                    if mock_fallback:
                        fallback_result = _generate_mock_llm_result(item_data, result_data, tool_checks, rule_issues)
                        fallback_result["fallback"] = True
                        fallback_result["fallback_used"] = True
                        fallback_result["fallback_provider"] = "mock"
                        fallback_result["fallback_reason"] = f"{llm_error_type}: {llm_error_message}"
                    else:
                        fallback_result = {
                            "score": 0,
                            "risk_level": "high",
                            "suggestion_action": "fallback_required",
                            "confidence": 0,
                            "summary": f"AI预审失败: {llm_error_message or 'unknown'}",
                            "dimensions": {},
                            "tool_checks": tool_checks,
                            "problems": [],
                            "suggestions": [],
                            "issue_tags": [],
                        }

                    run_record.output_json = fallback_result
                    run_record.score = fallback_result.get("score")
                    run_record.risk_level = fallback_result.get("risk_level")
                    run_record.suggestion_action = fallback_result.get("suggestion_action")
                    run_record.confidence = fallback_result.get("confidence")
                    run_record.used_fallback = bool(mock_fallback)
                    if mock_fallback:
                        # mock 兜底成功：status 保持 success
                        run_record.status = "success"
                    db.commit()

                    return _build_final_result(
                        fallback_result, run_record, start_time, db,
                        task_id, item_id, labeler_id, work_key,
                        used_fallback=bool(mock_fallback),
                        error_type=llm_error_type,
                        error_message=run_record.error_message,
                    )

            run_record.token_usage_json = llm_response.get("token_usage", {})

        # Stage 5: Normalize LLM output (Qwen returns overall_score/dimension_scores, mock returns score/dimensions)
        # Only apply tool-LLM conflict detection for real LLM results
        is_real_llm = provider.get_provider_name() != "mock"
        if llm_result:
            llm_result = _normalize_llm_output(llm_result, tool_checks, check_tool_conflict=is_real_llm)

        # Stage 5b: Validate LLM output JSON schema
        if llm_result:
            if not isinstance(llm_result.get("dimensions"), dict):
                llm_result = _generate_mock_llm_result(item_data, result_data, tool_checks, rule_issues)

        # Stage 6: Merge results
        if not llm_result:
            llm_result = _generate_mock_llm_result(item_data, result_data, tool_checks, rule_issues)

        for issue in rule_issues:
            if issue not in llm_result.get("problems", []):
                llm_result.setdefault("problems", []).append(issue)

        if tool_checks and "tool_checks" not in llm_result:
            llm_result["tool_checks"] = tool_checks
        elif tool_checks and not llm_result.get("tool_checks"):
            llm_result["tool_checks"] = tool_checks

        # Stage 7: Write to DB and audit log
        run_record.output_json = llm_result
        run_record.score = llm_result.get("score")
        run_record.risk_level = llm_result.get("risk_level")
        run_record.suggestion_action = llm_result.get("suggestion_action")
        run_record.confidence = llm_result.get("confidence")
        run_record.status = "success"
        run_record.latency_ms = int((time.time() - start_time) * 1000)
        run_record.error_type = None
        run_record.error_message = None
        run_record.used_fallback = False
        db.commit()

        return _build_final_result(llm_result, run_record, start_time, db, task_id, item_id, labeler_id, work_key)

    except Exception as e:
        run_record.status = "failed"
        err_type, err_msg = classify_error(e, None)
        run_record.error_type = err_type
        run_record.error_message = str(e)[:500] if str(e) else err_msg
        run_record.latency_ms = int((time.time() - start_time) * 1000)
        run_record.used_fallback = False
        db.commit()

        try:
            log_action(
                db=db, user_id=labeler_id, action=AuditAction.AI_PRECHECK_FAILED,
                target_type=AuditTargetType.AI_REVIEW, target_id=run_record.id,
                role="labeler", action_label="AI预审失败",
                task_id=task_id, item_id=item_id, work_key=work_key,
                message=f"AI预审失败 [{err_type}]: {str(e)[:200]}"
            )
        except Exception:
            pass

        if not is_mock and mock_fallback:
            fallback = _generate_mock_llm_result(item_data or {}, result_data or {}, [], rule_issues if 'rule_issues' in dir() else [])
            fallback["fallback"] = True
            fallback["fallback_used"] = True
            fallback["fallback_provider"] = "mock"
            fallback["fallback_reason"] = f"{err_type}: {err_msg}"
            run_record.used_fallback = True
            run_record.output_json = fallback
            run_record.score = fallback.get("score")
            run_record.risk_level = fallback.get("risk_level")
            run_record.suggestion_action = fallback.get("suggestion_action")
            run_record.confidence = fallback.get("confidence")
            run_record.status = "success"
            db.commit()
            return _build_final_result(
                fallback, run_record, start_time, db, task_id, item_id, labeler_id, work_key,
                used_fallback=True, error_type=err_type, error_message=run_record.error_message,
            )

        # mock_fallback=False -> 返回真实失败
        return {
            "success": False,
            "score": 0,
            "risk_level": "high",
            "suggestion_action": "fallback_required",
            "passed": False,
            "confidence": 0,
            "summary": f"AI预审失败 [{err_type}]: {err_msg}",
            "issues": [],
            "suggestions": [],
            "dimensions": {},
            "tool_checks": [],
            "matched_rubrics": [],
            "prompt_template": PROMPT_TEMPLATE_NAME,
            "prompt_version": PROMPT_VERSION,
            "model_provider": provider_name,
            "model_name": model_name,
            "base_url": base_url,
            "latency_ms": run_record.latency_ms,
            "run_id": run_record.id,
            "fallback": False,
            "error_type": err_type,
            "error_message": run_record.error_message,
            "used_fallback": False,
        }


def _extract_matched_rubrics(db: Session, task_id: int, llm_result: Dict) -> List[Dict]:
    try:
        from app.models.task import Task
        from app.models.template_schema import TemplateSchema
        
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task or not task.template_id:
            return []
        
        template = db.query(TemplateSchema).filter(TemplateSchema.id == task.template_id).first()
        if not template or not template.schema:
            return []
        
        schema_json = template.schema
        if isinstance(schema_json, str):
            import json as _json

            try:
                schema_json = _json.loads(schema_json)
            except:
                return []
        
        rubrics = schema_json.get("rubrics", [])
        dimensions = llm_result.get("dimensions", {})
        matched = []
        
        for idx, rubric in enumerate(rubrics):
            if not isinstance(rubric, dict):
                continue
            criterion = rubric.get("criterion") or rubric.get("title") or rubric.get("label") or ""
            dimension = rubric.get("dimension") or rubric.get("group") or ""
            rubric_type = rubric.get("type") or rubric.get("rubric_type") or "subjective"
            priority = rubric.get("priority") or rubric.get("level") or "nice_to_have"
            
            ai_judgement = "unknown"
            evidence = ""
            if dimension in dimensions:
                dim_data = dimensions[dimension]
                ai_judgement = dim_data.get("label", "unknown")
                ev_list = dim_data.get("evidence", [])
                if ev_list:
                    evidence = ev_list[0] if isinstance(ev_list[0], str) else str(ev_list[0])
            
            matched.append({
                "rubric_id": f"R{idx+1}",
                "criterion": criterion,
                "dimension": dimension,
                "type": rubric_type,
                "priority": priority,
                "ai_judgement": ai_judgement,
                "evidence": evidence
            })
        
        return matched
    except Exception as e:
        logger.debug(f"[_extract_matched_rubrics] error: {e}")
        return []


def _build_final_result(
    llm_result: Dict,
    run_record: AIReviewRun,
    start_time: float,
    db: Session,
    task_id: int,
    item_id: int,
    labeler_id: int,
    work_key: str,
    used_fallback: Optional[bool] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Dict:
    try:
        log_action(
            db=db, user_id=labeler_id, action=AuditAction.AI_PRECHECK_SUCCESS,
            target_type=AuditTargetType.AI_REVIEW, target_id=run_record.id,
            role="labeler", action_label="AI预审成功",
            task_id=task_id, item_id=item_id, work_key=work_key,
            message=f"AI预审完成：{llm_result.get('score')}分，{llm_result.get('risk_level')}风险",
            payload_json={"run_id": run_record.id, "score": llm_result.get("score"), "risk_level": llm_result.get("risk_level")}
        )
    except Exception:
        pass

    matched_rubrics = _extract_matched_rubrics(db, task_id, llm_result)

    fallback_used = bool(used_fallback) if used_fallback is not None else bool(llm_result.get("fallback") or llm_result.get("fallback_used"))
    if fallback_used and (llm_result.get("fallback") or llm_result.get("fallback_used")):
        llm_result["fallback"] = True

    return {
        "success": True,
        "score": llm_result.get("score", 0),
        "risk_level": llm_result.get("risk_level", "high"),
        "suggestion_action": llm_result.get("suggestion_action", "manual_review"),
        "passed": llm_result.get("score", 0) >= 60,
        "confidence": llm_result.get("confidence", 0.5),
        "summary": llm_result.get("summary", ""),
        "issues": llm_result.get("problems", []),
        "suggestions": llm_result.get("suggestions", []),
        "dimensions": llm_result.get("dimensions", {}),
        "tool_checks": llm_result.get("tool_checks", []),
        "matched_rubrics": matched_rubrics,
        "prompt_template": PROMPT_TEMPLATE_NAME,
        "prompt_version": PROMPT_VERSION,
        "model_provider": run_record.model_provider,
        "model_name": run_record.model_name,
        "base_url": run_record.base_url,
        "latency_ms": run_record.latency_ms,
        "run_id": run_record.id,
        "output_json": llm_result,
        "fallback": fallback_used,
        "fallback_used": fallback_used,
        "fallback_provider": llm_result.get("fallback_provider") if fallback_used else None,
        "fallback_reason": llm_result.get("fallback_reason") if fallback_used else None,
        "used_fallback": fallback_used,
        "error_type": error_type or run_record.error_type,
        "error_message": error_message or run_record.error_message,
        "raw_response_preview": run_record.raw_response_preview,
    }
