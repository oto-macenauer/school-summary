"""FastAPI dependency injection."""

from __future__ import annotations

from fastapi import HTTPException

from .services.log_manager import LogManager, get_log_manager
from .services.push_service import PushService
from .services.scheduler import BackgroundScheduler
from .services.student_manager import StudentContext, StudentManager

_student_manager: StudentManager | None = None
_scheduler: BackgroundScheduler | None = None
_push_service: PushService | None = None


def set_student_manager(manager: StudentManager) -> None:
    global _student_manager
    _student_manager = manager


def set_scheduler(scheduler: BackgroundScheduler) -> None:
    global _scheduler
    _scheduler = scheduler


def set_push_service(push: PushService) -> None:
    global _push_service
    _push_service = push


def get_manager() -> StudentManager:
    if _student_manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return _student_manager


def get_scheduler() -> BackgroundScheduler:
    if _scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")
    return _scheduler


def get_push_service() -> PushService:
    if _push_service is None:
        raise HTTPException(status_code=503, detail="Push service not initialized")
    return _push_service


def get_student_or_404(name: str) -> StudentContext:
    manager = get_manager()
    ctx = manager.get_student(name)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Student '{name}' not found")
    return ctx
