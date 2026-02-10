"""Google Drive reports endpoints."""

from fastapi import APIRouter

from ..dependencies import get_student_or_404

router = APIRouter(tags=["gdrive"])


@router.get("/api/students/{name}/gdrive")
async def get_gdrive_reports(name: str):
    """Get all cached weekly reports for a student."""
    ctx = get_student_or_404(name)
    return {
        "reports": ctx.gdrive_storage.get_all_reports_data(),
        "total": len(ctx.gdrive_storage.get_all_reports()),
    }
