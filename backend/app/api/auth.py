"""Auth/status endpoints."""

from fastapi import APIRouter

from ..dependencies import get_manager

router = APIRouter(tags=["status"])


@router.get("/api/status")
async def get_status():
    """App health and auth status per student."""
    manager = get_manager()
    students = {}
    for name, ctx in manager.students.items():
        students[name] = {
            "authenticated": ctx.client.auth.is_authenticated,
            "timetable_updated": ctx.timetable_updated.isoformat() if ctx.timetable_updated else None,
            "marks_updated": ctx.marks_updated.isoformat() if ctx.marks_updated else None,
            "komens_updated": ctx.komens_updated.isoformat() if ctx.komens_updated else None,
            "summary_updated": ctx.summary_updated.isoformat() if ctx.summary_updated else None,
            "prepare_updated": ctx.prepare_updated.isoformat() if ctx.prepare_updated else None,
        }
    return {
        "status": "ok",
        "students": students,
        "gemini_available": manager.gemini is not None,
        "gdrive_available": manager.gdrive_available,
    }
