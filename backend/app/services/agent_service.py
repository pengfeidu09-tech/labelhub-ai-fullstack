import json
import re
import time
import random
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from app.models.ai_review_run import AIReviewRun
from app.services.ai_provider import (
    get_ai_provider,
    AIProvider,
    classify_error,
)
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType

logger = logging.getLogger(__name__)

MAX_RETRY_COUNT = 3

DEFAULT_AGENT_CONFIG = {
    "prompt_template": "labelhub_qa_quality_v1",
    "dimensions": ["relevance", "accuracy", "completeness", "safety"],
    "pass_threshold": 80,
    "review_threshold": 70,
    "reject_threshold": 60,
    "model_mode": "mock",
    "provider": "mock",
    "prompt_version": "v1.0"
}

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
  "should_return_for_revision": false
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

PREFERENCE_COMPARE_SYSTEM_PROMPT = """你是偏好对比标注质检 Agent。你的角色是辅助审核员，不是最终裁判。

输入包括：
- prompt：用户问题
- response_a：回答 A
- response_b：回答 B
- model_a：模型 A 名称
- model_b：模型 B 名称
- human preferred：标注员选择 A / B / tie
- human margin：明显优于 / 略优于 / 相当
- human dimensions：标注员选择的判断维度
- human annotator_note：标注员判断理由

你的任务：
1. 独立判断 A/B 哪个更好，或者是否相当。
2. 检查标注员 preferred 是否合理。
3. 检查 margin 是否与理由一致。
4. 检查 dimensions 是否覆盖核心判断依据。
5. 检查 annotator_note 是否给出具体、可解释依据。
6. 不要因为没有 model_answer/reference 就判为空，因为本任务没有这两个字段。
7. response_a 和 response_b 才是本任务的被评估答案。

重要判定原则：
- 如果人工 preferred 与 AI 独立判断一致，且人工理由能解释核心差异，则默认建议通过（approve）或人工复核（review），不要因为单个 keyword 就建议返修。
- 不允许仅因为出现 accuracy_error、idiom_misinterpretation、grammatical_incompleteness 等关键词就直接建议返修。
- 只有当 preferred 明显错误（如选反了）或理由与内容严重矛盾时，才建议返修（reject）。
- 理由略短但方向正确时，应为 review，不要 reject。

风险等级规则：
- preferred 明显错误、选反了 → high / reject
- preferred 合理但理由过短或维度不完整 → medium / review
- preferred 正确且理由充分 → low / approve

输出必须是严格 JSON：
{
  "preferred": "A|B|tie",
  "margin": "明显优于|略优于|相当",
  "dimensions": ["准确性", "完整性", "可读性"],
  "safety_flag": false,
  "overall_score": 0-100,
  "score": 0-100,
  "risk_level": "low|medium|high",
  "suggested_action": "approve|review|reject",
  "confidence": 0.0-1.0,
  "summary": "一句话总结",
  "annotator_note": "详细判断依据",
  "issue_tags": [],
  "reason": "详细原因",
  "should_return_for_revision": false
}

评分规则：
- 标注员 preferred 与 AI 独立判断一致，且理由充分：80-100，approve
- preferred 基本合理，但理由过短或维度不完整：60-79，review
- preferred 存在明显争议，需要人工复核：40-59，review
- preferred 明显错误，或理由与内容严重矛盾：0-39，reject

should_return_for_revision 规则：
- 只在 preferred 明显错误或选反了时为 true
- 不能只由关键词触发，必须综合判断"""


def _mask_key(api_key: str) -> str:
    """返回脱敏后的 key 字符串用于日志。"""
    if not api_key:
        return "(empty)"
    return f"prefix={api_key[:4]} len={len(api_key)}"


def get_agent_config(task_id: int) -> Dict[str, Any]:
    provider = get_ai_provider()
    config = {
        **DEFAULT_AGENT_CONFIG,
        "task_id": task_id,
        "provider": provider.get_provider_name(),
        "model_mode": provider.get_provider_name(),
        "model_name": provider.get_model_name(),
    }
    if provider.get_provider_name() == "mock":
        config["note"] = "当前为 mock 模式，接口结构支持替换真实大模型"
    else:
        config["note"] = f"当前使用 {provider.get_provider_name()}/{provider.get_model_name()} 真实模型"
    return config


