from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.dashboard_service import (
    compute_dashboard_stats,
    compute_dashboard_quality,
    get_recent_activities,
    compute_system_health,
)
from app.services.audit_service import log_action
from app.core.enums import AuditAction, AuditTargetType

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    try:
        result = compute_dashboard_stats(db)
    except Exception as e:
        result = {"error": str(e)}
    try:
        log_action(
            db=db, user_id=1, action="dashboard_view",
            target_type=AuditTargetType.TASK, target_id=0,
            role="owner", action_label="查看仪表盘",
            message="查看 Owner 仪表盘"
        )
    except Exception:
        pass
    return result


@router.get("/quality")
def get_dashboard_quality(db: Session = Depends(get_db)):
    try:
        result = compute_dashboard_quality(db)
    except Exception as e:
        result = {"error": str(e)}
    return result


@router.get("/activities")
def get_dashboard_activities(db: Session = Depends(get_db)):
    try:
        result = get_recent_activities(db, limit=10)
    except Exception:
        result = []
    return result


@router.get("/health-check")
def get_system_health(db: Session = Depends(get_db)):
    try:
        result = compute_system_health(db)
    except Exception as e:
        result = {"error": str(e)}
    try:
        log_action(
            db=db, user_id=1, action="system_health_check",
            target_type=AuditTargetType.TASK, target_id=0,
            role="owner", action_label="系统健康检查",
            message="执行系统健康检查"
        )
    except Exception:
        pass
    return result
