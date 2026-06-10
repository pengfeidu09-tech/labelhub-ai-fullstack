from fastapi import APIRouter, Query
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["ai"])


def _detect_dataset_type(request: dict, db=None) -> str:
    """Detect dataset_type from request payload or DB lookup."""
    item_data = request.get("item_data") or {}
    ds = item_data.get("dataset_type")
    if ds:
        return ds

    # Try from schema
    schema = request.get("schema_json") or {}
    if isinstance(schema, dict):
        ds = schema.get("dataset_type")
        if ds:
            return ds

    # Try from task lookup
    task_id = request.get("task_id")
    if task_id and db:
        try:
            from app.models.task import Task
            task = db.query(Task).filter(Task.id == task_id).first()
            if task and task.name and "preference_compare" in task.name:
                return "preference_compare"
        except Exception:
            pass

    return "qa_quality"


@router.post("/precheck")
def precheck_annotation(request: dict) -> Dict[str, Any]:
    """AI 预审：根据 dataset_type 路由到不同引擎。
    - qa_quality: 使用 ai_precheck_pipeline (规则 + LLM-as-Judge)
    - preference_compare: 使用 agent_service (端到端 Agent 链路)
    """
    try:
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            dataset_type = _detect_dataset_type(request, db)

            if dataset_type == "preference_compare":
                result = _run_preference_compare_precheck(db, request)
            else:
                result = _run_qa_quality_precheck(db, request)
        finally:
            db.close()

        # Persist AI review result to annotations.json
        task_id = request.get("task_id", 0)
        dataset_item_id = request.get("dataset_item_id", 0)
        labeler_id = request.get("labeler_id", 2)

        if task_id and dataset_item_id and result.get("success"):
            try:
                from app.services.annotation_service import update_ai_review
                from datetime import datetime
                ai_review_data = {
                    **result,
                    "prechecked_at": datetime.now().isoformat(),
                    "work_key": request.get("work_key", ""),
                    "trigger_type": result.get("trigger_type", "labeler_assist_manual"),
                    "dataset_type": dataset_type,
                }
                update_ai_review(
                    task_id=task_id,
                    dataset_item_id=dataset_item_id,
                    labeler_id=labeler_id,
                    ai_review=ai_review_data
                )
            except Exception as save_err:
                logger.debug(f"[ai_precheck] save error (non-fatal): {save_err}")

        return result

    except Exception as e:
        logger.error(f"[ai_precheck] error: {e}")
        return {
            "success": False,
            "score": 0,
            "risk_level": "high",
            "passed": False,
            "issues": [],
            "suggestions": [],
            "summary": f"AI预审暂不可用: {str(e)}",
        }


def _run_qa_quality_precheck(db, request: dict) -> Dict[str, Any]:
    """Route to ai_precheck_pipeline for qa_quality tasks."""
    from app.services.ai_precheck_pipeline import run_pipeline

    result = run_pipeline(
        db=db,
        task_id=request.get("task_id", 0),
        item_id=request.get("dataset_item_id", 0),
        labeler_id=request.get("labeler_id", 2),
        work_key=request.get("work_key", ""),
        item_data=request.get("item_data", {}),
        result_data=request.get("result_data", {}),
        schema_json=request.get("schema_json"),
        annotation_id=request.get("annotation_id"),
        submission_id=request.get("submission_id"),
    )
    result["trigger_type"] = "labeler_assist_manual"
    result["dataset_type"] = "qa_quality"
    return result


