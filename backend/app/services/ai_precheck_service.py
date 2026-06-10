import re


def run_precheck(
    task_id: int,
    dataset_item_id: int,
    annotation_id: int,
    work_key: str,
    item_data: dict,
    result_data: dict,
    schema_json: dict,
) -> dict:
    """
    基于规则的标注质量预审服务。
    返回包含 score、risk_level、passed、issues、suggestions、summary 的字典。
    """
    score = 100
    issues = []
    suggestions = []

    # ---- 规则4: 空结果 ----
    if not result_data:
        return {
            "success": True,
            "score": 0,
            "risk_level": "high",
            "passed": False,
            "issues": [{"field": "result_data", "level": "high", "message": "标注结果为空"}],
            "suggestions": ["请填写标注结果后再提交"],
            "summary": "标注结果为空，无法进行质量评估。",
        }

    # ---- 规则1: 必填字段完整性 ----
    required_fields = list(schema_json.get("required", [])) if isinstance(schema_json, dict) else []
    
    # Also check fields[].required
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
            value is None or 
            value == "" or 
            value == [] or 
            value == {} or
            (isinstance(value, str) and value.strip() == "")
        )
        if is_empty:
            score -= 30
            issues.append({
                "field": field,
                "level": "high",
                "message": f"必填字段 '{field}' 缺失",
            })
            suggestions.append(f"请补充必填字段 '{field}'")

    # ---- 规则2: 原因/理由字段过短 ----
    reason_fields = ["reason", "overall_comment", "detail_reason", "comment", "explanation"]
    for field in reason_fields:
        if field in result_data and result_data[field] is not None:
            value = str(result_data[field]).strip()
            # 统计中文字符数
            chinese_chars = re.findall(r'[\u4e00-\u9fff]', value)
            if len(chinese_chars) < 5 and len(value) < 10:
                score -= 10
                issues.append({
                    "field": field,
                    "level": "warning",
                    "message": f"'{field}' 字段内容过短，建议补充判断依据",
                })
                suggestions.append(f"{field} 字段可以写得更具体")

    # ---- 规则3: 所有评分维度相同 ----
    rating_fields = ["relevance", "accuracy", "completeness", "safety", "fluency", "quality"]
    rating_values = []
    for field in rating_fields:
        if field in result_data and result_data[field] is not None:
            rating_values.append(result_data[field])
    if len(rating_values) >= 2 and len(set(str(v) for v in rating_values)) == 1:
        score -= 5
        issues.append({
            "field": "rating_dimensions",
            "level": "warning",
            "message": "所有评分维度值相同，请确认是否经过仔细评估",
        })
        suggestions.append("建议对不同维度进行差异化评分")

    # ---- 规则5: accuracy 为 incorrect 但无原因 ----
    accuracy_value = result_data.get("accuracy")
    if accuracy_value is not None and str(accuracy_value).lower() in ("incorrect", "wrong", "错误", "不准确"):
        has_reason = False
        for field in reason_fields:
            if field in result_data and result_data[field] not in (None, ""):
                has_reason = True
                break
        if not has_reason:
            score -= 10
            issues.append({
                "field": "accuracy",
                "level": "warning",
                "message": "标注为不准确但未提供原因说明",
            })
            suggestions.append("标注为不准确时，建议补充原因说明")

    # ---- 规则6: relevance 为 low 但无原因 ----
    relevance_value = result_data.get("relevance")
    if relevance_value is not None and str(relevance_value).lower() in ("low", "低", "不相关"):
        has_reason = False
        for field in reason_fields:
            if field in result_data and result_data[field] not in (None, ""):
                has_reason = True
                break
        if not has_reason:
            score -= 10
            issues.append({
                "field": "relevance",
                "level": "warning",
                "message": "标注为低相关性但未提供原因说明",
            })
            suggestions.append("标注为低相关性时，建议补充原因说明")

    # ---- 计算最终结果 ----
    score = max(0, score)

    if score >= 80:
        risk_level = "low"
    elif score >= 60:
        risk_level = "medium"
    else:
        risk_level = "high"

    passed = score >= 60

    # ---- 生成摘要 ----
    if score >= 80:
        summary = "整体标注较完整"
    elif score >= 60:
        summary = "标注基本完整，但存在部分问题需要关注"
    else:
        summary = "标注存在较多问题，建议重新审核"

    if issues:
        issue_summary_parts = []
        for issue in issues:
            issue_summary_parts.append(issue["message"])
        if len(issue_summary_parts) <= 2:
            summary += "，" + "；".join(issue_summary_parts) + "。"
        else:
            summary += "，" + "；".join(issue_summary_parts[:2]) + "等。"
    else:
        summary += "。"

    return {
        "success": True,
        "score": score,
        "risk_level": risk_level,
        "passed": passed,
        "issues": issues,
        "suggestions": suggestions,
        "summary": summary,
    }
