"""Auth/status endpoints."""

from fastapi import APIRouter, HTTPException, Response

from ..dependencies import get_manager

router = APIRouter(tags=["status"])


@router.api_route("/api/health", methods=["GET", "HEAD"])
async def get_health():
    """Liveness probe: answers as long as the server loop is running.

    Deliberately touches no student state or external service, so a slow
    Bakalari login or a Gemini outage never marks the container unhealthy.
    """
    return {"status": "ok"}


@router.api_route("/api/ready", methods=["GET", "HEAD"])
async def get_ready(response: Response):
    """Readiness probe for external monitors (e.g. Uptime Kuma).

    503 until the app is initialized with at least one student and every
    student holds a Bakalari session, so a monitor alerts on broken
    credentials or a school server outage, not just a dead process.
    """
    manager = _manager_or_none()
    if manager is None:
        response.status_code = 503
        return {"status": "starting", "students": {}}

    students = {
        name: ctx.client.auth.is_authenticated
        for name, ctx in manager.students.items()
    }
    ready = bool(students) and all(students.values())
    if not ready:
        response.status_code = 503
    return {
        "status": "ok" if ready else ("unconfigured" if not students else "degraded"),
        "students": students,
    }


def _manager_or_none():
    try:
        return get_manager()
    except HTTPException:
        return None


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