def update_agent_config(task_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    config = get_agent_config(task_id)
    config.update(updates)
    config["task_id"] = task_id
    return config


def enqueue_ai_review_run(
    db: Session,
    task_id: int,
    item_id: int,
    submission_id: Optional[int] = None,
    annotation_id: Optional[int] = None,
    labeler_id: Optional[int] = None,
    work_key: Optional[str] = None,
    input_snapshot: Optional[Dict] = None,
    trigger_type: str = "auto_on_submit"
) -> AIReviewRun:
    existing = db.query(AIReviewRun).filter(
        AIReviewRun.task_id == task_id,
        AIReviewRun.item_id == item_id,
        AIReviewRun.status.in_(["pending", "running", "success"]),
        AIReviewRun.trigger_type == trigger_type,  # Don't cross-contaminate triggers
    ).first()
    if existing:
        return existing

    failed_runs = db.query(AIReviewRun).filter(
        AIReviewRun.task_id == task_id,
        AIReviewRun.item_id == item_id,
        AIReviewRun.trigger_type == trigger_type,  # Same trigger only
        AIReviewRun.status.in_(["failed", "fallback_required"])
    ).all()
    if failed_runs:
        latest = max(failed_runs, key=lambda r: r.id)
        if latest.retry_count is not None and latest.retry_count >= MAX_RETRY_COUNT:
            latest.status = "fallback_required"
            latest.updated_at = datetime.now(timezone.utc)
            db.commit()
            return latest

    provider = get_ai_provider()
    run = AIReviewRun(
        task_id=task_id,
        item_id=item_id,
        annotation_id=annotation_id,
        submission_id=submission_id,
        labeler_id=labeler_id or 2,
        prompt_template_id=None,
        prompt_version=DEFAULT_AGENT_CONFIG["prompt_version"],
        model_provider=provider.get_provider_name(),
        model_name=provider.get_model_name(),
        base_url=getattr(provider, "get_base_url", lambda: "")(),
        input_snapshot_json=input_snapshot or {},
        output_json=None,
        score=None,
        risk_level=None,
        suggestion_action=None,
        confidence=None,
        status="pending",
        error_type=None,
        error_message=None,
        raw_response_preview=None,
        used_fallback=False,
        retry_count=0,
        latency_ms=None,
        token_usage_json=None,
        trigger_type=trigger_type,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        log_action(
            db=db, user_id=0, action=AuditAction.AGENT_ENQUEUE,
            target_type=AuditTargetType.AI_REVIEW, target_id=run.id,
            role="system", action_label="AI Agent 入队",
            task_id=task_id, item_id=item_id,
            submission_id=submission_id, work_key=work_key,
            message=f"AIReviewRun #{run.id} 入队 (trigger={trigger_type})",
            payload_json={"run_id": run.id, "status": "pending", "trigger_type": trigger_type, "annotation_id": annotation_id}
        )
    except Exception:
        pass

    return run


def execute_agent_run(db: Session, run: AIReviewRun) -> AIReviewRun:
    run.status = "running"
    run.updated_at = datetime.now(timezone.utc)
    db.commit()

    try:
        log_action(
            db=db, user_id=0, action=AuditAction.AGENT_RUN_START,
            target_type=AuditTargetType.AI_REVIEW, target_id=run.id,
            role="system", action_label="AI Agent 开始执行",
            task_id=run.task_id, item_id=run.item_id,
            submission_id=run.submission_id, annotation_id=run.annotation_id,
            work_key=f"{run.task_id}:{run.item_id}:{run.labeler_id or 2}",
            message=f"AIReviewRun #{run.id} 开始执行",
            payload_json={"run_id": run.id, "retry_count": run.retry_count, "provider": provider_name, "model": model_name}
        )
    except Exception:
        pass

    start_time = time.time()
    provider = get_ai_provider()
    is_mock = provider.get_provider_name() == "mock"
    provider_name = provider.get_provider_name()
    model_name = provider.get_model_name()
    base_url = getattr(provider, "get_base_url", lambda: "")()

    # 读取运行时配置以获取 mock_fallback 设置
    from app.services.ai_config_service import get_runtime_config
    runtime_config = get_runtime_config()
    mock_fallback = bool(runtime_config.get("mock_fallback", True))

    # 把 provider / model / base_url 写入 run 记录
    run.model_provider = provider_name
    run.model_name = model_name
    run.base_url = base_url
    db.commit()

    try:
        if is_mock:
            result = _run_mock_agent(run)
        else:
            result = _run_real_agent(provider, run)

        latency_ms = int((time.time() - start_time) * 1000)

        run.output_json = result
        run.score = result.get("overall_score")
        run.risk_level = result.get("risk_level")
        run.suggestion_action = result.get("suggested_action")
        run.confidence = result.get("confidence")
        run.status = "success"
        run.latency_ms = latency_ms
        run.used_fallback = False
        run.error_type = None
        run.error_message = None
        run.raw_response_preview = None
        run.model_provider = provider_name
        run.model_name = model_name
        run.base_url = base_url
        run.prompt_version = DEFAULT_AGENT_CONFIG["prompt_version"]
        run.updated_at = datetime.now(timezone.utc)

        if result.get("fallback"):
            # mock 兜底成功：状态保持 success，但标记 used_fallback
            run.output_json["fallback"] = True
            run.used_fallback = True

        db.commit()

        try:
            log_action(
                db=db, user_id=0, action=AuditAction.AGENT_RUN_SUCCESS,
                target_type=AuditTargetType.AI_REVIEW, target_id=run.id,
                role="system", action_label="AI Agent 执行成功",
                task_id=run.task_id, item_id=run.item_id,
                submission_id=run.submission_id, annotation_id=run.annotation_id,
                work_key=f"{run.task_id}:{run.item_id}:{run.labeler_id or 2}",
                message=f"AIReviewRun #{run.id} 执行成功，分数={run.score}{' (mock兜底)' if run.used_fallback else ''}",
                payload_json={
                    "run_id": run.id,
                    "score": run.score,
                    "risk_level": run.risk_level,
                    "suggestion_action": run.suggestion_action,
                    "latency_ms": latency_ms,
                    "provider": provider_name,
                    "model": model_name,
                    "used_fallback": run.used_fallback,
                }
            )
        except Exception:
            pass

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        err_type, err_msg = classify_error(e, None)
        # err_msg 是简短描述，error_message 保留完整堆栈/原始消息
        full_error_msg = str(e)[:500] if str(e) else err_msg
        logger.error(
            f"[agent] run #{run.id} failed provider={provider_name}/{model_name} "
            f"err_type={err_type} latency_ms={latency_ms} msg={str(e)[:200]}"
        )

        if not is_mock and mock_fallback:
            try:
                fallback_result = _run_mock_agent(run)
                fallback_result["fallback"] = True
                fallback_result["fallback_used"] = True
                fallback_result["fallback_provider"] = "mock"
                fallback_result["fallback_reason"] = f"{err_type}: {err_msg}"

                run.output_json = fallback_result
                run.score = fallback_result.get("overall_score")
                run.risk_level = fallback_result.get("risk_level")
                run.suggestion_action = fallback_result.get("suggested_action")
                run.confidence = fallback_result.get("confidence")
                run.status = "success"
                run.latency_ms = latency_ms
                run.used_fallback = True
                run.error_type = err_type
                run.error_message = full_error_msg
                run.raw_response_preview = None
                run.model_provider = provider_name
                run.model_name = model_name
                run.base_url = base_url
                run.updated_at = datetime.now(timezone.utc)
                db.commit()

                try:
                    log_action(
                        db=db, user_id=0, action=AuditAction.AGENT_FALLBACK_REQUIRED,
                        target_type=AuditTargetType.AI_REVIEW, target_id=run.id,
                        role="system", action_label="AI Agent 模型失败，mock 兜底",
                        task_id=run.task_id, item_id=run.item_id,
                        submission_id=run.submission_id, annotation_id=run.annotation_id,
                        work_key=f"{run.task_id}:{run.item_id}:{run.labeler_id or 2}",
                        message=(
                            f"AIReviewRun #{run.id} 真实模型失败({err_type})，已使用 mock 兜底: {err_msg[:200]}"
                        ),
                        payload_json={
                            "run_id": run.id,
                            "error_type": err_type,
                            "error_message": err_msg,
                            "fallback": True,
                            "fallback_provider": "mock",
                            "submission_id": run.submission_id,
                        }
                    )
                except Exception:
                    pass

                return run
            except Exception as fb_exc:
                logger.error(f"[agent] run #{run.id} mock fallback also failed: {fb_exc}")

        # mock_fallback=False 或 mock 兜底也失败 -> 真实失败
        run.status = "failed"
        run.error_type = err_type
        run.error_message = full_error_msg
        run.raw_response_preview = None
        run.latency_ms = latency_ms
        run.retry_count = (run.retry_count or 0) + 1
        run.used_fallback = False
        run.model_provider = provider_name
        run.model_name = model_name
        run.base_url = base_url
        run.updated_at = datetime.now(timezone.utc)
        db.commit()

        if run.retry_count >= MAX_RETRY_COUNT:
            run.status = "fallback_required"
            db.commit()
            try:
                log_action(
                    db=db, user_id=0, action=AuditAction.AGENT_FALLBACK_REQUIRED,
                    target_type=AuditTargetType.AI_REVIEW, target_id=run.id,
                    role="system", action_label="AI Agent 需人工兜底",
                    task_id=run.task_id, item_id=run.item_id,
                    submission_id=run.submission_id, annotation_id=run.annotation_id,
                    work_key=f"{run.task_id}:{run.item_id}:{run.labeler_id or 2}",
                    message=f"AIReviewRun #{run.id} 超过最大重试次数，需人工兜底",
                    payload_json={"run_id": run.id, "retry_count": run.retry_count, "error_type": err_type, "submission_id": run.submission_id}
                )
            except Exception:
                pass
        else:
            try:
                log_action(
                    db=db, user_id=0, action=AuditAction.AGENT_RUN_FAILED,
                    target_type=AuditTargetType.AI_REVIEW, target_id=run.id,
                    role="system", action_label="AI Agent 执行失败",
                    task_id=run.task_id, item_id=run.item_id,
                    submission_id=run.submission_id, annotation_id=run.annotation_id,
                    work_key=f"{run.task_id}:{run.item_id}:{run.labeler_id or 2}",
                    message=f"AIReviewRun #{run.id} 执行失败({err_type}): {err_msg[:200]}",
                    payload_json={"run_id": run.id, "error_type": err_type, "error_message": err_msg, "retry_count": run.retry_count, "submission_id": run.submission_id}
                )
            except Exception:
                pass

    return run


def run_pending_queue(db: Session, limit: int = 10) -> List[AIReviewRun]:
    pending_runs = db.query(AIReviewRun).filter(
        AIReviewRun.status == "pending"
    ).order_by(AIReviewRun.id.asc()).limit(limit).all()

    results = []
    for run in pending_runs:
        executed = execute_agent_run(db, run)
        results.append(executed)

    return results


def retry_agent_run(db: Session, run_id: int) -> AIReviewRun:
    run = db.query(AIReviewRun).filter(AIReviewRun.id == run_id).first()
    if not run:
        return None

    if run.status not in ("failed", "fallback_required"):
        return run

    current_retry = (run.retry_count or 0)
    if current_retry >= MAX_RETRY_COUNT:
        run.status = "fallback_required"
        run.updated_at = datetime.now(timezone.utc)
        db.commit()
        try:
            log_action(
                db=db, user_id=0, action=AuditAction.AGENT_FALLBACK_REQUIRED,
                target_type=AuditTargetType.AI_REVIEW, target_id=run.id,
                role="system", action_label="AI Agent 需人工兜底",
                task_id=run.task_id, item_id=run.item_id,
                submission_id=run.submission_id, annotation_id=run.annotation_id,
                work_key=f"{run.task_id}:{run.item_id}:{run.labeler_id or 2}",
                message=f"AIReviewRun #{run.id} 超过最大重试次数({MAX_RETRY_COUNT})，需人工兜底",
                payload_json={"run_id": run.id, "retry_count": run.retry_count}
            )
        except Exception:
            pass
        return run

    run.retry_count = current_retry + 1
    run.status = "pending"
    run.error_message = None
    run.error_type = None
    run.raw_response_preview = None
    run.updated_at = datetime.now(timezone.utc)
    db.commit()

    try:
        log_action(
            db=db, user_id=0, action=AuditAction.AGENT_RETRY,
            target_type=AuditTargetType.AI_REVIEW, target_id=run.id,
            role="system", action_label="AI Agent 重试",
            task_id=run.task_id, item_id=run.item_id,
            submission_id=run.submission_id, annotation_id=run.annotation_id,
            work_key=f"{run.task_id}:{run.item_id}:{run.labeler_id or 2}",
            message=f"AIReviewRun #{run.id} 重试 (第{run.retry_count}次)",
            payload_json={"run_id": run.id, "retry_count": run.retry_count, "submission_id": run.submission_id}
        )
    except Exception:
        pass

    return execute_agent_run(db, run)


def rerun_ai_review(db: Session, submission_id: int) -> Dict[str, Any]:
    """Re-run AI review for a submission using current provider config (qwen3.7-plus).
    Creates a NEW AIReviewRun record; does NOT overwrite the old one.
    """
    from app.models.submission import Submission
    from app.models.dataset_item import DatasetItem
    from app.models.task import Task

    # Find the submission
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub:
        return {"success": False, "error": f"Submission #{submission_id} not found"}

    task_id = sub.task_id
    item_id = sub.dataset_item_id

    # Get original run for context
    old_run = db.query(AIReviewRun).filter(
        AIReviewRun.submission_id == submission_id
    ).order_by(AIReviewRun.id.desc()).first()

    # Build input snapshot from submission data
    input_snapshot = {
        "dataset_type": "qa_quality",
        "trigger_type": "reviewer_rerun",
        "prompt_profile": "labelhub_qa_quality_v1",
        "result_data": sub.result_data if hasattr(sub, 'result_data') else {},
        "item_data": {},
    }

    # Try to detect dataset_type from task
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task and task.name and "preference_compare" in task.name:
            input_snapshot["dataset_type"] = "preference_compare"
            input_snapshot["prompt_profile"] = "labeler_assist_preference_compare_v1"
    except Exception:
        pass

    # Enrich with dataset item data
    try:
        di = db.query(DatasetItem).filter(DatasetItem.id == item_id).first()
        if di and di.raw_data_json:
            input_snapshot["item_data"] = di.raw_data_json
            if input_snapshot["dataset_type"] == "preference_compare":
                for k in ("prompt", "response_a", "response_b", "model_a", "model_b"):
                    if not input_snapshot["item_data"].get(k):
                        input_snapshot["item_data"][k] = di.raw_data_json.get(k, "")
    except Exception:
        pass

    # Merge old run input if available
    if old_run and old_run.input_snapshot_json:
        old_inp = old_run.input_snapshot_json
        if old_inp.get("item_data"):
            for k, v in old_inp["item_data"].items():
                if not input_snapshot["item_data"].get(k):
                    input_snapshot["item_data"][k] = v
        if old_inp.get("dataset_type"):
            input_snapshot["dataset_type"] = old_inp["dataset_type"]
        if old_inp.get("result_data"):
            input_snapshot["result_data"] = old_inp["result_data"]

    # Create new run
    new_run = enqueue_ai_review_run(
        db=db,
        task_id=task_id,
        item_id=item_id,
        labeler_id=sub.labeler_id or 2,
        work_key=f"{task_id}:{item_id}:{sub.labeler_id or 2}",
        input_snapshot=input_snapshot,
        trigger_type="reviewer_rerun",
        submission_id=submission_id,
        annotation_id=sub.annotation_id if hasattr(sub, 'annotation_id') else None,
    )

    # Execute
    completed_run = execute_agent_run(db, new_run)

    # Audit log
    try:
        log_action(
            db=db, user_id=1, action=AuditAction.AI_REVIEW_RERUN,
            target_type=AuditTargetType.AI_REVIEW, target_id=completed_run.id,
            role="reviewer", action_label="AI 预审重新运行",
            task_id=task_id, item_id=item_id,
            submission_id=submission_id,
            annotation_id=sub.annotation_id if hasattr(sub, 'annotation_id') else None,
            work_key=f"{task_id}:{item_id}:{sub.labeler_id or 2}",
            message=f"AI 预审重新运行: 新 Run #{completed_run.id}，模型 {completed_run.model_name}",
            payload_json={
                "new_run_id": completed_run.id,
                "old_run_id": old_run.id if old_run else None,
                "submission_id": submission_id,
                "model_name": completed_run.model_name,
            }
        )
    except Exception:
        pass

    return {
        "success": completed_run.status == "success",
        "run_id": completed_run.id,
        "old_run_id": old_run.id if old_run else None,
        "model_name": completed_run.model_name,
        "model_provider": completed_run.model_provider,
        "score": completed_run.score,
        "risk_level": completed_run.risk_level,
        "status": completed_run.status,
        "output_json": completed_run.output_json,
    }


def get_agent_runs(
    db: Session,
    status: Optional[str] = None,
    task_id: Optional[int] = None,
    item_id: Optional[int] = None,
    trigger_type: Optional[str] = None,
    page: int = 1,
    limit: int = 20
) -> Dict[str, Any]:
    query = db.query(AIReviewRun)

    if status:
        query = query.filter(AIReviewRun.status == status)
    if task_id:
        query = query.filter(AIReviewRun.task_id == task_id)
    if item_id:
        query = query.filter(AIReviewRun.item_id == item_id)
    if trigger_type:
        # 支持逗号分隔的多值：trigger_type=auto_on_submit,manual_review_run
        types = [t.strip() for t in trigger_type.split(",") if t.strip()]
        if types:
            query = query.filter(AIReviewRun.trigger_type.in_(types))

    total = query.count()
    items = query.order_by(AIReviewRun.id.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "items": [_serialize_run(r) for r in items],
        "total": total,
        "page": page,
        "limit": limit
    }


def get_agent_run_detail(db: Session, run_id: int) -> Optional[Dict[str, Any]]:
    run = db.query(AIReviewRun).filter(AIReviewRun.id == run_id).first()
    if not run:
        return None
    return _serialize_run(run, detail=True)


def get_agent_stats(db: Session, task_id: Optional[int] = None) -> Dict[str, Any]:
    query = db.query(AIReviewRun)
    if task_id:
        query = query.filter(AIReviewRun.task_id == task_id)

    runs = query.all()
    pending = sum(1 for r in runs if r.status == "pending")
    running = sum(1 for r in runs if r.status == "running")
    success = sum(1 for r in runs if r.status == "success")
    failed = sum(1 for r in runs if r.status == "failed")
    fallback = sum(1 for r in runs if r.status == "fallback_required")

    scores = [r.score for r in runs if r.score is not None]
    latencies = [r.latency_ms for r in runs if r.latency_ms is not None]
    retries = [r.retry_count for r in runs if r.retry_count and r.retry_count > 0]

    return {
        "pending": pending,
        "running": running,
        "success": success,
        "failed": failed,
        "fallback_required": fallback,
        "total": len(runs),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "total_retries": sum(retries) if retries else 0
    }


def build_agent_input_context(input_data: Dict) -> Dict:
    """根据 dataset_type 构建 AI Agent 输入上下文。"""
    item_data = input_data.get("item_data") or {}
    result_data = input_data.get("result_data") or {}
    human_result = input_data.get("human_result") or result_data
    dataset_type = input_data.get("dataset_type") or item_data.get("dataset_type") or "qa_quality"

    ctx = {"dataset_type": dataset_type}

    if dataset_type == "preference_compare":
        ctx.update({
            "official_id": item_data.get("official_id", ""),
            "task_type": item_data.get("task_type", ""),
            "lang": item_data.get("lang", "zh"),
            "prompt": item_data.get("prompt", ""),
            "response_a": item_data.get("response_a", ""),
            "response_b": item_data.get("response_b", ""),
            "model_a": item_data.get("model_a", ""),
            "model_b": item_data.get("model_b", ""),
            "dimensions": item_data.get("dimensions", []),
        })
        # 人工标注结果（仅在提交后审核时才有）
        if human_result:
            ctx["human_submission"] = {
                "preferred": human_result.get("preferred"),
                "margin": human_result.get("margin"),
                "dimensions": human_result.get("dimensions"),
                "safety_flag": human_result.get("safety_flag"),
                "summary": human_result.get("summary"),
                "annotator_note": human_result.get("annotator_note"),
            }
    else:
        # qa_quality (default)
        ctx.update({
            "official_id": item_data.get("official_id", ""),
            "prompt": item_data.get("prompt") or item_data.get("question", ""),
            "model_answer": item_data.get("model_answer") or item_data.get("answer", ""),
            "reference": item_data.get("reference") or item_data.get("reference_answer", ""),
            "category": item_data.get("category", ""),
            "difficulty": item_data.get("difficulty", ""),
            "lang": item_data.get("lang", "zh"),
            "media_type": item_data.get("media_type", ""),
            "media_url": item_data.get("media_url", ""),
            "content_markdown": item_data.get("content_markdown", ""),
            "expected_dimensions": item_data.get("expected_dimensions", []),
        })

    return ctx


def _run_real_agent(provider: AIProvider, run: AIReviewRun) -> Dict[str, Any]:
    """使用真实 AI 模型执行审核，返回结构化结果。"""
    input_data = run.input_snapshot_json or {}
    item_data = input_data.get("item_data") or {}
    result_data = input_data.get("result_data") or {}
    schema_json = input_data.get("schema_json") or {}
    dataset_type = input_data.get("dataset_type") or item_data.get("dataset_type") or "qa_quality"

    # Build context based on dataset_type
    ctx = build_agent_input_context(input_data)

    # Build prompt
    if dataset_type == "preference_compare":
        prompt_parts = [
            "请评估以下偏好对比标注数据：\n",
            f"## 用户问题 (prompt)\n{ctx.get('prompt', '')}\n",
            f"## 回答 A\n{ctx.get('response_a', '')}\n",
            f"## 回答 B\n{ctx.get('response_b', '')}\n",
            f"## 模型信息\nmodel_a: {ctx.get('model_a', '')}  model_b: {ctx.get('model_b', '')}\n",
            f"## 任务类型\n{ctx.get('task_type', '')}\n",
        ]
        human_sub = ctx.get("human_submission")
        if human_sub:
            prompt_parts.append(f"## 标注员提交\n{json.dumps(human_sub, ensure_ascii=False, indent=2)}\n")
        else:
            prompt_parts.append("## 标注员提交\n（尚未提交，请仅基于内容独立判断 A/B 偏好）\n")
        prompt_parts.append("\n请严格按照JSON Schema输出评估结果。")
        system_prompt = PREFERENCE_COMPARE_SYSTEM_PROMPT
    else:
        prompt_parts = [
            "请评估以下标注数据的质量：\n",
            f"## 原始题目\n{ctx.get('prompt', '')}\n",
            f"## 模型回答\n{ctx.get('model_answer', '')}\n",
            f"## 参考答案\n{ctx.get('reference', '')}\n",
            f"## 人工标注结果\n{json.dumps(result_data, ensure_ascii=False, indent=2) if result_data else '无'}\n",
        ]
        if schema_json:
            prompt_parts.append(f"## 标注模板 Schema\n{json.dumps(schema_json, ensure_ascii=False, indent=2)}\n")
        prompt_parts.append("\n请严格按照JSON Schema输出评估结果。")
        system_prompt = SYSTEM_PROMPT

    prompt = "\n".join(prompt_parts)

    response = provider.generate(prompt, system_prompt=system_prompt)

    if response.get("error") or response.get("error_type"):
        err_type = response.get("error_type") or "unknown_error"
        err_msg = response.get("error_message") or "AI模型调用失败"
        # 携带分类好的错误信息和原始响应片段返回给上层
        preview = (response.get("raw_text") or "")[:500]
        raise RuntimeError(
            f"AI模型调用失败 [{err_type}]: {err_msg} | raw_preview={preview}"
        )

    raw_text = response.get("raw_text", "")
    parsed = response.get("parsed")

    # Try to parse JSON if not already parsed
    if not parsed and raw_text:
        from app.services.ai_provider import _extract_json_object
        parsed = _extract_json_object(raw_text)

    if not parsed or not isinstance(parsed, dict):
        preview = raw_text[:500] if raw_text else "(empty)"
        raise RuntimeError(
            f"AI模型返回非JSON格式 [json_parse_error]: 原始响应前500字符={preview}"
        )

    # Validate required fields
    result = _validate_and_normalize_agent_output(parsed)

    # Store token usage if available
    if response.get("token_usage"):
        result["_token_usage"] = response["token_usage"]

    return result


def _validate_and_normalize_agent_output(data: Dict) -> Dict:
    """验证并规范化 Agent 输出，确保包含所有必需字段。

    同时支持 qa_quality（relevance/accuracy/completeness/safety）
    和 preference_compare（preferred/margin/dimensions/safety_flag）两种输出格式。
    """
    result = {
        "overall_score": data.get("overall_score", data.get("score", 0)),
        "risk_level": data.get("risk_level", "medium"),
        "suggested_action": data.get("suggested_action", data.get("suggestion_action", data.get("action", "manual_review"))),
        "confidence": data.get("confidence", 0.5),
        "summary": data.get("summary", ""),
        "reason": data.get("reason", data.get("annotator_note", "")),
        "dimension_scores": data.get("dimension_scores", {}),
        "issue_tags": data.get("issue_tags", []),
        "suggested_fix": data.get("suggested_fix", ""),
    }

    # preference_compare 特有字段
    if "preferred" in data:
        result["preferred"] = data["preferred"] if data["preferred"] in ("A", "B", "tie") else "tie"
    if "margin" in data:
        valid_margins = ("明显优于", "略优于", "相当")
        result["margin"] = data["margin"] if data["margin"] in valid_margins else "相当"
    if "dimensions" in data and isinstance(data["dimensions"], list):
        result["pref_dimensions"] = data["dimensions"]
    if "safety_flag" in data:
        result["safety_flag"] = bool(data["safety_flag"])
    # action 字段映射到 suggested_action
    action_val = data.get("action")
    if action_val and not data.get("suggested_action"):
        action_map = {"approve": "submit", "manual_review": "manual_review", "revise": "rework"}
        result["suggested_action"] = action_map.get(action_val, "manual_review")

    # Normalize risk_level
    if result["risk_level"] not in ("low", "medium", "high"):
        result["risk_level"] = "medium"

    # Normalize suggested_action
    action = result["suggested_action"]
    if action not in ("submit", "reject", "manual_review", "rework"):
        result["suggested_action"] = "manual_review"

    # Ensure score is int
    try:
        result["overall_score"] = int(result["overall_score"])
    except (TypeError, ValueError):
        result["overall_score"] = 0

    # Ensure confidence is float
    try:
        result["confidence"] = float(result["confidence"])
    except (TypeError, ValueError):
        result["confidence"] = 0.5

    return result


def _run_mock_agent(run: AIReviewRun) -> Dict[str, Any]:
    input_data = run.input_snapshot_json or {}
    result_data = input_data.get("result_data") or input_data.get("annotation_result") or {}
    dataset_type = input_data.get("dataset_type") or (input_data.get("item_data") or {}).get("dataset_type") or "qa_quality"

    base_score = random.randint(65, 95)
    has_issues = False

    if dataset_type == "preference_compare":
        # preference_compare mock: evaluate preferred/margin/dimensions/safety_flag
        human_sub = result_data if isinstance(result_data, dict) else {}
        preferred = human_sub.get("preferred")
        margin = human_sub.get("margin")
        annotator_note = human_sub.get("annotator_note", "")

        # AI 随机独立判断
        ai_preferred = random.choice(["A", "B", "tie"])
        ai_margin = random.choice(["明显优于", "略优于", "相当"])
        ai_dims = random.sample(["准确性", "完整性", "可读性", "逻辑性", "安全性"], k=random.randint(2, 4))
        ai_safety = random.random() < 0.1

        # 如果人工结果与 AI 判断不一致，降分
        if preferred and preferred != ai_preferred:
            base_score = max(base_score - 15, 40)
            has_issues = True
        if margin and margin != ai_margin:
            base_score = max(base_score - 5, 45)
        if isinstance(annotator_note, str) and len(annotator_note) < 10:
            base_score = max(base_score - 10, 50)
            has_issues = True

        if base_score >= 80:
            risk_level = "low"
            suggested_action = "submit"
        elif base_score >= 70:
            risk_level = "medium"
            suggested_action = "manual_review"
        else:
            risk_level = "high"
            suggested_action = "rework"

        issue_tags = []
        if has_issues:
            issue_tags.append("preferred_mismatch")
        if isinstance(annotator_note, str) and len(annotator_note) < 10:
            issue_tags.append("annotator_note_too_short")
        if base_score < 70:
            issue_tags.append("low_quality")

        return {
            "overall_score": base_score,
            "preferred": ai_preferred,
            "margin": ai_margin,
            "dimensions": ai_dims,
            "safety_flag": ai_safety,
            "risk_level": risk_level,
            "suggested_action": suggested_action,
            "confidence": round(random.uniform(0.7, 0.95), 2),
            "summary": "标注员偏好判断合理" if base_score >= 80 else ("偏好判断存在争议" if base_score >= 70 else "偏好判断明显有误，建议返修"),
            "reason": "标注员选择与 AI 独立判断一致" if not has_issues else "标注员选择与 AI 判断不一致或理由不充分",
            "dimension_scores": {},
            "pref_dimensions": ai_dims,
            "issue_tags": issue_tags,
            "suggested_fix": "建议补充判断依据" if has_issues else "",
        }

    # qa_quality mock (default)
    if isinstance(result_data, dict):
        reason = result_data.get("reason", "")
        if isinstance(reason, str) and len(reason) < 10:
            base_score = max(base_score - 10, 50)
            has_issues = True

        for dim in ["relevance", "accuracy", "completeness", "safety"]:
            if not result_data.get(dim):
                base_score = max(base_score - 5, 50)
                has_issues = True

    if base_score >= 80:
        risk_level = "low"
        suggested_action = "submit"
    elif base_score >= 70:
        risk_level = "medium"
        suggested_action = "manual_review"
    else:
        risk_level = "high"
        suggested_action = "rework"

    dim_scores = {}
    for dim in ["relevance", "accuracy", "completeness", "safety"]:
        dim_base = base_score + random.randint(-10, 10)
        dim_base = max(0, min(100, dim_base))
        labels = {
            "relevance": ["high", "medium", "low"],
            "accuracy": ["correct", "partially_correct", "incorrect"],
            "completeness": ["complete", "partial", "incomplete"],
            "safety": ["safe", "caution", "risk"]
        }
        label_idx = 0 if dim_base >= 80 else (1 if dim_base >= 60 else 2)
        dim_scores[dim] = {
            "value": labels.get(dim, ["high", "medium", "low"])[label_idx],
            "score": dim_base
        }

    issue_tags = []
    if has_issues:
        issue_tags.append("reason_too_short")
    if base_score < 70:
        issue_tags.append("low_quality")

    return {
        "overall_score": base_score,
        "risk_level": risk_level,
        "suggested_action": suggested_action,
        "confidence": round(random.uniform(0.7, 0.95), 2),
        "summary": "整体标注较完整" if base_score >= 80 else ("标注存在部分问题" if base_score >= 70 else "标注质量较低，建议返修"),
        "reason": "理由偏短，但核心判断基本正确" if has_issues and base_score >= 70 else ("各项维度评分正常" if base_score >= 80 else "多项维度评分偏低"),
        "dimension_scores": dim_scores,
        "issue_tags": issue_tags,
        "suggested_fix": "建议补充理由说明" if has_issues else ""
    }


def _serialize_run(run: AIReviewRun, detail: bool = False) -> Dict[str, Any]:
    data = {
        "id": run.id,
        "task_id": run.task_id,
        "item_id": run.item_id,
        "annotation_id": run.annotation_id,
        "submission_id": run.submission_id,
        "labeler_id": run.labeler_id,
        "status": run.status,
        "score": run.score,
        "risk_level": run.risk_level,
        "suggestion_action": run.suggestion_action,
        "confidence": run.confidence,
        "provider": run.model_provider,
        "model_provider": run.model_provider,
        "model_name": run.model_name,
        "base_url": run.base_url,
        "prompt_version": run.prompt_version,
        "retry_count": run.retry_count or 0,
        "trigger_type": run.trigger_type,
        "latency_ms": run.latency_ms,
        "error_type": run.error_type,
        "error_message": run.error_message,
        "raw_response_preview": run.raw_response_preview,
        "used_fallback": bool(run.used_fallback) if run.used_fallback is not None else False,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }
    if detail:
        data["input_snapshot_json"] = run.input_snapshot_json
        data["output_json"] = run.output_json
        data["token_usage_json"] = run.token_usage_json
        data["prompt_template_id"] = run.prompt_template_id
    return data


def _update_annotation_after_agent(
    db: Session,
    run: AIReviewRun,
    annotation_id: Optional[int],
    item_id: int,
    task_id: int,
):
    """Agent 执行完成后回写 annotations.json 的 ai_review 字段和 DatasetItem.annotation_phase。

    此函数在 BackgroundTasks 中调用，使用独立的 db session。
    AI 失败时仍然更新 annotation_phase（标记为 annotation_qc），但不写入 ai_review 评分。
    """
    from app.models.dataset_item import DatasetItem

    # 1. 回写 annotations.json 的 ai_review 字段
    if annotation_id is not None:
        try:
            from app.services.annotation_service import _load_annotations, _save_annotations
            annotations = _load_annotations()
            for idx, ann in enumerate(annotations):
                if ann.get("id") == annotation_id:
                    ai_review = {
                        "run_id": run.id,
                        "status": run.status,
                        "score": run.score,
                        "risk_level": run.risk_level,
                        "suggestion": run.suggestion_action,
                        "trigger_type": run.trigger_type or "auto_on_submit",
                        "confidence": run.confidence,
                        "summary": (run.output_json or {}).get("summary", "") if run.output_json else "",
                        "reason": (run.output_json or {}).get("reason", "") if run.output_json else "",
                        "dimension_scores": (run.output_json or {}).get("dimension_scores", {}) if run.output_json else {},
                        "issue_tags": (run.output_json or {}).get("issue_tags", []) if run.output_json else [],
                        "used_fallback": bool(run.used_fallback),
                    }
                    if run.status == "failed":
                        ai_review["error"] = run.error_message
                        ai_review["error_type"] = run.error_type
                    if run.status == "fallback_required":
                        ai_review["error"] = run.error_message
                        ai_review["fallback_required"] = True
                    annotations[idx]["ai_review"] = ai_review
                    break
            _save_annotations(annotations)
            logger.debug(f"[agent_post] annotations.json ai_review updated for annotation #{annotation_id}")
        except Exception as e:
            logger.error(f"[agent_post] failed to update annotations.json for annotation #{annotation_id}: {e}")

    # 2. 更新 DatasetItem.annotation_phase = annotation_qc
    try:
        item = db.query(DatasetItem).filter(DatasetItem.id == item_id).first()
        if item:
            item.annotation_phase = "annotation_qc"
            db.commit()
            logger.debug(f"[agent_post] DatasetItem #{item_id} annotation_phase -> annotation_qc")
    except Exception as e:
        logger.error(f"[agent_post] failed to update annotation_phase for item #{item_id}: {e}")
