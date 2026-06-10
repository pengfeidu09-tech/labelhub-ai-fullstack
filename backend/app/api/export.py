from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any
import json
import csv
import io
import os
import logging


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/export", tags=["export"])

ANNOTATIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "annotations.json")


def _load_annotations():
    if os.path.exists(ANNOTATIONS_FILE):
        with open(ANNOTATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _build_export_rows() -> List[Dict[str, Any]]:
    annotations = _load_annotations()
    rows = []
    for a in annotations:
        task_id = a.get("task_id", "")
        dataset_item_id = a.get("dataset_item_id", "")
        labeler_id = a.get("labeler_id", "")
        work_key = a.get("work_key") or f"{task_id}:{dataset_item_id}:{labeler_id}"
        ai_review = a.get("ai_review")
        rows.append({
            "annotation_id": a.get("annotation_id"),
            "task_id": task_id,
            "dataset_item_id": dataset_item_id,
            "labeler_id": labeler_id,
            "work_key": work_key,
            "status": a.get("status"),
            "result_data": a.get("result_data"),
            "review_reason": a.get("review_reason"),
            "reviewer_id": a.get("reviewer_id"),
            "reviewed_at": a.get("reviewed_at"),
            "created_at": a.get("created_at"),
            "updated_at": a.get("updated_at"),
            "duration_seconds": a.get("duration_seconds"),
            "ai_score": ai_review.get("score") if isinstance(ai_review, dict) else None,
            "ai_risk_level": ai_review.get("risk_level") if isinstance(ai_review, dict) else None,
            "ai_passed": ai_review.get("passed") if isinstance(ai_review, dict) else None,
            "ai_review_summary": ai_review.get("summary") if isinstance(ai_review, dict) else None,
            "ai_review_json": json.dumps(ai_review, ensure_ascii=False) if ai_review else None,
        })
    return rows


@router.get("/annotations")
def export_annotations(format: str = Query("json")):
    rows = _build_export_rows()

    # Write audit log
    try:
        from app.services.audit_service import create_audit_log
        from app.core.database import SessionLocal
        audit_db = SessionLocal()
        try:
            create_audit_log(
                db=audit_db,
                user_id=1,
                action="export_create",
                target_type="task",
                target_id=None,
                after_data={"format": format, "task_id": None}
            )
        finally:
            audit_db.close()
    except Exception as audit_err:
        logger.error(f"[export] audit log error: {audit_err}")

    if format == "csv":
        output = io.StringIO()
        columns = [
            "annotation_id", "task_id", "dataset_item_id", "labeler_id",
            "work_key", "status", "result_json", "review_reason",
            "reviewer_id", "reviewed_at", "created_at", "updated_at",
            "ai_score", "ai_risk_level", "ai_passed", "ai_review_summary", "ai_review_json",
        ]
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            csv_row = {k: row.get(k) for k in columns if k != "result_json"}
            csv_row["result_json"] = json.dumps(row.get("result_data"), ensure_ascii=False) if row.get("result_data") is not None else ""
            writer.writerow(csv_row)
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=annotations_export.csv"},
        )

    # default: json
    return StreamingResponse(
        iter([json.dumps(rows, ensure_ascii=False, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=annotations_export.json"},
    )
