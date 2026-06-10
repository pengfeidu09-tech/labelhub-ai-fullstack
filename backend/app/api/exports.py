from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional
import os

from app.core.database import get_db
from app.services.export_service import export_task_data, get_export_jobs, get_submission_export, get_export_job
from app.schemas.export import ExportCreateRequest, ExportListResponse
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.post("/task/{task_id}")
def export_task(
    task_id: int,
    request: ExportCreateRequest,
    db: Session = Depends(get_db),
    user_id: int = Query(1)
):
    job = export_task_data(db, task_id, user_id, request.format)
    return {"job_id": job.id, "status": job.status, "message": "Export started"}


@router.get("", response_model=ExportListResponse)
def get_exports(
    task_id: Optional[int] = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    return get_export_jobs(db, task_id, page, limit)


@router.get("/submission/{submission_id}")
def get_submission_export_endpoint(
    submission_id: int,
    format: str = Query("json"),
    db: Session = Depends(get_db)
):
    result = get_submission_export(db, submission_id, format)
    if not result:
        raise HTTPException(status_code=404, detail="Submission not found")
    return result


@router.get("/{job_id}/download")
def download_export(job_id: int, db: Session = Depends(get_db)):
    job = get_export_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    if job.status != "success":
        raise HTTPException(status_code=400, detail="Export not ready")
    if not job.file_path or not os.path.exists(job.file_path):
        raise HTTPException(status_code=404, detail="Export file not found")
    filename = os.path.basename(job.file_path)
    return FileResponse(path=job.file_path, filename=filename, media_type="application/octet-stream")


@router.get("/{job_id}/snapshot-summary")
def get_snapshot_summary(job_id: int, db: Session = Depends(get_db)):
    import json
    job = get_export_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")

    snapshot_data = {}
    if job.error_message:
        try:
            snapshot_data = json.loads(job.error_message)
        except Exception:
            pass

    if not snapshot_data.get("snapshot_id"):
        ts = job.created_at.strftime('%Y%m%d_%H%M%S') if job.created_at else 'unknown'
        snapshot_data["snapshot_id"] = f"snapshot_task_{job.task_id or 0}_{ts}"

    if not snapshot_data.get("quality_policy_version"):
        snapshot_data["quality_policy_version"] = "quality_policy_v1"

    if not snapshot_data.get("data_filter"):
        snapshot_data["data_filter"] = "approved_only"

    if snapshot_data.get("total_rows") is None:
        snapshot_data["total_rows"] = job.row_count or 0

    snapshot_data["job_id"] = job.id
    snapshot_data["task_id"] = job.task_id
    snapshot_data["format"] = job.format
    snapshot_data["status"] = job.status
    snapshot_data["file_path"] = job.file_path
    snapshot_data["created_at"] = job.created_at.isoformat() if job.created_at else None

    try:
        log_action(
            db=db, user_id=1, action="snapshot_summary_view",
            target_type=AuditTargetType.EXPORT, target_id=job_id,
            role="owner", action_label="查看导出快照摘要",
            task_id=job.task_id, message=f"查看导出快照 #{job_id} 摘要"
        )
    except Exception:
        pass

    return snapshot_data