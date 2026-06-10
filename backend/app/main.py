from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.config import settings
from app.api.health import router as health_router
from app.api.tasks import router as tasks_router
from app.api.templates import router as templates_router
from app.api.datasets import router as datasets_router
from app.api.labeler import router as labeler_router
from app.api.ai_reviews import router as ai_reviews_router
from app.api.reviews import router as reviews_router
from app.api.exports import router as exports_router
from app.api.export import router as export_router
from app.api.audit_logs import router as audit_logs_router
from app.api.owner import router as owner_router
from app.api.dev import router as dev_router
from app.api.ai_precheck import router as ai_precheck_router
from app.api.seed_demo import router as seed_demo_router
from app.api.workbench_session import router as workbench_session_router
from app.api.work_report import router as work_report_router
from app.api.item_actions import router as item_actions_router
from app.api.rubrics import router as rubrics_router
from app.api.quality import router as quality_router
from app.api.dashboard import router as dashboard_router
from app.api.agent import router as agent_router, compat_router as agent_compat_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="LabelHub API", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(tasks_router)
    app.include_router(templates_router)
    app.include_router(datasets_router)
    app.include_router(labeler_router)
    app.include_router(ai_reviews_router)
    app.include_router(reviews_router)
    app.include_router(exports_router)
    app.include_router(export_router)
    app.include_router(audit_logs_router)
    app.include_router(owner_router)
    app.include_router(dev_router)
    app.include_router(ai_precheck_router)
    app.include_router(seed_demo_router)
    app.include_router(workbench_session_router)
    app.include_router(work_report_router)
    app.include_router(item_actions_router)
    app.include_router(rubrics_router)
    app.include_router(quality_router)
    app.include_router(dashboard_router)
    app.include_router(agent_router)
    app.include_router(agent_compat_router)

    return app


app = create_app()


