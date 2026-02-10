"""Read-only admin endpoints for logs, scheduler, and config."""

from fastapi import APIRouter, Query

from ..config import get_config_path, load_config
from ..dependencies import get_manager, get_scheduler
from ..services.log_manager import LogCategory, get_log_manager

router = APIRouter(tags=["admin"])


@router.get("/api/admin/logs")
async def get_logs(
    category: str | None = Query(None),
    level: str | None = Query(None),
    student: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get recent log entries, filterable by category/level/student."""
    log_mgr = get_log_manager()
    cat = None
    if category:
        try:
            cat = LogCategory(category)
        except ValueError:
            pass
    entries = log_mgr.get_logs(
        category=cat, level=level, student=student,
        limit=limit, offset=offset,
    )
    return {
        "entries": [e.to_dict() for e in entries],
        "total": log_mgr.count,
        "categories": [c.value for c in LogCategory],
    }


@router.get("/api/admin/scheduler")
async def get_scheduler_status():
    """Get all task statuses."""
    scheduler = get_scheduler()
    return {
        "tasks": [s.to_dict() for s in scheduler.task_statuses.values()],
    }


@router.get("/api/admin/scheduler/{task_name}")
async def get_task_detail(task_name: str):
    """Get single task detail."""
    scheduler = get_scheduler()
    # Find tasks matching the name (could be multiple students)
    matching = [
        s.to_dict() for key, s in scheduler.task_statuses.items()
        if s.task_name == task_name or key == task_name
    ]
    if not matching:
        return {"detail": "Task not found"}
    return {"tasks": matching}


@router.get("/api/config")
async def get_config():
    """Get current configuration with passwords masked."""
    manager = get_manager()
    config = manager.config
    config_path = get_config_path()
    return {
        "config": config.masked() if config else {},
        "config_path": str(config_path),
        "config_exists": config_path.exists(),
        "last_modified": config_path.stat().st_mtime if config_path.exists() else None,
    }


@router.post("/api/config/reload")
async def reload_config():
    """Force reload config from YAML file."""
    try:
        config = load_config()
        return {"status": "ok", "message": "Configuration reloaded"}
    except Exception as err:
        return {"status": "error", "message": str(err)}


@router.post("/api/config/test-connection")
async def test_connection():
    """Test Bakalari credentials."""
    import aiohttp
    from ..config import load_config
    from ..core.auth import BakalariAuth, BakalariAuthError

    config = load_config()
    results = {}
    async with aiohttp.ClientSession() as session:
        for student in config.students:
            auth = BakalariAuth(config.base_url, student.username, student.password, session)
            try:
                token = await auth.login()
                results[student.name] = {
                    "status": "ok",
                    "api_version": token.api_version,
                    "user_id": token.user_id,
                }
            except BakalariAuthError as err:
                results[student.name] = {"status": "error", "message": str(err)}
            finally:
                await auth.close()
    return {"results": results}


@router.get("/api/admin/gemini-usage")
async def get_gemini_usage():
    """Get Gemini API usage stats."""
    manager = get_manager()
    if manager.gemini:
        return manager.gemini.usage_stats.to_dict()
    return {"error": "Gemini not configured"}