def _run_preference_compare_precheck(db, request: dict) -> Dict[str, Any]:
    """Route to agent_service for preference_compare tasks.
    Uses the full Agent chain with correct prompt profile and input context.
    """
    from app.services.agent_service import enqueue_ai_review_run, execute_agent_run
    from app.models.dataset_item import DatasetItem
    from app.models.task import Task

    task_id = request.get("task_id", 0)
    item_id = request.get("dataset_item_id", 0)
    item_data = request.get("item_data") or {}
    result_data = request.get("result_data") or {}

    # Look up official_id from DatasetItem if available
    official_id = item_data.get("official_id", "")
    if not official_id and item_id:
        try:
            di = db.query(DatasetItem).filter(DatasetItem.id == item_id).first()
            if di:
                official_id = di.official_id or ""
                if di.raw_data_json and isinstance(di.raw_data_json, dict):
                    # Merge raw_data into item_data for any missing fields
                    for k in ("prompt", "response_a", "response_b", "model_a", "model_b",
                              "task_type", "lang", "dimensions", "official_id"):
                        if not item_data.get(k):
                            item_data[k] = di.raw_data_json.get(k, "")
        except Exception:
            pass

    # Build input snapshot with preference_compare context
    input_snapshot = {
        "dataset_type": "preference_compare",
        "official_id": official_id,
        "prompt_profile": "labeler_assist_preference_compare_v1",
        "trigger_type": "labeler_assist_manual",
        "item_data": item_data,
        "result_data": result_data,
    }

    # Validate minimum required fields
    if not item_data.get("prompt") and not item_data.get("response_a"):
        return {
            "success": False,
            "score": 0,
            "risk_level": "medium",
            "summary": "preference_compare 输入不完整：需要 prompt 和 response_a/response_b",
            "error_type": "missing_input_fields",
            "trigger_type": "labeler_assist_manual",
            "dataset_type": "preference_compare",
        }

    try:
        run = enqueue_ai_review_run(
            db=db,
            task_id=task_id,
            item_id=item_id,
            labeler_id=request.get("labeler_id", 2),
            work_key=request.get("work_key", ""),
            input_snapshot=input_snapshot,
            trigger_type="labeler_assist_manual",
        )

        # Only execute if pending; if already completed (existing run), use as-is
        if run.status == "pending":
            completed_run = execute_agent_run(db, run)
        else:
            completed_run = run

        # Convert to frontend-compatible result
        output = completed_run.output_json or {}
        return {
            "success": completed_run.status == "success",
            "score": completed_run.score or output.get("score", 0),
            "risk_level": completed_run.risk_level or output.get("risk_level", "low"),
            "suggestion_action": output.get("action", "suggest_only"),
            "passed": True,
            "confidence": completed_run.confidence or output.get("confidence", 0.0),
            "summary": output.get("summary", ""),
            "reason": output.get("reason", ""),
            "preferred": output.get("preferred"),
            "margin": output.get("margin"),
            "dimensions": output.get("dimensions") or output.get("pref_dimensions"),
            "safety_flag": output.get("safety_flag"),
            "issue_tags": output.get("issue_tags", []),
            "issues": output.get("issues", []),
            "suggestions": output.get("suggestions", []),
            "output_json": output,
            "status": completed_run.status,
            "run_id": completed_run.id,
            "model_provider": completed_run.model_provider,
            "model_name": completed_run.model_name,
            "latency_ms": completed_run.latency_ms,
            "fallback": completed_run.used_fallback or False,
            "fallback_used": completed_run.used_fallback or False,
            "prompt_template": "labeler_assist_preference_compare_v1",
            "prompt_profile": "labeler_assist_preference_compare_v1",
            "trigger_type": "labeler_assist_manual",
            "dataset_type": "preference_compare",
            "error_type": completed_run.error_type,
            "error_message": completed_run.error_message,
            "raw_response_preview": completed_run.raw_response_preview,
        }
    except Exception as e:
        logger.error(f"[ai_precheck] preference_compare pipeline error: {e}")
        return {
            "success": False,
            "score": 0,
            "risk_level": "medium",
            "summary": f"preference_compare AI 辅助暂不可用: {str(e)}",
            "error_type": "pipeline_error",
            "error_message": str(e),
            "trigger_type": "labeler_assist_manual",
            "dataset_type": "preference_compare",
        }


@router.get("/latest-assist")
def get_latest_labeler_assist(
    item_id: int = Query(..., description="Dataset item ID"),
    task_id: Optional[int] = Query(None),
    trigger_type: str = Query("labeler_assist_manual,labeler_assist_on_open",
                              description="Comma-separated trigger types to filter"),
) -> Dict[str, Any]:
    """Query the latest valid labeler_assist result for a specific item.
    Does NOT auto-run — only returns existing results.
    """
    from app.core.database import SessionLocal
    from app.models.ai_review_run import AIReviewRun

    db = SessionLocal()
    try:
        triggers = [t.strip() for t in trigger_type.split(",") if t.strip()]

        query = db.query(AIReviewRun).filter(
            AIReviewRun.item_id == item_id,
            AIReviewRun.trigger_type.in_(triggers),
            AIReviewRun.status.in_(["success", "fallback_required"]),
        )
        if task_id:
            query = query.filter(AIReviewRun.task_id == task_id)

        # Also filter by valid prompt_profile (no qa_quality for preference_compare)
        run = query.order_by(AIReviewRun.id.desc()).first()

        if not run:
            return {"found": False, "result": None}

        output = run.output_json or {}
        inp = run.input_snapshot_json or {}
        return {
            "found": True,
            "result": {
                "run_id": run.id,
                "status": run.status,
                "score": run.score,
                "risk_level": run.risk_level,
                "confidence": run.confidence,
                "trigger_type": run.trigger_type,
                "dataset_type": inp.get("dataset_type", "qa_quality"),
                "prompt_profile": inp.get("prompt_profile", ""),
                "model_provider": run.model_provider,
                "model_name": run.model_name,
                "latency_ms": run.latency_ms,
                "output_json": output,
                "summary": output.get("summary", ""),
                "preferred": output.get("preferred"),
                "margin": output.get("margin"),
                "dimensions": output.get("dimensions") or output.get("pref_dimensions"),
                "safety_flag": output.get("safety_flag"),
                "issue_tags": output.get("issue_tags", []),
                "created_at": run.created_at.isoformat() if run.created_at else None,
            }
        }
    finally:
        db.close()