@app.on_event("startup")
async def startup_event():
    from app.core.database import Base, engine
    from app.models.audit_log import AuditLog
    from app.models.ai_review_run import AIReviewRun
    from app.models.annotation_work_session import AnnotationWorkSession
    from app.models.draft_version import DraftVersion
    from app.models.work_report import WorkReport
    Base.metadata.create_all(bind=engine)

    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.connect() as conn:
        task_cols = {c["name"] for c in insp.get_columns("tasks")}
        task_migrations = [
            ("task_no", "ALTER TABLE tasks ADD COLUMN task_no VARCHAR(32)"),
            ("work_mode", "ALTER TABLE tasks ADD COLUMN work_mode VARCHAR(32) DEFAULT 'single'"),
            ("phase", "ALTER TABLE tasks ADD COLUMN phase VARCHAR(32) DEFAULT 'annotation'"),
            ("team", "ALTER TABLE tasks ADD COLUMN team VARCHAR(64)"),
            ("project_no", "ALTER TABLE tasks ADD COLUMN project_no VARCHAR(32)"),
        ]
        for col_name, sql in task_migrations:
            if col_name not in task_cols:
                conn.execute(text(sql))
        conn.execute(text("UPDATE tasks SET ai_review_enabled = 0 WHERE ai_review_enabled IS NULL"))
        conn.commit()

        item_cols = {c["name"] for c in insp.get_columns("dataset_items")}
        item_migrations = [
            ("item_key", "ALTER TABLE dataset_items ADD COLUMN item_key VARCHAR(128)"),
            ("pack_id", "ALTER TABLE dataset_items ADD COLUMN pack_id VARCHAR(64)"),
            ("is_valid", "ALTER TABLE dataset_items ADD COLUMN is_valid BOOLEAN DEFAULT 1"),
            ("is_first_annotated", "ALTER TABLE dataset_items ADD COLUMN is_first_annotated BOOLEAN DEFAULT 0"),
            ("category", "ALTER TABLE dataset_items ADD COLUMN category VARCHAR(64)"),
            ("supplier", "ALTER TABLE dataset_items ADD COLUMN supplier VARCHAR(64)"),
            ("invalid_reason", "ALTER TABLE dataset_items ADD COLUMN invalid_reason VARCHAR(256)"),
            ("annotation_phase", "ALTER TABLE dataset_items ADD COLUMN annotation_phase VARCHAR(32)"),
            ("phase_status", "ALTER TABLE dataset_items ADD COLUMN phase_status VARCHAR(32)"),
            ("qc_status", "ALTER TABLE dataset_items ADD COLUMN qc_status VARCHAR(32)"),
            ("round_no", "ALTER TABLE dataset_items ADD COLUMN round_no INTEGER DEFAULT 1"),
            ("total_rounds", "ALTER TABLE dataset_items ADD COLUMN total_rounds INTEGER DEFAULT 1"),
            ("skipped_by", "ALTER TABLE dataset_items ADD COLUMN skipped_by INTEGER"),
        ]
        for col_name, sql in item_migrations:
            if col_name not in item_cols:
                conn.execute(text(sql))
        conn.commit()

        ws_cols = {c["name"] for c in insp.get_columns("annotation_work_sessions")} if insp.get_table_names().__contains__("annotation_work_sessions") else set()
        ws_migrations = [
            ("ended_at", "ALTER TABLE annotation_work_sessions ADD COLUMN ended_at DATETIME"),
        ]
        for col_name, sql in ws_migrations:
            if col_name not in ws_cols:
                conn.execute(text(sql))
        conn.commit()

        # DraftVersion 新增字段：version_type / operator_role
        dv_cols = {c["name"] for c in insp.get_columns("draft_versions")} if insp.get_table_names().__contains__("draft_versions") else set()
        dv_migrations = [
            ("version_type", "ALTER TABLE draft_versions ADD COLUMN version_type VARCHAR(32)"),
            ("operator_role", "ALTER TABLE draft_versions ADD COLUMN operator_role VARCHAR(16)"),
        ]
        for col_name, sql in dv_migrations:
            if col_name not in dv_cols:
                conn.execute(text(sql))
        conn.commit()

        # AIReviewRun 新增字段：base_url / error_type / raw_response_preview / used_fallback
        run_cols = {c["name"] for c in insp.get_columns("ai_review_runs")} if insp.get_table_names().__contains__("ai_review_runs") else set()
        run_migrations = [
            ("base_url", "ALTER TABLE ai_review_runs ADD COLUMN base_url VARCHAR(256)"),
            ("error_type", "ALTER TABLE ai_review_runs ADD COLUMN error_type VARCHAR(64)"),
            ("raw_response_preview", "ALTER TABLE ai_review_runs ADD COLUMN raw_response_preview TEXT"),
            ("used_fallback", "ALTER TABLE ai_review_runs ADD COLUMN used_fallback BOOLEAN DEFAULT 0"),
            ("trigger_type", "ALTER TABLE ai_review_runs ADD COLUMN trigger_type VARCHAR(32)"),
        ]
        for col_name, sql in run_migrations:
            if col_name not in run_cols:
                try:
                    conn.execute(text(sql))
                except Exception as e:
                    logger.debug(f"[migration] ai_review_runs add {col_name} skipped: {e}")
        conn.commit()

        conn.execute(text("UPDATE annotation_work_sessions SET accumulated_seconds = 0 WHERE accumulated_seconds IS NULL"))
        conn.execute(text("UPDATE annotation_work_sessions SET status = 'stopped' WHERE status IS NULL OR status = ''"))
        conn.execute(text("UPDATE annotation_work_sessions SET status = 'stopped', started_at = NULL WHERE status = 'active' AND started_at IS NULL"))
        conn.commit()

        from sqlalchemy import func as sa_func
        dup_result = conn.execute(text(
            "SELECT labeler_id, item_id, MAX(id) as keep_id FROM annotation_work_sessions "
            "WHERE status = 'active' GROUP BY labeler_id, item_id HAVING COUNT(*) > 1"
        )).fetchall()
        for row in dup_result:
            lbl_id, itm_id, keep_id = row[0], row[1], row[2]
            conn.execute(text(
                f"UPDATE annotation_work_sessions SET status = 'stopped', started_at = NULL, "
                f"ended_at = COALESCE(ended_at, closed_at, updated_at, created_at), "
                f"closed_at = COALESCE(closed_at, updated_at, created_at) "
                f"WHERE labeler_id = {lbl_id} AND item_id = {itm_id} AND status = 'active' AND id != {keep_id}"
            ))
        conn.commit()

        fix_count = len(dup_result)
        if fix_count > 0:
            logger.debug(f"[migration] Fixed {fix_count} duplicate active sessions")

    logger.debug("LabelHub API started successfully!")


@app.on_event("shutdown")
async def shutdown_event():
    logger.debug("LabelHub API shutdown!")
