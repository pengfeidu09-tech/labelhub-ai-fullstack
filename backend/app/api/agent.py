from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.core.database import get_db
from app.services.agent_service import (
    get_agent_runs, get_agent_run_detail, run_pending_queue,
    retry_agent_run, rerun_ai_review, get_agent_config, update_agent_config, get_agent_stats
)
from app.services.ai_provider import get_ai_provider
from app.services.ai_config_service import get_effective_config, update_runtime_config
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])

# 兼容路由：处理旧前端可能发出的 /api/api/agent/... 请求
compat_router = APIRouter(prefix="/api/api/agent", tags=["agent-compat"])


@router.get("/provider-config")
def get_provider_config():
    """获取当前 AI Provider 配置。不返回 API Key 明文。"""
    return get_effective_config()


@router.put("/provider-config")
def save_provider_config(request: dict, db: Session = Depends(get_db)):
    """更新 AI Provider 配置。

    不保存 API Key。provider 只能是 mock 或 dashscope。
    """
    try:
        result = update_runtime_config(request, updated_by="owner")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 写审计日志
    try:
        log_action(
            db=db, user_id=1, action=AuditAction.AGENT_PROVIDER_CONFIG_UPDATE,
            target_type=AuditTargetType.AI_REVIEW, target_id=0,
            role="owner", action_label="更新 AI Provider 配置",
            message=f"Provider 切换为 {request.get('provider', 'unknown')}/{request.get('model', 'unknown')}",
            payload_json=request
        )
    except Exception:
        pass

    return {"success": True, "config": result}


@router.get("/provider-test")
def test_provider():
    """测试当前 AI Provider 连接是否正常。

    返回字段：
    - provider / model / base_url / api_key_present / api_key_length
    - request_url
    - test_status: success / failed / skipped
    - http_status
    - error_type: invalid_api_key / model_not_found / timeout / network_error / json_parse_error / unknown_error / ...
    - error_message
    - raw_response_preview (前 500 字符)
    - latency_ms
    - fallback_available

    测试失败时绝不 fallback 到 mock，便于真实排查错误。
    """
    provider = get_ai_provider()
    result = provider.test_connection()
    # 测试接口不向 mock 兜底；如确需 mock，可走 /api/agent/provider-config
    if result.get("test_status") == "failed":
        logger.warning(
            f"[provider-test] FAILED provider={result.get('provider')} model={result.get('model')} "
            f"err_type={result.get('error_type')} msg={(result.get('error_message') or '')[:200]}"
        )
    return result


@router.get("/runs")
def list_agent_runs(
    status: Optional[str] = None,
    task_id: Optional[int] = None,
    item_id: Optional[int] = None,
    trigger_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    try:
        log_action(
            db=db, user_id=1, action=AuditAction.AGENT_QUEUE_VIEW,
            target_type=AuditTargetType.AI_REVIEW, target_id=0,
            role="owner", action_label="查看 Agent 队列",
            message="查看 AI Agent 运行队列"
        )
    except Exception:
        pass
    return get_agent_runs(db, status=status, task_id=task_id, item_id=item_id, trigger_type=trigger_type, page=page, limit=limit)


@router.get("/runs/stats")
def agent_stats(
    task_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    return get_agent_stats(db, task_id=task_id)


@router.post("/run-pending")
def run_pending(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    results = run_pending_queue(db, limit=limit)
    return {
        "success": True,
        "executed_count": len(results),
        "results": [
            {"run_id": r.id, "status": r.status, "score": r.score, "risk_level": r.risk_level}
            for r in results
        ]
    }


@router.post("/runs/{run_id}/retry")
def retry_run(run_id: int, db: Session = Depends(get_db)):
    result = retry_agent_run(db, run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return {
        "success": True,
        "run_id": result.id,
        "status": result.status,
        "score": result.score,
        "retry_count": result.retry_count
    }


@router.post("/rerun/{submission_id}")
def rerun_review(submission_id: int, db: Session = Depends(get_db)):
    """Re-run AI review for a submission using current provider config.
    Creates a new AIReviewRun record; old run is preserved.
    """
    result = rerun_ai_review(db, submission_id)
    if not result.get("success") and "not found" in result.get("error", ""):
        raise HTTPException(status_code=404, detail=result.get("error", "Submission not found"))
    return result


@router.get("/runs/{run_id}")
def get_run_detail(run_id: int, db: Session = Depends(get_db)):
    result = get_agent_run_detail(db, run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return result


@router.get("/config")
def get_config(task_id: Optional[int] = None, db: Session = Depends(get_db)):
    try:
        log_action(
            db=db, user_id=1, action=AuditAction.AGENT_CONFIG_VIEW,
            target_type=AuditTargetType.TASK, target_id=task_id or 0,
            role="owner", action_label="查看 Agent 配置",
            task_id=task_id, message=f"查看任务 #{task_id} Agent 配置"
        )
    except Exception:
        pass
    return get_agent_config(task_id or 0)


@router.put("/config")
def save_config(request: dict, db: Session = Depends(get_db)):
    task_id = request.get("task_id", 0)
    try:
        log_action(
            db=db, user_id=1, action=AuditAction.AGENT_CONFIG_UPDATE,
            target_type=AuditTargetType.TASK, target_id=task_id,
            role="owner", action_label="更新 Agent 配置",
            task_id=task_id, message=f"更新任务 #{task_id} Agent 配置",
            payload_json=request
        )
    except Exception:
        pass
    result = update_agent_config(task_id, request)
    return {"success": True, "config": result}


# ---- 兼容路由：旧前端 /api/api/agent/... 请求 ----

@compat_router.get("/provider-config")
def compat_get_provider_config():
    """兼容旧前端 /api/api/agent/provider-config 请求。"""
    logger.warning("[compat] /api/api/agent/provider-config hit — frontend path needs fixing")
    return get_effective_config()


@compat_router.put("/provider-config")
def compat_save_provider_config(request: dict, db: Session = Depends(get_db)):
    """兼容旧前端 PUT /api/api/agent/provider-config 请求。"""
    logger.warning("[compat] PUT /api/api/agent/provider-config hit — frontend path needs fixing")
    try:
        result = update_runtime_config(request, updated_by="owner")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "config": result}


@compat_router.get("/provider-test")
def compat_test_provider():
    """兼容旧前端 /api/api/agent/provider-test 请求。"""
    logger.warning("[compat] /api/api/agent/provider-test hit — frontend path needs fixing")
    provider = get_ai_provider()
    return provider.test_connection()
